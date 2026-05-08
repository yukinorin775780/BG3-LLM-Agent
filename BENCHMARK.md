# BG3 LLM Agent Real-LLM Benchmark

Status: Baseline

## Run Metadata

- Timestamp: `2026-05-08T03:13:55.959460+00:00`
- Model: `qwen-plus`
- Suite: `benchmark`
- Cases: `4`
- Steps: `4`
- Eval Pass: `4/4`
- Artifacts: `artifacts/benchmarks/real_llm_20260508T031349Z`

## Latency

| Metric | Avg ms | P95 ms | Count |
| --- | ---: | ---: | ---: |
| First Graph Node Update (not token TTFT) | 45 | 56 | 4 |
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
| dm_router | 182 | 1447 | 8 |
| physics | 1 | 1 | 2 |
| generation | 1545 | 1545 | 1 |
| actor_runtime | 3 | 4 | 3 |
| event_drain | 6 | 7 | 2 |
| other | 472 | 1494 | 6 |

## Token Economy

| Metric | Value |
| --- | ---: |
| Avg Prompt Tokens | Unavailable |
| Avg Output Tokens | Unavailable |
| Avg Total Tokens | Unavailable |

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
- Provider or LangChain response did not expose token usage metadata for this run.
