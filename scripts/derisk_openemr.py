"""FAITHFUL node-identity go/no-go: two OpenEMR patient demographics screens
(same template, different data, fixed VIEWPORT — what a computer-use agent sees)
should COLLAPSE; a different EHR screen should SPLIT.

OpenEMR selects the patient via demographics.php?set_pid=N (the finder's own mechanism)."""
import sys, pathlib, time, itertools
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np
from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import sync_playwright
from veche.node_identity import layout_hash, hamming, VoyageEmbedder

CAP = pathlib.Path(__file__).resolve().parent.parent / "captures"
BASE = "https://demo.openemr.io/openemr"
HAMMING_THRESH, SIM_THRESH = 12, 0.85


def capture():
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page(); page.set_default_timeout(25000)
        page.goto(f"{BASE}/interface/login/login.php?site=default", wait_until="networkidle")
        page.fill("input[name=authUser]", "admin"); page.fill("input[name=clearPass]", "pass")
        for sel in ("#login-button", "button[type=submit]", "input[type=submit]", "button:has-text('Login')"):
            try:
                page.click(sel, timeout=3000); break
            except Exception:
                continue
        page.wait_for_load_state("networkidle"); time.sleep(2)
        targets = {
            "oemr_patient1.png": f"{BASE}/interface/patient_file/summary/demographics.php?set_pid=1",
            "oemr_patient2.png": f"{BASE}/interface/patient_file/summary/demographics.php?set_pid=2",
            "oemr_patient3.png": f"{BASE}/interface/patient_file/summary/demographics.php?set_pid=3",
            "oemr_fees.png":     f"{BASE}/interface/patient_file/pos_checkout.php",
        }
        for name, url in targets.items():
            try:
                page.goto(url, wait_until="networkidle"); time.sleep(1.5)
                page.screenshot(path=str(CAP / name), full_page=False)  # VIEWPORT, not full page
                print(f"  saved {name}")
                out[name] = CAP / name
            except Exception as e:
                print(f"  FAILED {name}: {e}")
        ctx.close(); b.close()
    return out


def embed_safe(emb, path):
    for attempt in range(6):
        try:
            return np.array(emb.embed_image(str(path)), dtype=float)
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                print(f"   rate-limited; sleep 22s ({attempt+1})"); time.sleep(22); continue
            raise
    raise RuntimeError("voyage retries exhausted")


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    files = capture()
    names = [n for n in ("oemr_patient1.png", "oemr_patient2.png", "oemr_patient3.png", "oemr_fees.png")
             if (CAP / n).exists()]
    print("\nvalidating:", names)
    emb = VoyageEmbedder()
    ph = {n: layout_hash(str(CAP / n)) for n in names}
    ev = {n: embed_safe(emb, CAP / n) for n in names}
    print("\n=== pairwise (phash hamming | voyage cosine) ===")
    for a, b in itertools.combinations(names, 2):
        print(f"  {a:18} vs {b:18}  hamming={hamming(ph[a], ph[b]):3d}  cos={cos(ev[a], ev[b]):.3f}")
    if {"oemr_patient1.png", "oemr_patient2.png"} <= set(names):
        h = hamming(ph["oemr_patient1.png"], ph["oemr_patient2.png"]); c = cos(ev["oemr_patient1.png"], ev["oemr_patient2.png"])
        print(f"\n  PATIENT1 vs PATIENT2 (should COLLAPSE): hamming={h} cos={c:.3f} -> collapse_at_default={(h<=HAMMING_THRESH and c>=SIM_THRESH)}")
    if {"oemr_patient1.png", "oemr_fees.png"} <= set(names):
        h = hamming(ph["oemr_patient1.png"], ph["oemr_fees.png"]); c = cos(ev["oemr_patient1.png"], ev["oemr_fees.png"])
        print(f"  PATIENT1 vs FEES (should SPLIT): hamming={h} cos={c:.3f} -> split={not (h<=HAMMING_THRESH and c>=SIM_THRESH)}")


if __name__ == "__main__":
    main()
