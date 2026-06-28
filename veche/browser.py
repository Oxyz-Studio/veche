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
    def __init__(self, viewport=(1440, 900), headless: bool = True, video_dir=None):
        self.w, self.h = viewport
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        kw = {"viewport": {"width": self.w, "height": self.h}}
        if video_dir:
            kw["record_video_dir"] = str(video_dir)
            kw["record_video_size"] = {"width": self.w, "height": self.h}
        self._ctx = self._browser.new_context(**kw)
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

    @staticmethod
    def _key(keys: str) -> str:
        """Normalize a computer-use key string into Playwright's key syntax
        ('enter' -> 'Enter', 'ctrl+a' -> 'Control+A')."""
        alias = {"ctrl": "Control", "control": "Control", "cmd": "Meta", "command": "Meta",
                 "meta": "Meta", "win": "Meta", "alt": "Alt", "option": "Alt", "opt": "Alt",
                 "shift": "Shift", "esc": "Escape", "return": "Enter", "del": "Delete"}
        parts = [p for p in str(keys).replace(" ", "").split("+") if p]
        if not parts:
            return "Enter"
        out = []
        for p in parts:
            lp = p.lower()
            if lp in alias:
                out.append(alias[lp])
            elif len(p) == 1:
                out.append(p.upper() if p.isalpha() else p)
            else:
                out.append(p[:1].upper() + p[1:].lower())   # enter->Enter, tab->Tab, escape->Escape
        return "+".join(out)

    def execute(self, name: str, args: dict) -> bool:
        """Execute a computer-use action. NEVER raises — a single bad action must
        not crash a long capture; returns False on failure."""
        n = (name or "").lower()
        try:
            if "double_click" in n:
                x, y = self._px(args.get("x"), args.get("y")); self.page.mouse.dblclick(x, y)
            elif "click" in n:
                x, y = self._px(args.get("x"), args.get("y")); self.page.mouse.click(x, y)
            elif "type" in n:
                x, y = self._px(args.get("x"), args.get("y"))
                if args.get("x") is not None:
                    self.page.mouse.click(x, y)
                self.page.keyboard.type(args.get("text") or "")
            elif "key" in n or "press" in n or "hotkey" in n:
                self.page.keyboard.press(self._key(args.get("keys") or args.get("text") or "Enter"))
            elif "scroll" in n:
                self.page.mouse.wheel(0, 600 if "down" in str(args).lower() else -600)
            elif "back" in n:
                self.page.go_back()
            elif "forward" in n:
                self.page.go_forward()
            elif "navigate" in n or "open_web" in n:
                if args.get("url"):
                    self.goto(args["url"])
            elif "wait" in n:
                time.sleep(1.5)
            else:
                return False
            try:
                self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            time.sleep(0.4)
            return True
        except Exception:
            try:
                self.page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            return False

    def close(self):
        """Close everything. Returns the recorded video path (if video_dir was set)."""
        video = None
        try:
            video = self.page.video
        except Exception:
            video = None
        try:
            self._ctx.close()      # finalizes the video file
        except Exception:
            pass
        vp = None
        if video is not None:
            try:
                vp = video.path()
            except Exception:
                vp = None
        try:
            self._browser.close(); self._pw.stop()
        except Exception:
            pass
        return vp
