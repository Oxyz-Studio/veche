"""Empirical answer to "is 2-agent agreement enough to confirm a transition?"

We simulate a ground-truth GUI graph, give each agent the ~80% per-step reliability
of a single computer-use agent (UI-CUBE), with INDEPENDENT errors, run the REAL
veche consolidator, and measure:
  - precision  = committed transitions that are actually correct
  - commit-rate = fraction of transitions that reach K agreement (recall/coverage)

Single agent = precision p, no filter. The question is what agreement buys you.
"""
import sys, pathlib, random, statistics
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from veche.types import Observation
from veche.consolidator import consolidate

random.seed(7)
NODES = [f"n{i:04d}" for i in range(18)]   # ~ the demo's 18 screens


def one_trial(p, observers, n_trans=200, k=2):
    truth = {}
    for t in range(n_trans):
        frm = random.choice(NODES)
        to = random.choice([n for n in NODES if n != frm])
        truth[(frm, f"act{t}")] = to               # one true destination per (screen, action)
    obs = []
    for (frm, act), to in truth.items():
        for i in range(observers):
            got = to if random.random() < p else random.choice([n for n in NODES if n != to])
            obs.append(Observation(f"ag{i}", frm, act, got))
    res = consolidate(obs, k=k)
    committed = [e for e in res.edges if e.committed]
    correct = sum(1 for e in committed if truth[(e.from_node, e.action)] == e.to_node)
    precision = (correct / len(committed)) if committed else float("nan")
    return precision, len(committed) / len(truth)


def avg(p, observers, trials=30, k=2):
    rows = [one_trial(p, observers, k=k) for _ in range(trials)]
    return statistics.mean(r[0] for r in rows), statistics.mean(r[1] for r in rows)


print("Per-agent reliability is the single-agent baseline precision.\n")
print(f"{'1 agent':>9} {'observers':>10} {'K':>2} {'precision':>10} {'committed':>10}")
for p in (0.7, 0.8, 0.9):
    for observers in (2, 3, 4, 5):
        pr, cr = avg(p, observers, k=2)
        print(f"{p:>9.0%} {observers:>10} {2:>2} {pr:>10.1%} {cr:>10.1%}")
    print()
