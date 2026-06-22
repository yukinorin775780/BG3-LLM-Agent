import asyncio
import copy
from unittest.mock import patch

from core.actors.builders import build_actor_view
from core.campaigns.necromancer_lab import (
    detect_poison_trap_trigger_context,
    detect_trap_awareness_context,
)
from core.graph.nodes.dm import dm_node
from core.graph.nodes.input import input_node
from core.systems import mechanics
from core.systems.world_init import get_initial_world_state


def _build_lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    state["flags"] = {}
    state["journal_events"] = []
    state["pending_events"] = []
    state["speaker_responses"] = []
    return state


def _open_corridor_and_move_near_trap(state: dict) -> dict:
    state = copy.deepcopy(state)
    for bucket_name in ("entities", "environment_objects"):
        door = state.get(bucket_name, {}).get("door_a_to_b")
        if isinstance(door, dict):
            door["is_open"] = True
            door["status"] = "open"
    player = state.get("entities", {}).get("player")
    if isinstance(player, dict):
        player["x"] = 5
        player["y"] = 12
    return state


def _warn_about_trap(state: dict) -> dict:
    state = _open_corridor_and_move_near_trap(state)
    state["flags"]["act2_corridor_entered"] = True
    with patch(
        "core.systems.mechanics.roll_d20",
        return_value={
            "total": 17,
            "raw_roll": 12,
            "rolls": [12],
            "is_success": True,
            "result_type": "SUCCESS",
            "log_str": "🎲 (12) + +5 = 17 vs DC 13 [SUCCESS]",
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


def test_trap_awareness_helper_and_initial_actor_view_do_not_leak_hidden_trap():
    state = _build_lab_state()

    initial_context = detect_trap_awareness_context(state, "继续往前走", {})
    player_view = build_actor_view(state, "player")
    astarion_view = build_actor_view(state, "astarion")

    assert initial_context is None
    context = detect_trap_awareness_context(
        _open_corridor_and_move_near_trap(state),
        "继续往前走",
        {},
    )
    assert context is not None
    assert context["topic"] == "poison_trap"
    assert context["trap_id"] == "gas_trap_1"
    assert context["can_detect"] is True
    assert context["revealed"] is False
    assert "gas_trap_1" not in player_view.visible_environment_objects
    assert "gas_trap_1" not in astarion_view.visible_environment_objects


def test_trap_awareness_helper_noops_outside_necromancer_lab():
    state = _build_lab_state()
    state["map_data"]["id"] = "goblin_camp"

    assert detect_trap_awareness_context(state, "继续往前走", {}) is None


def test_trap_awareness_requires_corridor_access_proximity_and_single_check():
    state = _build_lab_state()
    assert detect_trap_awareness_context(state, "前面的走廊安全吗？", {}) is None

    door_open_far = copy.deepcopy(state)
    door_open_far["entities"]["door_a_to_b"]["is_open"] = True
    door_open_far["entities"]["door_a_to_b"]["status"] = "open"
    door_open_far["entities"]["player"]["x"] = 2
    door_open_far["entities"]["player"]["y"] = 2
    assert detect_trap_awareness_context(door_open_far, "前面的走廊安全吗？", {}) is None

    near = _open_corridor_and_move_near_trap(state)
    context = detect_trap_awareness_context(near, "前面的走廊安全吗？", {})
    assert context is not None
    assert context["trap_id"] == "gas_trap_1"

    near["flags"]["act2_astarion_perception_checked"] = True
    assert detect_trap_awareness_context(near, "前面的走廊安全吗？", {}) is None


def test_dm_routes_trap_awareness_to_astarion_perception_roll():
    state = _open_corridor_and_move_near_trap(_build_lab_state())
    state["flags"]["act2_corridor_entered"] = True

    dm_patch = asyncio.run(dm_node({**state, "user_input": "前面的走廊安全吗？", "intent": "chat"}))

    assert dm_patch["intent"] == "PERCEPTION"
    assert dm_patch["intent_context"]["action_actor"] == "astarion"
    assert dm_patch["intent_context"]["action_target"] == "gas_trap_1"
    assert dm_patch["intent_context"]["source"] == "trap_awareness"
    assert dm_patch["intent_context"]["trap_awareness_context"]["detect_dc"] == 13


def test_dm_preserves_structured_trap_awareness_perception_intent():
    state = _open_corridor_and_move_near_trap(_build_lab_state())
    state["flags"]["act2_corridor_entered"] = True

    dm_patch = asyncio.run(dm_node({
        **state,
        "user_input": "阿斯代伦检查走廊里的可疑机关。",
        "intent": "PERCEPTION",
        "target": "gas_trap_1",
        "source": "trap_awareness",
        "intent_context": {
            "action_actor": "astarion",
            "action_target": "gas_trap_1",
            "source": "trap_awareness",
        },
    }))

    assert dm_patch["intent"] == "PERCEPTION"
    assert dm_patch["intent_context"]["source"] == "trap_awareness"
    assert dm_patch["intent_context"]["action_actor"] == "astarion"
    assert dm_patch["intent_context"]["action_target"] == "gas_trap_1"
    assert dm_patch["intent_context"]["trap_awareness_context"]["detect_dc"] == 13


def test_poison_trap_trigger_helper_requires_necromancer_lab():
    state = _build_lab_state()
    state["map_data"]["id"] = "goblin_camp"

    context = detect_poison_trap_trigger_context(
        state,
        "",
        {"action_target": "gas_trap_1", "source": "trap_trigger"},
    )

    assert context is None


def test_astarion_warning_reveals_poison_trap_and_writes_journal():
    state = _warn_about_trap(_build_lab_state())

    assert state["flags"]["necromancer_lab_poison_trap_revealed"] is True
    assert state["flags"]["astarion_detected_gas_trap"]["value"] is True
    assert state["raw_roll_data"]["actor"] == "astarion"
    assert state["raw_roll_data"]["skill"] == "perception"
    assert state["raw_roll_data"]["dc"] == 13
    assert state["environment_objects"]["gas_trap_1"]["is_hidden"] is False
    assert state["entities"]["gas_trap_1"]["is_hidden"] is False
    assert any("[陷阱感知] astarion -> gas_trap_1" in line for line in state["journal_events"])


def test_astarion_disarms_revealed_trap_and_safe_crossing_does_not_poison():
    warned = _warn_about_trap(_build_lab_state())

    disarmed = mechanics.execute_disarm_action(
        {
            **warned,
            "intent": "DISARM",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "gas_trap_1",
            },
        }
    )
    crossed = mechanics.execute_move_action(
        {
            **warned,
            **disarmed,
            "intent": "MOVE",
            "intent_context": {
                "action_actor": "player",
                "action_target": "5,11",
            },
        }
    )

    assert disarmed["flags"]["necromancer_lab_poison_trap_disarmed"] is True
    assert disarmed["environment_objects"]["gas_trap_1"]["status"] == "disabled"
    assert "gas_trap_1" not in disarmed["entities"]
    assert any("[陷阱解除] astarion -> gas_trap_1" in line for line in disarmed["journal_events"])
    assert not any(effect.get("type") == "poisoned" for effect in crossed["entities"]["player"]["status_effects"])


def test_ignored_poison_trap_triggers_poison_once():
    state = _build_lab_state()
    triggered = mechanics.execute_move_action(
        {
            **state,
            "intent": "MOVE",
            "intent_context": {
                "action_actor": "player",
                "action_target": "5,11",
            },
        }
    )
    repeated = mechanics.execute_move_action(
        {
            **state,
            **triggered,
            "intent": "MOVE",
            "intent_context": {
                "action_actor": "player",
                "action_target": "5,11",
            },
        }
    )

    first_effects = triggered["entities"]["player"]["status_effects"]
    repeated_effects = repeated["entities"]["player"]["status_effects"]
    assert triggered["flags"]["necromancer_lab_poison_trap_triggered"] is True
    assert triggered["environment_objects"]["gas_trap_1"]["status"] == "triggered"
    assert any(effect.get("type") == "poisoned" for effect in first_effects)
    assert sum(1 for effect in repeated_effects if effect.get("type") == "poisoned") == 1
    assert not any("[毒气陷阱] gas_trap_1 triggered" in line for line in repeated["journal_events"])


def test_structured_trap_trigger_action_writes_flags_status_and_poison():
    state = _build_lab_state()

    triggered = mechanics.execute_trigger_trap_action(
        {
            **state,
            "intent": "TRIGGER_TRAP",
            "target": "gas_trap_1",
            "source": "trap_trigger",
            "intent_context": {
                "action_actor": "player",
                "action_target": "gas_trap_1",
                "source": "trap_trigger",
            },
        }
    )

    player_effects = triggered["entities"]["player"]["status_effects"]
    poisoned = [effect for effect in player_effects if effect.get("type") == "poisoned"]
    assert any("[毒气陷阱] gas_trap_1 triggered" in line for line in triggered["journal_events"])
    assert triggered["flags"]["necromancer_lab_poison_trap_triggered"] is True
    assert triggered["environment_objects"]["gas_trap_1"]["status"] == "triggered"
    assert len(poisoned) == 1
    assert poisoned[0]["duration"] == 3


def test_repeated_structured_trap_trigger_does_not_duplicate_poison():
    state = _build_lab_state()
    trigger_state = {
        "intent": "TRIGGER_TRAP",
        "target": "gas_trap_1",
        "source": "trap_trigger",
        "intent_context": {
            "action_actor": "player",
            "action_target": "gas_trap_1",
            "source": "trap_trigger",
        },
    }
    triggered = mechanics.execute_trigger_trap_action({**state, **trigger_state})
    repeated = mechanics.execute_trigger_trap_action({**state, **triggered, **trigger_state})

    repeated_effects = repeated["entities"]["player"]["status_effects"]
    assert sum(1 for effect in repeated_effects if effect.get("type") == "poisoned") == 1
    assert not any("[毒气陷阱] gas_trap_1 triggered" in line for line in repeated["journal_events"])


def test_teammate_entering_poison_trap_zone_triggers_trap():
    state = _build_lab_state()

    triggered = mechanics.execute_move_action(
        {
            **state,
            "intent": "MOVE",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "5,11",
            },
        }
    )

    astarion_effects = triggered["entities"]["astarion"]["status_effects"]
    assert triggered["flags"]["necromancer_lab_poison_trap_triggered"] is True
    assert any(effect.get("type") == "poisoned" for effect in astarion_effects)


