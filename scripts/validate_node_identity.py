"""H0 GO/NO-GO: does pixel node-identity (phash + Voyage multimodal) collapse
same-layout/different-data and split different screens — on REAL screenshots?

Uses 1 Voyage multimodal call per image (free tier = 3 RPM, so we back off)."""
import os, time, pathlib, itertools
import numpy as np
from dotenv import load_dotenv
load_dotenv()

from veche.node_identity import layout_hash, hamming, VoyageEmbedder

CAP = pathlib.Path(__file__).resolve().parent.parent / "captures"
HAMMING_THRESH = 12
SIM_THRESH = 0.85

emb = VoyageEmbedder()

def embed_safe(path):
    for attempt in range(6):
        try:
            return np.array(emb.embed_image(str(path)), dtype=float)
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                print(f"   rate-limited; sleep 22s (try {attempt+1})"); time.sleep(22); continue
            raise
    raise RuntimeError("voyage retries exhausted")

def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))

# The pair under test + a clearly-different screen.
imgs = ["gh_profile_a.png", "gh_profile_b.png", "gh_explore.png"]
imgs = [n for n in imgs if (CAP / n).exists()]
print("images:", imgs)

ph = {n: layout_hash(str(CAP / n)) for n in imgs}
ev = {}
for n in imgs:
    ev[n] = embed_safe(CAP / n)
    print(f"  embedded {n} (dim={len(ev[n])})")

print("\n=== pairwise (phash hamming | voyage cosine | same-node?) ===")
for a, b in itertools.combinations(imgs, 2):
    h = hamming(ph[a], ph[b]); c = cos(ev[a], ev[b])
    same = (h <= HAMMING_THRESH) and (c >= SIM_THRESH)
    print(f"  {a:18} vs {b:18}  hamming={h:3d}  cos={c:.3f}  -> same={same}")

print("\n=== GO/NO-GO ===")
if {"gh_profile_a.png", "gh_profile_b.png"} <= set(imgs):
    h = hamming(ph["gh_profile_a.png"], ph["gh_profile_b.png"])
    c = cos(ev["gh_profile_a.png"], ev["gh_profile_b.png"])
    collapse = (h <= HAMMING_THRESH) and (c >= SIM_THRESH)
    print(f"  same-layout/different-data COLLAPSE: {collapse}  (hamming={h}, cos={c:.3f})")
if "gh_explore.png" in imgs and "gh_profile_a.png" in imgs:
    h = hamming(ph["gh_profile_a.png"], ph["gh_explore.png"])
    c = cos(ev["gh_profile_a.png"], ev["gh_explore.png"])
    split = not ((h <= HAMMING_THRESH) and (c >= SIM_THRESH))
    print(f"  different-screen SPLIT: {split}  (hamming={h}, cos={c:.3f})")
