"""Tests for the portable, tool-agnostic map (the toolkit surface)."""
from veche import Executor, Map, MapEdge, MapNode, operate


def _toy():
    nodes = {n: MapNode(n) for n in ("a", "b", "c", "d")}
    edges = [
        MapEdge("a", "b", "click_at", {"x": 1, "y": 2}, confirmations=2, committed=True),
        MapEdge("b", "c", "click_at", {}, confirmations=2, committed=True),
        MapEdge("a", "d", "navigate", {}, confirmations=1, committed=False),
    ]
    return Map(nodes, edges, meta={"app": "toy"})


def test_route_committed_shortest_path():
    assert [e.to_node for e in _toy().route("a", "c")] == ["b", "c"]


def test_route_skips_uncommitted_by_default():
    m = _toy()
    assert m.route("a", "d") is None                       # d only via an uncommitted edge
    assert m.route("a", "d", committed_only=False) is not None


def test_next_action_and_actions():
    m = _toy()
    assert m.next_action("a", "c").to_node == "b"
    assert {e.to_node for e in m.actions("a")} == {"b"}    # committed only


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "m.json"
    _toy().save(p)
    m2 = Map.load(p)
    assert len(m2.nodes) == 4 and len(m2.edges) == 3
    assert m2.edges[0].args == {"x": 1, "y": 2}
    assert m2.meta["app"] == "toy"


class _FakeExecutor:
    def __init__(self): self.here, self.log = "a", []
    def screenshot(self): return b""
    def execute(self, action, args):
        self.log.append((action, args)); self.here = "b" if self.here == "a" else "c"; return True


class _FakeEmbedder:
    def embed_image(self, image): return [1.0]


def test_executor_protocol_and_operate(monkeypatch):
    m, f = _toy(), _FakeExecutor()
    assert isinstance(f, Executor)
    monkeypatch.setattr(m, "locate", lambda img, emb, **k: f.here)   # report executor's screen
    assert operate(m, f, "c", embedder=_FakeEmbedder(), max_steps=5) is True
    assert f.log[0] == ("click_at", {"x": 1, "y": 2})
