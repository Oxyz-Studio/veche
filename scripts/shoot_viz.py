"""Render viz/index.html at projector resolution and screenshot each beat."""
import pathlib, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = (ROOT / "viz" / "index.html").as_uri()
OUT = ROOT / "captures"


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_context(viewport={"width": 1600, "height": 900}).new_page()
        page.goto(URL, wait_until="networkidle")
        time.sleep(2.0)
        names = ["d0_problem", "d1_cold", "d2_swarm", "d3_consensus", "d4_overrule", "d5_map", "d6_mapguided"]
        page.screenshot(path=str(OUT / f"{names[0]}.png"))
        for n in names[1:]:
            page.keyboard.press("Space")
            time.sleep(2.0)
            page.screenshot(path=str(OUT / f"{n}.png"))
        print("shot:", names)
        b.close()


if __name__ == "__main__":
    main()
