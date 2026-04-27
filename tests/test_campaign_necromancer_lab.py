from unittest.mock import patch

from core.graph.nodes.dialogue import dialogue_node
from core.graph.nodes.event_drain import event_drain_node
from core.systems import mechanics
from core.systems.world_init import get_initial_world_state


def _build_lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    entities = state.get("entities") or {}
    # 统一修正敌对阵营标记，避免 "enemy" 与 "hostile" 的旧卡数据差异影响测试稳定性
    for entity_id in ("goblin_guard_1", "goblin_guard_2"):
        entity = entities.get(entity_id)
        if isinstance(entity, dict):
            entity["faction"] = "hostile"
    state["demo_cleared"] = False
    return state


def test_necromancer_lab_kill_loot_then_interact_clears_demo():
    state = _build_lab_state()
    entities = state["entities"]
    entities["player"]["x"] = 13
    entities["player"]["y"] = 11
    gribbo = entities["gribbo"]
    gribbo["hp"] = 0
    gribbo["status"] = "dead"
    gribbo["inventory"] = {"heavy_iron_key": 1}

    loot_result = mechanics.execute_loot_action(
        {
            **state,
            "intent_context": {
                "action_actor": "player",
                "action_target": "gribbo",
            },
        }
    )

    assert loot_result["player_inventory"].get("heavy_iron_key", 0) == 1
    assert loot_result["entities"]["gribbo"]["inventory"] == {}
    assert any("搜刮" in event for event in loot_result.get("journal_events", []))

    interact_result = mechanics.execute_interact_action(
        {
            **state,
            **{
                **loot_result,
                "entities": {
                    **(loot_result.get("entities") or {}),
                    "player": {
                        **((loot_result.get("entities") or {}).get("player") or {}),
                        "x": 13,
                        "y": 11,
                    },
                },
            },
            "intent_context": {
                "action_actor": "player",
                "action_target": "heavy_oak_door_1",
            },
        }
    )

    door = interact_result["entities"]["heavy_oak_door_1"]
    assert door["is_open"] is True
    assert interact_result.get("demo_cleared") is True
    assert any("DEMO CLEARED" in event for event in interact_result.get("journal_events", []))


def test_necromancer_lab_interact_without_key_fails():
    state = _build_lab_state()
    state["entities"]["player"]["x"] = 13
    state["entities"]["player"]["y"] = 11

    interact_result = mechanics.execute_interact_action(
        {
            **state,
            "intent_context": {
                "action_actor": "player",
                "action_target": "heavy_oak_door_1",
            },
        }
    )

    door = interact_result["entities"]["heavy_oak_door_1"]
    assert door["is_open"] is False
    assert interact_result.get("demo_cleared", False) is False
    assert any("需要一把沉重的铁钥匙" in event for event in interact_result.get("journal_events", []))


def test_necromancer_lab_dialogue_transfer_key_then_interact_clears_demo():
    state = _build_lab_state()
    state["entities"]["player"]["x"] = 13
    state["entities"]["player"]["y"] = 11
    state["entities"]["gribbo"]["faction"] = "neutral"
    state["entities"]["gribbo"]["inventory"] = {"heavy_iron_key": 1}

    start_result = dialogue_node(
        {
            **state,
            "intent": "START_DIALOGUE",
            "intent_context": {
                "action_actor": "player",
                "action_target": "gribbo",
            },
            "user_input": "我想和格里波谈谈",
        }
    )
    assert start_result.get("active_dialogue_target") == "gribbo"

    mocked_dialogue_json = (
        '{"internal_monologue":"",'
        '"reply":"拿去吧，别烦我。",'
        '"trigger_combat": false,'
        '"state_changes":{"patience_delta":0,"fear_delta":0},'
        '"physical_action":{"action_type":"transfer_item","source_id":"gribbo","target_id":"player","item_id":"heavy_iron_key","count":1}}'
    )

    with patch("core.engine.generate_dialogue", return_value=mocked_dialogue_json):
        dialogue_result = dialogue_node(
            {
                **state,
                **start_result,
                "intent": "DIALOGUE_REPLY",
                "intent_context": {
                    "action_actor": "player",
                    "action_target": "gribbo",
                },
                "user_input": "把钥匙给我",
            }
        )

    assert dialogue_result["pending_events"]
    tx_event = dialogue_result["pending_events"][0]
    assert tx_event["event_type"] == "actor_item_transaction_requested"
    assert tx_event["payload"]["transaction"]["transaction_type"] == "transfer"
    assert tx_event["payload"]["transaction"]["from_entity"] == "gribbo"
    assert tx_event["payload"]["transaction"]["to_entity"] == "player"
    assert tx_event["payload"]["transaction"]["item"] == "heavy_iron_key"
    assert dialogue_result["player_inventory"].get("heavy_iron_key", 0) == 0
    assert dialogue_result["entities"]["gribbo"]["inventory"].get("heavy_iron_key", 0) == 1

    drained_patch = event_drain_node(
        {
            **state,
            **start_result,
            **dialogue_result,
        }
    )
    drained_state = {
        **state,
        **start_result,
        **dialogue_result,
        **drained_patch,
    }
    assert drained_state["player_inventory"].get("heavy_iron_key", 0) == 1
    assert drained_state["entities"]["gribbo"]["inventory"].get("heavy_iron_key", 0) == 0
    assert any(
        "heavy_iron_key" in event or "沉重铁钥匙" in event
        for event in drained_state.get("journal_events", [])
    )

    interact_result = mechanics.execute_interact_action(
        {
            **drained_state,
            "intent_context": {
                "action_actor": "player",
                "action_target": "heavy_oak_door_1",
            },
        }
    )

    assert interact_result["entities"]["heavy_oak_door_1"]["is_open"] is True
    assert interact_result.get("demo_cleared") is True
    assert any("DEMO CLEARED" in event for event in interact_result.get("journal_events", []))
