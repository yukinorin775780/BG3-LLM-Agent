import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, HumanMessage

import core.graph.nodes.generation as generation
from core.actors.views import ActorSelfState, ActorView, PublicEntityView, VisibleMessage


def _make_actor_view() -> ActorView:
    return ActorView(
        actor_id="shadowheart",
        user_input="你好",
        intent="CHAT",
        intent_context={},
        is_probing_secret=False,
        self_state=ActorSelfState(
            actor_id="shadowheart",
            name="Shadowheart",
            hp=10,
            max_hp=10,
            inventory={"healing_potion": 1},
            affection=15,
            active_buffs=[],
            position="camp_center",
            dynamic_states={},
        ),
        other_entities={
            "astarion": PublicEntityView(
                entity_id="astarion",
                name="Astarion",
                position="camp_center",
                status="alive",
                faction="party",
            )
        },
        current_location="camp_center",
        time_of_day="黄昏",
        turn_count=3,
        visible_environment_objects={"camp_fire": {"name": "篝火", "status": "burning"}},
        visible_flags={"world_ready": True},
        visible_history=[
            VisibleMessage(role="user", speaker_id="user", content="你好"),
            VisibleMessage(role="assistant", speaker_id="astarion", content="嗯哼？"),
        ],
        recent_public_events=["事件A"],
        latest_roll={},
        memory_snippets=["她记得玩家曾帮助过她。"],
    )


def test_generation_node_routes_prompt_building_through_actor_view():
    node = generation.create_generation_node()
    state = {
        "entities": {"shadowheart": {"hp": 10, "affection": 15, "inventory": {}}},
        "current_speaker": "shadowheart",
        "user_input": "你好",
    }
    fake_character = Mock()
    actor_view = _make_actor_view()
    context = {
        "speaker": "shadowheart",
        "idle_banter": False,
        "player_inv_for_physics": {},
        "current_entities": {"shadowheart": {"hp": 10, "position": "camp_center"}},
        "entities": {"shadowheart": {"hp": 10, "position": "camp_center"}},
        "current_env_objs": {},
        "history_dicts": [{"role": "user", "content": "你好"}],
    }

    with patch("characters.loader.load_character", return_value=fake_character), patch(
        "core.graph.nodes.generation.build_actor_view",
        return_value=actor_view,
    ) as build_actor_view, patch(
        "core.graph.nodes.generation._build_unconscious_response",
        return_value=None,
    ), patch(
        "core.graph.nodes.generation._prepare_generation_context",
        return_value=context,
    ) as prepare_context, patch(
        "core.graph.nodes.generation._maybe_generate_banter_response",
        return_value=None,
    ), patch(
        "core.graph.nodes.generation._build_system_prompt",
        return_value="SYSTEM",
    ) as build_system_prompt, patch(
        "core.graph.nodes.generation._build_lc_messages",
        return_value=[HumanMessage(content="你好")],
    ), patch(
        "core.graph.nodes.generation._create_llm_client",
        return_value=SimpleNamespace(ainvoke=AsyncMock()),
    ), patch(
        "core.graph.nodes.generation._execute_llm_with_tools",
        return_value=(AIMessage(content='{"reply":"ok"}'), []),
    ), patch(
        "core.graph.nodes.generation._parse_and_apply_actions",
        return_value={
            "clean_text": "ok",
            "thought_process": "",
            "tool_physics_events": [],
            "state_changes_applied": False,
            "idle_merged": None,
        },
    ), patch(
        "core.graph.nodes.generation._assemble_generation_output",
        return_value={"ok": True},
    ):
        result = asyncio.run(node(state))

    assert result == {"ok": True}
    build_actor_view.assert_called_once()
    _, kwargs = prepare_context.call_args
    assert kwargs["actor_view"] is actor_view
    build_system_prompt.assert_called_once_with(actor_view, context)


def test_format_history_messages_consumes_actor_view_only():
    actor_view = _make_actor_view()
    context = {
        "user_input": "继续",
        "is_first_npc_of_player_turn": False,
        "idle_banter": False,
        "intent": "chat",
        "speaker": "shadowheart",
        "npc_inv": {"healing_potion": 1},
        "prev_responses": [],
    }

    history_dicts = generation._format_history_messages(actor_view, context)

    assert history_dicts[0] == {"role": "user", "content": "你好"}
    assert history_dicts[1]["role"] == "assistant"
    assert "🚨 [CRITICAL OVERRIDE - PHYSICAL ACTION REQUIRED]:" not in history_dicts[0]["content"]

