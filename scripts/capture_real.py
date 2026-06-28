"""Capture REAL screenshots (no Docker) for the node-identity go/no-go.

Guaranteed set: two GitHub profiles (same layout, different data) + one different page.
Best-effort: OpenEMR online demo (login + dashboard + finder).
Saves PNGs to captures/. Defensive: screenshot whatever loads, continue on error.
"""
import pathlib
from playwright.sync_api import sync_playwright

CAP = pathlib.Path(__file__).resolve().parent.parent / "captures"
CAP.mkdir(exist_ok=True)


def shot(page, name):
    p = CAP / name
    try:
        page.screenshot(path=str(p), full_page=True)
        print(f"  saved {name}")
    except Exception as e:
        print(f"  FAILED {name}: {e}")


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(20000)

        # --- Guaranteed same-layout/different-data pair + a different screen ---
        print("GitHub set:")
        for url, name in [
            ("https://github.com/torvalds", "gh_profile_a.png"),
            ("https://github.com/gvanrossum", "gh_profile_b.png"),
            ("https://github.com/explore", "gh_explore.png"),
        ]:
            try:
                page.goto(url, wait_until="networkidle")
                shot(page, name)
            except Exception as e:
                print(f"  nav {url} failed: {e}")

        # --- Best-effort OpenEMR online demo ---
        print("OpenEMR demo:")
        try:
            page.goto("https://demo.openemr.io/openemr/interface/login/login.php?site=default",
                      wait_until="networkidle")
            shot(page, "oemr_01_login.png")
            for sel, val in [("input[name=authUser]", "admin"), ("input[name=clearPass]", "pass")]:
                try:
                    page.fill(sel, val)
                except Exception as e:
                    print(f"  fill {sel} failed: {e}")
            # try a few likely submit triggers
            for sel in ("#login-button", "button[type=submit]", "input[type=submit]", "button:has-text('Login')"):
                try:
                    page.click(sel, timeout=3000)
                    break
                except Exception:
                    continue
            page.wait_for_load_state("networkidle")
            shot(page, "oemr_02_dashboard.png")
            # patient finder (session cookie is set) — a distinct list screen
            try:
                page.goto("https://demo.openemr.io/openemr/interface/main/finder/dynamic_finder.php",
                          wait_until="networkidle")
                shot(page, "oemr_03_finder.png")
            except Exception as e:
                print(f"  finder failed: {e}")
        except Exception as e:
            print(f"  OpenEMR demo failed: {e}")

        ctx.close()
        b.close()
    print("Captured files:", sorted(p.name for p in CAP.glob("*.png")))


if __name__ == "__main__":
    main()
