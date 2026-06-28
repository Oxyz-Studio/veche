"""Swarm exploration -> shared Atlas log -> consensus map, on REAL OpenEMR screens.

Two agents traverse the patient-dashboard tabs. Each transition is node-identified
(Voyage cosine) and appended to the shared Atlas log. The consolidator then fuses
the agents' observations by K-agreement into a consensus map. Node-identity is
SHARED across agents (one registry), exactly as Atlas vector search shares it in prod.
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from veche.browser import Browser
from veche.node_identity import NodeRegistry, VoyageEmbedder
from veche.store import Store
from veche.consolidator import consolidate

# Tabs reachable from the patient dashboard, with model-space (0-999) coords.
TABS = [("History", 221, 96), ("Issues", 540, 109), ("Ledger", 478, 92), ("Documents", 397, 92)]


class Backoff:
    """Wrap an embedder with Voyage free-tier (3 RPM) backoff."""
    def __init__(self, inner):
        self.inner = inner
    def embed_image(self, image):
        for _ in range(6):
            try:
                return self.inner.embed_image(image)
            except Exception as e:
                if "rate" in str(e).lower() or "429" in str(e):
                    print("   (voyage rate-limit, sleep 22s)"); time.sleep(22); continue
                raise
        raise RuntimeError("voyage backoff exhausted")


def explore(agent_id, br, registry, store):
    for label, x, y in TABS:
        br.open_patient(1)
        from_node = registry.identify(br.screenshot())
        br.execute("click_at", {"x": x, "y": y})
        to_node = registry.identify(br.screenshot())
        store.append_observation({"agent_id": agent_id, "from_node": from_node,
                                  "action": f"click:{label}", "to_node": to_node, "ts": 0})
        print(f"  {agent_id}: {from_node} --click:{label}--> {to_node}")


def main():
    registry = NodeRegistry(Backoff(VoyageEmbedder()))
    store = Store(db="veche_demo"); store.clear()
    br = Browser(headless=True)
    br.login_openemr()
    for aid in ("a1", "a2"):
        print(f"agent {aid} exploring {len(TABS)} routes...")
        explore(aid, br, registry, store)
    br.close()

    obs = store.read_log()
    res = consolidate(obs, k=2)
    print(f"\n=== CONSENSUS MAP — {len(registry.nodes)} nodes, {len(obs)} observations ===")
    for e in res.edges:
        flag = "✅ committed" if e.committed else "… below-K"
        conf = "  ⚠ CONFLICT" if e.is_conflict else ""
        print(f"  {e.from_node} --{e.action:16}--> {e.to_node}  ({e.confirmations} agents) {flag}{conf}")
    store.close()


if __name__ == "__main__":
    main()
