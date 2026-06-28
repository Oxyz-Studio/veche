"""VECHE — a swarm maps a GUI into one shared world-model by consensus; any tool
then operates the app by reading the map.

Toolkit surface:
    from veche import Map, Action, operate, Executor, VoyageEmbedder
    m = Map.load("veche_map.json")          # the downloadable consensus map
    node = m.locate(screenshot, embedder)   # which screen am I on?
    edge = m.next_action(node, goal)         # the replayable action toward a goal
    operate(m, my_executor, goal)            # drive any executor via the map
"""
from .consolidator import consolidate
from .executor import Executor
from .node_identity import Embedder, NodeRegistry, VoyageEmbedder
from .operate import operate
from .portable_map import Action, Map, MapEdge, MapNode
from .types import ConsensusResult, Edge, Observation

__all__ = [
    "Map", "MapNode", "MapEdge", "Action", "operate", "Executor",
    "Embedder", "VoyageEmbedder", "NodeRegistry",
    "consolidate", "Observation", "Edge", "ConsensusResult",
]
