# Backend / Infra Freeze Baseline

Status: Frozen Baseline

## Scope

This document freezes the backend/infra baseline after:

- Necromancer Lab V2 Showcase Demo
- Real LLM Benchmark v2
- ActorView / Memory isolation
- ActorRuntime + EventDrain flow
- Golden Eval + Telemetry integration

This is a stabilization checkpoint, not a feature-expansion sprint.

## Frozen Contracts

The following contracts are frozen and must not change without a new sprint RFC:

- `GameService.process_chat_turn`
- `GameService.get_state_snapshot` / `GameService.get_session_state`
- `ActorView` contract (visibility + shape)
- `MemoryService` read/write interfaces
- `ActorRuntime` decision boundary
- `DomainEvent` envelope
- `EventDrain` apply semantics
- `core/eval/runner.py` deterministic golden replay behavior
- `scripts/generate_benchmark.py` benchmark report shape

## Runtime Modes

### 1) Playable Mode
- Real gameplay runtime.
- Backend state is source of truth.

### 2) Showcase Mode
- Frontend-guided demo mode for presentation.
- Can include controlled frontend fallback for demo continuity.
- Must not be treated as backend correctness proof.

### 3) Golden / Eval Mode
- Deterministic replay mode for CI/regression.
- Stable scripted assertions and repeatable outputs.

### 4) Benchmark Mode
- Real-LLM measurement mode (manual/opt-in).
- Not a CI gate.
- Artifacts stay local and are not committed.

## Do Not Change Without New Sprint

- LangGraph main topology
- Event protocol (`DomainEvent` types + envelope semantics)
- `GameService` API contract
- `ActorView` visibility contract
- `eval/golden` deterministic runner contract
- Benchmark report schema in `BENCHMARK.md`

## Known Non-Blocking Risks

- Token-level TTFT still needs generation streaming instrumentation.
- Provider token usage may be unavailable; benchmark falls back to estimator values.
- Backend YAML semantic map and frontend TMX/JSON visual map are not strict tile-by-tile twins.
- Content growth should be driven by Content Showcase Sprint 2, not infra expansion.

## Governance Notes

- Freeze does not block bug fixes for regressions.
- Any change that alters frozen contracts requires explicit sprint-level approval.
