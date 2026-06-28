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
        time.sleep(1.2)
        page.screenshot(path=str(OUT / "viz_0_title.png"))
        for i, name in enumerate(["viz_1_explore", "viz_2_conflict", "viz_3_overrule", "viz_4_cost"]):
            page.keyboard.press("Space")
            time.sleep(1.4)
            page.screenshot(path=str(OUT / f"{name}.png"))
        print("shot:", [p.name for p in sorted(OUT.glob("viz_*.png"))])
        b.close()


if __name__ == "__main__":
    main()
