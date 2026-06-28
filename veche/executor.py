"""Bring-your-own computer-use tool: the Executor protocol.

VECHE builds the map; YOU operate the app with whatever tool you like — Playwright,
Gemini or Claude computer-use, an existing MCP, a desktop driver. Any object with
these two methods is a valid Executor:

    screenshot() -> bytes          # current screen pixels (PNG)
    execute(action, args) -> bool  # perform one action, return success

``veche.browser.Browser`` is the reference Playwright implementation. To plug in your
own tool, wrap it so ``execute("click_at", {"x": .., "y": ..})`` (and the other
action names your map uses) drive your tool, and ``screenshot()`` returns PNG bytes.
"""
from __future__ import annotations

import typing


@typing.runtime_checkable
class Executor(typing.Protocol):
    def screenshot(self) -> bytes:
        ...

    def execute(self, action: str, args: dict) -> bool:
        ...
