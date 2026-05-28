# BG3 LLM Agent Release Acceptance - 2026-05-28

## Verdict

- Web Demo: **FAIL**
- Unity Client: **PARTIAL / NOT RUN**. Per acceptance rule, Unity is gated on Web PASS, so Unity curated flow was not started.
- Ready for recording/freeze: **NO**

Reason: the Web fresh-session run reached and opened the final exit, but Act4 party strategy did not produce the required three companion barks. It repeatedly produced only Shadowheart's strategy journal entry.

## Test Gates

All required gates were run before the Web acceptance pass:

- `npm test -- --runInBand`: PASS, 288 tests passed.
- `pytest -q`: PASS, 468 tests passed.
- `python -m core.eval.runner --suite golden`: PASS, 50/50 golden cases passed. Full path case `necromancer_lab_full_path_act2_to_act4_truth_negotiation` passed with 18 executed steps and no failed steps.
- `make check`: PASS. Re-ran pytest and golden suite; pytest 468 passed, golden 50/50 passed.

## Evidence

- Web session: `owner_web_goal_20260527_235347`
- Web URL: `http://127.0.0.1:8000/web_ui/?session_id=owner_web_goal_20260527_235347&map_id=necromancer_lab`
- Web artifacts: `artifacts/release_acceptance/web_20260527_235347/`
- Saved state snapshots: `state_01_initial.json` through `state_19_after_screenshot_check.json`
- Saved screenshot: `screenshot_01_final_exit.png`

Screenshot caveat: Browser CDP screenshots timed out. A headless Chrome screenshot was saved, but after reloading the same session the visual canvas showed Act1 while `/api/state` still proved the final backend state. Treat state snapshots, not that screenshot, as the authoritative pass/fail evidence.

## Web Flow Results

Act1 Safe Room:

- PASS: A-B door opened by normal Web interaction.
- Evidence: `state_02_ab_door_open.json`
- Backend state: `environment_objects.door_a_to_b.is_open=true`, `entities.door_a_to_b.is_open=true`, `flags.act2_corridor_entered=true`.

Act2 Poison Corridor:

- PASS: Trap perception wrote real backend state, not just a frontend card.
- Evidence: `state_04_trap_revealed.json`
- Backend state: `gas_trap_1.status=revealed`, `is_hidden=false`, `flags.act2_gas_trap_revealed=true`, `flags.necromancer_lab_poison_trap_revealed=true`.
- PASS: Disarm wrote disabled backend state.
- Evidence: `state_05_trap_disarmed.json`
- Backend state: `gas_trap_1.status=disabled`, `flags.act2_gas_trap_disarmed=true`, `flags.necromancer_lab_poison_trap_disarmed=true`.
- PASS: Crossing the disabled trap did not poison the player.
- Evidence: `state_06_cross_disabled_trap.json`
- Backend state: player `status_effects=[]`, no poison trigger flags.
- PASS: B-D door inspection did not auto-lockpick.
- Evidence: `state_08_bd_door_inspected.json`
- Backend state: `door_b_to_d.is_locked=true`, `flags.act2_corridor_exit_requires_key=true`, no lockpick success flags, latest roll result `MISSING_KEY`.

Act3 Secret Study:

- PASS: Secret study path opened from cracked wall.
- Evidence: `state_09_secret_study.json`
- PASS: `chemical_notes`, `iron_key_sketch`, and `necromancer_diary` were read and diary truth decoded.
- Evidence: `state_10_diary_decoded.json`
- Backend state: `act3_chemical_notes_seen=true`, `act3_key_sketch_seen=true`, `act3_diary_decoded=true`, `act3_gribbo_potion_truth_known=true`.
- PASS: `study_chest` loot granted `lab_key`.
- Evidence: `state_11_lab_key_looted.json`
- Backend state: `player_inventory.lab_key=1`.

Act4 Gribbo Lab:

- PASS: `door_b_to_d` opened with `lab_key`.
- Evidence: `state_12_bd_door_open.json`
- Backend state: `door_b_to_d.is_open=true`, `door_b_to_d.is_locked=false`, `flags.act2_corridor_exit_opened_with_key=true`.
- FAIL: party strategy did not produce three companion barks.
- Evidence: `state_15_party_strategy_dock_retry.json`
- Observed journal entries: only `[Boss方案] shadowheart -> contain_corruption`, repeated three times.
- Missing required entries: `[Boss方案] astarion -> steal_key` and `[Boss方案] laezel -> execute`.
- PASS: truth negotiation obtained `heavy_iron_key`.
- Evidence: `state_16_truth_negotiation_key.json`
- Backend state: `act4_negotiation_success=true`, `act4_heavy_iron_key_obtained=true`, `act4_gribbo_spared=true`, `player_inventory.heavy_iron_key=1`, `gribbo.status=spared`, `gribbo.faction=neutralized`.

