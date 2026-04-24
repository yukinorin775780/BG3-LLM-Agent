from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from core.eval.init import discover_golden_eval_cases
from core.eval.runner import run_eval_suite_sync
from core.eval.telemetry import emit_telemetry


class _FakeEvalGameService:
    def __init__(self, db_path: str):
        _ = db_path

    async def process_chat_turn(
        self,
        *,
        user_input: str = "",
        intent: str | None = None,
        session_id: str,
        character: str | None = None,
    ):
        _ = (user_input, intent, session_id, character)
        emit_telemetry("turn_finished", session_id=session_id, intent=intent or "", duration_ms=1)
        return {
            "responses": [],
            "journal_events": [],
            "current_location": "camp_center",
            "environment_objects": {},
            "party_status": {},
            "player_inventory": {},
            "combat_state": {},
        }

    async def get_state_snapshot(self, *, session_id: str, initialize_if_missing: bool = True):
        _ = (session_id, initialize_if_missing)
        return {
            "game_state": {
                "flags": {},
                "entities": {"shadowheart": {"hp": 10}},
            },
            "responses": [],
            "journal_events": [],
            "current_location": "camp_center",
            "environment_objects": {},
            "party_status": {},
            "player_inventory": {},
            "combat_state": {},
        }


def test_golden_suite_contains_expected_minimum_cases():
    cases = discover_golden_eval_cases("evals/golden")
    case_ids = {case.session_id for case in cases}
    assert {
        "astarion_runtime_isolation",
        "laezel_runtime_registry",
        "shadowheart_artifact_probe",
        "gift_potion_acceptance",
        "combat_opening_round",
        "reflection_queue_drain",
        "world_flag_reveal",
    }.issubset(case_ids)


def test_golden_suite_smoke_passes(tmp_path):
    eval_dir = tmp_path / "evals" / "golden"
    eval_dir.mkdir(parents=True, exist_ok=True)
    case_payload = {
        "session": {"id": "smoke_case"},
        "determinism": {"strict": False},
        "steps": [{"id": "s1", "intent": "init_sync", "user_input": ""}],
        "expected": {},
    }
    (eval_dir / "smoke_case.yaml").write_text(
        yaml.safe_dump(case_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with patch("core.eval.runner.GameService", new=_FakeEvalGameService):
        result = run_eval_suite_sync(
            suite="golden",
            eval_dir=Path(eval_dir),
            case_selector=None,
            output_root=str(tmp_path / "eval_artifacts"),
        )

    assert result["case_count"] == 1
    assert result["ok"] is True
    assert result["failed_count"] == 0
