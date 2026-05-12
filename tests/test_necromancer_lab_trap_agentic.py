import asyncio
import copy

from core.actors.builders import build_actor_view
from core.campaigns.necromancer_lab import detect_trap_awareness_context
from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.dm import dm_node
from core.graph.nodes.event_drain import event_drain_node
from core.systems import mechanics
from core.systems.world_init import get_initial_world_state


def _build_lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    state["flags"] = {}
    state["journal_events"] = []
    state["pending_events"] = []
    state["speaker_responses"] = []
    return state


def _warn_about_trap(state: dict) -> dict:
    state = {
        **state,
        "user_input": "前面安全吗？继续往前走。",
        "intent": "chat",
        "pending_events": [],
        "speaker_responses": [],
    }
    dm_patch = asyncio.run(dm_node(state))
    after_dm = {**state, **dm_patch}
    invocation_patch = asyncio.run(actor_invocation_node(after_dm))
    after_invocation = {**after_dm, **invocation_patch}
    drain_patch = event_drain_node(after_invocation)
    return {**after_invocation, **drain_patch}


def test_trap_awareness_helper_and_initial_actor_view_do_not_leak_hidden_trap():
    state = _build_lab_state()

    context = detect_trap_awareness_context(state, "继续往前走", {})
    player_view = build_actor_view(state, "player")
    astarion_view = build_actor_view(state, "astarion")

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


def test_astarion_warning_reveals_poison_trap_and_writes_journal():
    state = _warn_about_trap(_build_lab_state())

    assert state["flags"]["necromancer_lab_poison_trap_revealed"] is True
    assert state["flags"]["astarion_detected_gas_trap"]["value"] is True
    assert state["environment_objects"]["gas_trap_1"]["is_hidden"] is False
    assert state["entities"]["gas_trap_1"]["is_hidden"] is False
    assert any("[陷阱感知] astarion -> gas_trap_1" in line for line in state["journal_events"])
    assert any("毒气压力板" in text for _, text in state["speaker_responses"])


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
                "action_target": "4,6",
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
                "action_target": "4,6",
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
                "action_target": "4,6",
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


def test_deepcopy_state_not_required_for_warning_path():
    state = _build_lab_state()
    original = copy.deepcopy(state)

    _warn_about_trap(state)

    assert original["entities"]["gas_trap_1"]["is_hidden"] is True
