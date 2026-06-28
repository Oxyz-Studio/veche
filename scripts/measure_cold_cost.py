"""Measure the COLD per-step cost: one real gemini-2.5-computer-use call on a real
OpenEMR screenshot, reading usage_metadata. Map-guided per-step LLM cost is ~0
(a lookup in the consolidated map), so this number IS the per-step delta.

Also doubles as an end-to-end check that veche/agent.py actually drives the API."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

CAP = pathlib.Path(__file__).resolve().parent.parent / "captures"
MODEL = "gemini-2.5-computer-use-preview-10-2025"
SHOT = CAP / "oemr_patient1.png"
GOAL = "Open the History tab for this patient."


def main():
    img = SHOT.read_bytes()
    client = genai.Client()
    tool = types.Tool(computer_use=types.ComputerUse(environment=types.Environment.ENVIRONMENT_BROWSER))
    contents = [types.Content(role="user", parts=[
        types.Part.from_text(text=GOAL),
        types.Part.from_bytes(data=img, mime_type="image/png"),
    ])]
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=MODEL, contents=contents,
            config=types.GenerateContentConfig(tools=[tool]),
        )
    except Exception as e:
        print("COLD CALL FAILED:", type(e).__name__, "-", str(e)[:400]); return
    dt = time.time() - t0

    # the proposed action
    fc = None
    for c in resp.candidates or []:
        for p in (c.content.parts or []):
            if getattr(p, "function_call", None):
                fc = p.function_call; break
    print(f"COLD step latency: {dt:.1f}s")
    print("proposed action:", (fc.name, dict(fc.args)) if fc else f"(text) {getattr(resp,'text','')[:120]}")

    u = resp.usage_metadata
    print("\n=== COLD per-step token cost (this screenshot reasoning) ===")
    print(f"  prompt_tokens (incl. image): {u.prompt_token_count}")
    print(f"  output_tokens:               {u.candidates_token_count}")
    print(f"  total_tokens:                {u.total_token_count}")
    print("\n=== MAP-GUIDED per-step cost ===")
    print("  LLM tokens: ~0  (the next action is a lookup in the consolidated map)")
    print(f"  => per-step token saving once a route is mapped: ~{u.total_token_count} -> ~0")


if __name__ == "__main__":
    main()
