"""PIXEL node-identity for VECHE (H0 make-or-break).

No DOM is available, so a screen's identity is derived from its pixels.

DESIGN (revised after H0 validation on REAL OpenEMR screenshots):
  The decision is COSINE-PRIMARY on a multimodal embedding. On real, data-heavy
  EHR screens a perceptual hash (phash) is NOT a usable layout signal — two
  instances of the SAME patient-dashboard template (different patient data)
  measured phash-hamming ~112-138 (≈random), because the changing data dominates
  the pixels. Voyage multimodal embeddings, by contrast, separate cleanly:

      same logical screen (3 patient dashboards):  cosine 0.67 – 0.85
      different screen (dashboard vs fees):         cosine 0.30 – 0.33

  So identity = nearest existing node by embedding cosine, accepted when the best
  similarity >= ``sim_thresh`` (default 0.55, the midpoint of the observed gap).
  phash is kept only as (a) a cheap EXACT-MATCH fast-path that collapses a
  re-render of a screen we just saw without spending a Voyage call, and (b)
  stored metadata. It is NEVER a gate (gating on it is what broke collapse).

  At scale, the linear cosine scan below is replaced by Atlas $vectorSearch over
  ``nodes.embedding`` (see veche.store.Store.search_similar_node), which returns
  the same nearest-node-by-cosine — threshold its score the same way.

Public surface:
  - layout_hash(image) -> str
  - hamming(h1, h2) -> int
  - Embedder (Protocol), VoyageEmbedder (real), and NodeRegistry.
"""
from __future__ import annotations

import io
import os
import math
import typing

import imagehash
from PIL import Image

__all__ = ["layout_hash", "hamming", "Embedder", "VoyageEmbedder", "NodeRegistry"]

_HASH_SIZE = 16


def _to_pil(image: typing.Any) -> Image.Image:
    """Accept a PIL.Image, raw image bytes, or a filesystem path."""
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, (bytes, bytearray)):
        return Image.open(io.BytesIO(bytes(image)))
    if isinstance(image, (str, os.PathLike)):
        return Image.open(os.fspath(image))
    raise TypeError(f"expects a PIL.Image, bytes, or path, got {type(image)!r}")


def layout_hash(image: typing.Any) -> str:
    """Perceptual hash via imagehash.phash(hash_size=16). Hex string."""
    return str(imagehash.phash(_to_pil(image), hash_size=_HASH_SIZE))


def hamming(h1: str, h2: str) -> int:
    """Hamming distance between two layout_hash hex strings."""
    return int(imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2))


def _cosine(a: typing.Sequence[float], b: typing.Sequence[float]) -> float:
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


@typing.runtime_checkable
class Embedder(typing.Protocol):
    """Anything that turns an image into a dense vector."""

    def embed_image(self, image: typing.Any) -> list[float]:
        ...


class VoyageEmbedder:
    """Real multimodal embedder backed by Voyage AI (voyage-multimodal-3, dim 1024).

    Verified against voyageai==0.4.1: client.multimodal_embed(inputs, model=...),
    inputs a list of "documents" each a list of interleaved content; result has
    ``.embeddings`` (one float vector per document). Lazy client so importing this
    module never requires a key. Free tier is 3 RPM — callers should back off.
    """

    def __init__(self, model: str = "voyage-multimodal-3"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import voyageai  # reads VOYAGE_API_KEY from the environment
            self._client = voyageai.Client()
        return self._client

    def embed_image(self, image: typing.Any) -> list[float]:
        img = _to_pil(image).convert("RGB")
        result = self._get_client().multimodal_embed(
            inputs=[[img]], model=self.model, input_type="document"
        )
        return list(result.embeddings[0])


class NodeRegistry:
    """Assigns stable node_ids to screens from pixels alone — COSINE-PRIMARY.

    identify(image):
      1. EXACT-MATCH fast-path: if phash is within ``exact_match_hamming`` of a
         known node, return it (a re-render of a screen we just saw) — no embed call.
      2. Otherwise embed the image and return the nearest existing node by cosine
         if best similarity >= ``sim_thresh``; else mint a fresh id ("n0001", ...).

    Embeddings are cached per phash so identify() is idempotent and cheap on repeats.
    """

    def __init__(
        self,
        embedder: Embedder,
        sim_thresh: float = 0.55,
        exact_match_hamming: int = 4,
    ):
        self.embedder = embedder
        self.sim_thresh = sim_thresh
        self.exact_match_hamming = exact_match_hamming
        # node_id -> {"phash": str, "embedding": list[float]}
        self.nodes: dict[str, dict] = {}
        self._counter = 0
        self._embed_cache: dict[str, list[float]] = {}

    def _next_id(self) -> str:
        self._counter += 1
        return f"n{self._counter:04d}"

    def _embed_for(self, phash: str, image: typing.Any) -> list[float]:
        cached = self._embed_cache.get(phash)
        if cached is not None:
            return cached
        emb = list(self.embedder.embed_image(image))
        self._embed_cache[phash] = emb
        return emb

    def identify(self, image: typing.Any) -> str:
        phash = layout_hash(image)

        # 1. Exact-match fast-path: a near-identical render we've already seen.
        for nid, data in self.nodes.items():
            if hamming(phash, data["phash"]) <= self.exact_match_hamming:
                return nid

        # 2. Cosine-primary: nearest existing node by embedding similarity.
        emb = self._embed_for(phash, image)
        best_id, best_sim = None, -1.0
        for nid, data in self.nodes.items():
            sim = _cosine(emb, data["embedding"])
            if sim > best_sim:
                best_sim, best_id = sim, nid
        if best_id is not None and best_sim >= self.sim_thresh:
            return best_id

        nid = self._next_id()
        self.nodes[nid] = {"phash": phash, "embedding": emb}
        return nid
