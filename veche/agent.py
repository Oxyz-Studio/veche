"""Gemini Computer-Use agent wrapper for the VECHE swarm.

Wraps the google-genai SDK's computer-use tool so a swarm worker can hand a
screenshot + a goal to a Gemini model and get back a single normalized UI
``Action`` (click / type / scroll / keypress / ...).

Verified against google-genai 2.10.0 with model
``gemini-2.5-computer-use-preview-10-2025``. The computer-use tool is configured
as ``types.Tool(computer_use=types.ComputerUse(environment=...))`` and the model
replies with a ``function_call`` part whose ``name`` is a predefined action
(e.g. ``click_at``) and whose ``args`` carry coordinates normalized to 0-999.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from google import genai
from google.genai import types

# Coordinate space used by the computer-use model: x/y are integers in [0, 999].
COORD_SCALE = 1000

# Map the model's predefined function names onto the swarm's canonical action
# vocabulary. The 2.5 computer-use model emits names like ``click_at`` /
# ``type_text_at``; newer models may emit ``click`` / ``type``. We accept both.
_ACTION_ALIASES = {
    "click_at": "click",
    "click": "click",
    "double_click_at": "double_click",
    "double_click": "double_click",
    "hover_at": "hover",
    "type_text_at": "type",
    "type": "type",
    "scroll_document": "scroll",
    "scroll_at": "scroll",
    "scroll": "scroll",
    "key_combination": "keypress",
    "press_key": "keypress",
    "keypress": "keypress",
    "drag_and_drop": "drag",
    "navigate": "navigate",
    "open_web_browser": "navigate",
    "wait_5_seconds": "wait",
    "wait": "wait",
}


@dataclass
class Action:
    """A single normalized UI action proposed by the model.

    Coordinates ``x`` / ``y`` are denormalized to the supplied screen pixel size
    when ``screen_size`` is passed to :meth:`ComputerUseAgent.next_action`;
    otherwise they remain in the model's native 0-999 space.
    """

    type: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    target: str | None = None
    raw: dict | None = None


class ComputerUseAgent:
    """Thin wrapper around a Gemini computer-use model for one swarm worker."""

    def __init__(
        self,
        model: str = "gemini-2.5-computer-use-preview-10-2025",
        agent_id: str = "a1",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.agent_id = agent_id
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set and no api_key provided")
        # Never log or repr the key.
        self._client = genai.Client(api_key=key)

    def _tool(self) -> types.Tool:
        return types.Tool(
            computer_use=types.ComputerUse(
                environment=types.Environment.ENVIRONMENT_BROWSER,
            )
        )

    def next_action(
        self,
        screenshot: bytes,
        goal: str,
        history: list | None = None,
        screen_size: tuple[int, int] | None = None,
    ) -> Action:
        """Ask the model for the next UI action given a screenshot + goal.

        ``screenshot`` is raw PNG bytes. ``history`` is an optional list of prior
        ``types.Content`` turns (or plain strings) to give the model context.
        ``screen_size`` (width, height) denormalizes 0-999 coords into pixels.
        """
        parts = [
            types.Part.from_text(text=goal),
            types.Part.from_bytes(data=screenshot, mime_type="image/png"),
        ]
        contents: list = []
        if history:
            contents.extend(history)
        contents.append(types.Content(role="user", parts=parts))

        config = types.GenerateContentConfig(tools=[self._tool()])

        resp = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        return self._parse(resp, screen_size)

    def _parse(self, resp, screen_size: tuple[int, int] | None) -> Action:
        fc = self._extract_function_call(resp)
        if fc is None:
            # No tool call -> model returned text (e.g. a question / completion).
            text = getattr(resp, "text", None)
            return Action(type="text", text=text, raw={"text": text})

        name = fc.name or ""
        args = dict(fc.args or {})
        canonical = _ACTION_ALIASES.get(name, name)

        x = args.get("x")
        y = args.get("y")
        if x is not None and y is not None and screen_size is not None:
            w, h = screen_size
            x = int(round(x / COORD_SCALE * w))
            y = int(round(y / COORD_SCALE * h))

        # Text payload may live under a few different arg keys depending on action.
        text = args.get("text")
        if text is None:
            text = args.get("keys") or args.get("query") or args.get("url")

        # Live observation (gemini-3.5-flash): each function_call also carries an
        # ``intent`` string and may carry a ``safety_decision`` dict. When the
        # model wants confirmation it sets
        # safety_decision.decision == "require_confirmation"; a swarm runner must
        # acknowledge it (send back a FunctionResponse) before the action runs.
        raw = {
            "name": name,
            "args": args,
            "intent": args.get("intent"),
            "safety_decision": args.get("safety_decision"),
        }

        return Action(
            type=canonical,
            x=x,
            y=y,
            text=text,
            target=name,
            raw=raw,
        )

    @staticmethod
    def _extract_function_call(resp):
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    return fc
        return None
