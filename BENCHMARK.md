# BG3 LLM Agent Real-LLM Benchmark

Status: Baseline

## Executive Summary

- Physics path averages `1 ms`, while generation LLM node averages `1461 ms`.
- ActorView-scoped prompt budget is estimated to be `95.7%` lower than full-state prompts.
- Mechanics/action turns completed with `2` action attempts and `100.0%` success rate.
- This benchmark separates deterministic game-state computation from high-latency LLM narration.

## Run Metadata

- Timestamp: `2026-05-08T07:09:58.234502+00:00`
- Model: `qwen-plus`
- Suite: `benchmark`
- Cases: `4`
- Steps: `4`
- Eval Pass: `4/4`
- Artifacts: `artifacts/benchmarks/real_llm_20260508T070951Z`

## Latency

| Metric | Avg ms | P95 ms | Count |
| --- | ---: | ---: | ---: |
| First Graph Node Update (not token TTFT) | 45 | 59 | 4 |
| TTFT (token-level) | N/A | N/A | 0 |

## Coverage Summary

| Metric | Value |
| --- | ---: |
| DM LLM calls | 1 |
| Generation LLM calls | 1 |
| Physics node samples | 2 |
| Action attempts | 2 |

## Node Breakdown

| Node Class | Avg ms | P95 ms | Count |
| --- | ---: | ---: | ---: |
| dm_router | 184 | 1464 | 8 |
| physics | 1 | 1 | 2 |
| generation | 1461 | 1461 | 1 |
| actor_runtime | 2 | 4 | 3 |
| event_drain | 5 | 7 | 2 |
| other | 468 | 1430 | 6 |

## Token Economy

| Metric | Provider Usage | Estimated |
| --- | ---: | ---: |
| Avg Prompt Tokens | Unavailable | 171.8 |
| Avg Output Tokens | Unavailable | 50.5 |
| Avg Total Tokens | Unavailable | 222.2 |

## Architecture Comparison

| Metric | Optimized Graph Agent | Naive Monolithic Agent | Improvement |
| --- | ---: | ---: | ---: |
| LLM Calls / Turn | 1 | 1 | +0.0% |
| Avg Turn Latency | 1486 | 3067 | +51.5% |
| Prompt Tokens / Turn (est.) | 172 | 3950 | +95.7% |
| Physics Compute | 1 | N/A | deterministic code path |
| Action Success Rate | 100.0% | 100.0% | same benchmark actions |

## Prompt Budget Comparison (Estimated)

| Case | Optimized Scoped Prompt Tokens (est.) | Naive Full-State Tokens (est.) | Reduction |
| --- | ---: | ---: | ---: |
| benchmark_dm_actor_runtime_turn | 165 | 4020 | -95.9% |
| benchmark_gribbo_generation_turn | 147 | 3877 | -96.2% |
| benchmark_mechanics_physics_turn | 204 | 4057 | -95.0% |
| benchmark_physical_action_turn | 171 | 3845 | -95.6% |

## Routing Efficiency

| Path | Turns | Avg Turn Latency | Core Node Latency | LLM Calls / Turn | Prompt Tokens / Turn | Description |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Mechanics-only | 1 | 1479 | 1 | 0 | 171 | deterministic movement/interaction |
| ActorRuntime | 2 | 1482 | 2 | 1.5 | 184 | template/runtime companion response |
| Generation LLM | 1 | 1503 | 1461 | 1 | 147 | rich freeform NPC dialogue |

## Baseline Criteria

| Criterion | Required | Actual | OK |
| --- | --- | --- | --- |
| Eval pass rate | >= 80% | 100.0% | yes |
| DM LLM calls | > 0 | 1 | yes |
| Generation LLM calls | > 0 | 1 | yes |
| Generation node samples | > 0 | 1 | yes |
| Physics node samples | > 0 | 2 | yes |
| Action attempts | > 0 | 2 | yes |
| Action success rate | >= 80% | 100.0% | yes |

## Action Success

| Metric | Value |
| --- | ---: |
| Attempts | 2 |
| Successes | 2 |
| Unknown | 0 |
| Success Rate | 100.0% |

## Per-Case Details

| Case | Path | OK | Turn ms | LLM Calls | Optimized Prompt | Naive Prompt | Reduction | Action |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| benchmark_dm_actor_runtime_turn | ActorRuntime | yes | 1541 | 2 | 165 | 4020 | -95.9% | none |
| benchmark_gribbo_generation_turn | Generation LLM | yes | 1503 | 1 | 147 | 3877 | -96.2% | none |
| benchmark_mechanics_physics_turn | ActorRuntime | yes | 1423 | 1 | 204 | 4057 | -95.0% | success |
| benchmark_physical_action_turn | Mechanics-only | yes | 1479 | 0 | 171 | 3845 | -95.6% | success |

## Case Results

| Case | OK | Steps | Failed Steps | Error |
| --- | --- | ---: | --- | --- |
| benchmark_dm_actor_runtime_turn | yes | 1/1 | - | - |
| benchmark_gribbo_generation_turn | yes | 1/1 | - | - |
| benchmark_mechanics_physics_turn | yes | 1/1 | - | - |
| benchmark_physical_action_turn | yes | 1/1 | - | - |

## Notes

- This is a real LLM benchmark, not the deterministic CI golden replay runner.
- Current graph stream is node-update streaming; strict token-level TTFT requires generation LLM astream instrumentation.
- Benchmark results can vary by provider, network conditions, and model load.
- Provider Usage is real LLM token usage returned by the provider or LangChain metadata.
- Token counts are provider usage when available; otherwise estimated using deterministic local estimator.
- Naive latency is estimated from observed LLM latency plus prompt-size penalty; it is not a second live LLM run.
- Turn latency includes graph orchestration and session initialization; core node latency isolates the routed execution path.
- Provider or LangChain response did not expose token usage metadata for this run.
