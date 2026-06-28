# Use VECHE on your own app

VECHE turns any GUI into a **downloadable, tool-agnostic map**. A swarm of
computer-use agents explores the app once and fuses their observations into one
consensus world-model (`veche_map.json`). After that, **any** computer-use tool —
yours — operates the app by *reading the map* instead of re-perceiving every screen
with a frontier model. Reliable through agreement, cheap through reuse.

There are two phases: **map once** (the swarm, needs vision models), then **operate
forever** (your tool, near-free).

---

## 1. Map an app with the swarm

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env        # GEMINI_API_KEY (computer-use), VOYAGE_API_KEY, MONGODB_URI

python scripts/record_swarm.py    # the swarm explores the app (records screens + actions)
python scripts/build_map.py       # node-identity + consensus -> veche_map.json
```

`record_swarm.py` holds the app entry point and the per-agent goals — point it at
your app and describe what to explore. The swarm writes a screen per step (pixels +
the action it took, **including the action args** so the map is replayable). The
build step recognizes the same screen seen by different agents (Voyage multimodal
cosine), keeps a transition only when ≥K agents agree (reliability-weighted
K-agreement), and emits the portable map.

Inspect what was learned:

```bash
python -m veche inspect viz/recording/veche_map.json
python -m veche route   viz/recording/veche_map.json --from n0001 --to n0008
```

How many agents? You don't fix it up front — keep adding agents until **new-screen
discovery dries up** (loop-until-dry). K-agreement also needs ≥2 agents per
transition to commit one, so run a handful and watch the coverage flatten.

---

## 2. Operate the app with YOUR tool

The map is just data. Bring your own executor — anything with `screenshot()` and
`execute(action, args)`:

```python
from veche import Map, operate, VoyageEmbedder

m = Map.load("viz/recording/veche_map.json")
emb = VoyageEmbedder()                       # cheap pixel node-identity (free tier)

# --- option A: let VECHE drive your executor to a goal screen ---
operate(m, my_executor, goal_node="n0008",
        embedder=emb,
        on_step=lambda i, node, edge: print(i, node, "->", edge and edge.action))

# --- option B: drive it yourself, one step at a time ---
node = m.locate(my_executor.screenshot(), emb)   # which screen am I on?
edge = m.next_action(node, goal_node="n0008")     # the agreed next action
my_executor.execute(edge.action, edge.args)       # do it with your tool
```

No frontier computer-use call per screen — each step is one node-identity embedding
plus a map lookup. That is the amortized cost of every reuse after a route is mapped
once.

### Bring your own executor

`veche.browser.Browser` is the reference Playwright implementation. To use a
different tool (Claude/Gemini computer-use, a desktop driver, an existing MCP), wrap
it so it satisfies the `Executor` protocol:

```python
class MyTool:
    def screenshot(self) -> bytes:        # PNG bytes of the current screen
        ...
    def execute(self, action: str, args: dict) -> bool:
        # map VECHE actions to your tool. The action names + args are whatever your
        # capture recorded, e.g. {"x": 412, "y": 233} for "click_at".
        ...
```

`isinstance(MyTool(), veche.Executor)` will be `True`.

---

## The map format (`veche_map.json`)

```jsonc
{
  "meta":  { "app": "OpenEMR demo", "source": "swarm", "screens": 18 },
  "nodes": [ { "id": "n0001", "phash": "...", "embedding": [/* 1024 */], "thumbnail": "a1_00.png" } ],
  "edges": [ { "from_node": "n0001", "to_node": "n0002", "action": "click_at",
               "args": { "x": 412, "y": 233 }, "confirmations": 2, "committed": true } ]
}
```

- `phash` + `embedding` let any tool recognize a screen from pixels alone (no DOM).
- `committed` marks transitions ≥K agents agreed on — the trusted routes.
- `args` are the replayable parameters; present when the capture recorded them.

It is plain data: commit it, share it, or regenerate it as the app changes.
