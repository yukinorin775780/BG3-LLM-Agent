import asyncio

from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.event_drain import event_drain_node
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


def _reveal_trap_with_astarion(state: dict) -> dict:
    state = {
        **state,
        "user_input": "前面的走廊安全吗？",
        "intent": "chat",
        "pending_events": [],
        "speaker_responses": [],
    }
    dm_patch = {
        "intent": "CHAT",
        "current_speaker": "astarion",
        "speaker_queue": [],
        "intent_context": {
            "trap_awareness_context": {
                "topic": "poison_trap",
                "trap_id": "gas_trap_1",
                "actor_id": "astarion",
                "can_detect": True,
                "can_disarm": True,
                "revealed": False,
                "disarmed": False,
                "triggered": False,
            }
        },
    }
    after_dm = {**state, **dm_patch}
    invocation_patch = asyncio.run(actor_invocation_node(after_dm))
    after_invocation = {**after_dm, **invocation_patch}
    drain_patch = event_drain_node(after_invocation)
    return {**after_invocation, **drain_patch}


def test_act2_astarion_warning_sets_act2_perception_flags():
    state = _reveal_trap_with_astarion(_lab_state())

    assert state["flags"]["act2_corridor_entered"] is True
    assert state["flags"]["act2_astarion_perception_checked"] is True
    assert state["flags"]["act2_astarion_perception_success"] is True
    assert state["flags"]["act2_gas_trap_revealed"] is True
    assert state["flags"]["necromancer_lab_poison_trap_revealed"] is True
    assert any("[陷阱感知] astarion -> gas_trap_1" in line for line in state["journal_events"])


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
    assert result["raw_roll_data"]["result"]["result_type"] == "MISSING_KEY"
    assert any("lab_key" in line for line in result["journal_events"])


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
