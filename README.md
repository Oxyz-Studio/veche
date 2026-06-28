# VECHE

### A swarm that learns to operate software, and remembers it together.

VECHE is a swarm of computer-use agents that explore a GUI and fuse their noisy
observations into **one shared world-model by consensus**. A small model then
operates the app by **reading the map** instead of re-perceiving the screen every
step, so operation gets reliable through *agreement* and cheap through
*accumulation*: the more a route is used, the less it costs.

It targets the surfaces that have **no API, no DOM, and no first-party agent**,
Citrix-streamed EHRs, mainframe green-screens, where vision is the only door and
a single agent (≈80% reliable, [UI-CUBE](https://arxiv.org/abs/2511.17131)) is not
trustworthy enough for money/compliance/safety work.

> Built at the **AI Engineer World's Fair Hackathon 2026**, Continual Learning track. This repository is the hackathon submission: the demo and the experiments. A reusable, hackathon-free toolkit to run this on your own apps lives in a separate repository.

---

## What works (validated on the real OpenEMR EHR)

| Claim | Result | Where |
|---|---|---|
| **A swarm builds a consensus map** | 2 agents × real screens → 4 nodes, every edge K-agreed & committed | `scripts/explore_swarm.py` |
| **The swarm overrules a misreading agent** | a3 acts on a stale screenshot → reliability-weighted K-agreement keeps the truth, quarantines a3's claim, drops a3's reliability (0.33 vs 0.67) | `scripts/hero_swarm.py` |
| **Operating via the map is cheaper** | same 4-step task, same success: **cold = 28,794 paid tokens (~$0.04)** vs **map-guided = 0 paid tokens** | `scripts/cold_run.py` vs `scripts/mapped_run.py` |
| **Concurrent shared memory** | 5 agents × 100 concurrent appends to one Atlas log → 500, zero loss | `veche/store.py` |
| **Pixel node-identity (no DOM)** | Voyage multimodal cosine separates "same screen, different data" (0.67–0.85) from "different screen" (0.30–0.33) | `veche/node_identity.py` |

The cost saving compounds: the first traversal builds the route, every reuse is
~free, so cost-per-task ≈ `28,794 / (N+1)` tokens → ~11× cheaper at 10 reuses,
~100× at 100.

## How it works

```
 swarm of computer-use agents  ──►  shared append-only log (MongoDB Atlas)
 (Gemini 2.5 Computer Use)            │
        ▲ screenshots                 ▼
        │                    the Veche consolidator  (pure fn of a log snapshot)
   pixel node-identity         1. node-identity   (Voyage multimodal cosine)
   (no DOM → pixels)           2. reliability-weighted K-agreement on edges
        │                      3. decay / versioning
        ▼                                 │
 small operator (Gemma 4)  ◄── reads ── consensus map (nodes → routes)
```

The consensus/aggregation primitive is **cited commodity plumbing** (Dawid–Skene
truth inference; self-consistency; multi-agent debate), not a claimed invention.
The contribution is this stack running live on a noisy, pixels-only GUI with a
measured compounding cost curve.

## Stack

- **Gemini 2.5 Computer Use**, the exploration swarm
- **Gemma 4**, the small operator that reads the map (free)
- **Voyage AI** `voyage-multimodal-3`, pixel node-identity
- **MongoDB Atlas**, the shared append-only log + consolidated graph + vector search

## Watch the demo

`viz/index.html` replays a **real recorded swarm run** (agent screen recordings +
the consensus map, all bound to the captured data). Generate the recording with the
two scripts below, then open the file in **Chrome**. Use **Space** / **← →** to move
through the three acts; on the map you can zoom (wheel), pan (drag), and hover a node
for its details.

## Reproduce it from scratch

```bash
uv venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env        # fill GEMINI_API_KEY, VOYAGE_API_KEY, MONGODB_URI
.venv/bin/python -m pytest -q                 # consolidator + node-identity + Atlas tests
.venv/bin/python scripts/record_swarm.py      # swarm explores OpenEMR -> raw capture (computer-use)
.venv/bin/python scripts/build_map.py         # node-identity + consensus -> viz/recording/recording.json
```

Get keys: [Gemini](https://aistudio.google.com/app/api-keys) (billing on for the
computer-use preview), [Voyage](https://dashboard.voyageai.com), and a free
[MongoDB Atlas](https://cloud.mongodb.com) M0 cluster.

## License

MIT
