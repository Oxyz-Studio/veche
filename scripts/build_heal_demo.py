"""Pick a REAL self-healing example from the capture: a screen that went from
provisional (one agent, K=1, untrusted) to confirmed (a second independent agent, K=2).

This is the continual-learning loop on real data: when the operator hits a screen the
map only half-knows, it does not guess, it re-explores just that path, and consensus
promotes the screen once an independent agent confirms it. Writes an `R.heal` block into
recording.json (+ regenerates data.js). No API calls: pure selection over captured data.

    VECHE_REC_DIR=viz/recording_deep .venv/bin/python scripts/build_heal_demo.py
"""
import os, sys, pathlib, json, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / os.environ.get("VECHE_REC_DIR", "viz/recording_deep")
PREFERRED = ["Patient Ledger", "Patient Transactions", "Patient Details"]  # recognizable, harm-relevant


def main():
    rec = json.loads((REC / "recording.json").read_text())
    labels = {n["id"]: n.get("label", "") for n in rec["nodes"]}
    by_id = {n["id"]: n for n in rec["nodes"]}
    fn = rec["frame_node"]
    hero = rec.get("hero_conflict") or {}
    hero_ids = {hero.get("from"), hero.get("winner"), hero.get("dissenter_to")}
    hero_dissenter = hero.get("dissenter")  # keep the heal pair visually clean (no flagged agent)

    # capture order: which distinct agents saw each node, in the order they saw it
    agent_of = {f: ag["id"] for ag in rec["agents"] for f in ag["frames"]}
    seq_agents = collections.defaultdict(list)
    first_frame = collections.defaultdict(dict)   # node -> agent -> first frame
    for ag in rec["agents"]:
        for f in ag["frames"]:
            nid = fn[f]
            if ag["id"] not in seq_agents[nid]:
                seq_agents[nid].append(ag["id"])
            first_frame[nid].setdefault(ag["id"], f)

    # clean promotion candidate: exactly two distinct agents, labeled, not part of the overrule
    candidates = [n["id"] for n in rec["nodes"]
                  if len(n["seen_by"]) == 2 and labels.get(n["id"]) and n["id"] not in hero_ids
                  and hero_dissenter not in n["seen_by"]]
    if not candidates:
        print("no clean K=1->K=2 candidate found"); return
    candidates.sort(key=lambda nid: (PREFERRED.index(labels[nid]) if labels[nid] in PREFERRED else 99, nid))
    nid = candidates[0]
    prov_agent, conf_agent = seq_agents[nid][0], seq_agents[nid][1]

    provisional_total = sum(1 for n in rec["nodes"] if len(n["seen_by"]) == 1)
    confirmed_total = sum(1 for n in rec["nodes"] if len(n["seen_by"]) >= 2)

    heal = {
        "node": nid, "label": labels[nid], "frame": by_id[nid]["frame"],
        "provisional_agent": prov_agent, "confirm_agent": conf_agent,
        "provisional_frame": first_frame[nid][prov_agent], "confirm_frame": first_frame[nid][conf_agent],
        "k_before": 1, "k_after": 2,
        "provisional_total": provisional_total, "confirmed_total": confirmed_total,
    }
    rec["heal"] = heal
    (REC / "recording.json").write_text(json.dumps(rec, indent=2))
    (REC / "data.js").write_text("window.RECORDING = " + json.dumps(rec) + ";")
    print(f"  heal example: {nid} '{labels[nid]}' provisional via {prov_agent} -> confirmed by {conf_agent} "
          f"(K=1 -> K=2)")
    print(f"  map confidence: {confirmed_total} confirmed (K>=2), {provisional_total} still provisional (K=1)")
    print(f"  wrote R.heal into {REC / 'recording.json'} (+ data.js)")


if __name__ == "__main__":
    main()
