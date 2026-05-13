import asyncio

from core.actors.builders import build_actor_view
from core.campaigns.necromancer_lab import (
    detect_astarion_memory_echo_context,
    detect_diary_negotiation_context,
    detect_gribbo_mercy_context,
    detect_key_guidance_context,
)
from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.dm import dm_node
from core.graph.nodes.event_drain import event_drain_node
from core.graph.nodes.input import input_node
from core.systems.world_init import get_initial_world_state


def _build_lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    state["flags"] = {}
    state["journal_events"] = []
    state["pending_events"] = []
    state["speaker_responses"] = []
    state.setdefault("actor_runtime_state", {})
    return state


def _with_mercy_window(state: dict, *, diary_decoded: bool = False) -> dict:
    out = {**state}
    flags = {
        **dict(state.get("flags") or {}),
        "necromancer_lab_gribbo_mercy_window": True,
    }
    if diary_decoded:
        flags["necromancer_lab_diary_decoded"] = True
    out["flags"] = flags
    return out


def _with_rebuke_history(state: dict) -> dict:
    out = {**state}
    out["flags"] = {
        **dict(state.get("flags") or {}),
        "necromancer_lab_astarion_mocked_gribbo": True,
        "necromancer_lab_player_sided_with_astarion": False,
    }
    out["actor_runtime_state"] = {
        **dict(state.get("actor_runtime_state") or {}),
        "astarion": {"memory_notes": ["玩家当众训斥了我，我会记住这笔账。"]},
    }
    return out


def _with_side_history(state: dict) -> dict:
    out = {**state}
    out["flags"] = {
        **dict(state.get("flags") or {}),
        "necromancer_lab_astarion_mocked_gribbo": True,
        "necromancer_lab_player_sided_with_astarion": True,
    }
    out["actor_runtime_state"] = {
        **dict(state.get("actor_runtime_state") or {}),
        "astarion": {"memory_notes": ["玩家与我一起嘲笑了 Gribbo，这种默契让我满意。"]},
    }
    return out


def _run_chat_turn(state: dict, user_input: str) -> dict:
    turn_state = {
        **state,
        "user_input": user_input,
        "intent": "chat",
        "pending_events": [],
        "speaker_responses": [],
    }
    dm_patch = asyncio.run(dm_node(turn_state))
    after_dm = {**turn_state, **dm_patch}
    invocation_patch = asyncio.run(actor_invocation_node(after_dm))
    after_invocation = {**after_dm, **invocation_patch}
    drain_patch = event_drain_node(after_invocation)
    return {**after_invocation, **drain_patch}


def test_gribbo_mercy_helper_noops_outside_necromancer_lab():
    state = _with_mercy_window(_build_lab_state())
    state["map_data"]["id"] = "goblin_camp"

    assert detect_gribbo_mercy_context(state, "怎么处理他？", {}) is None


def test_mercy_window_active_returns_stance_context():
    state = _with_mercy_window(_build_lab_state(), diary_decoded=True)

    context = detect_gribbo_mercy_context(state, "队友怎么看，怎么处理他？", {})

    assert context is not None
    assert context["topic"] == "gribbo_mercy"
    assert context["phase"] == "stance"
    assert context["diary_decoded"] is True
    assert context["available_choices"] == ["mercy", "execute"]


def test_party_stances_reflect_diary_and_astarion_rebuke_history():
    state = _with_rebuke_history(_with_mercy_window(_build_lab_state(), diary_decoded=True))
    result = _run_chat_turn(state, "队友怎么看，应该怎么处理他？")

    response_text = "\n".join(text for _, text in result.get("speaker_responses", []))
    assert "死灵实验" in response_text
    assert "受害者" in response_text
    assert "处决他" in response_text
    assert "现在又要装仁慈" in response_text
    assert any("[站队] shadowheart -> mercy" in line for line in result.get("journal_events", []))
    assert any("[站队] laezel -> execute" in line for line in result.get("journal_events", []))
    assert any("[站队] astarion -> resentful" in line for line in result.get("journal_events", []))


def test_mercy_choice_writes_spared_state_affection_and_private_memories_without_key_grant():
    state = _with_mercy_window(_build_lab_state(), diary_decoded=True)
    result = _run_chat_turn(state, "放过他，留他一命。")

    assert result["flags"]["necromancer_lab_gribbo_spared"] is True
    assert result["flags"]["necromancer_lab_gribbo_mercy_resolved"] is True
    assert result["entities"]["gribbo"]["status"] == "spared"
    assert result["entities"]["gribbo"]["faction"] == "neutralized"
    assert result["entities"]["shadowheart"]["affection"] == 52
    assert result["entities"]["laezel"]["affection"] == -1
    assert "heavy_iron_key" not in result.get("player_inventory", {})
    runtime_state = result["actor_runtime_state"]
    assert "被死灵实验扭曲" in "\n".join(runtime_state["shadowheart"]["memory_notes"])
    assert "危险的失控实验体" in "\n".join(runtime_state["laezel"]["memory_notes"])
    assert "Gribbo" in "\n".join(runtime_state["astarion"]["memory_notes"])
    assert "__party_shared__" not in runtime_state
    assert any("[抉择] gribbo -> spared" in line for line in result.get("journal_events", []))


