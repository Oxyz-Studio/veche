"""The VECHE consolidator — reliability-weighted K-agreement over noisy observations.

This is the named mechanism. It is a PURE function of (observations, prior_reliability):
recompute the consolidated graph from a log snapshot each tick → deterministic, re-runnable.

Stages (see veche-spec.md §4):
  1. node-identity (canonicalize "same screen") happens UPSTREAM — observations already carry node_ids.
  2. reliability-weighted K-agreement on edges (here): a transition is committed only if K distinct
     agents agree; conflicting destinations are adjudicated by reliability-weighted vote; the loser is
     quarantined (kept visible), and disagreeing agents lose reliability.
  3. decay/versioning — stubbed for the demo (a version/ts field elsewhere).

We treat the aggregation primitive as cited commodity plumbing (Dawid-Skene / truth-inference); the
contribution is running it live on a noisy pixels-only GUI. Reliability is a Beta(alpha,beta) mean.
"""
from __future__ import annotations
from collections import defaultdict

from .types import Edge, ConsensusResult


def consolidate(
    observations,
    k: int = 2,
    prior_reliability: dict | None = None,
    reward: float = 1.0,
    penalty: float = 1.0,
) -> ConsensusResult:
    """Fuse noisy observations into a consolidated, conflict-resolved edge set.

    Args:
        observations: iterable of Observation.
        k: minimum number of DISTINCT agreeing agents for an edge to be `committed`.
        prior_reliability: optional {agent_id: reliability in [0,1]} carried from past consolidations.
        reward/penalty: Beta pseudo-counts added for agreeing/disagreeing with the consensus winner.
    """
    # Per-agent Beta(alpha, beta); mean alpha/(alpha+beta). Uninformative prior = Beta(1,1) = 0.5.
    alpha: dict[str, float] = defaultdict(lambda: 1.0)
    beta: dict[str, float] = defaultdict(lambda: 1.0)
    if prior_reliability:
        for a, r in prior_reliability.items():
            r = min(max(r, 1e-6), 1 - 1e-6)
            # encode the prior mean as light pseudo-counts (total weight 2)
            alpha[a] = r * 2.0
            beta[a] = (1.0 - r) * 2.0

    def rel(agent_id: str) -> float:
        return alpha[agent_id] / (alpha[agent_id] + beta[agent_id])

    # Group observations by the transition key (from_node, action).
    groups: dict[tuple, list] = defaultdict(list)
    agents_seen = set()
    for o in observations:
        groups[(o.from_node, o.action)].append(o)
        agents_seen.add(o.agent_id)

    edges: list[Edge] = []
    # Deterministic order: sort group keys so output is reproducible on stage.
    for (from_node, action) in sorted(groups.keys()):
        obs = groups[(from_node, action)]

        votes: dict[str, float] = defaultdict(float)
        backers: dict[str, set] = defaultdict(set)
        for o in obs:
            votes[o.to_node] += rel(o.agent_id)
            backers[o.to_node].add(o.agent_id)

        # Winner = highest reliability-weighted vote; tie broken deterministically by node_id.
        winner = max(sorted(votes.keys()), key=lambda tn: votes[tn])
        confirmations = len(backers[winner])
        committed = confirmations >= k
        quarantined = sorted(tn for tn in votes if tn != winner)
        is_conflict = len(votes) > 1

        edges.append(Edge(
            from_node=from_node,
            action=action,
            to_node=winner,
            support=votes[winner],
            confirmations=confirmations,
            committed=committed,
            votes=dict(votes),
            quarantined=quarantined,
            is_conflict=is_conflict,
        ))

        # Update reliability: agents who backed the winner are rewarded, dissenters penalized.
        for o in obs:
            if o.to_node == winner:
                alpha[o.agent_id] += reward
            else:
                beta[o.agent_id] += penalty

    reliability = {a: rel(a) for a in agents_seen}
    return ConsensusResult(edges=edges, reliability=reliability)
