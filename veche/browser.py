"""Browser executor: turns a computer-use Action into real clicks/keys on a page,
and captures screenshots. Used by both the COLD loop and the MAP-GUIDED operator.

Coordinates from the model are normalized to 0-999 (Gemini computer-use); we
denormalize to viewport pixels here.
"""
from __future__ import annotations

import time
from playwright.sync_api import sync_playwright

OPENEMR = "https://demo.openemr.io/openemr"


class Browser:
    def __init__(self, viewport=(1440, 900), headless: bool = True):
        self.w, self.h = viewport
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._ctx = self._browser.new_context(viewport={"width": self.w, "height": self.h})
        self.page = self._ctx.new_page()
        self.page.set_default_timeout(25000)

    # --- navigation ---
    def goto(self, url: str):
        self.page.goto(url, wait_until="networkidle")

    def login_openemr(self, user="admin", pw="pass"):
        self.goto(f"{OPENEMR}/interface/login/login.php?site=default")
        self.page.fill("input[name=authUser]", user)
        self.page.fill("input[name=clearPass]", pw)
        for sel in ("#login-button", "button[type=submit]", "input[type=submit]", "button:has-text('Login')"):
            try:
                self.page.click(sel, timeout=3000)
                break
            except Exception:
                continue
        self.page.wait_for_load_state("networkidle")
        time.sleep(1.5)

    def open_patient(self, pid: int):
        self.goto(f"{OPENEMR}/interface/patient_file/summary/demographics.php?set_pid={pid}")
        time.sleep(1.0)

    # --- perception ---
    def screenshot(self) -> bytes:
        return self.page.screenshot(full_page=False)

    def url(self) -> str:
        return self.page.url

    def text(self) -> str:
        try:
            return self.page.inner_text("body")[:4000]
        except Exception:
            return ""

    # --- actuation ---
    def _px(self, x, y):
        return int(round((x or 0) / 1000 * self.w)), int(round((y or 0) / 1000 * self.h))

    def execute(self, name: str, args: dict):
        """Execute a computer-use action by its predefined name + args."""
        n = (name or "").lower()
        if "click" in n and "double" not in n:
            x, y = self._px(args.get("x"), args.get("y"))
            self.page.mouse.click(x, y)
        elif "double_click" in n:
            x, y = self._px(args.get("x"), args.get("y"))
            self.page.mouse.dblclick(x, y)
        elif "type" in n:
            x, y = self._px(args.get("x"), args.get("y"))
            if args.get("x") is not None:
                self.page.mouse.click(x, y)
            self.page.keyboard.type(args.get("text") or "")
        elif "key" in n or "press" in n:
            keys = args.get("keys") or args.get("text") or ""
            self.page.keyboard.press(keys.replace("+", "+") if keys else "Enter")
        elif "scroll" in n:
            dy = 600 if "down" in str(args).lower() else -600
            self.page.mouse.wheel(0, dy)
        elif "navigate" in n or "open_web" in n:
            url = args.get("url")
            if url:
                self.goto(url)
        elif "wait" in n:
            time.sleep(2)
        else:
            return False
        self.page.wait_for_load_state("networkidle")
        time.sleep(0.5)
        return True

    def close(self):
        try:
            self._ctx.close(); self._browser.close(); self._pw.stop()
        except Exception:
            pass
