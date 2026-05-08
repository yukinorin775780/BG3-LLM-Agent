from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core.eval.assertions import AssertionReport
from core.eval.models import EvalStep
from scripts import generate_benchmark as bench


def _write_case(eval_dir: Path) -> Path:
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / "sample_case.yaml"
    path.write_text(
        """
session:
  id: sample_case
  map_id: necromancer_lab
determinism:
  strict: false
steps:
  - id: step_1
    user_input: hello
    intent: chat
expected: {}
""".strip(),
        encoding="utf-8",
    )
    return path


class _FakeBenchmarkService:
    def __init__(self, *args, **kwargs) -> None:
        self.db_path = kwargs.get("db_path")

    async def process_chat_turn(self, **kwargs):
        stream_handler = kwargs.get("stream_handler")
        if stream_handler is not None:
            await stream_handler("generation", {"ok": True})
        return {"responses": [{"speaker": "dm", "text": "ok"}], "journal_events": []}

    async def get_state_snapshot(self, **kwargs):
        return {"game_state": {"messages": [object()], "ok": True}}


def test_percentile_uses_nearest_rank():
    assert bench.percentile([10, 20, 30, 40], 0) == 10
    assert bench.percentile([10, 20, 30, 40], 50) == 20
    assert bench.percentile([10, 20, 30, 40], 95) == 40
    assert bench.percentile([], 95) is None


@pytest.mark.parametrize(
    ("node_name", "expected"),
    [
        ("dm_analyze_intent", "dm_router"),
        ("mechanics_resolution", "physics"),
        ("generate_dialogue", "generation"),
        ("actor_invocation", "actor_runtime"),
        ("event_drain", "event_drain"),
        ("misc", "other"),
    ],
)
def test_node_name_classification(node_name, expected):
    assert bench.classify_node_name(node_name) == expected