def test_disarmed_poison_trap_does_not_trigger():
    warned = _warn_about_trap(_build_lab_state())
    disarmed = mechanics.execute_disarm_action(
        {
            **warned,
            "intent": "DISARM",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "gas_trap_1",
            },
        }
    )

    triggered = mechanics.execute_trigger_trap_action(
        {
            **warned,
            **disarmed,
            "intent": "TRIGGER_TRAP",
            "target": "gas_trap_1",
            "source": "trap_trigger",
            "intent_context": {
                "action_actor": "player",
                "action_target": "gas_trap_1",
                "source": "trap_trigger",
            },
        }
    )

    assert disarmed["flags"]["necromancer_lab_poison_trap_disarmed"] is True
    assert triggered["flags"]["necromancer_lab_poison_trap_disarmed"] is True
    assert "necromancer_lab_poison_trap_triggered" not in triggered["flags"]
    assert not any(effect.get("type") == "poisoned" for effect in triggered["entities"]["player"]["status_effects"])


def test_forced_astarion_disarm_failure_triggers_trap_without_disarmed_flag():
    warned = _warn_about_trap(_build_lab_state())

    failed = mechanics.execute_disarm_action(
        {
            **warned,
            "intent": "DISARM",
            "intent_context": {
                "action_actor": "astarion",
                "action_target": "gas_trap_1",
                "force_disarm_failure": True,
            },
        }
    )

    player_effects = failed["entities"]["player"]["status_effects"]
    assert any("[陷阱解除失败] astarion -> gas_trap_1" in line for line in failed["journal_events"])
    assert any("[毒气陷阱] gas_trap_1 triggered" in line for line in failed["journal_events"])
    assert failed["flags"]["necromancer_lab_poison_trap_triggered"] is True
    assert "necromancer_lab_poison_trap_disarmed" not in failed["flags"]
    assert failed["environment_objects"]["gas_trap_1"]["status"] == "triggered"
    assert any(effect.get("type") == "poisoned" and effect.get("duration") == 3 for effect in player_effects)


