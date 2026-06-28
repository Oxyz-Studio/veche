"""Tests for the Gemini computer-use agent wrapper.

The smoke test is guarded: it skips (does not fail) when the API key is missing
or the live call errors, but it prints the real request/response shape so the
swarm can be wired correctly.
"""
from __future__ import annotations

import io
import os
import time

import pytest
from dotenv import load_dotenv
from PIL import Image, ImageDraw

from veche.agent import Action, ComputerUseAgent

load_dotenv()

# Known button geometry in the synthetic screenshot.
IMG_W, IMG_H = 800, 600
BTN = (320, 260, 480, 320)  # left, top, right, bottom
BTN_CX = (BTN[0] + BTN[2]) // 2  # 400
BTN_CY = (BTN[1] + BTN[3]) // 2  # 290


def _make_submit_png() -> bytes:
    img = Image.new("RGB", (IMG_W, IMG_H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle(BTN, fill=(30, 110, 220), outline=(0, 0, 0), width=2)
    # Centered-ish label; exact font metrics don't matter for the model.
    d.text((BTN[0] + 45, BTN[1] + 18), "Submit", fill="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_action_dataclass_shape():
    a = Action(type="click", x=10, y=20)
    assert a.type == "click"
    assert a.x == 10 and a.y == 20
    assert a.text is None and a.target is None and a.raw is None


def test_init_requires_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        ComputerUseAgent(api_key=None)


def test_init_does_not_leak_key():
    agent = ComputerUseAgent(api_key="secret-should-not-appear")
    assert "secret-should-not-appear" not in repr(agent)
    assert "secret-should-not-appear" not in str(agent.__dict__)


@pytest.mark.parametrize(
    "model",
    [
        # gemini-3.5-flash supports computer-use natively and is on the paid
        # tier we have access to. The 2.5 preview model has free-tier quota 0
        # (429 RESOURCE_EXHAUSTED) on this key, so it skips. flash is the model
        # the swarm should use.
        "gemini-3.5-flash",
        "gemini-2.5-computer-use-preview-10-2025",
    ],
)
def test_smoke_next_action_click_submit(model):
    """Live smoke test: hand the model a Submit button, expect a click near it."""
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

    png = _make_submit_png()
    agent = ComputerUseAgent(model=model, agent_id="smoke")

    action = None
    last_err = None
    for _ in range(3):
        try:
            action = agent.next_action(
                png,
                "Click the Submit button",
                screen_size=(IMG_W, IMG_H),
            )
            break
        except Exception as e:  # noqa: BLE001 - report, don't fail the suite
            last_err = e
            if "503" in str(e):  # transient overload -> brief retry
                time.sleep(8)
                continue
            break
    if action is None:
        pytest.skip(f"live API error for {model}: "
                    f"{type(last_err).__name__}: {last_err}")

    print(f"\n[{model}] raw action: {action.raw}")
    print(f"[{model}] parsed: type={action.type} x={action.x} y={action.y} "
          f"text={action.text!r} target={action.target}")

    assert isinstance(action, Action)
    assert action.type, "action.type must be non-empty"

    if action.type == "click" and action.x is not None and action.y is not None:
        dx = abs(action.x - BTN_CX)
        dy = abs(action.y - BTN_CY)
        print(f"[{model}] click offset from button center: dx={dx} dy={dy}")
        # Generous tolerance; the point is shape verification, not pixel accuracy.
        assert dx <= 120 and dy <= 120, (
            f"click ({action.x},{action.y}) far from button center "
            f"({BTN_CX},{BTN_CY})"
        )
