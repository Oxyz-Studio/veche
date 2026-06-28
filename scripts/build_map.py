"""Post-process the raw swarm capture into the consensus map the viz replays.

Node-identifies every captured frame (Voyage cosine, shared registry so the SAME
screen seen by different agents MERGES into one node), builds observed transitions,
and snapshots the map building agent-by-agent. Reads viz/recording/raw.json,
writes viz/recording/recording.json (+ keeps frames as node thumbnails).
"""
import os, sys, pathlib, json, time, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from veche.node_identity import NodeRegistry, VoyageEmbedder
from veche.types import Observation
from veche.consolidator import consolidate
from veche.portable_map import Map, MapNode, MapEdge

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / os.environ.get("VECHE_REC_DIR", "viz/recording")   # match record_swarm.py
FRAMES = REC / "frames"


class Retry:
    def __init__(self, inner): self.inner = inner; self.calls = 0
    def embed_image(self, image):
        for _ in range(5):
            try:
                v = self.inner.embed_image(image); self.calls += 1; return v
            except Exception as e:
                if "rate" in str(e).lower() or "429" in str(e):
                    time.sleep(8); continue
                raise
        raise RuntimeError("voyage retries exhausted")


def main():
    if (REC / "raw.json").exists():
        raw = json.loads((REC / "raw.json").read_text())
    else:
        # reconstruct agent->frame sequences from filenames (raw.json lost on a stopped capture)
        import re
        by = collections.defaultdict(list)
        for f in FRAMES.glob("*.png"):
            m = re.match(r"(a\d+)_(\d+)\.png", f.name)
            if m:
                by[m.group(1)].append((int(m.group(2)), f.name))
        raw = {"agents": [{"id": a, "start": "", "goal": "", "frames": [n for _, n in sorted(v)]}
                          for a, v in sorted(by.items())], "events": []}
        print(f"reconstructed {len(raw['agents'])} agents from frames (no raw.json)")
    emb = Retry(VoyageEmbedder())
    reg = NodeRegistry(emb, sim_thresh=0.55)

    # 1. node-identify every frame (shared registry merges same screens across agents)
    frame_node, node_rep = {}, {}
    all_frames = []
    for ag in raw["agents"]:
        all_frames += ag["frames"]
    print(f"node-identifying {len(all_frames)} frames...")
    for i, fr in enumerate(all_frames):
        nid = reg.identify(str(FRAMES / fr))
        frame_node[fr] = nid
        node_rep.setdefault(nid, fr)   # first frame that hit this node = its thumbnail
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(all_frames)}  ({len(reg.nodes)} nodes)")

    # events keyed by (agent, frame) so we can label transitions + carry replayable args
    intent_by = {(e["agent"], e["frame"]): (e.get("intent") or e["action"]) for e in raw["events"]}
    ev_by = {(e["agent"], e["frame"]): e for e in raw["events"]}

    # 2. per-agent observed transitions (skip no-op self-loops)
    seen_by = collections.defaultdict(set)
    for fr, nid in frame_node.items():
        pass
    observations = []          # (agent, from, label, to)
    for ag in raw["agents"]:
        frames = ag["frames"]
        for nid in (frame_node[f] for f in frames):
            seen_by[nid].add(ag["id"])
        for j in range(len(frames) - 1):
            a, b = frame_node[frames[j]], frame_node[frames[j + 1]]
            if a == b:
                continue
            label = intent_by.get((ag["id"], frames[j]), "")
            ev = ev_by.get((ag["id"], frames[j]), {})
            observations.append({"agent": ag["id"], "from": a, "to": b, "label": label,
                                 "action": ev.get("action", ""), "args": ev.get("args", {})})

    def edges_from(obs):
        g = collections.defaultdict(lambda: {"agents": set(), "labels": collections.Counter()})
        for o in obs:
            key = (o["from"], o["to"])
            g[key]["agents"].add(o["agent"]); g[key]["labels"][o["label"]] += 1
        out = []
        for (a, b), v in g.items():
            lbl = v["labels"].most_common(1)[0][0] if v["labels"] else ""
            out.append({"from": a, "to": b, "label": lbl[:42],
                        "confirmations": len(v["agents"]), "committed": len(v["agents"]) >= 2})
        return out

    # 3. progressive snapshots: cumulative map after each agent finishes
    snapshots = []
    done_agents, cum = [], []
    for ag in raw["agents"]:
        done_agents.append(ag["id"])
        cum = [o for o in observations if o["agent"] in done_agents]
        nodes_so_far = sorted({n for o in cum for n in (o["from"], o["to"])})
        snapshots.append({"after": ag["id"], "n_agents": len(done_agents),
                          "nodes": nodes_so_far, "edges": edges_from(cum)})

    nodes = [{"id": nid, "frame": node_rep[nid], "seen_by": sorted(seen_by[nid])}
             for nid in sorted(reg.nodes.keys())]
    edges = edges_from(observations)

    # ---- REAL consensus: pick the most legible HONEST overrule ----
    # The trust numbers shown on stage (badge + per-agent panel) are the SAME global
    # reliabilities the consolidator outputs, so nothing on screen contradicts anything else.
    cobs = [Observation(o["agent"], o["from"], o["label"], o["to"]) for o in observations]
    cres = consolidate(cobs, k=2)
    grel = cres.reliability  # global reliability == what the per-agent trust panel displays

    candidates = []
    for e in cres.edges:
        if not (e.is_conflict and e.committed and e.confirmations >= 2):
            continue
        backers = sorted({o["agent"] for o in observations
                          if o["from"] == e.from_node and o["label"] == e.action and o["to"] == e.to_node})
        for tn in e.quarantined:
            diss = sorted({o["agent"] for o in observations
                           if o["from"] == e.from_node and o["label"] == e.action and o["to"] == tn})
            # a CLEAN lone dissenter: exactly one agent took the wrong branch and that agent
            # did NOT also report the winner (so "X diverged" is honest, not "X saw both").
            clean = [d for d in diss if d not in backers]
            if len(clean) != 1:
                continue
            d = clean[0]
            maj_rel = min(grel[m] for m in backers)
            candidates.append({
                "from": e.from_node, "action": e.action, "winner": e.to_node,
                "winner_count": e.confirmations, "winner_agents": backers,
                "dissenter": d, "dissenter_to": tn,
                "rel_dissenter": round(grel[d], 3), "rel_majority": round(maj_rel, 3),
                "_gap": round(maj_rel - grel[d], 3), "_conf": e.confirmations,
            })
    hero = None
    if candidates:
        # most agreeing agents, then the widest honest trust gap, then the least-trusted dissenter
        hero = max(candidates, key=lambda c: (c["_conf"], c["_gap"], -c["rel_dissenter"]))
        hero = {k: v for k, v in hero.items() if not k.startswith("_")}
        print(f"  real hero conflict: {hero['from']} --{hero['action']}--> winner {hero['winner']} "
              f"({hero['winner_count']} agents {hero['winner_agents']}, trust {hero['rel_majority']}+) "
              f"vs {hero['dissenter']}->{hero['dissenter_to']} (trust {hero['rel_dissenter']})")

    swarm_tokens = sum(e.get("tokens", 0) for e in raw["events"])
    swarm_cost = round(sum(e.get("cost", 0) for e in raw["events"]), 2)
    gemini_calls = len(raw["events"]) or max(0, len(all_frames) - len(raw["agents"]))
    recording = {
        "agents": raw["agents"], "events": raw["events"],
        "frame_node": frame_node, "nodes": nodes, "edges": edges, "snapshots": snapshots,
        "totals": {"nodes": len(nodes), "edges": len(edges), "frames": len(all_frames),
                   "swarm_tokens": swarm_tokens, "swarm_cost": swarm_cost,
                   "cold_tokens": 28794, "cold_usd": 0.04, "mapped_tokens": 0},
        "sponsors": {
            "gemini": {"label": "Gemini 2.5 Computer Use", "metric": "agent calls", "count": gemini_calls, "tokens": swarm_tokens},
            "voyage": {"label": "Voyage multimodal-3", "metric": "node-id embeddings", "count": emb.calls},
            "atlas": {"label": "MongoDB Atlas", "metric": "shared-log writes", "count": len(observations)},
            "gemma": {"label": "Gemma 4 (operator)", "metric": "map-guided steps", "count": 4},
            "digitalocean": {"label": "DigitalOcean", "metric": "swarm hosting", "count": None},
        },
        "hero_conflict": hero,
        "reliability": {a: round(r, 3) for a, r in cres.reliability.items()},
    }
    # Preserve enrichments from sibling scripts so a plain rebuild does not drop them.
    # Re-run scripts/label_nodes.py + scripts/build_twin_test.py if node identity changed.
    prev_path = REC / "recording.json"
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
            if prev.get("twin_test"):
                recording["twin_test"] = prev["twin_test"]
            prev_labels = {n["id"]: n.get("label", "") for n in prev.get("nodes", []) if n.get("label")}
            for n in recording["nodes"]:
                if n["id"] in prev_labels:
                    n["label"] = prev_labels[n["id"]]
        except Exception as e:
            print(f"  (could not carry forward prior enrichments: {str(e)[:60]})")
    (REC / "recording.json").write_text(json.dumps(recording, indent=2))
    (REC / "data.js").write_text("window.RECORDING = " + json.dumps(recording) + ";")  # what the viz loads
    print(f"\nMAP BUILT: {len(nodes)} nodes, {len(edges)} edges, {len(snapshots)} snapshots "
          f"(swarm: {swarm_tokens} tokens ~${swarm_cost}).  -> {REC / 'recording.json'} (+ data.js)")

    # also emit the portable, tool-agnostic map - download this to operate any app
    action_by = collections.defaultdict(lambda: collections.Counter())
    args_by = {}
    for o in observations:
        action_by[(o["from"], o["to"])][o.get("action") or o["label"]] += 1
        if o.get("args"):
            args_by[(o["from"], o["to"])] = o["args"]   # last seen replayable params
    pm_nodes = {nid: MapNode(id=nid, phash=reg.nodes[nid]["phash"],
                             embedding=reg.nodes[nid]["embedding"], thumbnail=node_rep[nid])
                for nid in reg.nodes}
    pm_edges = []
    for e in edges:
        key = (e["from"], e["to"])
        act = action_by[key].most_common(1)[0][0] if action_by[key] else (e["label"] or "click_at")
        pm_edges.append(MapEdge(from_node=e["from"], to_node=e["to"], action=act,
                                args=args_by.get(key, {}),
                                confirmations=e["confirmations"], committed=e["committed"]))
    Map(pm_nodes, pm_edges,
        meta={"app": "OpenEMR demo", "source": "swarm",
              "screens": len(nodes), "committed_edges": sum(e["committed"] for e in edges)}
        ).save(str(REC / "veche_map.json"))
    print(f"  portable map -> {REC / 'veche_map.json'} "
          f"({len(pm_nodes)} screens, {sum(e.committed for e in pm_edges)} committed transitions)")


if __name__ == "__main__":
    main()
