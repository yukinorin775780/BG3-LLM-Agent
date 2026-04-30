"""
Application service 保护性测试。
锁定空存档 Genesis、常规聊天推进和返回 JSON 契约。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from langgraph.graph import START

from core.application.game_service import GameService, process_chat_turn


class _AsyncContextManager:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeGraph:
    def __init__(self, snapshots, invoke_result):
        self._snapshots = list(snapshots)
        self._invoke_result = invoke_result
        self.aupdate_state_calls = []
        self.ainvoke_calls = []

    async def aget_state(self, config):
        values = self._snapshots.pop(0)
        return SimpleNamespace(values=values)

    async def aupdate_state(self, config, payload, as_node):
        self.aupdate_state_calls.append(
            {"config": config, "payload": payload, "as_node": as_node}
        )

    async def ainvoke(self, payload, config):
        self.ainvoke_calls.append({"payload": payload, "config": config})
        return self._invoke_result


def test_process_chat_turn_initializes_empty_checkpoint_then_invokes_graph():
    initial_world_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2},
        "journal_events": ["Genesis created"],
        "current_location": "camp_center",
        "environment_objects": {"iron_chest": {"status": "locked"}},
    }
    final_state = {
        "speaker_responses": [("shadowheart", "风停了。")],
        "journal_events": ["Genesis created", "Shadowheart spoke"],
        "current_location": "camp_center",
        "environment_objects": {"iron_chest": {"status": "locked"}},
        "entities": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2},
    }
    fake_graph = _FakeGraph(
        snapshots=[{}, initial_world_state],
        invoke_result=final_state,
    )
    build_graph = Mock(return_value=fake_graph)
    saver_factory = Mock(return_value=_AsyncContextManager(value=object()))
    initial_state_factory = Mock(return_value=initial_world_state)

    result = asyncio.run(
        process_chat_turn(
            user_input="你好",
            intent=None,
            session_id="session-1",
            character=None,
            saver_factory=saver_factory,
            graph_builder=build_graph,
            initial_state_factory=initial_state_factory,
        )
    )

    saver_factory.assert_called_once_with("memory.db")
    build_graph.assert_called_once()
    initial_state_factory.assert_called_once_with()
    assert fake_graph.aupdate_state_calls == [
        {
            "config": {"configurable": {"thread_id": "session-1"}},
            "payload": initial_world_state,
            "as_node": START,
        }
    ]
    assert fake_graph.ainvoke_calls == [
        {
            "payload": {"user_input": "你好", "intent": "chat", "target": "", "source": ""},
            "config": {"configurable": {"thread_id": "session-1"}},
        }
    ]
    assert result == {
        "responses": [{"speaker": "shadowheart", "text": "风停了。"}],
        "journal_events": ["Shadowheart spoke"],
        "current_location": "camp_center",
        "environment_objects": {"iron_chest": {"status": "locked"}},
        "party_status": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2},
        "combat_state": {
            "combat_active": False,
            "initiative_order": [],
            "current_turn_index": 0,
            "turn_resources": {},
            "recent_barks": [],
        },
    }


def test_process_chat_turn_uses_existing_checkpoint_for_regular_dialogue():
    existing_state = {
        "entities": {"astarion": {"hp": 15}},
        "journal_events": ["old event"],
    }
    final_state = {
        "speaker_responses": [("astarion", "多么有趣。")],
        "journal_events": ["old event", "Astarion replied"],
        "current_location": "camp_fire",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "entities": {"astarion": {"hp": 15}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result=final_state)

    result = asyncio.run(
        process_chat_turn(
            user_input="说点什么",
            intent="chat",
            session_id="session-2",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert fake_graph.aupdate_state_calls == []
    assert fake_graph.ainvoke_calls == [
        {
            "payload": {"user_input": "说点什么", "intent": "chat", "target": "", "source": ""},
            "config": {"configurable": {"thread_id": "session-2"}},
        }
    ]
    assert result == {
        "responses": [{"speaker": "astarion", "text": "多么有趣。"}],
        "journal_events": ["Astarion replied"],
        "current_location": "camp_fire",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "party_status": {"astarion": {"hp": 15}},
        "player_inventory": {},
        "combat_state": {
            "combat_active": False,
            "initiative_order": [],
            "current_turn_index": 0,
            "turn_resources": {},
            "recent_barks": [],
        },
    }


def test_process_chat_turn_passes_structured_target_source_into_graph_payload():
    existing_state = {
        "entities": {"player": {"hp": 20}, "gribbo": {"hp": 18}},
        "journal_events": [],
    }
    final_state = {
        "speaker_responses": [("gribbo", "离远点。")],
        "journal_events": ["gribbo replied"],
        "current_location": "necromancer_lab",
        "environment_objects": {},
        "entities": {"player": {"hp": 20}, "gribbo": {"hp": 18}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result=final_state)

    asyncio.run(
        process_chat_turn(
            user_input="",
            intent="CHAT",
            session_id="session-structured-payload",
            character="player",
            map_id="necromancer_lab",
            target="gribbo",
            source="interaction",
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert fake_graph.ainvoke_calls[0]["payload"] == {
        "user_input": "",
        "intent": "CHAT",
        "target": "gribbo",
        "source": "interaction",
        "intent_context": {
            "action_actor": "player",
            "action_target": "gribbo",
            "source": "interaction",
        },
    }


def test_process_chat_turn_init_sync_initializes_empty_checkpoint_with_map_id():
    initial_world_state = {
        "entities": {"gribbo": {"hp": 18}},
        "player_inventory": {"healing_potion": 2},
        "journal_events": [],
        "current_location": "死灵法师的废弃实验室",
        "environment_objects": {},
    }
    fake_graph = _FakeGraph(
        snapshots=[{}, initial_world_state],
        invoke_result={},
    )
    build_graph = Mock(return_value=fake_graph)
    saver_factory = Mock(return_value=_AsyncContextManager(value=object()))
    initial_state_factory = Mock(return_value=initial_world_state)

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-necromancer-map",
            character=None,
            map_id="necromancer_lab",
            saver_factory=saver_factory,
            graph_builder=build_graph,
            initial_state_factory=initial_state_factory,
        )
    )

    initial_state_factory.assert_called_once_with(map_id="necromancer_lab")
    assert fake_graph.aupdate_state_calls == [
        {
            "config": {"configurable": {"thread_id": "session-necromancer-map"}},
            "payload": initial_world_state,
            "as_node": START,
        }
    ]
    assert result["current_location"] == "死灵法师的废弃实验室"


def test_process_chat_turn_init_sync_applies_necromancer_lab_intro_awareness_once():
    initial_world_state = {
        "entities": {
            "shadowheart": {
                "hp": 10,
                "status_effects": [],
                "ability_scores": {"WIS": 15},
            },
            "astarion": {
                "hp": 12,
                "status_effects": [],
                "ability_scores": {"DEX": 17, "WIS": 10},
            },
        },
        "player_inventory": {"healing_potion": 2},
        "journal_events": [],
        "flags": {},
        "map_data": {"id": "necromancer_lab"},
        "current_location": "死灵法师的废弃实验室",
        "environment_objects": {
            "gas_trap_1": {"entity_type": "trap", "is_hidden": True}
        },
    }
    intro_applied_state = {
        **initial_world_state,
        "flags": {
            "necromancer_lab_intro_seen": True,
            "world_necromancer_lab_intro_entered": True,
        },
        "journal_events": [
            "🧪 [实验室] 空气里弥漫着刺鼻的化学与腐败气味。",
            "🗣️ [Astarion] 小心，前面有毒气机关的痕迹。",
            "🗣️ [Shadowheart] 这里有死灵残留……我感觉很不对劲。",
        ],
        "entities": {
            "shadowheart": {
                "hp": 10,
                "status_effects": [{"type": "tense", "duration": 3}],
                "ability_scores": {"WIS": 15},
            },
            "astarion": {
                "hp": 12,
                "status_effects": [],
                "ability_scores": {"DEX": 17, "WIS": 10},
            },
        },
    }
    fake_graph = _FakeGraph(
        snapshots=[{}, initial_world_state, intro_applied_state],
        invoke_result={},
    )
    build_graph = Mock(return_value=fake_graph)
    saver_factory = Mock(return_value=_AsyncContextManager(value=object()))
    initial_state_factory = Mock(return_value=initial_world_state)

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-necromancer-intro",
            character=None,
            map_id="necromancer_lab",
            saver_factory=saver_factory,
            graph_builder=build_graph,
            initial_state_factory=initial_state_factory,
        )
    )

    assert len(fake_graph.aupdate_state_calls) == 2
    assert fake_graph.aupdate_state_calls[0]["payload"] == initial_world_state
    intro_payload = fake_graph.aupdate_state_calls[1]["payload"]
    assert intro_payload["flags"]["necromancer_lab_intro_seen"] is True
    assert any(
        "Astarion" in line and ("陷阱" in line or "机关" in line)
        for line in intro_payload["journal_events"]
    )
    # P0-3: init_sync no longer leaks intro journal entries into the response.
    # The intro is still persisted in state, just not surfaced in the API delta.
    assert result["journal_events"] == []
    assert "gas_trap_1" not in result["environment_objects"]


def test_process_chat_turn_init_sync_without_map_id_keeps_default_goblin_camp():
    initial_world_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2},
        "journal_events": [],
        "map_data": {"id": "goblin_camp"},
        "current_location": "地精营地",
        "environment_objects": {},
    }
    fake_graph = _FakeGraph(
        snapshots=[{}, initial_world_state],
        invoke_result={},
    )

    def _initial_state_factory(map_id: str = "goblin_camp"):
        _ = map_id
        return initial_world_state

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-default-map",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=_initial_state_factory,
        )
    )

    persisted = fake_graph.aupdate_state_calls[0]["payload"]
    assert persisted["map_data"]["id"] == "goblin_camp"
    assert result["current_location"] == "地精营地"


def test_reset_session_preserves_existing_map_and_returns_quiet_delta():
    existing_state = {
        "entities": {"player": {"hp": 10}},
        "map_data": {"id": "necromancer_lab"},
        "journal_events": ["旧事件"],
    }
    reset_state = {
        "entities": {"player": {"hp": 20}},
        "map_data": {"id": "necromancer_lab"},
        "journal_events": ["开场剧情", "更多日志"],
        "current_location": "死灵法师的废弃实验室",
        "environment_objects": {},
        "player_inventory": {"healing_potion": 2},
    }
    fake_graph = _FakeGraph(
        snapshots=[existing_state, reset_state],
        invoke_result={},
    )
    service = GameService(
        saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
        graph_builder=Mock(return_value=fake_graph),
        initial_state_factory=Mock(return_value=reset_state),
    )

    result = asyncio.run(service.reset_session(session_id="session-reset", map_id=None))

    persisted_payload = fake_graph.aupdate_state_calls[0]["payload"]
    assert persisted_payload["map_data"]["id"] == "necromancer_lab"
    assert result["journal_events"] == []
    assert result["responses"] == []
    assert result["current_location"] == "死灵法师的废弃实验室"


def test_process_chat_turn_init_sync_returns_current_state_without_invoking_graph():
    existing_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2, "gold": 50},
        "journal_events": ["old event"],
        "recent_barks": [
            {
                "entity": "astarion",
                "entity_name": "阿斯代伦 (Astarion)",
                "event_type": "CRITICAL_HIT",
                "target": "地精巡逻兵",
                "text": "漂亮一击",
            }
        ],
        "current_location": "camp_center",
        "environment_objects": {"iron_chest": {"status": "locked"}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-init",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert fake_graph.aupdate_state_calls == []
    assert fake_graph.ainvoke_calls == []
    assert result == {
        "responses": [],
        "journal_events": [],
        "current_location": "camp_center",
        "environment_objects": {"iron_chest": {"status": "locked"}},
        "party_status": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2, "gold": 50},
        "combat_state": {
            "combat_active": False,
            "initiative_order": [],
            "current_turn_index": 0,
            "turn_resources": {},
            "recent_barks": [],
        },
    }


def test_process_chat_turn_surfaces_recent_barks_for_current_turn_only():
    existing_state = {
        "entities": {"astarion": {"hp": 15}},
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
    }
    final_state = {
        "speaker_responses": [],
        "journal_events": ["old event", '💬 [台词] 阿斯代伦 (Astarion): "就这点本事？"'],
        "recent_barks": [
            {
                "entity": "astarion",
                "entity_name": "阿斯代伦 (Astarion)",
                "event_type": "CRITICAL_HIT",
                "target": "地精巡逻兵",
                "text": "就这点本事？",
            }
        ],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "entities": {"astarion": {"hp": 15}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result=final_state)

    result = asyncio.run(
        process_chat_turn(
            user_input="攻击地精",
            intent="ATTACK",
            session_id="session-barks",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert result["journal_events"] == ['💬 [台词] 阿斯代伦 (Astarion): "就这点本事？"']
    assert result["combat_state"]["recent_barks"] == [
        {
            "entity": "astarion",
            "entity_name": "阿斯代伦 (Astarion)",
            "event_type": "CRITICAL_HIT",
            "target": "地精巡逻兵",
            "text": "就这点本事？",
        }
    ]


def test_process_chat_turn_projects_hostile_entities_into_environment_objects():
    existing_state = {
        "entities": {
            "shadowheart": {"hp": 10, "faction": "neutral", "position": "camp_center"},
            "goblin_1": {
                "name": "地精巡逻兵",
                "hp": 7,
                "max_hp": 7,
                "ac": 15,
                "status": "alive",
                "faction": "hostile",
                "position": "camp_center",
                "x": 4,
                "y": 3,
            },
        },
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit", "x": 4, "y": 6}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-hostile",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert result["environment_objects"] == {
        "camp_fire": {"status": "lit", "x": 4, "y": 6},
        "goblin_1": {
            "id": "goblin_1",
            "type": "entity",
            "name": "地精巡逻兵",
            "description": "敌对单位 · HP 7/7 · AC 15 · 位置 camp_center",
            "hp": 7,
            "max_hp": 7,
            "ac": 15,
            "status": "alive",
            "faction": "hostile",
            "position": "camp_center",
            "x": 4,
            "y": 3,
            "inventory": {},
        },
    }


def test_process_chat_turn_filters_hostile_and_neutral_entities_from_party_status():
    existing_state = {
        "entities": {
            "shadowheart": {"hp": 10},
            "villager": {"hp": 8, "faction": "neutral"},
            "goblin_1": {"hp": 0, "faction": "hostile", "status": "dead"},
        },
        "journal_events": [],
        "environment_objects": {},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-party-filter",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert result["party_status"] == {"shadowheart": {"hp": 10}}


def test_process_chat_turn_keeps_known_companions_in_party_status_without_faction():
    existing_state = {
        "entities": {
            "player": {"hp": 20, "x": 4, "y": 9},
            "shadowheart": {"hp": 10, "x": 3, "y": 8},
            "astarion": {"hp": 15, "x": 5, "y": 8},
            "laezel": {"hp": 13, "x": 6, "y": 8},
            "villager": {"hp": 8, "faction": "neutral"},
            "goblin_1": {"hp": 0, "faction": "hostile", "status": "dead"},
        },
        "journal_events": [],
        "environment_objects": {},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-companions",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert result["party_status"] == {
        "player": {"hp": 20, "x": 4, "y": 9},
        "shadowheart": {"hp": 10, "x": 3, "y": 8},
        "astarion": {"hp": 15, "x": 5, "y": 8},
        "laezel": {"hp": 13, "x": 6, "y": 8},
    }


def test_process_chat_turn_ui_loot_transfers_dead_entity_items_to_player_inventory():
    existing_state = {
        "entities": {
            "shadowheart": {"hp": 10, "inventory": {}},
            "goblin_1": {
                "name": "地精巡逻兵",
                "hp": 0,
                "max_hp": 7,
                "status": "dead",
                "faction": "hostile",
                "inventory": {"gold_coin": 5, "scimitar": 1},
            },
        },
        "player_inventory": {"healing_potion": 2},
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
    }
    updated_state = {
        "entities": {
            "shadowheart": {"hp": 10, "inventory": {}},
            "goblin_1": {
                "name": "地精巡逻兵",
                "hp": 0,
                "max_hp": 7,
                "status": "dead",
                "faction": "hostile",
                "inventory": {},
            },
        },
        "player_inventory": {"healing_potion": 2, "gold_coin": 5, "scimitar": 1},
        "journal_events": ["old event", "💰 [搜刮] 玩家 从 地精巡逻兵 上搜刮到了: 金币 x 5, 弯刀 x 1。"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state, updated_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="我要搜刮 goblin_1",
            intent="ui_action_loot",
            session_id="session-ui-loot",
            character="shadowheart",
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    persisted_payload = fake_graph.aupdate_state_calls[0]["payload"]
    assert persisted_payload["player_inventory"] == {
        "healing_potion": 2,
        "gold_coin": 5,
        "scimitar": 1,
    }
    assert persisted_payload["entities"]["goblin_1"]["inventory"] == {}
    assert "玩家 从 地精巡逻兵 上搜刮到了" in persisted_payload["journal_events"][0]
    assert result["player_inventory"] == {
        "healing_potion": 2,
        "gold_coin": 5,
        "scimitar": 1,
    }
    assert result["journal_events"] == ["💰 [搜刮] 玩家 从 地精巡逻兵 上搜刮到了: 金币 x 5, 弯刀 x 1。"]


def test_process_chat_turn_ui_loot_accepts_player_as_valid_character():
    existing_state = {
        "entities": {
            "shadowheart": {"hp": 10, "inventory": {}},
            "goblin_1": {
                "name": "地精巡逻兵",
                "hp": 0,
                "max_hp": 7,
                "status": "dead",
                "faction": "hostile",
                "inventory": {"gold_coin": 5, "scimitar": 1},
            },
        },
        "player_inventory": {"healing_potion": 2},
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
    }
    updated_state = {
        "entities": {
            "shadowheart": {"hp": 10, "inventory": {}},
            "goblin_1": {
                "name": "地精巡逻兵",
                "hp": 0,
                "max_hp": 7,
                "status": "dead",
                "faction": "hostile",
                "inventory": {},
            },
        },
        "player_inventory": {"healing_potion": 2, "gold_coin": 5, "scimitar": 1},
        "journal_events": ["old event", "📦 [系统裁定] 玩家搜刮了 地精巡逻兵，获得了 金币 x 5, 弯刀 x 1。"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state, updated_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="我要搜刮 goblin_1",
            intent="ui_action_loot",
            session_id="session-ui-loot-player",
            character="player",
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    persisted_payload = fake_graph.aupdate_state_calls[0]["payload"]
    assert persisted_payload["player_inventory"] == {
        "healing_potion": 2,
        "gold_coin": 5,
        "scimitar": 1,
    }
    assert result["player_inventory"] == {
        "healing_potion": 2,
        "gold_coin": 5,
        "scimitar": 1,
    }


def test_process_chat_turn_ui_loot_necromancer_gribbo_key_drains_event_before_persist():
    existing_state = {
        "map_data": {"id": "necromancer_lab"},
        "flags": {"world_necromancer_lab_gribbo_defeated": True},
        "entities": {
            "player": {"hp": 20, "inventory": {}, "x": 4, "y": 9},
            "gribbo": {
                "name": "Gribbo",
                "hp": 18,
                "max_hp": 18,
                "status": "alive",
                "faction": "hostile",
                "x": 4,
                "y": 9,
                "inventory": {"heavy_iron_key": 1},
            },
        },
        "player_inventory": {},
        "journal_events": [],
        "current_location": "necromancer_lab",
        "environment_objects": {},
    }
    updated_state = {
        "map_data": {"id": "necromancer_lab"},
        "flags": {
            "world_necromancer_lab_gribbo_defeated": True,
            "necromancer_lab_gribbo_key_looted": True,
        },
        "entities": {
            "player": {"hp": 20, "inventory": {}, "x": 4, "y": 9},
            "gribbo": {
                "name": "Gribbo",
                "hp": 0,
                "max_hp": 18,
                "status": "dead",
                "faction": "hostile",
                "x": 4,
                "y": 9,
                "inventory": {},
            },
        },
        "player_inventory": {"heavy_iron_key": 1},
        "pending_events": [],
        "journal_events": ["💰 [搜刮] 玩家 从 Gribbo 身上搜刮到了: heavy_iron_key x 1。"],
        "current_location": "necromancer_lab",
        "environment_objects": {},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state, updated_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="loot gribbo",
            intent="ui_action_loot",
            session_id="session-ui-loot-necromancer-gribbo",
            character="player",
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    persisted_payload = fake_graph.aupdate_state_calls[0]["payload"]
    assert persisted_payload["player_inventory"].get("heavy_iron_key", 0) == 1
    assert persisted_payload["entities"]["gribbo"]["inventory"].get("heavy_iron_key", 0) == 0
    assert persisted_payload["pending_events"] == []
    assert persisted_payload["flags"]["necromancer_lab_gribbo_key_looted"] is True
    assert result["player_inventory"].get("heavy_iron_key", 0) == 1


def test_process_chat_turn_process_reflections_handles_runtime_queue_without_graph_invoke():
    existing_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "reflection_queue": [
            {
                "actor_id": "shadowheart",
                "reason": "need to reassess trust",
                "priority": 1,
                "source_turn": 7,
                "payload": {"topic": "trust"},
            }
        ],
        "pending_events": [],
        "actor_runtime_state": {},
    }
    updated_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "journal_events": [
            "old event",
            "🧠 [认知] shadowheart 的内部信念发生了变化。",
            "🧠 [记忆] shadowheart 记录了一条私有记忆。",
        ],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "reflection_queue": [],
        "pending_events": [],
        "actor_runtime_state": {
            "shadowheart": {"beliefs": ["我需要重新评估: need to reassess trust"]}
        },
    }
    fake_graph = _FakeGraph(snapshots=[existing_state, updated_state], invoke_result={})

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="process_reflections",
            session_id="session-reflections",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert fake_graph.ainvoke_calls == []
    persisted_payload = fake_graph.aupdate_state_calls[0]["payload"]
    assert persisted_payload["reflection_queue"] == []
    assert persisted_payload["pending_events"] == []
    assert "actor_runtime_state" in persisted_payload
    assert result["journal_events"] == [
        "🧠 [认知] shadowheart 的内部信念发生了变化。",
        "🧠 [记忆] shadowheart 记录了一条私有记忆。",
    ]


def test_process_chat_turn_background_step_processes_up_to_three_reflections():
    existing_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "reflection_queue": [
            {
                "actor_id": "shadowheart",
                "reason": "r1",
                "priority": 1,
                "source_turn": 1,
                "payload": {},
            },
            {
                "actor_id": "shadowheart",
                "reason": "r2",
                "priority": 1,
                "source_turn": 2,
                "payload": {},
            },
            {
                "actor_id": "shadowheart",
                "reason": "r3",
                "priority": 1,
                "source_turn": 3,
                "payload": {},
            },
            {
                "actor_id": "shadowheart",
                "reason": "r4",
                "priority": 1,
                "source_turn": 4,
                "payload": {},
            },
        ],
        "pending_events": [],
        "actor_runtime_state": {},
    }
    updated_state = {
        "entities": {"shadowheart": {"hp": 10}},
        "journal_events": ["old event"],
        "current_location": "camp_center",
        "environment_objects": {"camp_fire": {"status": "lit"}},
        "reflection_queue": [
            {
                "actor_id": "shadowheart",
                "reason": "r4",
                "priority": 1,
                "source_turn": 4,
                "payload": {},
            }
        ],
        "pending_events": [],
        "actor_runtime_state": {},
    }
    fake_graph = _FakeGraph(snapshots=[existing_state, updated_state], invoke_result={})

    asyncio.run(
        process_chat_turn(
            user_input="",
            intent="background_step",
            session_id="session-background-step",
            character=None,
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(),
        )
    )

    assert fake_graph.ainvoke_calls == []
    persisted_payload = fake_graph.aupdate_state_calls[0]["payload"]
    assert len(persisted_payload["reflection_queue"]) == 1
    assert persisted_payload["reflection_queue"][0]["reason"] == "r4"


# ═══════════════════════════════════════════════════════════════
# P0 Backend Fix Tests
# ═══════════════════════════════════════════════════════════════


def test_p0_gribbo_render_prompt_succeeds():
    """P0-1: Gribbo's hostile NPC template renders without UndefinedError."""
    from characters.loader import load_character

    ch = load_character("gribbo")
    prompt = ch.render_prompt(
        relationship_score=0,
        affection=0,
        flags={},
        summary="test",
        journal_entries=[],
        inventory_items=["heavy_iron_key", "scroll_of_firebolt"],
        has_healing_potion=False,
        time_of_day="晨曦",
        hp=18,
        active_buffs=[],
        shar_faith=None,
        memory_awakening=None,
    )
    assert len(prompt) > 100
    # Template must reference Gribbo's personality traits
    assert "arrogant" in prompt.lower() or "genius" in prompt.lower()
    # Template must reference the secret_objective
    assert "iron key" in prompt.lower() or "password" in prompt.lower()


