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
    with patch("core.graph.nodes.dm.analyze_intent", side_effect=AssertionError("should not call llm")):
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


def test_dm_node_overrides_act4_post_combat_banter_to_party_turn_chat():
    state = _build_dm_state("钥匙拿到了，快离开这鬼地方。")
    state["flags"] = {
        "world_necromancer_lab_gribbo_defeated": True,
        "necromancer_lab_gribbo_key_looted": True,
    }
    state["player_inventory"] = {"heavy_iron_key": 1}
    state["active_dialogue_target"] = None

    with patch("core.graph.nodes.dm.analyze_intent", return_value=_dialogue_reply_analysis()) as mocked_llm:
        result = asyncio.run(dm_node(state))

    mocked_llm.assert_called_once()
    assert result["intent"] == "CHAT"
    assert result["current_speaker"] == "astarion"
    assert result["speaker_queue"] == ["shadowheart", "laezel"]
    assert result["intent_context"]["act4_post_combat_banter"] is True


def test_dm_node_structured_chat_to_gribbo_routes_without_llm_timeout():
    state = _build_dm_state("")
    state["intent"] = "CHAT"
    state["target"] = "gribbo"
    state["source"] = "interaction"
    state["active_dialogue_target"] = None
    state["intent_context"] = {"action_target": "gribbo", "source": "interaction"}
    with patch("core.graph.nodes.dm.analyze_intent", side_effect=AssertionError("should not call llm")):
        result = asyncio.run(dm_node(state))

    assert result["intent"] == "START_DIALOGUE"
    assert result["intent_context"]["action_target"] == "gribbo"
    assert result["active_dialogue_target"] == "gribbo"


def test_dm_node_plain_chat_does_not_force_structured_dialogue_from_active_target():
    state = _build_dm_state("移动到 13,11。")
    state["active_dialogue_target"] = "gribbo"
    move_analysis = {
        "action_type": "MOVE",
        "difficulty_class": 0,
        "reason": "scripted_move",
        "is_probing_secret": False,
        "responders": ["player"],
        "affection_changes": {},
        "flags_changed": {},
        "item_transfers": [],
        "hp_changes": [],
        "action_actor": "player",
        "action_target": "13,11",
    }

    with patch("core.graph.nodes.dm.analyze_intent", return_value=move_analysis) as mocked_llm:
        result = asyncio.run(dm_node(state))

    mocked_llm.assert_called_once()
    assert result["intent"] == "MOVE"
    assert result["intent_context"]["action_target"] == "13,11"


def test_dm_node_structured_read_diary_never_uses_player_as_current_speaker():
    state = _build_dm_state("")
    state["intent"] = "READ"
    state["target"] = "necromancer_diary"
    state["source"] = "interaction"
    state["active_dialogue_target"] = None
    state["intent_context"] = {"action_target": "necromancer_diary", "source": "interaction"}
    with patch("core.graph.nodes.dm.analyze_intent", side_effect=AssertionError("should not call llm")):
        result = asyncio.run(dm_node(state))

    assert result["intent"] == "READ"
    assert result["current_speaker"] != "player"
    assert result["intent_context"]["action_target"] == "necromancer_diary"


def test_dm_node_structured_interact_door_never_uses_player_as_current_speaker():
    state = _build_dm_state("打开门")
    state["intent"] = "INTERACT"
    state["target"] = "heavy_oak_door_1"
    state["source"] = "interaction"
    state["active_dialogue_target"] = None
    state["intent_context"] = {"action_target": "heavy_oak_door_1", "source": "interaction"}
    with patch("core.graph.nodes.dm.analyze_intent", side_effect=AssertionError("should not call llm")):
        result = asyncio.run(dm_node(state))

    assert result["intent"] == "INTERACT"
    assert result["current_speaker"] != "player"
    assert result["intent_context"]["action_target"] == "heavy_oak_door_1"
