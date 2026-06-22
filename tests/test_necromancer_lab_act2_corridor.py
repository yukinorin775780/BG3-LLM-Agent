import asyncio
from unittest.mock import patch

from core.graph.nodes.dm import dm_node
from core.graph.nodes.input import input_node
from core.systems import mechanics
from core.systems.world_init import get_initial_world_state


def _lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    state["flags"] = {}
    state["journal_events"] = []
    state["pending_events"] = []
    state["speaker_responses"] = []
    return state


def _open_corridor(state: dict) -> dict:
    for bucket_name in ("entities", "environment_objects"):
        door = state.get(bucket_name, {}).get("door_a_to_b")
        if isinstance(door, dict):
            door["is_open"] = True
            door["status"] = "open"
    state["flags"]["act2_corridor_entered"] = True
    return state


def _move_near_trap_with_astarion_perception(
    state: dict,
    *,
    raw_roll: int = 12,
    total: int = 17,
    success: bool = True,
) -> dict:
    state = _open_corridor(state)
    with patch(
        "core.systems.mechanics.roll_d20",
        return_value={
            "total": total,
            "raw_roll": raw_roll,
            "rolls": [raw_roll],
            "is_success": success,
            "result_type": "SUCCESS" if success else "FAILURE",
            "log_str": f"🎲 ({raw_roll}) + +5 = {total} vs DC 13 [{'SUCCESS' if success else 'FAILURE'}]",
        },
    ):
        result = mechanics.execute_move_action(
            {
                **state,
                "intent": "MOVE",
                "intent_context": {
                    "action_actor": "player",
                    "action_target": "5,12",
                },
            }
        )
    return {**state, **result}


def _reveal_trap_with_astarion(state: dict) -> dict:
    return _move_near_trap_with_astarion_perception(state)


def test_act2_astarion_warning_sets_act2_perception_flags():
    state = _reveal_trap_with_astarion(_lab_state())

    assert state["flags"]["act2_corridor_entered"] is True
    assert state["flags"]["act2_astarion_perception_checked"] is True
    assert state["flags"]["act2_astarion_perception_success"] is True
    assert state["flags"]["act2_gas_trap_revealed"] is True
    assert state["flags"]["necromancer_lab_poison_trap_revealed"] is True
    latest_roll = state["raw_roll_data"]
    assert latest_roll["actor"] == "astarion"
    assert latest_roll["skill"] == "perception"
    assert latest_roll["dc"] == 13
    assert any("[陷阱感知] astarion -> gas_trap_1" in line for line in state["journal_events"])


def test_act2_astarion_proximity_perception_failure_keeps_trap_hidden():
    state = _move_near_trap_with_astarion_perception(
        _lab_state(),
        raw_roll=2,
        total=7,
        success=False,
    )

    assert state["flags"]["act2_astarion_perception_checked"] is True
    assert state["flags"]["act2_astarion_perception_success"] is False
    assert "act2_gas_trap_revealed" not in state["flags"]
    assert "necromancer_lab_poison_trap_revealed" not in state["flags"]
    assert state["environment_objects"]["gas_trap_1"]["is_hidden"] is True
    assert state["entities"]["gas_trap_1"]["is_hidden"] is True
    assert state["environment_objects"]["gas_trap_1"].get("status", "armed") in {"armed", "hidden"}
    assert state["raw_roll_data"]["actor"] == "astarion"
    assert state["raw_roll_data"]["skill"] == "perception"
    assert state["raw_roll_data"]["dc"] == 13
    assert any("[陷阱感知失败] astarion -> gas_trap_1" in line for line in state["journal_events"])


def test_act2_astarion_perception_checked_does_not_repeat_near_trap():
    checked = _move_near_trap_with_astarion_perception(
        _lab_state(),
        raw_roll=2,
        total=7,
        success=False,
    )

    with patch("core.systems.mechanics.roll_d20", side_effect=AssertionError("roll should not repeat")):
        repeated = mechanics.execute_move_action(
            {
                **checked,
                "intent": "MOVE",
                "intent_context": {
                    "action_actor": "player",
                    "action_target": "5,10",
                },
            }
        )

    assert repeated["flags"]["act2_astarion_perception_checked"] is True
    assert repeated["flags"]["act2_astarion_perception_success"] is False
    assert repeated["raw_roll_data"]["intent"] == "MOVE"
    assert not any("[陷阱感知]" in line for line in repeated["journal_events"])
    assert not any("[陷阱感知失败]" in line for line in repeated["journal_events"])