Final Exit:

- PASS: player moved near `heavy_oak_door_1`.
- Evidence: `state_17_near_final_exit.json`
- PASS: final exit opened.
- Evidence: `state_18_final_exit_cleared.json`, `state_19_after_screenshot_check.json`
- Backend state: `flags.act4_final_exit_opened=true`, `game_state.demo_cleared=true`, top-level `demo_cleared=true`, `heavy_oak_door_1.is_open=true`, `heavy_oak_door_1.is_locked=false`.

## Issues

P0:

- Act4 party strategy is not release-ready. The strategy detector is present, but runtime output only emits Shadowheart. Current evidence points to `core/graph/nodes/dm.py`: `_apply_gribbo_boss_strategy_override` runs before `_apply_diary_negotiation_override`, then the diary override changes the same turn to `reason=diary_evidence_pressure` and `responders=["gribbo", "shadowheart"]`. It does not guard against existing `gribbo_boss_strategy_context`.

P1:

- Screenshot evidence is weak. Browser CDP screenshot timed out, and headless Chrome reload did not hydrate the same final visual scene even though backend state remained final. State snapshots are authoritative, but recording-readiness still needs a reliable capture path.
- The exact requested URL leaves idle banter enabled. During long acceptance, idle turns advanced `turn_count` and added noise. It did not block the final state, but it makes evidence noisier.

P2:

- `demo_cleared` is present as top-level and `game_state.demo_cleared`; it is not under `flags`. The objective only required `demo_cleared=true`, so this passed, but report readers should check the correct location.

## Minimal Fix List

1. In `core/graph/nodes/dm.py`, prevent `_apply_diary_negotiation_override` from overriding an existing `gribbo_boss_strategy_context`, or reorder the overrides so boss strategy remains authoritative for strategy prompts.
2. Add/adjust a test where Act4 strategy is asked after diary truth is decoded and assert:
   - responders/party turn include `astarion`, `shadowheart`, `laezel`;
   - journal includes all three `[Boss方案]` entries;
   - diary evidence pressure still works for actual truth negotiation.
3. Re-run the full required gates, then re-run a fresh Web session from Act1 to final exit.
4. Establish a reliable Web screenshot method for the in-progress session before recording/freeze.

## Dirty Git / Do Not Commit

Current dirty tracked files:

- `core/graph/nodes/dm.py`
- `core/graph/nodes/input.py`
- `core/systems/mechanics.py`
- `evals/golden/necromancer_lab_full_path_act2_to_act4_truth_negotiation.yaml`
- `evals/golden/necromancer_lab_gribbo_mercy_execute.yaml`
- `evals/golden/necromancer_lab_gribbo_mercy_spare.yaml`
- `evals/golden/necromancer_lab_key_aware_guidance.yaml`
- `unity_client/BG3UnityClient/Assets/Scripts/Gameplay/ActFlowController.cs`
- `unity_client/BG3UnityClient/Assets/Scripts/Gameplay/SceneBootstrap.cs`
- `unity_client/BG3UnityClient/Assets/Scripts/Gameplay/TopDownCameraFollow.cs`
- `unity_client/BG3UnityClient/Assets/Scripts/UI/ActObjectiveHud.cs`
- `unity_client/BG3UnityClient/Assets/Scripts/UI/BackendDebugPanel.cs`
- `web_ui/app.js`
- `web_ui/tests/app.test.js`

Current untracked files:

- `data/chroma_db_legacy/`
- `docs/necromancer_lab_p0_web_demo_report_20260527.md`
- `docs/release_acceptance_2026-05-28.md`
- `tests/test_owner_web_playtest_p0.py`
- `unity_client/BG3UnityClient/Assets/Scripts/Gameplay/ObjectiveMarker.cs`
- `unity_client/BG3UnityClient/Assets/Scripts/Gameplay/ObjectiveMarker.cs.meta`

Do not commit / do not include in release changes:

- `artifacts/`
- `output/`
- Unity cache folders such as `unity_client/BG3UnityClient/Library/`, `Temp/`, and `Logs/`
- `.DS_Store`
- `.vscode/`
- `docs/runtime-knowledge-base/`
- `data/chroma_db_legacy/`
