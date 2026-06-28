"""COLD computer-use loop on the real OpenEMR demo: the model drives the task from
scratch, re-perceiving every step. Measures steps + tokens. Saves the action trace
so the MAP-GUIDED replay can reuse the discovered route.
"""
import sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
from veche.browser import Browser

MODEL = "gemini-2.5-computer-use-preview-10-2025"
GOAL = "Open the patient's History tab, then their Issues tab, then their Ledger tab — in that order."
MAX_STEPS = 10


def extract_fc(resp):
    for c in resp.candidates or []:
        for p in (c.content.parts or []):
            if getattr(p, "function_call", None):
                return p.function_call, c.content
    return None, (resp.candidates[0].content if resp.candidates else None)


def main():
    client = genai.Client()
    cfg = types.GenerateContentConfig(
        tools=[types.Tool(computer_use=types.ComputerUse(environment=types.Environment.ENVIRONMENT_BROWSER))]
    )
    br = Browser(headless=True)
    print("login + open patient dashboard...")
    br.login_openemr()
    br.open_patient(1)

    shot = br.screenshot()
    contents = [types.Content(role="user", parts=[
        types.Part.from_text(text=GOAL),
        types.Part.from_bytes(data=shot, mime_type="image/png"),
    ])]
    total_in = total_out = steps = 0
    trace = []
    for i in range(MAX_STEPS):
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
        except Exception as e:
            print("API error:", type(e).__name__, "-", str(e)[:300]); break
        u = resp.usage_metadata
        total_in += u.prompt_token_count or 0
        total_out += u.candidates_token_count or 0
        fc, model_content = extract_fc(resp)
        if fc is None:
            print("  model returned no action (done?):", (getattr(resp, "text", "") or "")[:140]); break
        steps += 1
        print(f"  step {steps}: {fc.name} args={dict(fc.args)}  [cum_tokens={total_in + total_out}]")
        trace.append({"name": fc.name, "args": dict(fc.args)})
        br.execute(fc.name, dict(fc.args))
        new_shot = br.screenshot()
        contents.append(model_content)
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=fc.name, response={"url": br.url()}),
            types.Part.from_bytes(data=new_shot, mime_type="image/png"),
        ]))

    print(f"\n=== COLD RESULT ===\n  steps={steps}  input_tokens={total_in}  output_tokens={total_out}  TOTAL={total_in + total_out}")
    (pathlib.Path(__file__).resolve().parent.parent / "captures" / "cold_trace.json").write_text(json.dumps(trace, indent=2))
    print("  trace saved -> captures/cold_trace.json")
    br.close()


if __name__ == "__main__":
    main()
