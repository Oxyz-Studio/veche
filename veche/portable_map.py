"""Portable, tool-agnostic VECHE map — download it, point your own tool at the app.

A ``Map`` is the consensus world-model the swarm built, serialized so that ANY
computer-use tool can operate the app the same way:

    1. ``locate(screenshot)`` — which known screen am I on? (cheap pixel node-identity)
    2. ``route(from, to)`` / ``next_action(here, goal)`` — the replayable action(s)
       toward a goal, no vision-reasoning needed.

This is "the MCP you never write": the swarm maps the app once, everyone downloads
the map, and a small model (or your own agent, whatever the tool) operates it cheaply.

The map carries each screen's pixel identity (phash + multimodal embedding) so
``locate`` works offline against the reference set, and each transition's *action*
(type + args). Args are the replayable parameters (click coords, typed text) — they
are present when the capture recorded them (see ``scripts/record_swarm.py``); a map
without args is still fully *navigable* (route/inspect), just not blind-replayable.
"""
from __future__ import annotations

import collections
import json
import typing
from dataclasses import asdict, dataclass, field

from .node_identity import Embedder, _cosine, hamming, layout_hash


@dataclass
class Action:
    """A replayable executor action: a name plus its parameters."""
    name: str
    args: dict = field(default_factory=dict)


@dataclass
class MapNode:
    """One screen: a stable id plus the pixel identity used to recognize it."""
    id: str
    phash: str = ""
    embedding: list = field(default_factory=list)
    thumbnail: str = ""          # optional frame filename, for display
    label: str = ""              # optional human label


@dataclass
class MapEdge:
    """A consensus transition: from a screen, an action leads to a screen."""
    from_node: str
    to_node: str
    action: str                  # action type, e.g. "click_at"
    args: dict = field(default_factory=dict)   # replayable params (coords/text), if captured
    confirmations: int = 1       # distinct agents that agreed
    committed: bool = False       # passed the K threshold -> trusted


class Map:
    """The downloadable world-model. Consume it from any executor."""

    def __init__(self, nodes=None, edges=None, meta=None):
        self.nodes: dict[str, MapNode] = nodes or {}
        self.edges: list[MapEdge] = edges or []
        self.meta: dict = meta or {}

    # ---- consumption API (tool-agnostic) ----
    def locate(self, image, embedder: Embedder, sim_thresh: float = 0.55,
               exact_hamming: int = 4) -> str | None:
        """Return the id of the known screen that best matches ``image``, or None.

        ``image`` may be a PIL image, raw bytes, or a path. Mirrors the node-identity
        used to build the map: phash exact-match fast-path, else nearest by cosine.
        """
        ph = layout_hash(image)
        for n in self.nodes.values():
            if n.phash and hamming(ph, n.phash) <= exact_hamming:
                return n.id
        emb = list(embedder.embed_image(image))
        best, best_sim = None, -1.0
        for n in self.nodes.values():
            if not n.embedding:
                continue
            s = _cosine(emb, n.embedding)
            if s > best_sim:
                best_sim, best = s, n.id
        return best if best_sim >= sim_thresh else None

    def actions(self, node_id: str, committed_only: bool = True) -> list[MapEdge]:
        """Outgoing transitions from a screen (committed = consensus-trusted)."""
        return [e for e in self.edges
                if e.from_node == node_id and (e.committed or not committed_only)]

    def route(self, from_node: str, to_node: str,
              committed_only: bool = True) -> list[MapEdge] | None:
        """Shortest action path between two screens (BFS), or None if unreachable."""
        if from_node == to_node:
            return []
        adj = collections.defaultdict(list)
        for e in self.edges:
            if e.committed or not committed_only:
                adj[e.from_node].append(e)
        seen = {from_node}
        q = collections.deque([(from_node, [])])
        while q:
            cur, path = q.popleft()
            for e in adj[cur]:
                if e.to_node in seen:
                    continue
                step = path + [e]
                if e.to_node == to_node:
                    return step
                seen.add(e.to_node)
                q.append((e.to_node, step))
        return None

    def next_action(self, current_node: str, goal_node: str,
                    committed_only: bool = True) -> MapEdge | None:
        """The first action to take from ``current_node`` toward ``goal_node``."""
        r = self.route(current_node, goal_node, committed_only)
        return r[0] if r else None

    # ---- persistence ----
    def save(self, path) -> None:
        json.dump(
            {"meta": self.meta,
             "nodes": [asdict(n) for n in self.nodes.values()],
             "edges": [asdict(e) for e in self.edges]},
            open(path, "w"),
        )

    @classmethod
    def load(cls, path) -> "Map":
        d = json.load(open(path))
        nodes = {n["id"]: MapNode(**n) for n in d["nodes"]}
        edges = [MapEdge(**e) for e in d["edges"]]
        return cls(nodes, edges, d.get("meta", {}))
