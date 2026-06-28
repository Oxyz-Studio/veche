"""Operate an app via a VECHE map with ANY executor — zero vision-reasoning tokens.

Each step is cheap: screenshot -> locate (one node-identity embedding) -> ask the map
for the next action -> execute it with your tool. No frontier computer-use call per
screen; the route was already agreed by the swarm. This is the amortized, near-free
cost of every reuse after a route has been mapped once.
"""
from __future__ import annotations

from .executor import Executor
from .node_identity import Embedder, VoyageEmbedder
from .portable_map import Map


def operate(map: Map, executor: Executor, goal_node: str, *,
            embedder: Embedder | None = None, max_steps: int = 25,
            on_step=None) -> bool:
    """Drive ``executor`` to ``goal_node`` using ``map``. Returns True on arrival.

    ``on_step(i, node, edge)`` is an optional callback for logging each step.
    Returns False if the current screen is unknown, no route exists, or max_steps hit.
    """
    embedder = embedder or VoyageEmbedder()
    for i in range(max_steps):
        node = map.locate(executor.screenshot(), embedder)
        if node == goal_node:
            if on_step:
                on_step(i, node, None)
            return True
        edge = map.next_action(node, goal_node) if node else None
        if on_step:
            on_step(i, node, edge)
        if edge is None:
            return False
        executor.execute(edge.action, edge.args)
    return False