def test_act2_failed_perception_then_stepping_on_trap_triggers_poison():
    checked = _move_near_trap_with_astarion_perception(
        _lab_state(),
        raw_roll=2,
        total=7,
        success=False,
    )

    with patch("core.systems.mechanics.roll_d20", side_effect=AssertionError("perception should not repeat")):
        triggered = mechanics.execute_move_action(
            {
                **checked,
                "intent": "MOVE",
                "intent_context": {
                    "action_actor": "player",
                    "action_target": "5,11",
                },
            }
        )

    assert triggered["flags"]["act2_astarion_perception_checked"] is True
    assert triggered["flags"]["act2_astarion_perception_success"] is False
    assert triggered["flags"]["necromancer_lab_poison_trap_triggered"] is True
    assert triggered["flags"]["act2_gas_trap_triggered"] is True
    assert triggered["environment_objects"]["gas_trap_1"]["status"] == "triggered"
    assert any(
        effect.get("type") == "poisoned"
        for effect in triggered["entities"]["player"]["status_effects"]
    )
    assert any("[毒气陷阱] gas_trap_1 triggered" in line for line in triggered["journal_events"])


def test_act2_astarion_disarm_success_sets_act2_flags():
    state = _reveal_trap_with_astarion(_lab_state())
    result = mechanics.execute_disarm_action(
        {
            **state,
            "intent": "DISARM",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "gas_trap_1",
            },
        }
    )

    assert result["flags"]["act2_astarion_ordered_to_disarm"] is True
    assert result["flags"]["act2_disarm_actor"] == "astarion"
    assert result["flags"]["act2_disarm_attempted"] is True
    assert result["flags"]["act2_disarm_success"] is True
    assert result["flags"]["act2_gas_trap_disarmed"] is True
    assert result["environment_objects"]["gas_trap_1"]["status"] == "disabled"


def test_act2_corridor_move_near_lab_door_does_not_trigger_act4_poison_valve():
    state = _reveal_trap_with_astarion(_lab_state())
    disarmed = mechanics.execute_disarm_action(
        {
            **state,
            "intent": "DISARM",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "gas_trap_1",
            },
        }
    )
    move_result = mechanics.execute_move_action(
        {
            **state,
            **disarmed,
            "intent": "MOVE",
            "intent_context": {"action_actor": "player", "action_target": "5,8"},
        }
    )

    assert move_result["entities"]["player"]["x"] == 5
    assert move_result["entities"]["player"]["y"] == 8
    poison_valve = move_result["environment_objects"]["poison_valve"]
    potion_tank = move_result["environment_objects"]["potion_tank"]
    assert poison_valve["status"] == "armed"
    assert poison_valve.get("room_id") == "room_d_lab"
    assert potion_tank.get("room_id") == "room_d_lab"
    assert poison_valve["y"] < 8
    assert potion_tank["y"] < 8
    assert not any("poison_valve" in line or "毒气阀门" in line for line in move_result["journal_events"])


def test_act2_astarion_disarm_failure_triggers_poison_state():
    state = _reveal_trap_with_astarion(_lab_state())
    state["flags"]["necromancer_lab_force_trap_disarm_failure"] = True
    result = mechanics.execute_disarm_action(
        {
            **state,
            "intent": "DISARM",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "gas_trap_1",
            },
        }
    )

    assert result["flags"]["act2_disarm_attempted"] is True
    assert result["flags"]["act2_disarm_success"] is False
    assert result["flags"]["act2_gas_trap_triggered"] is True
    assert result["flags"]["act2_gas_trap_damage_applied"] is True
    assert result["entities"]["player"]["status_effects"][0]["type"] == "poisoned"
    assert any("[陷阱解除失败] astarion -> gas_trap_1" in line for line in result["journal_events"])
    assert any("[毒气陷阱] gas_trap_1 triggered" in line for line in result["journal_events"])


def test_input_routes_astarion_natural_language_disarm_to_gas_trap():
    state = {
        **_lab_state(),
        "user_input": "阿斯代伦，解除陷阱。",
        "intent": "chat",
    }

    patch = input_node(state)

    assert patch["intent"] == "DISARM"
    assert patch["target"] == "gas_trap_1"
    assert patch["intent_context"]["action_actor"] == "astarion"
    assert patch["intent_context"]["action_target"] == "gas_trap_1"


def test_world_init_has_corridor_lab_door_with_key_and_lockpick_contract():
    state = _lab_state()
    door = state["entities"]["door_b_to_d"]

    assert door["entity_type"] == "door"
    assert door["is_locked"] is True
    assert door["key_required"] == "lab_key"
    assert door["lockpick_dc"] == 15


def test_corridor_lab_door_interact_without_key_reports_key_gate():
    state = _lab_state()
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8
    state["player_inventory"].pop("lab_key", None)

    result = mechanics.execute_interact_action(
        {
            **state,
            "intent": "INTERACT",
            "intent_context": {
                "action_actor": "player",
                "action_target": "door_b_to_d",
            },
        }
    )

    assert result["flags"]["act2_corridor_exit_door_inspected"] is True
    assert result["flags"]["act2_corridor_exit_requires_key"] is True
    assert result["flags"]["act2_secret_study_hint_given"] is True
    assert result["flags"]["act2_secret_study_route_unlocked"] is True
    assert result["raw_roll_data"]["result"]["result_type"] == "MISSING_KEY"
    assert any("lab_key" in line for line in result["journal_events"])
    assert any("书房" in line or "入口" in line for line in result["journal_events"])


