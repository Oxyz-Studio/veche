"""Atlas shared-memory store for VECHE.

A single MongoDB Atlas database acts as the shared long-term memory for N
concurrent agents. Every agent appends Observations to ONE log collection;
the H0 concurrency claim is that N agents can append to that one log with
zero loss. ObjectId is monotonic per-process and globally ordered enough for
our purposes, so insertion order is recoverable by sorting on _id.

Nodes (canonical screens) carry an embedding + perceptual hash and are
queried via Atlas Vector Search.
"""
from __future__ import annotations

import os

import certifi
from pymongo import MongoClient, ASCENDING

from veche.types import Observation


class Store:
    def __init__(self, uri: str | None = None, db: str = "veche_test"):
        # The URI in .env already works as-is with pymongo even if the SRV
        # password has special chars — pass it through untouched.
        uri = uri or os.environ.get("MONGODB_URI")
        if not uri:
            raise ValueError("No Mongo URI: pass uri= or set MONGODB_URI")
        # tlsCAFile=certifi.where() avoids macOS system-trust TLS failures.
        self.client = MongoClient(uri, tlsCAFile=certifi.where())
        self.db = self.client[db]
        self.observations = self.db["observations"]
        self.nodes = self.db["nodes"]

    # ------------------------------------------------------------------ log

    def append_observation(self, obs: dict) -> str:
        """Insert one observation. Returns str(inserted_id).

        The server-assigned ObjectId _id is monotonic, so insertion order is
        preserved by sorting on _id in read_log(). This single-document insert
        is atomic and is the operation N agents hammer concurrently.
        """
        doc = dict(obs)
        result = self.observations.insert_one(doc)
        return str(result.inserted_id)

    def read_log(self) -> list[Observation]:
        """Return ALL observations sorted by _id as Observation objects."""
        out: list[Observation] = []
        for d in self.observations.find().sort("_id", ASCENDING):
            out.append(
                Observation(
                    agent_id=d.get("agent_id", ""),
                    from_node=d.get("from_node", ""),
                    action=d.get("action", ""),
                    to_node=d.get("to_node", ""),
                    ts=d.get("ts", 0),
                )
            )
        return out

    # ---------------------------------------------------------------- nodes

    def upsert_node(self, node_id: str, embedding: list[float], phash: str):
        self.nodes.update_one(
            {"_id": node_id},
            {"$set": {"embedding": embedding, "phash": phash}},
            upsert=True,
        )

    def ensure_vector_index(self):
        """Best-effort create an Atlas Vector Search index 'vector_index' on
        nodes.embedding. Index build can take minutes; we DO NOT block on it.
        """
        # Infer dimensions from an existing node if present, else default 1024
        # (voyage-3.5). The index can still be created before any node exists.
        num_dims = 1024
        sample = self.nodes.find_one({"embedding": {"$exists": True}})
        if sample and isinstance(sample.get("embedding"), list) and sample["embedding"]:
            num_dims = len(sample["embedding"])

        definition = {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": num_dims,
                    "similarity": "cosine",
                }
            ]
        }
        try:
            from pymongo.operations import SearchIndexModel

            # Skip if it already exists.
            existing = {ix.get("name") for ix in self.nodes.list_search_indexes()}
            if "vector_index" in existing:
                print(f"[ensure_vector_index] 'vector_index' already exists (dims={num_dims})")
                return
            model = SearchIndexModel(
                definition=definition, name="vector_index", type="vectorSearch"
            )
            self.nodes.create_search_index(model=model)
            print(
                f"[ensure_vector_index] requested 'vector_index' "
                f"(dims={num_dims}, cosine). Build is async — not blocking."
            )
        except Exception as e:  # noqa: BLE001 — best-effort by design
            print(f"[ensure_vector_index] best-effort skipped: {type(e).__name__}: {e}")

    def search_similar_node(self, embedding, k: int = 5) -> list[dict]:
        """$vectorSearch against 'vector_index'. Returns [] if not ready."""
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": list(embedding),
                    "numCandidates": max(100, k * 10),
                    "limit": k,
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "phash": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        try:
            return list(self.nodes.aggregate(pipeline))
        except Exception as e:  # noqa: BLE001 — index may not be queryable yet
            print(f"[search_similar_node] not ready: {type(e).__name__}: {e}")
            return []

    # -------------------------------------------------------------- cleanup

    def clear(self):
        self.observations.drop()
        self.nodes.drop()

    def close(self):
        self.client.close()
