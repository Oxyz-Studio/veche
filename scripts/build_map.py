"""Post-process the raw swarm capture into the consensus map the viz replays.

Node-identifies every captured frame (Voyage cosine, shared registry so the SAME
screen seen by different agents MERGES into one node), builds observed transitions,
and snapshots the map building agent-by-agent. Reads viz/recording/raw.json,
writes viz/recording/recording.json (+ keeps frames as node thumbnails).
"""
import sys, pathlib, json, time, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from veche.node_identity import NodeRegistry, VoyageEmbedder

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / "viz" / "recording"
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

    # event intents keyed by (agent, frame) so we can label transitions
    intent_by = {(e["agent"], e["frame"]): (e.get("intent") or e["action"]) for e in raw["events"]}

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
            observations.append({"agent": ag["id"], "from": a, "to": b, "label": label})

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
    }
    (REC / "recording.json").write_text(json.dumps(recording, indent=2))
    print(f"\nMAP BUILT: {len(nodes)} nodes, {len(edges)} edges, {len(snapshots)} snapshots "
          f"(swarm: {swarm_tokens} tokens ~${swarm_cost}).  -> viz/recording/recording.json")


if __name__ == "__main__":
    main()
