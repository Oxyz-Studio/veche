"""Tests for the Atlas shared-memory Store against REAL Atlas (MONGODB_URI).

The headline test is H0: N concurrent agents append to ONE Atlas log with
zero loss.
"""
from __future__ import annotations

import threading

import pytest
from dotenv import load_dotenv

from veche.store import Store
from veche.types import Observation

load_dotenv()


@pytest.fixture()
def store():
    s = Store(db="veche_test")
    s.clear()
    yield s
    s.clear()
    s.close()


def test_h0_concurrent_append_no_loss(store):
    """5 threads x 100 appends -> read_log() returns EXACTLY 500, zero loss."""
    n_threads = 5
    per_thread = 100
    errors: list[Exception] = []

    def worker(tid: int):
        try:
            for i in range(per_thread):
                store.append_observation(
                    {
                        "agent_id": f"agent-{tid}",
                        "from_node": f"n{i}",
                        "action": "click:Next",
                        "to_node": f"n{i+1}",
                        "ts": i,
                    }
                )
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"worker errors: {errors}"

    log = store.read_log()
    assert len(log) == n_threads * per_thread, (
        f"H0 LOSS: expected {n_threads * per_thread}, got {len(log)}"
    )
    # Every observation is a real Observation; every agent contributed 100.
    assert all(isinstance(o, Observation) for o in log)
    from collections import Counter

    counts = Counter(o.agent_id for o in log)
    assert all(counts[f"agent-{t}"] == per_thread for t in range(n_threads)), counts


def test_round_trip(store):
    """append a few -> read_log returns matching Observation objects in order."""
    obs = [
        {"agent_id": "a", "from_node": "home", "action": "click:Login", "to_node": "login", "ts": 1},
        {"agent_id": "b", "from_node": "login", "action": "submit", "to_node": "dash", "ts": 2},
        {"agent_id": "a", "from_node": "dash", "action": "click:Settings", "to_node": "settings", "ts": 3},
    ]
    ids = [store.append_observation(o) for o in obs]
    assert all(isinstance(i, str) and len(i) == 24 for i in ids)

    log = store.read_log()
    assert len(log) == 3
    assert [o.action for o in log] == ["click:Login", "submit", "click:Settings"]
    assert log[0] == Observation("a", "home", "click:Login", "login", 1)
    assert log[2] == Observation("a", "dash", "click:Settings", "settings", 3)


def test_upsert_node_and_vector_index(store):
    """upsert_node + ensure_vector_index run without raising. Vector search
    itself is best-effort (index build is async)."""
    dim = 1024
    emb = [0.01 * (i % 7) for i in range(dim)]
    store.upsert_node("node-1", emb, "ph_abc123")
    # Upsert again -> same _id, updated fields, no duplicate.
    store.upsert_node("node-1", emb, "ph_xyz999")
    assert store.nodes.count_documents({"_id": "node-1"}) == 1
    assert store.nodes.find_one({"_id": "node-1"})["phash"] == "ph_xyz999"

    # Best-effort: must not raise.
    store.ensure_vector_index()

    # Search is allowed to return [] if the index is not queryable yet.
    results = store.search_similar_node(emb, k=3)
    assert isinstance(results, list)
