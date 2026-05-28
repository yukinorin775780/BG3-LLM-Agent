import asyncio
import copy

from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.dm import dm_node
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
    state["messages"] = []
    return state


def _distance_to(state: dict, target_id: str) -> int:
    player = state["entities"]["player"]
    target = state["environment_objects"].get(target_id) or state["entities"][target_id]
    return max(abs(int(player["x"]) - int(target["x"])), abs(int(player["y"]) - int(target["y"])))


def _open_ab_door(state: dict) -> dict:
    return mechanics.execute_interact_action(
        {
            **state,
            "intent": "INTERACT",
            "intent_context": {"action_actor": "player", "action_target": "door_a_to_b"},
        }
    )


def _move_player(state: dict, x: int, y: int) -> dict:
    updated = copy.deepcopy(state)
    updated["entities"]["player"]["x"] = x
    updated["entities"]["player"]["y"] = y
    return updated


def _astarion_reveals_trap(state: dict) -> dict:
    state = {
        **state,
        "user_input": "Astarion，小心检查前面的毒气压力板和 gas_trap_1 陷阱。",
        "intent": "chat",
        "source": "text_input",
        "target": "",
        "pending_events": [],
        "speaker_responses": [],
    }
    after_input = {**state, **input_node(state)}
    after_dm = {**after_input, **asyncio.run(dm_node(after_input))}
    after_invocation = {**after_dm, **asyncio.run(actor_invocation_node(after_dm))}
    return {**after_invocation, **event_drain_node(after_invocation)}


def _run_text_approach(state: dict, text: str) -> dict:
    turn = {
        **state,
        "user_input": text,
        "intent": "chat",
        "source": "text_input",
        "target": "",
    }
    after_input = {**turn, **input_node(turn)}
    return mechanics.execute_move_action(after_input)


def test_ab_door_interact_persists_backend_state_and_act2_flag():
    result = _open_ab_door(_lab_state())

    assert result["entities"]["door_a_to_b"]["status"] == "open"
    assert result["entities"]["door_a_to_b"]["is_open"] is True
    assert result["environment_objects"]["door_a_to_b"]["status"] == "open"
    assert result["environment_objects"]["door_a_to_b"]["is_open"] is True
    assert result["flags"]["act2_corridor_entered"] is True


def test_astarion_near_gas_trap_perception_writes_reveal_flags_status_and_journal():
    state = _move_player({**_lab_state(), **_open_ab_door(_lab_state())}, 5, 12)
    result = _astarion_reveals_trap(state)

    assert result["flags"]["necromancer_lab_poison_trap_revealed"] is True
    assert result["flags"]["act2_gas_trap_revealed"] is True
    assert result["environment_objects"]["gas_trap_1"]["is_hidden"] is False
    assert result["environment_objects"]["gas_trap_1"]["status"] == "revealed"
    assert result["entities"]["gas_trap_1"]["is_hidden"] is False
    assert result["entities"]["gas_trap_1"]["status"] == "revealed"
    assert any("[陷阱感知] astarion -> gas_trap_1" in line for line in result["journal_events"])
    assert any(speaker == "astarion" and "毒气压力板" in text for speaker, text in result["speaker_responses"])


def test_astarion_disarm_after_reveal_disables_trap_and_writes_journal():
    state = _move_player({**_lab_state(), **_open_ab_door(_lab_state())}, 5, 12)
    revealed = _astarion_reveals_trap(state)
    result = mechanics.execute_disarm_action(
        {
            **revealed,
            "intent": "DISARM",
            "intent_context": {"action_actor": "astarion", "action_target": "gas_trap_1"},
        }
    )

    assert result["flags"]["necromancer_lab_poison_trap_disarmed"] is True
    assert result["flags"]["act2_gas_trap_disarmed"] is True
    assert result["environment_objects"]["gas_trap_1"]["status"] == "disabled"
    assert result["environment_objects"]["gas_trap_1"]["is_hidden"] is False
    assert any("[陷阱解除] astarion -> gas_trap_1" in line for line in result["journal_events"])


