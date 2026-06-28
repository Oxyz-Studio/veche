"""THE HERO, on real data: the swarm overrules an agent that misreads a screen.

a1, a2 correctly observe  dashboard --click:History--> History.
a3 acts on a STALE screenshot (it re-uses its pre-click perception — the exact
~1-in-5 failure UI-CUBE documents), so it reports  dashboard --click:History--> dashboard.

Reliability-weighted K-agreement keeps the majority edge, quarantines a3's claim
(kept visible, not deleted), and drops a3's reliability. All node_ids are REAL
(node-identity on live OpenEMR screens)."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from veche.browser import Browser
from veche.node_identity import NodeRegistry, VoyageEmbedder
from veche.store import Store
from veche.consolidator import consolidate

HISTORY = (221, 96)


class Backoff:
    def __init__(self, inner): self.inner = inner
    def embed_image(self, image):
        for _ in range(6):
            try:
                return self.inner.embed_image(image)
            except Exception as e:
                if "rate" in str(e).lower() or "429" in str(e):
                    print("   (voyage rate-limit, sleep 22s)"); time.sleep(22); continue
                raise
        raise RuntimeError("voyage backoff exhausted")


def correct(aid, br, reg, store):
    br.open_patient(1)
    fn = reg.identify(br.screenshot())
    br.execute("click_at", {"x": HISTORY[0], "y": HISTORY[1]})
    tn = reg.identify(br.screenshot())            # re-perceives the landed screen
    store.append_observation({"agent_id": aid, "from_node": fn, "action": "click:History", "to_node": tn, "ts": 0})
    print(f"  {aid}: {fn} --click:History--> {tn}")


def misread(aid, br, reg, store):
    br.open_patient(1)
    stale = br.screenshot()                        # a3's perception, captured BEFORE the click
    fn = reg.identify(stale)
    br.execute("click_at", {"x": HISTORY[0], "y": HISTORY[1]})  # the page DID change...
    tn = reg.identify(stale)                        # ...but a3 acts on its STALE screenshot -> misread
    store.append_observation({"agent_id": aid, "from_node": fn, "action": "click:History", "to_node": tn, "ts": 0})
    print(f"  {aid}: MISREAD (stale perception) {fn} --click:History--> {tn}")


def main():
    reg = NodeRegistry(Backoff(VoyageEmbedder()))
    store = Store(db="veche_hero"); store.clear()
    br = Browser(headless=True); br.login_openemr()
    correct("a1", br, reg, store)
    correct("a2", br, reg, store)
    misread("a3", br, reg, store)
    br.close()

    res = consolidate(store.read_log(), k=2)
    e = res.edge("n0001", "click:History") or res.edges[0]
    print("\n=== CONSENSUS RESOLVES THE CONFLICT ===")
    print(f"  winning edge:  click:History -> {e.to_node}   committed={e.committed} ({e.confirmations} agents)")
    print(f"  votes (node -> weighted support): {{ {', '.join(f'{k}:{v:.2f}' for k,v in e.votes.items())} }}")
    print(f"  quarantined (overruled): {e.quarantined}")
    print("  agent reliability after consensus:")
    for a, r in sorted(res.reliability.items()):
        tag = "  <- penalized (misread)" if r < 0.5 else ""
        print(f"    {a}: {r:.3f}{tag}")
    store.close()


if __name__ == "__main__":
    main()
