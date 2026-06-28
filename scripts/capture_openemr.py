"""Capture OpenEMR screenshots into ./captures/ for node-identity de-risk.

Logs in with admin/pass (set in deploy/docker-compose.openemr.yml), then grabs
6 PNGs covering login, dashboard, patient finder, two patient charts
(same layout, different data), and an encounter/form screen.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
USER = "admin"
PWD = "pass"
OUT = Path(__file__).resolve().parent.parent / "captures"
OUT.mkdir(exist_ok=True)


def shot(page, name):
    p = OUT / name
    page.screenshot(path=str(p), full_page=False)
    print(f"SAVED {p}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  ignore_https_errors=True)
        page = ctx.new_page()

        # --- 01 login ---
        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        # OpenEMR login fields: name=authUser, name=clearPass
        try:
            page.wait_for_selector("input[name='authUser']", timeout=30000)
        except Exception:
            print("LOGIN_FORM_NOT_FOUND; current url:", page.url)
            shot(page, "01_login.png")
            browser.close()
            return
        shot(page, "01_login.png")

        page.fill("input[name='authUser']", USER)
        page.fill("input[name='clearPass']", PWD)
        # language default is fine; submit
        page.click("#login-button, button[type='submit'], input[type='submit']")
        page.wait_for_timeout(6000)

        # OpenEMR uses a frameset (main_top.php -> left_nav + main frames)
        # --- 02 dashboard ---
        page.wait_for_timeout(3000)
        shot(page, "02_dashboard.png")

        # --- 03 patient finder ---
        # Navigate the main content frame directly to the patient finder.
        page.goto(f"{BASE}/interface/main/finder/patient_select.php",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        shot(page, "03_patient_finder.png")

        # Discover patient pids from the finder list via the demographics API page.
        pids = []
        try:
            # patient list (search returns all when blank)
            page.goto(f"{BASE}/interface/main/finder/dynamic_finder.php",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception as e:
            print("finder list nav failed:", e)

        # Fall back: try a few common demo pids. We'll capture whichever load.
        candidate_pids = [1, 2, 3, 4, 5]

        def open_chart(pid):
            # Set the patient as active then load demographics summary.
            page.goto(f"{BASE}/interface/patient_file/summary/demographics.php?set_pid={pid}",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3500)
            txt = page.content()
            return "demographic" in txt.lower() or "Patient" in txt

        chart_pids = []
        for pid in candidate_pids:
            try:
                if open_chart(pid):
                    chart_pids.append(pid)
                if len(chart_pids) >= 2:
                    break
            except Exception as e:
                print(f"pid {pid} failed: {e}")

        if len(chart_pids) >= 1:
            open_chart(chart_pids[0])
            shot(page, "04_patient_chartA.png")
        else:
            shot(page, "04_patient_chartA.png")

        if len(chart_pids) >= 2:
            open_chart(chart_pids[1])
            shot(page, "05_patient_chartB.png")
        else:
            # still capture something
            shot(page, "05_patient_chartB.png")

        print("CHART_PIDS", chart_pids)

        # --- 06 encounter / form ---
        # Add/encounter screen for the first chart patient.
        try:
            if chart_pids:
                open_chart(chart_pids[0])
            page.goto(f"{BASE}/interface/forms/newpatient/new.php",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3500)
        except Exception as e:
            print("encounter nav failed:", e)
        shot(page, "06_form_or_encounter.png")

        browser.close()
        print("DONE")


if __name__ == "__main__":
    main()