def test_disabled_gas_trap_does_not_trigger_poison_when_stepped_on():
    state = _move_player({**_lab_state(), **_open_ab_door(_lab_state())}, 5, 12)
    revealed = _astarion_reveals_trap(state)
    disarmed = mechanics.execute_disarm_action(
        {
            **revealed,
            "intent": "DISARM",
            "intent_context": {"action_actor": "astarion", "action_target": "gas_trap_1"},
        }
    )
    result = mechanics.execute_move_action(
        {
            **revealed,
            **disarmed,
            "intent": "MOVE",
            "intent_context": {"action_actor": "player", "action_target": "5,11"},
        }
    )

    assert "necromancer_lab_poison_trap_triggered" not in result["flags"]
    assert all(effect.get("type") != "poisoned" for effect in result["entities"]["player"].get("status_effects", []))
    assert not any("[毒气陷阱] gas_trap_1 triggered" in line for line in result["journal_events"])


def test_text_approach_updates_player_xy_near_door_b_to_d():
    state = _move_player(_lab_state(), 16, 2)
    result = _run_text_approach(state, "走到 door_b_to_d 附近。")

    assert _distance_to(result, "door_b_to_d") <= 1
    assert (result["entities"]["player"]["x"], result["entities"]["player"]["y"]) != (16, 2)
    assert any("[空间移动]" in line for line in result["journal_events"])


def test_text_approach_updates_player_xy_near_heavy_oak_door_1():
    state = _move_player(_lab_state(), 7, 8)
    result = _run_text_approach(state, "走到 heavy_oak_door_1 附近。")

    assert _distance_to(result, "heavy_oak_door_1") <= 1
    assert (result["entities"]["player"]["x"], result["entities"]["player"]["y"]) != (7, 8)
    assert any("[空间移动]" in line for line in result["journal_events"])


def test_input_explicit_heavy_oak_door_target_overrides_active_gribbo_dialogue_target():
    state = {
        **_lab_state(),
        "user_input": "用 heavy_iron_key 打开 heavy_oak_door_1。",
        "intent": "INTERACT",
        "source": "dialogue_input",
        "target": "gribbo",
        "active_dialogue_target": "gribbo",
    }
    result = input_node(state)

    assert result["intent"] == "INTERACT"
    assert result["target"] == "heavy_oak_door_1"
    assert result["intent_context"]["action_target"] == "heavy_oak_door_1"


def test_input_preserves_empty_structured_interact_for_web_ui_door_sync():
    result = input_node(
        {
            **_lab_state(),
            "user_input": "",
            "intent": "INTERACT",
            "source": "interaction",
            "target": "door_a_to_b",
            "intent_context": {
                "action_actor": "player",
                "action_target": "door_a_to_b",
                "source": "interaction",
            },
        }
    )

    assert result["intent"] == "INTERACT"
    assert result["target"] == "door_a_to_b"
    assert result["source"] == "interaction"
    assert result["intent_context"]["action_actor"] == "player"
    assert result["intent_context"]["action_target"] == "door_a_to_b"


def test_door_b_to_d_opens_with_lab_key_after_text_approach():
    state = _move_player(_lab_state(), 16, 2)
    state["player_inventory"]["lab_key"] = 1
    approached = _run_text_approach(state, "走到 door_b_to_d 附近。")
    result = mechanics.execute_interact_action(
        {
            **state,
            **approached,
            "intent": "INTERACT",
            "intent_context": {"action_actor": "player", "action_target": "door_b_to_d"},
        }
    )

    assert result["entities"]["door_b_to_d"]["status"] == "open"
    assert result["entities"]["door_b_to_d"]["is_open"] is True
    assert result["environment_objects"]["door_b_to_d"]["status"] == "open"
    assert result["environment_objects"]["door_b_to_d"]["is_open"] is True


def test_final_exit_opens_with_heavy_iron_key_after_approach_and_clears_demo():
    state = _move_player(_lab_state(), 7, 8)
    state["player_inventory"]["heavy_iron_key"] = 1
    approached = _run_text_approach(state, "走到 heavy_oak_door_1 附近。")
    result = mechanics.execute_interact_action(
        {
            **state,
            **approached,
            "intent": "INTERACT",
            "intent_context": {"action_actor": "player", "action_target": "heavy_oak_door_1"},
        }
    )

    assert result["entities"]["heavy_oak_door_1"]["status"] == "open"
    assert result["entities"]["heavy_oak_door_1"]["is_open"] is True
    assert result["environment_objects"]["heavy_oak_door_1"]["status"] == "open"
    assert result["environment_objects"]["heavy_oak_door_1"]["is_open"] is True
    assert result["flags"]["act4_final_exit_opened"] is True
    assert result["demo_cleared"] is True