def test_token_usage_aggregation_from_fake_telemetry():
    events = [
        {
            "event_name": "llm_call",
            "payload": {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        },
        {
            "event_name": "llm_call",
            "payload": {"token_usage": {"input_tokens": 6, "output_tokens": 4}},
        },
        {"event_name": "llm_call", "payload": {}},
    ]

    economy = bench.collect_token_economy(events, step_count=2)

    assert economy["avg_prompt_tokens"] == 8
    assert economy["avg_completion_tokens"] == 4.5
    assert economy["avg_total_tokens"] == 12.5
    assert economy["llm_call_count"] == 3
    assert economy["missing_usage_count"] == 1
    assert economy["zero_usage_call_count"] == 0
    assert economy["usage_available"] is True


def test_real_provider_zero_token_usage_is_unavailable():
    events = [
        {
            "event_name": "llm_call",
            "payload": {
                "component": "dm",
                "provider": "openai",
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        }
    ]

    economy = bench.collect_token_economy(events, step_count=1)

    assert economy["usage_available"] is False
    assert economy["zero_usage_call_count"] == 1
    assert economy["missing_usage_count"] == 0


def test_template_runtime_zero_token_usage_is_not_missing_or_zero_usage():
    events = [
        {
            "event_name": "llm_call",
            "payload": {
                "component": "actor_runtime",
                "provider": "template_runtime",
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        }
    ]

    economy = bench.collect_token_economy(events, step_count=1)

    assert economy["usage_available"] is False
    assert economy["zero_usage_call_count"] == 0
    assert economy["missing_usage_count"] == 0


def test_action_attempt_success_and_unknown_aggregation():
    success_step = EvalStep(
        id="loot",
        user_input="/loot ancient_key",
        intent="chat",
        expected={"state": {"equals": {"game_state.player_inventory.ancient_key": 1}}},
    )
    unknown_step = EvalStep(id="move", user_input="move north", intent="MOVE")
    report = AssertionReport()

    success = bench.infer_action_outcome(
        step=success_step,
        response={},
        telemetry_events=[],
        assertion_report=report,
    )
    unknown = bench.infer_action_outcome(
        step=unknown_step,
        response={},
        telemetry_events=[],
        assertion_report=report,
    )

    assert success == (True, True, False)
    assert unknown == (True, False, True)
    reliability = bench.collect_action_reliability(
        [
            bench.StepMetric("case", "loot", ok=True, action_attempt=True, action_success=True),
            bench.StepMetric("case", "move", ok=False, action_attempt=True, action_unknown=True),
        ]
    )
    assert reliability["attempts"] == 2
    assert reliability["successes"] == 1
    assert reliability["unknown"] == 1
    assert reliability["success_rate"] == 50


def test_default_eval_dir_is_benchmark_suite():
    args = bench._build_parser().parse_args([])

    assert args.suite == "benchmark"
    assert args.eval_dir == "evals/benchmark"


def test_selected_benchmark_case_can_produce_action_attempts():
    cases = bench.select_cases(
        suite="benchmark",
        eval_dir="evals/benchmark",
        case_selector="physical_action_turn",
    )

    assert len(cases) == 1
    assert any(bench.is_action_attempt(step) for step in cases[0].steps)


def test_experimental_run_does_not_masquerade_as_baseline(tmp_path):
    result = bench.BenchmarkResult(
        suite="benchmark",
        model="test-model",
        timestamp="2026-05-08T00:00:00+00:00",
        run_dir=tmp_path / "run",
        cases=[
            bench.CaseMetric("case_1", "case_1.yaml", False, 1, 1),
            bench.CaseMetric("case_2", "case_2.yaml", False, 1, 1),
            bench.CaseMetric("case_3", "case_3.yaml", False, 1, 1),
        ],
        steps=[],
        telemetry_events=[],
    )

    markdown = bench.render_markdown_report(result)

    assert bench.benchmark_status(result) == "Experimental"
    assert "Status: Experimental" in markdown
    assert "should not be presented as a formal performance baseline" in markdown
    assert "Status: Baseline" not in markdown


def test_empty_case_expected_and_all_steps_ok_makes_case_ok(tmp_path):
    eval_dir = tmp_path / "evals"
    _write_case(eval_dir)
    case = bench.select_cases(suite="benchmark", eval_dir=eval_dir)[0]
    sink = bench.JsonlTelemetrySink(telemetry_path=tmp_path / "telemetry.jsonl")

    with bench.telemetry_scope(sink):
        case_metric, step_metrics = asyncio.run(
            bench.run_benchmark_case(
                case=case,
                service=_FakeBenchmarkService(),
                sink=sink,
                run_id="unit",
                case_artifacts_dir=tmp_path,
            )
        )

    assert [step.ok for step in step_metrics] == [True]
    assert case.expected == {}
    assert case_metric.ok is True
    assert case_metric.case_assertions["ok"] is True
    assert (tmp_path / "final_state.json").exists()


def test_summary_json_contains_case_results_for_fake_run(tmp_path, monkeypatch):
    eval_dir = tmp_path / "evals"
    _write_case(eval_dir)
    monkeypatch.setattr(bench.settings, "API_KEY", "test-key")
    monkeypatch.setattr(bench.settings, "BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(bench.settings, "MODEL_NAME", "test-model")

    import core.application.game_service as game_service_module

    monkeypatch.setattr(game_service_module, "GameService", _FakeBenchmarkService)
    result = asyncio.run(
        bench.run_benchmark_suite(
            bench.BenchmarkOptions(eval_dir=eval_dir, artifacts_dir=tmp_path / "artifacts")
        )
    )
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))

    assert summary["passed_count"] == 1
    assert summary["case_results"][0]["case_id"] == "sample_case"
    assert summary["case_results"][0]["ok"] is True
    assert summary["case_results"][0]["case_assertions"]["ok"] is True


def test_baseline_status_when_all_cases_ok_and_coverage_satisfied(tmp_path):
    result = bench.BenchmarkResult(
        suite="benchmark",
        model="test-model",
        timestamp="2026-05-08T00:00:00+00:00",
        run_dir=tmp_path / "run",
        cases=[bench.CaseMetric("case", "case.yaml", True, 1, 1)],
        steps=[bench.StepMetric("case", "step", True, action_attempt=True, action_success=True)],
        telemetry_events=[
            {"event_name": "node_finished", "payload": {"node_name": "generation", "timing_ms": 250}},
            {"event_name": "node_finished", "payload": {"node_name": "mechanics_processing", "timing_ms": 2}},
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "dm",
                    "provider": "openai",
                    "token_usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
                },
            },
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "generation",
                    "provider": "langchain_openai",
                    "token_usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                },
            },
        ],
    )

    assert bench.benchmark_status(result) == "Baseline"


def test_generation_missing_keeps_status_experimental_and_notes_explain(tmp_path):
    result = bench.BenchmarkResult(
        suite="benchmark",
        model="test-model",
        timestamp="2026-05-08T00:00:00+00:00",
        run_dir=tmp_path / "run",
        cases=[bench.CaseMetric("case", "case.yaml", True, 1, 1)],
        steps=[bench.StepMetric("case", "step", True, action_attempt=True, action_success=True)],
        telemetry_events=[
            {"event_name": "node_finished", "payload": {"node_name": "mechanics_processing", "timing_ms": 2}},
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "dm",
                    "provider": "openai",
                    "token_usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
                },
            },
        ],
    )

    markdown = bench.render_markdown_report(result)

    assert bench.benchmark_status(result) == "Experimental"
    assert "Generation LLM path was not covered; this run is not a formal baseline." in markdown
    assert "| Generation LLM calls | > 0 | 0 | no |" in markdown


def test_markdown_shows_unavailable_token_usage(tmp_path):
    result = bench.BenchmarkResult(
        suite="benchmark",
        model="test-model",
        timestamp="2026-05-08T00:00:00+00:00",
        run_dir=tmp_path / "run",
        cases=[bench.CaseMetric("case", "case.yaml", True, 1, 1)],
        steps=[bench.StepMetric("case", "step", True, action_attempt=True, action_success=True)],
        telemetry_events=[
            {"event_name": "node_finished", "payload": {"node_name": "generation", "timing_ms": 250}},
            {"event_name": "node_finished", "payload": {"node_name": "mechanics_processing", "timing_ms": 2}},
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "dm",
                    "provider": "openai",
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            },
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "generation",
                    "provider": "langchain_openai",
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            },
        ],
    )

    markdown = bench.render_markdown_report(result)

    assert "| Avg Prompt Tokens | Unavailable |" in markdown
    assert "| Avg Output Tokens | Unavailable |" in markdown
    assert "| Avg Total Tokens | Unavailable |" in markdown
    assert "Provider or LangChain response did not expose token usage metadata for this run." in markdown


