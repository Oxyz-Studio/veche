"""Compute the Twin Test - the pixels-only node-identity proof - from REAL frames.

Two agents land on the SAME logical screen for DIFFERENT patients (the pixels don't
match, and there is no DOM to compare). A Voyage multimodal embedding decides identity:
same screen scores well above the merge threshold, a genuinely different screen scores
well below it. This is the make-or-break of VECHE (veche-spec.md §4 stage 1).

Frames below were chosen by eye from the deep capture: the Medical Record Dashboard for
three different patients, plus the Message Center as a clearly different screen. This
script re-embeds them live and writes the measured cosines into recording.json (+ data.js),
so the number on stage is the real number, recomputable by anyone with the frames.

    VECHE_REC_DIR=viz/recording_deep .venv/bin/python scripts/build_twin_test.py
"""
import os, sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from veche.node_identity import VoyageEmbedder, _cosine

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / os.environ.get("VECHE_REC_DIR", "viz/recording_deep")
FRAMES = REC / "frames"

# Anchor + a same-screen-different-patient twin + a clearly different screen.
ANCHOR = {"frame": "a1_06.png", "label": "Medical Record Dashboard", "sub": "patient: Phil Belford", "agent": "a1"}
SAME   = {"frame": "a3_01.png", "label": "Medical Record Dashboard", "sub": "patient: Susan Ardmore Underwood", "agent": "a3"}
DIFF   = {"frame": "a4_11.png", "label": "Message Center",           "sub": "a different screen",               "agent": "a4"}
TAU = 0.55


def embed(e, frame):
    for _ in range(6):
        try:
            return e.embed_image(str(FRAMES / frame))
        except Exception as ex:
            print(f"  retry {frame}: {str(ex)[:60]}")
            time.sleep(20)
    raise RuntimeError(f"voyage retries exhausted for {frame}")


def main():
    e = VoyageEmbedder()
    va = embed(e, ANCHOR["frame"]); print("embedded anchor", ANCHOR["frame"])
    vs = embed(e, SAME["frame"]);   print("embedded same  ", SAME["frame"])
    vd = embed(e, DIFF["frame"]);   print("embedded diff  ", DIFF["frame"])

    cos_same = round(_cosine(va, vs), 3)
    cos_diff = round(_cosine(va, vd), 3)
    twin = {
        "tau": TAU,
        "anchor": ANCHOR,
        "same": {**SAME, "cosine": cos_same, "verdict": "merge" if cos_same >= TAU else "split"},
        "diff": {**DIFF, "cosine": cos_diff, "verdict": "merge" if cos_diff >= TAU else "split"},
    }
    print(f"\n  TWIN TEST (tau={TAU}):")
    print(f"    same screen, different patient: cosine {cos_same}  -> {twin['same']['verdict'].upper()}")
    print(f"    different screen:               cosine {cos_diff}  -> {twin['diff']['verdict'].upper()}")
    if twin["same"]["verdict"] != "merge" or twin["diff"]["verdict"] != "split":
        print("  WARNING: twin test did not produce the expected merge/split - pick different frames.")

    rec_path = REC / "recording.json"
    rec = json.loads(rec_path.read_text())
    rec["twin_test"] = twin
    rec_path.write_text(json.dumps(rec, indent=2))
    (REC / "data.js").write_text("window.RECORDING = " + json.dumps(rec) + ";")
    print(f"\n  wrote twin_test into {rec_path} and regenerated {REC / 'data.js'}")


if __name__ == "__main__":
    main()