def test_p0_gribbo_render_does_not_break_astarion():
    """P0-1 regression: existing companions must still render via persona_template."""
    from characters.loader import load_character

    for name in ("astarion", "shadowheart"):
        ch = load_character(name)
        prompt = ch.render_prompt(
            relationship_score=0,
            affection=0,
            flags={},
            summary="test",
            journal_entries=[],
            inventory_items=[],
            has_healing_potion=False,
        )
        assert len(prompt) > 100


def test_p0_init_sync_returns_empty_journal_on_fresh_necromancer_lab():
    """P0-3: init_sync must return journal_events=[] even when campaign intro fires."""
    initial_world_state = {
        "entities": {
            "shadowheart": {
                "hp": 10,
                "status_effects": [],
                "ability_scores": {"WIS": 15},
            },
            "astarion": {
                "hp": 12,
                "status_effects": [],
                "ability_scores": {"DEX": 17, "WIS": 10},
            },
        },
        "player_inventory": {},
        "journal_events": [],
        "flags": {},
        "map_data": {"id": "necromancer_lab"},
        "current_location": "死灵法师的废弃实验室",
        "environment_objects": {},
    }
    # After init: 0 journal entries.  After campaign intro: 3 entries.
    intro_state = {
        **initial_world_state,
        "flags": {
            "necromancer_lab_intro_seen": True,
            "world_necromancer_lab_intro_entered": True,
            "astarion_detected_gas_trap": {"value": True},
            "world_necromancer_lab_trap_warned": True,
            "shadowheart_senses_necromancy": {"value": True},
        },
        "journal_events": [
            "🧪 [实验室] 空气里弥漫着刺鼻的化学与腐败气味。",
            "🗣️ [Astarion] 小心，前面有毒气机关的痕迹。",
            "🗣️ [Shadowheart] 这里有死灵残留……我感觉很不对劲。",
        ],
    }
    fake_graph = _FakeGraph(
        snapshots=[{}, initial_world_state, intro_state],
        invoke_result={},
    )

    result = asyncio.run(
        process_chat_turn(
            user_input="",
            intent="init_sync",
            session_id="session-p0-init-quiet",
            character=None,
            map_id="necromancer_lab",
            saver_factory=Mock(return_value=_AsyncContextManager(value=object())),
            graph_builder=Mock(return_value=fake_graph),
            initial_state_factory=Mock(return_value=initial_world_state),
        )
    )

    # init_sync must NOT leak campaign intro journal entries
    assert result["journal_events"] == []


