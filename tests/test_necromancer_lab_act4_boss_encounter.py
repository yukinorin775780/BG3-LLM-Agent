import asyncio
from unittest.mock import Mock, patch

from core.actors.registry import get_default_actor_registry
from core.campaigns.necromancer_lab import (
    detect_gribbo_boss_intro_context,
    detect_gribbo_boss_resolution_context,
    detect_gribbo_boss_strategy_context,
)
from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.dm import dm_node
from core.graph.nodes.event_drain import event_drain_node
from core.graph.nodes.mechanics import mechanics_node
from core.systems import mechanics
from core.systems.world_init import get_initial_world_state


def _lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    state["pending_events"] = []
    state["speaker_responses"] = []
    state["messages"] = []
    return state


def _drain_after_mechanics(state: dict, result: dict) -> dict:
    event_patch = event_drain_node({**state, **result})
    merged_journal = list(result.get("journal_events") or [])
    merged_journal.extend(list(event_patch.get("journal_events") or []))
    return {**result, **event_patch, "journal_events": merged_journal}


def _door_obstacle(map_data: dict, door_id: str) -> dict:
    for obstacle in map_data.get("obstacles") or []:
        if obstacle.get("entity_id") == door_id:
            return obstacle
    return {}


def test_boss_intro_helper_exposes_truth_without_key_transfer():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    context = detect_gribbo_boss_intro_context(state, "进入实验室，和 Gribbo 谈谈。", {})

    assert context is not None
    assert context["diary_truth_available"] is True
    assert state["entities"]["gribbo"]["inventory"]["heavy_iron_key"] == 1
    assert "heavy_iron_key" not in state["player_inventory"]


def test_opening_lab_door_sets_act4_room_context_and_syncs_map_obstacle():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["player_inventory"]["lab_key"] = 1
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8

    result = mechanics.execute_interact_action(
        {
            **state,
            "intent_context": {"action_actor": "player", "action_target": "door_b_to_d"},
        }
    )

    assert result["flags"]["act2_corridor_exit_opened_with_key"] is True
    assert result["flags"]["act4_boss_room_entered"] is True
    assert result["flags"]["act4_diary_truth_available"] is True
    assert result["environment_objects"]["door_b_to_d"]["is_open"] is True
    assert result["environment_objects"]["door_b_to_d"]["is_locked"] is False
    obstacle = _door_obstacle(result["map_data"], "door_b_to_d")
    assert obstacle["is_open"] is True
    assert obstacle["is_locked"] is False
    assert obstacle["status"] == "open"
    assert obstacle["blocks_movement"] is False


def test_open_lab_door_no_longer_reports_missing_lab_key():
    state = _lab_state()
    state["entities"]["player"]["x"] = 5
    state["entities"]["player"]["y"] = 8
    for bucket_name in ("entities", "environment_objects"):
        state[bucket_name]["door_b_to_d"]["is_open"] = True
        state[bucket_name]["door_b_to_d"]["is_locked"] = False
        state[bucket_name]["door_b_to_d"]["status"] = "open"

    result = mechanics.execute_interact_action(
        {
            **state,
            "intent_context": {"action_actor": "player", "action_target": "door_b_to_d"},
        }
    )

    assert result["raw_roll_data"]["result"]["result_type"] == "ALREADY_OPEN"
    assert result["raw_roll_data"]["result"]["is_success"] is True
    assert not any("需要 lab_key" in line for line in result["journal_events"])


def test_party_strategy_after_lab_door_open_context_needs_no_extra_gribbo_intro_text():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["flags"]["act4_boss_room_entered"] = True
    state["flags"]["act4_diary_truth_available"] = True
    turn_state = {
        **state,
        "user_input": "我们怎么处理 Gribbo？",
        "intent": "CHAT",
        "target": "gribbo",
        "source": "boss_strategy",
    }

    context = detect_gribbo_boss_strategy_context(turn_state, turn_state["user_input"], {})
    dm_patch = asyncio.run(dm_node(turn_state))

    assert context is not None
    assert dm_patch["intent_context"]["reason"] == "act4_gribbo_boss_strategy"
    assert dm_patch["flags"]["act4_gribbo_confrontation_started"] is True
    assert dm_patch["current_speaker"] == "astarion"
    assert dm_patch["speaker_queue"] == ["shadowheart", "laezel"]


def test_party_strategy_text_with_gribbo_name_still_routes_after_intro_started():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["flags"]["act4_boss_room_entered"] = True
    state["flags"]["act4_gribbo_confrontation_started"] = True
    state["active_dialogue_target"] = "gribbo"
    turn_state = {
        **state,
        "user_input": "我们怎么处理 Gribbo？",
        "intent": "CHAT",
        "target": "gribbo",
        "source": "boss_strategy",
    }

    dm_patch = asyncio.run(dm_node(turn_state))

    assert dm_patch["intent_context"]["reason"] == "act4_gribbo_boss_strategy"
    assert dm_patch["current_speaker"] == "astarion"
    assert dm_patch["speaker_queue"] == ["shadowheart", "laezel"]


