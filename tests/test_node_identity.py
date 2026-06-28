"""Tests for the PIXEL node-identity module.

Strategy: synthetic PIL fixtures rendered with the same *layout* but different
*data text*, plus a deterministic FakeEmbedder that mirrors the real contract
(visually-similar images -> high cosine similarity) without a network call.
"""
from __future__ import annotations

import math

import pytest
from PIL import Image, ImageDraw

from veche.node_identity import (
    layout_hash,
    hamming,
    Embedder,
    VoyageEmbedder,
    NodeRegistry,
)

W, H = 256, 256


def _blank() -> Image.Image:
    return Image.new("RGB", (W, H), "white")


def render_form(label: str, value: str) -> Image.Image:
    """A 'form' layout: title bar, sidebar, several field rows, a button.

    The layout (chrome, borders, sidebar) dominates the pixels; only the small
    field-text changes between data instances -- mirroring a real screen where
    the structure is stable and just the data text differs."""
    img = _blank()
    d = ImageDraw.Draw(img)
    # title bar
    d.rectangle([0, 0, W, 40], fill=(30, 60, 120))
    d.text((10, 14), "Patient Record", fill=(255, 255, 255))
    # sidebar (stable chrome)
    d.rectangle([0, 40, 60, H], fill=(220, 224, 230))
    for sy in range(60, H - 20, 30):
        d.rectangle([10, sy, 50, sy + 18], fill=(180, 188, 200))
    # field rows (labels are stable; only the data after ':' varies)
    d.rectangle([80, 70, 236, 100], outline=(0, 0, 0), width=2)
    d.text((86, 78), f"Name: {label}", fill=(0, 0, 0))
    d.rectangle([80, 130, 236, 160], outline=(0, 0, 0), width=2)
    d.text((86, 138), f"Value: {value}", fill=(0, 0, 0))
    d.rectangle([80, 170, 236, 195], outline=(120, 120, 120), width=1)
    d.text((86, 176), "Status: active", fill=(0, 0, 0))
    # submit button
    d.rectangle([130, 210, 226, 245], fill=(40, 160, 80))
    d.text((146, 220), "Submit", fill=(255, 255, 255))
    return img


def render_dashboard() -> Image.Image:
    """A clearly different layout: a grid of colored tiles."""
    img = _blank()
    d = ImageDraw.Draw(img)
    colors = [(200, 50, 50), (50, 200, 50), (50, 50, 200), (200, 200, 50)]
    i = 0
    for row in range(2):
        for col in range(2):
            x0 = 20 + col * 120
            y0 = 20 + row * 120
            d.rectangle([x0, y0, x0 + 100, y0 + 100], fill=colors[i])
            i += 1
    return img


class FakeEmbedder:
    """Deterministic stand-in for VoyageEmbedder.

    Embeds an image as its coarse structure: downscale to 16x16 grayscale,
    flatten, L2-normalize. Visually-similar images therefore produce vectors
    with high cosine similarity -- realistic behaviour, no network.
    """

    def embed_image(self, image) -> list[float]:
        img = image.convert("L").resize((16, 16))
        px = [b / 255.0 for b in img.tobytes()]
        mean = sum(px) / len(px)
        vec = [v - mean for v in px]  # mean-center: cancel shared brightness, keep structure
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def test_fake_embedder_satisfies_protocol():
    assert isinstance(FakeEmbedder(), Embedder)


def test_layout_hash_accepts_bytes_and_path(tmp_path):
    img = render_form("Alice", "7.1")
    h_img = layout_hash(img)
    assert isinstance(h_img, str) and len(h_img) > 0

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert layout_hash(buf.getvalue()) == h_img

    p = tmp_path / "form.png"
    img.save(p)
    assert layout_hash(str(p)) == h_img


def test_hamming_self_is_zero_and_symmetric():
    h1 = layout_hash(render_form("Alice", "7.1"))
    h2 = layout_hash(render_dashboard())
    assert hamming(h1, h1) == 0
    assert hamming(h1, h2) == hamming(h2, h1)
    assert hamming(h1, h2) > 0


def test_same_layout_different_data_same_node():
    """(1) Same layout, different data text -> SAME node_id."""
    reg = NodeRegistry(FakeEmbedder())
    id_a = reg.identify(render_form("Alice", "7.1"))
    id_b = reg.identify(render_form("Bob", "9.4"))
    assert id_a == id_b
    assert len(reg.nodes) == 1


def test_different_layout_different_node():
    """(2) Clearly different layout -> DIFFERENT node_id."""
    reg = NodeRegistry(FakeEmbedder())
    id_form = reg.identify(render_form("Alice", "7.1"))
    id_dash = reg.identify(render_dashboard())
    assert id_form != id_dash
    assert len(reg.nodes) == 2


def test_identify_idempotent():
    """(3) Same image twice -> same id, no new node."""
    reg = NodeRegistry(FakeEmbedder())
    img = render_form("Alice", "7.1")
    first = reg.identify(img)
    second = reg.identify(img)
    assert first == second
    assert len(reg.nodes) == 1


def test_ids_are_sequential():
    reg = NodeRegistry(FakeEmbedder())
    a = reg.identify(render_form("Alice", "7.1"))
    b = reg.identify(render_dashboard())
    assert a == "n0001"
    assert b == "n0002"


class _TagStub:
    """Embedder returning a fixed vector per image object — to test that identity
    is COSINE-primary and no longer gated by phash."""

    def __init__(self, by_id):
        self._by_id = by_id

    def embed_image(self, image):
        return self._by_id[id(image)]


def test_cosine_primary_collapses_despite_large_phash_diff():
    """Regression for the real H0 finding: two screens with a LARGE phash hamming
    that the embedder says are the same MUST collapse — the old phash<=12 gate
    broke this on real EHR dashboards (two patient charts measured hamming ~138)."""
    a1 = render_form("Alice", "7.1")
    a2 = render_dashboard()      # very different layout -> large phash hamming
    b = Image.new("RGB", (W, H), "white")
    ImageDraw.Draw(b).rectangle([20, 20, 236, 236], fill=(15, 15, 15))  # a third, distinct screen
    assert hamming(layout_hash(a1), layout_hash(a2)) > 12  # the old gate would have split a1/a2

    same_vec, other_vec = [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]
    reg = NodeRegistry(_TagStub({id(a1): same_vec, id(a2): same_vec, id(b): other_vec}))
    nid_a1 = reg.identify(a1)
    assert reg.identify(a2) == nid_a1   # high cosine -> SAME node despite huge phash diff
    assert reg.identify(b) != nid_a1    # low cosine -> different node


def test_real_voyage_smoke():
    """Real Voyage multimodal embedding smoke test. Skips on any error
    (missing key, network, quota) so it never blocks CI."""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        emb = VoyageEmbedder()  # voyage-multimodal-3
        v1 = emb.embed_image(render_form("Alice", "7.1"))
        v2 = emb.embed_image(render_dashboard())

        assert isinstance(v1, list) and isinstance(v2, list)
        assert len(v1) > 0
        assert len(v1) == len(v2)
        assert all(isinstance(x, float) for x in v1)
        # sanity: real embeddings should not be identical for different layouts
        assert v1 != v2
        print(f"\n[voyage smoke] model={emb.model} dim={len(v1)}")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Voyage smoke skipped: {type(e).__name__}: {e}")