def test_p0_loot_target_alias_resolves_gribbo():
    """P0-2: Chinese alias '地精' resolves to entity ID 'gribbo'."""
    from core.application.game_service import GameService

    target = GameService._extract_loot_target_id(
        user_input="搜刮地精",
        entities={"gribbo": {"hp": 0}, "player": {"hp": 20}},
        environment_objects={},
    )
    assert target == "gribbo"


def test_p0_loot_target_alias_resolves_chest():
    """P0-2: Chinese alias '箱子' resolves to entity ID 'chest_1'."""
    from core.application.game_service import GameService

    target = GameService._extract_loot_target_id(
        user_input="搜刮箱子",
        entities={"chest_1": {"status": "open"}, "player": {"hp": 20}},
        environment_objects={},
    )
    assert target == "chest_1"


def test_p0_duplicate_gribbo_loot_blocked():
    """P0-2: Second loot of Gribbo must not re-add heavy_iron_key."""
    from core.systems.mechanics import execute_loot_action

    state = {
        "map_data": {"id": "necromancer_lab"},
        "flags": {
            "world_necromancer_lab_gribbo_defeated": True,
            "necromancer_lab_gribbo_key_looted": True,  # already looted once
        },
        "entities": {
            "player": {"hp": 20, "inventory": {}, "x": 4, "y": 9,
                       "name": "玩家", "faction": "player"},
            "gribbo": {
                "name": "Gribbo",
                "hp": 0,
                "max_hp": 18,
                "status": "dead",
                "faction": "hostile",
                "x": 4,
                "y": 9,
                "inventory": {},
            },
        },
        "player_inventory": {"heavy_iron_key": 1},
        "journal_events": [],
        "environment_objects": {},
        "intent_context": {
            "action_actor": "player",
            "action_target": "gribbo",
        },
    }
    result = execute_loot_action(state)
    # Should not add a second key
    assert result.get("player_inventory", {}).get("heavy_iron_key", 0) <= 1