def test_corridor_lab_door_check_does_not_auto_lockpick_when_dm_returns_unlock():
    state = _lab_state()
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8
    state["player_inventory"].pop("lab_key", None)

    result = mechanics.execute_unlock_action(
        {
            **state,
            "user_input": "检查 B-D 门。",
            "intent": "UNLOCK",
            "intent_context": {
                "action_actor": "player",
                "action_target": "door_b_to_d",
            },
        }
    )

    assert result["flags"]["act2_corridor_exit_door_inspected"] is True
    assert result["flags"]["act2_corridor_exit_requires_key"] is True
    assert result["flags"]["act2_secret_study_hint_given"] is True
    assert result["flags"]["act2_secret_study_route_unlocked"] is True
    assert "act2_corridor_exit_lockpick_attempted" not in result["flags"]
    assert result["raw_roll_data"]["result"]["result_type"] == "INSPECT_REQUIRES_EXPLICIT_LOCKPICK"


def test_input_routes_lab_door_check_to_interact_not_unlock():
    patch = input_node(
        {
            **_lab_state(),
            "user_input": "检查 B-D 门。",
            "intent": "chat",
        }
    )

    assert patch["intent"] == "INTERACT"
    assert patch["target"] == "door_b_to_d"
    assert patch["intent_context"]["action"] == "inspect_lab_door"


def test_negative_lockpick_text_downgrades_to_inspect():
    state = _lab_state()
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8
    state["player_inventory"].pop("lab_key", None)
    text = "检查 door_b_to_d，不要撬锁。"

    input_patch = input_node({**state, "user_input": text, "intent": "chat"})
    dm_patch = asyncio.run(dm_node({**state, "user_input": text, "intent": "chat"}))
    result = mechanics.execute_unlock_action(
        {
            **state,
            "user_input": text,
            "intent": "UNLOCK",
            "intent_context": {
                "action_actor": "player",
                "action_target": "door_b_to_d",
            },
        }
    )

    assert input_patch["intent"] == "INTERACT"
    assert input_patch["target"] == "door_b_to_d"
    assert dm_patch["intent"] == "INTERACT"
    assert dm_patch["intent_context"]["action_target"] == "door_b_to_d"
    assert result["raw_roll_data"]["result"]["result_type"] == "INSPECT_REQUIRES_EXPLICIT_LOCKPICK"
    assert "act2_corridor_exit_lockpick_attempted" not in result["flags"]


def test_explicit_lockpick_still_routes_to_unlock():
    patch = input_node(
        {
            **_lab_state(),
            "user_input": "Astarion lockpick the door_b_to_d door.",
            "intent": "chat",
        }
    )

    assert patch["intent"] == "UNLOCK"
    assert patch["target"] == "door_b_to_d"
    assert patch["intent_context"]["action"] == "lockpick_lab_door"


def test_corridor_lab_door_lockpick_success_skips_secret_study():
    state = _lab_state()
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8
    state["flags"]["necromancer_lab_force_lockpick_success"] = True
    state["player_inventory"].pop("lab_key", None)

    result = mechanics.execute_unlock_action(
        {
            **state,
            "intent": "UNLOCK",
            "intent_context": {
                "action_actor": "player",
                "action_target": "door_b_to_d",
            },
        }
    )

    assert result["flags"]["act2_corridor_exit_lockpick_attempted"] is True
    assert result["flags"]["act2_corridor_exit_lockpick_success"] is True
    assert result["flags"]["act2_lockpick_success_route_to_boss"] is True
    assert result["flags"].get("necromancer_lab_diary_decoded") is None
    assert result["entities"]["door_b_to_d"]["is_open"] is True
    assert result["entities"]["door_b_to_d"]["is_locked"] is False


def test_corridor_lab_door_lockpick_failure_hints_secret_study():
    state = _lab_state()
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8
    state["flags"]["necromancer_lab_force_lockpick_failure"] = True
    state["player_inventory"].pop("lab_key", None)

    result = mechanics.execute_unlock_action(
        {
            **state,
            "intent": "UNLOCK",
            "intent_context": {
                "action_actor": "player",
                "action_target": "door_b_to_d",
            },
        }
    )

    assert result["flags"]["act2_corridor_exit_lockpick_attempted"] is True
    assert result["flags"]["act2_corridor_exit_lockpick_success"] is False
    assert result["flags"]["act2_secret_study_hint_given"] is True
    assert result["flags"]["act2_secret_study_route_unlocked"] is True
    assert any("密道" in line or "别的入口" in line for line in result["journal_events"])
