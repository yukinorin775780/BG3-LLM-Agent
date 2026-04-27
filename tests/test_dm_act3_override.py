import asyncio
from unittest.mock import patch

from core.graph.nodes.dm import dm_node


def _build_dm_state(user_input: str) -> dict:
    return {
        "intent": "chat",
        "user_input": user_input,
        "active_dialogue_target": "gribbo",
        "time_of_day": "晨曦 (Morning)",
        "map_data": {"id": "necromancer_lab"},
        "flags": {},
        "entities": {
            "player": {"name": "玩家", "faction": "player", "status": "alive", "hp": 20},
            "astarion": {"name": "Astarion", "faction": "party", "status": "alive", "hp": 12},
            "shadowheart": {"name": "Shadowheart", "faction": "party", "status": "alive", "hp": 10},
            "gribbo": {"name": "Gribbo", "faction": "neutral", "status": "alive", "hp": 18},
        },
        "environment_objects": {},
    }


def _dialogue_reply_analysis() -> dict:
    return {
        "action_type": "DIALOGUE_REPLY",
        "difficulty_class": 0,
        "reason": "scripted_dialogue_reply",
        "is_probing_secret": False,
        "responders": ["gribbo"],
        "affection_changes": {},
        "flags_changed": {},
        "item_transfers": [],
        "hp_changes": [],
        "action_actor": "player",
        "action_target": "gribbo",
    }


def test_dm_node_overrides_act3_side_choice_to_party_turn_chat():
    state = _build_dm_state("阿斯代伦说得对，我们一起嘲笑 Gribbo。")
    with patch("core.graph.nodes.dm.analyze_intent", return_value=_dialogue_reply_analysis()):
        result = asyncio.run(dm_node(state))

    assert result["intent"] == "CHAT"
    assert result["current_speaker"] == "astarion"
    assert result["speaker_queue"] == ["shadowheart"]
    assert result["intent_context"]["act3_choice"] == "side_with_astarion"
    assert result["flags"]["necromancer_lab_player_sided_with_astarion"] is True


def test_dm_node_keeps_dialogue_reply_for_non_act3_input():
    state = _build_dm_state("把钥匙给我。")
    with patch("core.graph.nodes.dm.analyze_intent", return_value=_dialogue_reply_analysis()):
        result = asyncio.run(dm_node(state))

    assert result["intent"] == "DIALOGUE_REPLY"
    assert result["current_speaker"] == "gribbo"
    assert result["speaker_queue"] == []
