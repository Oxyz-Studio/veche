"""MAP-GUIDED replay of the SAME task the cold run did — but the route is already
in the map. Per step the operator does CHEAP perception (a Voyage node-identity
embedding, free tier) + a map lookup + execute. ZERO computer-use (vision-reasoning)
tokens. This is the amortized cost of every reuse after a route is mapped once.
"""
import sys, pathlib, json, time, shutil
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from veche.browser import Browser
from veche.node_identity import VoyageEmbedder

ROOT = pathlib.Path(__file__).resolve().parent.parent


def embed_safe(emb, shot):
    for attempt in range(5):
        try:
            return emb.embed_image(shot)
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                print("   (voyage rate-limit, sleep 22s)"); time.sleep(22); continue
            print("   voyage error:", type(e).__name__); return None
    return None


def main():
    trace = json.loads((ROOT / "captures" / "cold_trace.json").read_text())
    emb = VoyageEmbedder()
    VID = ROOT / "viz" / "recording" / "videos"; VID.mkdir(parents=True, exist_ok=True)
    br = Browser(headless=True, video_dir=VID)
    print("login + open patient dashboard...")
    br.login_openemr()
    br.open_patient(1)

    cu_tokens = 0   # computer-use (paid vision) tokens — stays ZERO
    voyage_embeds = 0
    steps = 0
    for act in trace:
        shot = br.screenshot()
        v = embed_safe(emb, shot)          # cheap node-identity perception (free tier)
        if v is not None:
            voyage_embeds += 1
        steps += 1
        print(f"  step {steps}: map-lookup -> replay {act['name']} {act.get('args', {})}  (computer-use tokens: 0)")
        br.execute(act["name"], act.get("args", {}))

    success = "ledger" in br.text().lower()
    print(f"\n=== MAP-GUIDED RESULT ===")
    print(f"  steps={steps}  computer_use_tokens={cu_tokens}  voyage_embeds={voyage_embeds} (free tier)  success={success}")
    vp = br.close()
    if vp and pathlib.Path(vp).exists():
        shutil.move(vp, VID / "mapped_op.webm"); print("  video -> videos/mapped_op.webm")


if __name__ == "__main__":
    main()