def test_benchmark_generation_case_dry_run_selectable():
    cases = bench.select_cases(
        suite="benchmark",
        eval_dir="evals/benchmark",
        case_selector="gribbo_generation_turn",
    )

    assert len(cases) == 1
    assert cases[0].steps[0].payload["target"] == "goblin_1"


def test_markdown_case_results_show_failure_details_and_eval_pass_consistency(tmp_path):
    failed_case = bench.CaseMetric(
        "broken_case",
        "broken_case.yaml",
        False,
        2,
        2,
        failed_steps=["step_2"],
        error="RuntimeError: failed",
        case_assertions={
            "ok": False,
            "failure_count": 1,
            "failures": [
                {
                    "category": "state_equals",
                    "path": "game_state.foo",
                    "message": "Value mismatch.",
                }
            ],
        },
    )
    passed_case = bench.CaseMetric("passed_case", "passed_case.yaml", True, 1, 1)
    result = bench.BenchmarkResult(
        suite="benchmark",
        model="test-model",
        timestamp="2026-05-08T00:00:00+00:00",
        run_dir=tmp_path / "run",
        cases=[failed_case, passed_case],
        steps=[],
        telemetry_events=[],
    )
    markdown = bench.render_markdown_report(result)

    assert "- Eval Pass: `1/2`" in markdown
    assert "## Case Results" in markdown
    assert "| broken_case | no | 2/2 | step_2 | RuntimeError: failed; state_equals:game_state.foo - Value mismatch. |" in markdown
    assert "| passed_case | yes | 1/1 | - | - |" in markdown


def test_markdown_generation_contains_required_sections(tmp_path):
    result = bench.BenchmarkResult(
        suite="benchmark",
        model="test-model",
        timestamp="2026-05-08T00:00:00+00:00",
        run_dir=tmp_path / "run",
        cases=[bench.CaseMetric("case", "case.yaml", True, 1, 1)],
        steps=[
            bench.StepMetric(
                "case",
                "step",
                True,
                first_update_latency_ms=123.4,
                action_attempt=True,
                action_success=True,
            )
        ],
        telemetry_events=[
            {"event_name": "node_finished", "payload": {"node_name": "generation", "timing_ms": 250}},
            {"event_name": "node_finished", "payload": {"node_name": "mechanics_processing", "timing_ms": 2}},
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "dm",
                    "provider": "openai",
                    "token_usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
                },
            },
            {
                "event_name": "llm_call",
                "payload": {
                    "component": "generation",
                    "provider": "langchain_openai",
                    "token_usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                },
            },
        ],
    )

    markdown = bench.render_markdown_report(result)

    assert "# BG3 LLM Agent Real-LLM Benchmark" in markdown
    assert "## Run Metadata" in markdown
    assert "## Latency" in markdown
    assert "## Coverage Summary" in markdown
    assert "## Node Breakdown" in markdown
    assert "## Token Economy" in markdown
    assert "## Baseline Criteria" in markdown
    assert "## Action Success" in markdown
    assert "## Case Results" in markdown
    assert "## Notes" in markdown
    assert "Status: Baseline" in markdown
    assert "First Graph Node Update (not token TTFT)" in markdown
    assert "| Action attempts | 1 |" in markdown
    assert "strict token-level TTFT requires generation LLM astream instrumentation" in markdown


def test_cli_dry_run_does_not_require_api_key(tmp_path, monkeypatch, capsys):
    eval_dir = tmp_path / "evals"
    _write_case(eval_dir)
    monkeypatch.setattr(bench.settings, "API_KEY", None)
    monkeypatch.setattr(bench.settings, "BASE_URL", None)
    monkeypatch.setattr(bench.settings, "MODEL_NAME", "")

    code = bench.main(["--eval-dir", str(eval_dir), "--dry-run"])

    assert code == 0
    assert "sample_case" in capsys.readouterr().out


def test_api_key_missing_fails_before_real_run(tmp_path, monkeypatch):
    eval_dir = tmp_path / "evals"
    _write_case(eval_dir)
    monkeypatch.setattr(bench.settings, "API_KEY", None)
    monkeypatch.setattr(bench.settings, "BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(bench.settings, "MODEL_NAME", "test-model")

    with pytest.raises(RuntimeError, match=bench.REQUIRED_CONFIG_ERROR):
        asyncio.run(
            bench.run_benchmark_suite(
                bench.BenchmarkOptions(
                    eval_dir=eval_dir,
                    artifacts_dir=tmp_path / "artifacts",
                )
            )
        )
