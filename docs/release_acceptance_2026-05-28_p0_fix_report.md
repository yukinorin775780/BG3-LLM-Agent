# Web Release Acceptance P0 Fix Report - 2026-05-28

## Verdict

- Web Demo: PASS
- Fixed P0: Act4 party strategy now emits all three required companion strategy journal entries.
- Final exit: PASS, `act4_final_exit_opened=true`.
- Demo clear: PASS, `demo_cleared=true`.
- Unity: not modified or rerun for this P0 fix.

## Change Summary

- `core/graph/nodes/dm.py`: `_apply_diary_negotiation_override` now returns immediately when `intent_context.gribbo_boss_strategy_context` already exists.
- This prevents decoded-diary evidence pressure from overriding the same-turn Act4 boss strategy analysis.
- Truth negotiation remains handled by `act4_gribbo_boss_truth_negotiation` and still grants `heavy_iron_key`.

## Regression Coverage

- `tests/test_necromancer_lab_act4_boss_encounter.py`
  - Added coverage for decoded diary plus Act4 strategy prompt.
  - Asserted strategy context remains `act4_gribbo_boss_strategy`.
  - Asserted journal includes:
    - `[Boss方案] astarion -> steal_key`
    - `[Boss方案] shadowheart -> contain_corruption`
    - `[Boss方案] laezel -> execute`
  - Extended truth negotiation coverage to assert `act4_heavy_iron_key_obtained=true` and `player_inventory.heavy_iron_key=1`.

## Test Gates

- `pytest -q tests/test_necromancer_lab_act4_boss_encounter.py tests/test_diary_negotiation_guidance.py`: PASS, 13 passed.
- `pytest -q`: PASS, 469 passed.
- `python -m core.eval.runner --suite golden`: PASS, 50/50 passed.
- `npm test -- --runInBand`: PASS, Jest 288 passed.
- `make check`: PASS, pytest 469 passed and golden 50/50 passed.

## Fresh Web Acceptance Evidence

- Web session: `owner_web_goal_20260528_093936`
- Artifacts: `artifacts/release_acceptance/web_20260528_093936/`
- Final screenshot: `artifacts/release_acceptance/web_20260528_093936/screenshot_01_final_exit.jpg`

Key snapshots:

- `state_13_party_strategy.json`
  - `game_state.intent_context.reason=act4_gribbo_boss_strategy`
  - `game_state.intent_context.diary_negotiation_context={}`
  - Journal contains all three required strategy entries:
    - `[Boss方案] astarion -> steal_key`
    - `[Boss方案] shadowheart -> contain_corruption`
    - `[Boss方案] laezel -> execute`
- `state_14_truth_negotiation_key.json`
  - `game_state.flags.act4_negotiation_success=true`
  - `game_state.flags.act4_heavy_iron_key_obtained=true`
  - `player_inventory.heavy_iron_key=1`
  - `gribbo.status=spared`
  - `gribbo.faction=neutralized`
- `state_15_final_exit_cleared.json`
  - `game_state.flags.act4_final_exit_opened=true`
  - `game_state.demo_cleared=true`
  - top-level `demo_cleared=true`
  - `heavy_oak_door_1.is_open=true`
  - `heavy_oak_door_1.is_locked=false`

## Scope Notes

- No Unity files were intentionally changed for this fix.
- Existing dirty files outside the P0 fix scope were left untouched.
- `data/chroma_db_legacy/` remains untracked and was not included in this fix.