def test_party_strategy_split_uses_runtime_metadata_journal():
    state = _lab_state()
    state["flags"]["act4_gribbo_confrontation_started"] = True
    context = detect_gribbo_boss_strategy_context(state, "我们怎么处理他？怎么拿钥匙？", {})
    assert context is not None

    turn_state = {**state, "user_input": "我们怎么处理他？怎么拿钥匙？"}
    dm_patch = asyncio.run(dm_node(turn_state))
    routed = {**turn_state, **dm_patch}

    class _FakeRetriever:
        def retrieve_for_actor(self, query):
            _ = query
            return []

        def retrieve_for_director(self, query):
            _ = query
            return []

    fake_memory_service = Mock()
    fake_memory_service.retriever = _FakeRetriever()
    with patch("core.actors.executor.get_default_memory_service", return_value=fake_memory_service):
        invocation_patch = asyncio.run(
            actor_invocation_node(routed, actor_registry=get_default_actor_registry())
        )

    drained = event_drain_node({**routed, **invocation_patch})
    assert "[Boss方案] astarion -> steal_key" in drained["journal_events"]
    assert "[Boss方案] shadowheart -> contain_corruption" in drained["journal_events"]
    assert "[Boss方案] laezel -> execute" in drained["journal_events"]
    assert "heavy_iron_key" not in drained.get("player_inventory", {})


def test_party_strategy_after_decoded_diary_is_not_overridden_by_diary_pressure():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["flags"]["act4_gribbo_confrontation_started"] = True
    turn_state = {**state, "user_input": "我们怎么处理他？队友们有什么建议，怎么拿钥匙？"}

    dm_patch = asyncio.run(dm_node(turn_state))
    routed = {**turn_state, **dm_patch}

    assert routed["intent_context"]["reason"] == "act4_gribbo_boss_strategy"
    assert routed["intent_context"]["gribbo_boss_strategy_context"]["stances"] == {
        "astarion": "steal_key",
        "shadowheart": "contain_corruption",
        "laezel": "execute",
    }
    assert routed["intent_context"].get("diary_negotiation_context") == {}
    assert routed["current_speaker"] == "astarion"
    assert routed["speaker_queue"] == ["shadowheart", "laezel"]

    class _FakeRetriever:
        def retrieve_for_actor(self, query):
            _ = query
            return []

        def retrieve_for_director(self, query):
            _ = query
            return []

    fake_memory_service = Mock()
    fake_memory_service.retriever = _FakeRetriever()
    with patch("core.actors.executor.get_default_memory_service", return_value=fake_memory_service):
        invocation_patch = asyncio.run(
            actor_invocation_node(routed, actor_registry=get_default_actor_registry())
        )

    drained = event_drain_node({**routed, **invocation_patch})

    assert "[Boss方案] astarion -> steal_key" in drained["journal_events"]
    assert "[Boss方案] shadowheart -> contain_corruption" in drained["journal_events"]
    assert "[Boss方案] laezel -> execute" in drained["journal_events"]
    assert "heavy_iron_key" not in drained.get("player_inventory", {})


def test_party_strategy_does_not_trigger_from_secret_study_context():
    state = _lab_state()
    state["flags"]["act3_secret_study_entered"] = True

    context = detect_gribbo_boss_strategy_context(
        state,
        "我们怎么处理他？",
        {"action_target": "room_c_secret_study"},
    )
    turn_state = {
        **state,
        "user_input": "我们怎么处理他？",
        "target": "room_c_secret_study",
        "intent_context": {"action_target": "room_c_secret_study"},
    }
    dm_patch = asyncio.run(dm_node(turn_state))

    assert context is None
    assert dm_patch.get("intent_context", {}).get("gribbo_boss_strategy_context") == {}


def test_truth_negotiation_success_transfers_key_through_event_drain():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["flags"]["act4_gribbo_confrontation_started"] = True
    state["flags"]["act4_boss_strategy_discussed"] = True
    state["user_input"] = "我知道药剂对你做了什么。把钥匙给我，我们带你离开。"
    shadowheart_affection = state["entities"]["shadowheart"]["affection"]
    laezel_affection = state["entities"]["laezel"]["affection"]
    context = detect_gribbo_boss_resolution_context(state, state["user_input"], {})
    assert context["has_truth_advantage"] is True

    result = mechanics.execute_gribbo_boss_resolution_action(
        {
            **state,
            "intent_context": {
                "action_actor": "player",
                "action_target": "gribbo",
                "gribbo_boss_resolution_context": context,
            },
        }
    )
    drained = _drain_after_mechanics(state, result)

    assert drained["flags"]["act4_negotiation_success"] is True
    assert drained["flags"]["act4_heavy_iron_key_obtained"] is True
    assert drained["flags"]["act4_gribbo_spared"] is True
    assert drained["player_inventory"]["heavy_iron_key"] == 1
    assert drained["entities"]["gribbo"]["inventory"].get("heavy_iron_key", 0) == 0
    assert drained["entities"]["shadowheart"]["affection"] == shadowheart_affection + 1
    assert drained["entities"]["laezel"]["affection"] == laezel_affection - 1
    assert "[物品转移] gribbo -> player heavy_iron_key" in drained["journal_events"]


