"""DEEP swarm capture (computer-use only, NO Voyage) — ROBUST.

One fresh browser PER AGENT -> one .webm screen recording per agent. Saves
raw.json INCREMENTALLY after each agent (a stop loses nothing) and RESUMES
(re-running skips agents already captured). Node-identity + consolidation happen
later in build_map.py.

Output: viz/recording/raw.json + frames/*.png + videos/*.webm
"""
import sys, pathlib, json, time, shutil
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
from veche.browser import Browser, OPENEMR

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = ROOT / "viz" / "recording"
FRAMES, VIDEOS = REC / "frames", REC / "videos"
MODEL = "gemini-2.5-computer-use-preview-10-2025"
PRICE_IN, PRICE_OUT = 1.25 / 1e6, 10.0 / 1e6
MAX_STEPS = 12
NO_HARM = " Visit as many DISTINCT screens as you can. Do NOT submit forms, save, or delete anything — only navigate."

AGENTS = [
    ("a1", "patient:1", "Explore this patient's chart in depth: open the History, Issues, Ledger, Documents, Transactions and Report tabs."),
    ("a2", "main", "From the top menu, open the Calendar, then the Messages center, then the Flow board."),
    ("a3", "main", "From the top menu, open Fees, then Reports — visit a few different report screens."),
    ("a4", "main", "From the top menu, open the Patient/Client finder, then open two different patients' charts."),
    ("a5", "main", "From the top menu, open Procedures, then Administration, then Miscellaneous."),
    ("a6", "patient:2", "Explore this patient's Documents, Transactions, Ledger and Report tabs."),
    ("a7", "main", "Open the Calendar, then the add-appointment screen (do not save), then the patient finder."),
    ("a8", "patient:3", "Open this patient's History and Issues tabs and the Demographics edit screen (do not save)."),
]


def extract_fc(resp):
    for c in resp.candidates or []:
        for p in (c.content.parts or []):
            if getattr(p, "function_call", None):
                return p.function_call, c.content
    return None, (resp.candidates[0].content if resp.candidates else None)


def goto_start(br, start):
    if start.startswith("patient:"):
        br.open_patient(int(start.split(":")[1]))
    else:
        br.goto(f"{OPENEMR}/interface/main/main_screen.php?auth=login&site=default")
        time.sleep(1.5)


def explore_one(client, cfg, aid, start, goal):
    """Run one agent in its own browser (with video) and return (agent_meta, events)."""
    br = Browser(headless=True, video_dir=VIDEOS)
    events, t0 = [], time.time()
    try:
        br.login_openemr()
        goto_start(br, start)
        shot = br.screenshot()
        frames = [f"{aid}_00.png"]; (FRAMES / frames[0]).write_bytes(shot)
        contents = [types.Content(role="user", parts=[
            types.Part.from_text(text=goal + NO_HARM), types.Part.from_bytes(data=shot, mime_type="image/png")])]
        for step in range(MAX_STEPS):
            s = time.time()
            try:
                resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            except Exception as e:
                print("  api error:", str(e)[:120]); break
            lat = time.time() - s
            u = resp.usage_metadata
            toks = (u.prompt_token_count or 0) + (u.candidates_token_count or 0)
            cost = (u.prompt_token_count or 0) * PRICE_IN + (u.candidates_token_count or 0) * PRICE_OUT
            fc, model_content = extract_fc(resp)
            cur = frames[-1]
            if fc is None:
                events.append({"agent": aid, "step": step, "t": round(time.time() - t0, 2), "frame": cur,
                               "action": "done", "intent": (getattr(resp, "text", "") or "")[:90],
                               "tokens": toks, "latency": round(lat, 1), "cost": round(cost, 4)})
                print(f"  step {step}: done"); break
            args = dict(fc.args)
            events.append({"agent": aid, "step": step, "t": round(time.time() - t0, 2), "frame": cur,
                           "action": fc.name, "args": {k: v for k, v in args.items() if k != "intent"},
                           "intent": (args.get("intent") or "")[:90],
                           "tokens": toks, "latency": round(lat, 1), "cost": round(cost, 4)})
            print(f"  step {step}: {fc.name} [{toks} tok, {lat:.1f}s]")
            br.execute(fc.name, args)
            shot = br.screenshot()
            nf = f"{aid}_{step+1:02d}.png"; (FRAMES / nf).write_bytes(shot); frames.append(nf)
            contents.append(model_content)
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=fc.name, response={"url": br.url()}),
                types.Part.from_bytes(data=shot, mime_type="image/png")]))
    finally:
        vp = br.close()
    video = f"{aid}.webm"
    if vp and pathlib.Path(vp).exists():
        shutil.move(vp, VIDEOS / video)
    else:
        video = None
    return {"id": aid, "start": start, "goal": goal, "frames": frames, "video": video}, events


def main():
    FRAMES.mkdir(parents=True, exist_ok=True); VIDEOS.mkdir(parents=True, exist_ok=True)
    raw = json.loads((REC / "raw.json").read_text()) if (REC / "raw.json").exists() else {"agents": [], "events": []}
    done = {a["id"] for a in raw["agents"]}
    if done:
        print("resuming — already captured:", sorted(done))

    client = genai.Client()
    cfg = types.GenerateContentConfig(
        tools=[types.Tool(computer_use=types.ComputerUse(environment=types.Environment.ENVIRONMENT_BROWSER))])

    for aid, start, goal in AGENTS:
        if aid in done:
            continue
        print(f"[{aid}] {start}: {goal}")
        meta, events = explore_one(client, cfg, aid, start, goal)
        raw["agents"].append(meta); raw["events"].extend(events)
        (REC / "raw.json").write_text(json.dumps(raw, indent=2))   # incremental checkpoint
        print(f"  -> saved {aid} ({len(meta['frames'])} frames, video={meta['video']})")

    tot = sum(e["tokens"] for e in raw["events"]); cost = sum(e["cost"] for e in raw["events"])
    print(f"\nCAPTURE COMPLETE: {len(raw['agents'])} agents, {len(raw['events'])} events, "
          f"{len(list(FRAMES.glob('*.png')))} frames, {len(list(VIDEOS.glob('*.webm')))} videos, "
          f"{tot} tokens ~${cost:.2f}")


if __name__ == "__main__":
    main()