def test_structured_interact_trap_trigger_is_not_downgraded_to_awareness():
    state = _build_lab_state()
    state.update(
        {
            "user_input": "",
            "intent": "INTERACT",
            "target": "gas_trap_1",
            "source": "trap_trigger",
            "intent_context": {
                "action_actor": "player",
                "action_target": "gas_trap_1",
                "source": "trap_trigger",
            },
            "pending_events": [],
            "speaker_responses": [],
        }
    )

    dm_patch = asyncio.run(dm_node(state))

    assert dm_patch["intent"] == "TRIGGER_TRAP"
    assert dm_patch["intent_context"]["action_target"] == "gas_trap_1"
    assert dm_patch["intent_context"]["source"] == "trap_trigger"


def test_input_node_normalizes_empty_structured_interact_trap_trigger():
    patch = input_node(
        {
            **_build_lab_state(),
            "user_input": "",
            "intent": "INTERACT",
            "target": "gas_trap_1",
            "source": "trap_trigger",
        }
    )

    assert patch["intent"] == "TRIGGER_TRAP"
    assert patch["intent_context"]["action_target"] == "gas_trap_1"
    assert patch["intent_context"]["source"] == "trap_trigger"


def test_deepcopy_state_not_required_for_warning_path():
    state = _build_lab_state()
    original = copy.deepcopy(state)

    _warn_about_trap(state)

    assert original["entities"]["gas_trap_1"]["is_hidden"] is True