def test_execute_choice_writes_dead_state_affection_and_diary_penalty_without_key_grant():
    state = _with_side_history(_with_mercy_window(_build_lab_state(), diary_decoded=True))
    result = _run_chat_turn(state, "杀了他，别留活口。")

    assert result["flags"]["necromancer_lab_gribbo_executed"] is True
    assert result["flags"]["necromancer_lab_gribbo_mercy_resolved"] is True
    assert result["entities"]["gribbo"]["status"] == "dead"
    assert result["entities"]["gribbo"]["faction"] == "defeated"
    assert result["entities"]["shadowheart"]["affection"] == 48
    assert result["entities"]["laezel"]["affection"] == 2
    assert result["entities"]["astarion"]["affection"] == 1
    assert "heavy_iron_key" not in result.get("player_inventory", {})
    runtime_state = result["actor_runtime_state"]
    assert "尽管日记已经说明" in "\n".join(runtime_state["shadowheart"]["memory_notes"])
    assert "果断行动" in "\n".join(runtime_state["laezel"]["memory_notes"])
    assert "残忍而实际" in "\n".join(runtime_state["astarion"]["memory_notes"])
    assert any("[抉择] gribbo -> executed" in line for line in result.get("journal_events", []))


def test_execute_without_diary_decoded_uses_smaller_shadowheart_penalty():
    state = _with_mercy_window(_build_lab_state(), diary_decoded=False)
    result = _run_chat_turn(state, "处决他。")

    assert result["entities"]["shadowheart"]["affection"] == 49
    assert result["entities"]["laezel"]["affection"] == 2


def test_resolved_mercy_window_does_not_retrigger():
    state = _with_mercy_window(_build_lab_state(), diary_decoded=True)
    state["flags"]["necromancer_lab_gribbo_mercy_resolved"] = True

    assert detect_gribbo_mercy_context(state, "放过他", {}) is None


def test_gribbo_mercy_input_routing_preserves_priority_paths():
    state = _with_mercy_window(_build_lab_state(), diary_decoded=True)

    spare = input_node({**state, "user_input": "放过他", "intent": "chat"})
    execute = input_node({**state, "user_input": "杀了他", "intent": "chat"})
    read = input_node({**state, "user_input": "读日记", "intent": "read"})
    disarm = input_node({**state, "user_input": "阿斯代伦解除陷阱", "intent": "chat"})

    assert spare["intent"] == "CHAT"
    assert spare["target"] == "gribbo"
    assert execute["intent"] == "CHAT"
    assert execute["target"] == "gribbo"
    assert read["intent"] == "READ"
    assert read["target"] == "necromancer_diary"
    assert disarm["intent"] == "DISARM"
    assert disarm["target"] == "gas_trap_1"


def test_existing_showcase_helpers_still_detect_their_contexts():
    base = _build_lab_state()
    assert detect_key_guidance_context(base, "怎么打开实验室门？", "astarion") is not None

    diary_state = _build_lab_state()
    diary_state["active_dialogue_target"] = "gribbo"
    diary_state["flags"]["necromancer_lab_diary_decoded"] = True
    assert detect_diary_negotiation_context(diary_state, "日记里写了你喝下死灵狂暴灵药。") is not None

    memory_state = _with_rebuke_history(_build_lab_state())
    assert detect_astarion_memory_echo_context(memory_state, "阿斯代伦，你怎么看？", {}) is not None


def test_mercy_private_memories_do_not_leak_to_other_actor_views():
    result = _run_chat_turn(
        _with_rebuke_history(_with_mercy_window(_build_lab_state(), diary_decoded=True)),
        "放过他，留他一命。",
    )

    shadowheart_view = build_actor_view(result, "shadowheart")
    laezel_view = build_actor_view(result, "laezel")

    assert "方便的道德" not in repr(shadowheart_view)
    assert "怜悯有代价" not in repr(laezel_view)
    assert not hasattr(shadowheart_view.other_entities["astarion"], "memory_notes")
    assert not hasattr(laezel_view.other_entities["shadowheart"], "memory_notes")
