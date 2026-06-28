"""Core data types for the VECHE consolidator."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Observation:
    """One agent's noisy observation of a transition: from a screen, an action led to a screen.

    `from_node` / `to_node` are canonical node_ids produced by node-identity (see node_identity.py).
    `action` is a canonical action label, e.g. "click:Submit".
    """
    agent_id: str
    from_node: str
    action: str
    to_node: str
    ts: int = 0


@dataclass
class Edge:
    """A consolidated transition after consensus."""
    from_node: str
    action: str
    to_node: str            # the consensus winner
    support: float          # summed reliability-weight backing the winner
    confirmations: int      # number of DISTINCT agents backing the winner
    committed: bool         # passed the K threshold → trusted in the map
    votes: dict             # to_node -> summed reliability-weight (all candidates)
    quarantined: list       # losing to_nodes, kept visible (not deleted)
    is_conflict: bool       # more than one distinct to_node was asserted


@dataclass
class ConsensusResult:
    edges: list = field(default_factory=list)
    reliability: dict = field(default_factory=dict)   # agent_id -> updated reliability in [0,1]

    def edge(self, from_node: str, action: str) -> Edge | None:
        for e in self.edges:
            if e.from_node == from_node and e.action == action:
                return e
        return None

    @property
    def conflicts(self) -> list:
        return [e for e in self.edges if e.is_conflict]
