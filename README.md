# BG3 LLM Agent

A playable AI CRPG vertical slice and LangGraph-powered agentic narrative engine.

LLMs handle intent and character expression. Deterministic systems handle state mutation,
memory isolation, event consistency, regression testing, and performance visibility.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-orange)
![FastAPI](https://img.shields.io/badge/API-FastAPI-green)
![Golden Eval](https://img.shields.io/badge/Eval-Golden_Replay-purple)
![Benchmark](https://img.shields.io/badge/Benchmark-Real_LLM-violet)

BG3_LLM_Agent is a playable AI CRPG vertical slice and an agentic narrative engine infrastructure prototype.

Core positioning:

> A LangGraph-powered AI CRPG narrative engine where LLMs handle intent and expression,
> while deterministic game systems own state mutation, memory isolation, event consistency,
> testing, and performance visibility.

## What This Project Demonstrates

- Multi-agent companion dialogue with isolated actor views.
- Deterministic physical actions through DomainEvent and EventDrain.
- Skill checks, traps, hidden lore, item transfer, and party reactions in one shared runtime.
- Golden replay evals for regression safety without real LLM calls.
- Real LLM benchmark coverage with architecture comparison and prompt budget estimates.
- A playable Necromancer Lab V2 browser demo with Showcase Mode overlays.
- FastAPI and CLI frontends sharing one GameService orchestration layer.

## Playable Vertical Slice: Necromancer Lab V2

The current public demo is a compact AI CRPG vertical slice:

```text
A -> B -> C -> D -> Exit
safe room -> poison corridor -> hidden study -> Gribbo lab -> final exit
```

It is intentionally small, but it exercises the backend in ways that matter:

- perception and trap awareness on entry
- hidden lore and diary reading branches
- companion agenda, disagreement, and party banter
- item transactions and key-gated escape flow
- state diff and director trace overlays in Showcase Mode

In practice, the slice covers the path implied by the shipped golden cases:

- Act 1: trap perception and lab intro awareness
- Act 2: necromancer diary success and failure branches
- Act 3: Gribbo negotiation, siding with or rebuking Astarion
- Act 4: key retrieval, door opening, and escape resolution

## Architecture Overview

```text
Web UI / CLI / FastAPI
        |
        v
GameService
        |
        v
LangGraph State Machine
  input -> dm_router -> mechanics/physics -> actor_runtime/generation -> event_drain
        |
        v
GameState Checkpoint + Memory + Eval Telemetry
```

`GameService` is the application entrypoint. It owns session lifecycle, Genesis/reset flow, state snapshotting, mode-specific orchestration, and transport-neutral response shaping.

LangGraph owns runtime routing. The current graph includes dedicated paths for input, DM routing, dialogue/lore handling, mechanics, actor invocation, event draining, narration, and generation. This means the backend is no longer a single prompt loop; it is a deterministic state machine with LLM-assisted branches.

`ActorView` constrains what each NPC can see. Actors do not read raw global state directly. They receive a scoped view with filtered flags, visible entities, visible history, visible environment objects, and actor-scoped memory snippets.

`DomainEvent` and `EventDrain` own state write-back. LLMs and ActorRuntime can propose actions, but inventory changes, memory updates, affection deltas, negotiation outcomes, and world flags are committed through the event pipeline.

Golden Eval and the real benchmark both reuse the same service layer and core graph contracts. That is the main backend value of the repository: gameplay, replay safety, and benchmark visibility all sit on the same architecture rather than separate demo-only code paths.

## Backend Infrastructure Highlights

### ActorView / Visibility

- NPCs do not consume unrestricted global state.
- Each actor receives a scoped `ActorView` with `self_state`, public peer views, filtered flags, visible history, public events, and actor-scoped memory snippets.
- Visibility policy is a backend contract, not a prompt convention.

### MemoryService

- Memory is separated into actor-private, party-shared, and world retrieval scopes.
- `MemoryService.retrieve_for_actor(...)` and `retrieve_for_director(...)` keep actor isolation explicit.
- This provides a backend-ready base for future RAG expansion without collapsing private memory boundaries.

### ActorRuntime

- `ActorRuntime` can emit deterministic companion responses and event decisions without always paying for a large generation prompt.
- It is a good fit for gift acceptance or rejection, relationship reactions, private memory updates, party choice commentary, and other structured companion behavior.
- This keeps simple companion logic cheap, testable, and replayable.

### DomainEvent / EventDrain

- LLMs may suggest actions, but world state changes land through the event pipeline.
- Item transfers, affection updates, memory writes, negotiation outcomes, combat flags, and public logs all converge on `DomainEvent` and `event_drain`.
- This is the main consistency boundary for the backend.

### Golden Eval

- Golden Eval is deterministic replay, not a real-LLM smoke test.
- It exists to protect routing, event application, actor visibility, memory isolation, and scenario regressions.
- The runner lives in `core/eval/runner.py` and uses cases under `evals/golden/`.

### Real LLM Benchmark

- Real benchmark runs are manual and opt-in.
- They are designed to measure real provider latency, graph routing behavior, action success, and prompt-budget deltas against a naive monolithic baseline.
- See [BENCHMARK.md](BENCHMARK.md) for the latest report.

## Runtime Modes

| Mode | Purpose | Uses Real LLM | Deterministic | Entry |
| --- | --- | --- | --- | --- |
| Playable | Real gameplay runtime | yes | no | Web UI / CLI / API |
| Showcase | Technical demo overlays and guided presentation | optional | no | `qa_showcase=1` |
| Golden Eval | Regression replay baseline | no | yes | `python -m core.eval.runner --suite golden` |
| Benchmark | Real LLM performance report | yes | no | `python scripts/generate_benchmark.py` |

Notes:

- Showcase Mode may include frontend-guided continuity helpers for presentation. It should not be treated as proof that the backend alone completed the full loop.
- Benchmark mode is not a default CI gate.
- Golden Eval is the regression truth source for deterministic backend behavior.

## Benchmark v2 Summary

See [BENCHMARK.md](BENCHMARK.md) for the latest full run.

Current baseline highlights:

- physics core node: about `1 ms`
- generation LLM node: about `1461 ms`
- first graph node update: about `45 ms` average
- estimated scoped prompt reduction: about `95.7%`
- action success: `100.0%` on the benchmark suite

Important interpretation notes:

- Provider token usage was unavailable in the referenced run, so prompt-token comparisons are estimated rather than provider-billed totals.
- Naive monolithic latency is an architecture comparison estimate, not a second live billing run.
- Token-level TTFT is still unavailable in the current node-update stream path and is reported as `N/A`.

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure `.env`:

```bash
BAILIAN_API_KEY=...
DASHSCOPE_API_BASE=...
MODEL_NAME=qwen-plus
```

Start the API and web UI:

```bash
python server.py
```

Open the playable demo:

```text
http://127.0.0.1:8000/web_ui/?map_id=necromancer_lab
```

Open Showcase Mode:

```text
http://127.0.0.1:8000/web_ui/?map_id=necromancer_lab&qa_showcase=1&qa_no_idle=1
```

Run the CLI:

```bash
python main.py
```

## Testing / Eval / Benchmark

Frontend tests:

```bash
npm test -- --runInBand
```

Python tests:

```bash
pytest -q
```

Golden replay:

```bash
python -m core.eval.runner --suite golden
```

Unified local check:

```bash
make check
```

Benchmark dry run:

```bash
python scripts/generate_benchmark.py --dry-run --max-cases 4
```

Real benchmark run:

```bash
python scripts/generate_benchmark.py --max-cases 4
```

Benchmark guidance:

- Real benchmark requires an API key and incurs provider cost.
- Do not treat benchmark output as a deterministic CI gate.
- Use Golden Eval for replay-safe regression protection.

## Repository Map

```text
core/application/      GameService orchestration
core/graph/            LangGraph state machine, nodes, and subgraphs
core/actors/           ActorView, ActorRuntime, registry, visibility contracts
core/events/           DomainEvent models, apply path, and event store
core/memory/           Memory scopes, retrieval, distillation, and service layer
core/eval/             Golden replay runner, assertions, telemetry, reporting
scripts/               Benchmark and simulation tooling
evals/golden/          deterministic regression cases
evals/benchmark/       real LLM performance cases
web_ui/                browser demo and Showcase Mode UI
data/maps/             YAML backend maps and TMX visual maps
characters/            YAML character definitions and prompts
docs/                  governance, freeze contracts, and design records
```

## Governance / Freeze Docs

- [Backend / Infra Freeze](docs/backend_infra_freeze.md)
- [Real LLM Benchmark](BENCHMARK.md)
- [V1 Contract Freeze](docs/v1_contract_freeze.md)
- [V1.3 Capability Freeze](docs/v1_3_capability_freeze.md)
- [Content Sprint 1 Playable Demo Freeze](docs/content_sprint_1_playable_demo_freeze.md)

More governance docs are under [`docs/`](docs/).

## Current Scope / Non-goals

This is not a full CRPG. It is a vertical slice focused on agentic narrative infrastructure.

Frozen backend contracts:

- GameService API
- ActorView, MemoryService, and ActorRuntime
- DomainEvent and EventDrain
- Golden Eval runner
- Benchmark report schema

Known future work:

- token-level TTFT via generation streaming
- provider token usage extraction when available
- richer combat presentation
- more content encounters driven by agentic narrative design
- optional tighter YAML/TMX map synchronization
