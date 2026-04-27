from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

from core.actors.registry import get_default_actor_registry
from core.campaigns.necromancer_lab import (
    ACT3_CHOICE_REBUKE_ASTARION,
    ACT3_CHOICE_SIDE_WITH_ASTARION,
    detect_lab_act3_choice,
)
from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.event_drain import event_drain_node


def _build_act3_state(user_input: str) -> dict:
    return {
        "current_speaker": "astarion",
        "speaker_queue": ["shadowheart"],
        "intent": "CHAT",
        "intent_context": {
            "action_actor": "player",
            "action_target": "gribbo",
        },
        "active_dialogue_target": "gribbo",
        "user_input": user_input,
        "turn_count": 42,
        "current_location": "necromancer_lab",
        "map_data": {"id": "necromancer_lab"},
        "flags": {},
        "entities": {
            "player": {
                "name": "玩家",
                "faction": "player",
                "status": "alive",
                "hp": 20,
                "max_hp": 20,
                "inventory": {},
                "x": 2,
                "y": 2,
            },
            "astarion": {
                "name": "Astarion",
                "faction": "party",
                "status": "alive",
                "hp": 12,
                "max_hp": 12,
                "affection": 0,
                "inventory": {"dagger": 1},
                "dynamic_states": {
                    "affection": {"current_value": 0},
                },
            },
            "shadowheart": {
                "name": "Shadowheart",
                "faction": "party",
                "status": "alive",
                "hp": 11,
                "max_hp": 11,
                "inventory": {"private_relic": 1},
            },
            "laezel": {
                "name": "Laezel",
                "faction": "party",
                "status": "alive",
                "hp": 13,
                "max_hp": 13,
                "inventory": {},
            },
            "gribbo": {
                "name": "Gribbo",
                "faction": "neutral",
                "status": "alive",
                "hp": 18,
                "max_hp": 18,
                "inventory": {"heavy_iron_key": 1},
                "dynamic_states": {
                    "patience": {"current_value": 15},
                    "fear": {"current_value": 5},
                },
            },
        },
        "pending_events": [],
        "speaker_responses": [],
        "messages": [],
        "flags": {"world_necromancer_lab_intro_entered": True},
    }


def test_detect_lab_act3_choice_parser_handles_side_and_rebuke():
    side_state = {
        "map_data": {"id": "necromancer_lab"},
        "active_dialogue_target": "gribbo",
        "user_input": "阿斯代伦说得对，我们一起嘲笑这个自大的地精。",
    }
    rebuke_state = {
        "map_data": {"id": "necromancer_lab"},
        "active_dialogue_target": "gribbo",
        "user_input": "阿斯代伦，闭嘴，别再拱火了。",
    }
    key_request_state = {
        "map_data": {"id": "necromancer_lab"},
        "active_dialogue_target": "gribbo",
        "user_input": "把钥匙给我。",
    }

    assert detect_lab_act3_choice(side_state) == ACT3_CHOICE_SIDE_WITH_ASTARION
    assert detect_lab_act3_choice(rebuke_state) == ACT3_CHOICE_REBUKE_ASTARION
    assert detect_lab_act3_choice(key_request_state) == ""


def test_act3_side_with_astarion_updates_state_via_event_drain():
    state = _build_act3_state("阿斯代伦说得对，我们一起嘲笑 Gribbo。")

    class _FakeRetriever:
        def retrieve_for_actor(self, query):
            _ = query
            return []

        def retrieve_for_director(self, query):
            _ = query
            return []

    fake_memory_service = Mock()
    fake_memory_service.retriever = _FakeRetriever()
    with patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        invocation_patch = asyncio.run(
            actor_invocation_node(
                state,
                actor_registry=get_default_actor_registry(),
            )
        )

    assert invocation_patch["actor_invocation_mode"] == "runtime"
    assert invocation_patch["actor_invocation_reason"] == "party_turn_runtime_multi"
    assert invocation_patch["speaker_queue"] == []

    patched_state = {**state, **invocation_patch}
    drain_patch = event_drain_node(patched_state)

    assert drain_patch["entities"]["astarion"]["affection"] == 2
    assert any(
        "玩家与我一起嘲笑了 Gribbo" in item
        for item in drain_patch["actor_runtime_state"]["astarion"]["memory_notes"]
    )
    gribbo = drain_patch["entities"]["gribbo"]
    assert gribbo["faction"] == "hostile"
    assert gribbo["dynamic_states"]["patience"]["current_value"] == 0
    assert drain_patch["combat_phase"] == "IN_COMBAT"
    assert drain_patch["combat_active"] is True
    assert "gribbo" in drain_patch["initiative_order"]
    assert drain_patch["flags"]["necromancer_lab_player_sided_with_astarion"] is True
    assert "shadowheart" not in drain_patch["actor_runtime_state"]
    assert "laezel" not in drain_patch["actor_runtime_state"]


def test_act3_rebuke_astarion_still_triggers_combat_due_to_paranoia():
    state = _build_act3_state("阿斯代伦，闭嘴。别再嘲笑他了。")

    class _FakeRetriever:
        def retrieve_for_actor(self, query):
            _ = query
            return []

        def retrieve_for_director(self, query):
            _ = query
            return []

    fake_memory_service = Mock()
    fake_memory_service.retriever = _FakeRetriever()

    with patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        invocation_patch = asyncio.run(
            actor_invocation_node(
                state,
                actor_registry=get_default_actor_registry(),
            )
        )

    patched_state = {**state, **invocation_patch}
    drain_patch = event_drain_node(patched_state)

    assert drain_patch["entities"]["astarion"]["affection"] == -3
    assert any(
        "玩家当众训斥了我" in item
        for item in drain_patch["actor_runtime_state"]["astarion"]["memory_notes"]
    )
    assert drain_patch["flags"]["necromancer_lab_player_sided_with_astarion"] is False
    assert drain_patch["flags"]["necromancer_lab_gribbo_combat_triggered"] is True
    gribbo = drain_patch["entities"]["gribbo"]
    assert gribbo["faction"] == "hostile"
    assert gribbo["dynamic_states"]["patience"]["current_value"] == 0
    assert gribbo["dynamic_states"]["paranoia"]["current_value"] >= 1
    assert drain_patch["combat_active"] is True
    assert any("paranoia" in event for event in drain_patch.get("journal_events", []))