def test_truth_negotiation_requires_boss_strategy_beat_before_resolution():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["flags"]["act4_boss_room_entered"] = True
    state["flags"]["act4_gribbo_confrontation_started"] = True
    state["user_input"] = "我知道药剂对你做了什么。把钥匙给我，我们带你离开。"

    context = detect_gribbo_boss_resolution_context(state, state["user_input"], {})

    assert context is None


def test_truth_negotiation_dm_priority_over_diary_evidence_branch():
    state = _lab_state()
    state["flags"]["necromancer_lab_diary_decoded"] = True
    state["flags"]["act4_gribbo_confrontation_started"] = True
    state["flags"]["act4_boss_strategy_discussed"] = True
    state["user_input"] = "用日记真相说服 Gribbo，把钥匙给我，我们带你离开。"
    state["target"] = "gribbo"
    state["intent_context"] = {"action_target": "gribbo"}

    dm_patch = asyncio.run(dm_node(state))

    assert dm_patch["intent"] == "ACTION"
    assert dm_patch["intent_context"]["gribbo_boss_resolution_context"]["route"] == "truth_negotiation"
    assert dm_patch["intent_context"].get("diary_negotiation_context") == {}
    assert dm_patch["intent_context"]["reason"] == "act4_gribbo_boss_truth_negotiation"

    result = mechanics.execute_gribbo_boss_resolution_action({**state, **dm_patch})
    drained = _drain_after_mechanics(state, result)

    assert drained["flags"]["act4_negotiation_success"] is True
    assert drained["flags"]["act4_heavy_iron_key_obtained"] is True
    assert drained["player_inventory"]["heavy_iron_key"] == 1
    assert "[物品转移] gribbo -> player heavy_iron_key" in drained["journal_events"]


def test_astarion_steal_key_failure_triggers_poison_valve():
    state = _lab_state()
    state["flags"]["necromancer_lab_force_steal_key_failure"] = True
    state["flags"]["act4_boss_strategy_discussed"] = True
    state["user_input"] = "阿斯代伦，偷钥匙。"
    result = mechanics.execute_gribbo_boss_resolution_action(
        {
            **state,
            "intent_context": {"action_actor": "astarion", "action_target": "gribbo"},
        }
    )
    drained = _drain_after_mechanics(state, result)

    assert drained["flags"]["act4_astarion_steal_key_success"] is False
    assert drained["flags"]["act4_poison_valve_triggered"] is True
    assert drained["flags"]["act4_lab_poison_leak"] is True
    assert drained["entities"]["gribbo"]["faction"] == "hostile"
    assert any(effect.get("type") == "poisoned" for effect in drained["entities"]["player"]["status_effects"])
    assert "[偷钥匙失败] astarion -> gribbo_alerted" in drained["journal_events"]


def test_assault_defeats_gribbo_and_transfers_key():
    state = _lab_state()
    state["flags"]["necromancer_lab_force_assault_success"] = True
    state["flags"]["act4_boss_strategy_discussed"] = True
    state["user_input"] = "Lae'zel，解决他。"
    shadowheart_affection = state["entities"]["shadowheart"]["affection"]
    laezel_affection = state["entities"]["laezel"]["affection"]
    result = mechanics_node(
        {
            **state,
            "intent": "ACTION",
            "intent_context": {
                "action_actor": "laezel",
                "action_target": "gribbo",
                "gribbo_boss_resolution_context": {"topic": "gribbo_boss_resolution", "route": "assault"},
            },
        }
    )
    drained = _drain_after_mechanics(state, result)

    assert drained["flags"]["act4_assault_success"] is True
    assert drained["flags"]["world_necromancer_lab_gribbo_defeated"] is True
    assert drained["entities"]["gribbo"]["status"] == "dead"
    assert drained["entities"]["gribbo"]["faction"] == "defeated"
    assert drained["player_inventory"]["heavy_iron_key"] == 1
    assert drained["entities"]["laezel"]["affection"] == laezel_affection + 1
    assert drained["entities"]["shadowheart"]["affection"] == shadowheart_affection - 1


def test_final_exit_adds_route_specific_resolution_line():
    state = _lab_state()
    state["player_inventory"]["heavy_iron_key"] = 1
    state["flags"]["act4_astarion_steal_key_success"] = True
    state["entities"]["player"]["x"] = 17
    state["entities"]["player"]["y"] = 4

    result = mechanics.execute_interact_action(
        {
            **state,
            "intent_context": {"action_actor": "player", "action_target": "heavy_oak_door_1"},
        }
    )

    assert result["flags"]["act4_final_exit_opened"] is True
    assert result["demo_cleared"] is True
    assert any("不流血，不讲道德，只是专业" in line for line in result["journal_events"])
