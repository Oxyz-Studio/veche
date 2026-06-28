"""Name every map node from its PIXELS (pixel -> feature), so the map reads like a
map of features instead of opaque ids.

Each consolidated node carries a representative thumbnail. We hand that thumbnail to a
Gemini vision model and ask for a short feature name ("Patient Dashboard", "Message
Center", ...). No DOM is read: the label is derived from the same pixels the swarm saw.
Labels are written back into recording.json + veche_map.json (+ data.js regenerated).

    VECHE_REC_DIR=viz/recording_deep .venv/bin/python scripts/label_nodes.py
"""
import os, sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / os.environ.get("VECHE_REC_DIR", "viz/recording_deep")
FRAMES = REC / "frames"
MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]

PROMPT = (
    "This is a screenshot of one screen in the OpenEMR medical-practice web app. "
    "Give a SHORT feature name (2 to 4 words, Title Case) for what this screen is, "
    "for example: Patient Dashboard, History & Lifestyle, Patient Ledger, Patient Reports, "
    "Message Center, Calendar, Add Appointment, Fee Sheet, Patient Finder, Login, "
    "Administration, Procedures. Reply with ONLY the label, no punctuation, no quotes."
)


def label_one(client, model, frame):
    data = (FRAMES / frame).read_bytes()
    resp = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[
            types.Part.from_text(text=PROMPT),
            types.Part.from_bytes(data=data, mime_type="image/png"),
        ])],
    )
    return (getattr(resp, "text", "") or "").strip().strip('".').splitlines()[0][:32]


def pick_model(client):
    for m in MODELS:
        try:
            client.models.generate_content(model=m, contents=[types.Part.from_text(text="ok")])
            return m
        except Exception as e:
            print(f"  model {m} unavailable: {str(e)[:70]}")
    raise RuntimeError("no usable Gemini text model")


def main():
    client = genai.Client()
    model = pick_model(client)
    print(f"labeling with {model}")
    rec = json.loads((REC / "recording.json").read_text())
    for n in rec["nodes"]:
        for _ in range(5):
            try:
                n["label"] = label_one(client, model, n["frame"])
                break
            except Exception as e:
                if "rate" in str(e).lower() or "429" in str(e) or "resource" in str(e).lower():
                    time.sleep(8); continue
                print(f"  {n['id']} error: {str(e)[:80]}"); n["label"] = ""; break
        print(f"  {n['id']:6s} {n['frame']:12s} -> {n.get('label','')!r}")
    (REC / "recording.json").write_text(json.dumps(rec, indent=2))
    (REC / "data.js").write_text("window.RECORDING = " + json.dumps(rec) + ";")

    # mirror labels into the portable map's node metadata (nodes is a list of dicts)
    pm_path = REC / "veche_map.json"
    if pm_path.exists():
        pm = json.loads(pm_path.read_text())
        labels = {n["id"]: n.get("label", "") for n in rec["nodes"]}
        for node in pm.get("nodes", []):
            if node.get("id") in labels:
                node["label"] = labels[node["id"]]
        pm_path.write_text(json.dumps(pm, indent=2))
    print(f"\n  labeled {len(rec['nodes'])} nodes -> {REC/'recording.json'}, {REC/'data.js'}, {pm_path}")


if __name__ == "__main__":
    main()
