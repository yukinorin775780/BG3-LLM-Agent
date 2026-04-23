import asyncio
from unittest.mock import ANY, AsyncMock, Mock, patch

from core.actors.contracts import ActorDecision
from core.actors.executor import invoke_actor_runtime
from core.events.models import DomainEvent
from core.graph.nodes.actor_invocation import actor_invocation_node


def test_invoke_actor_runtime_builds_view_and_invokes_runtime():
    state = {
        "user_input": "别靠太近。",
        "entities": {"shadowheart": {"hp": 10}},
    }

    fake_runtime = AsyncMock()
    fake_runtime.decide.return_value = ActorDecision(
        actor_id="shadowheart",
        kind="speak",
        spoken_text="别靠太近。",
        thought_summary="她不信任对方。",
        emitted_events=(),
        requested_reflections=(),
    )

    fake_registry = Mock()
    fake_registry.try_get.return_value = fake_runtime

    fake_memory_service = Mock()
    fake_memory_service.retriever = Mock()

    with patch("core.actors.executor.build_actor_view", return_value=object()) as build_view, patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        decision_meta, events, reflections = asyncio.run(
            invoke_actor_runtime(
                state=state,
                actor_id="shadowheart",
                registry=fake_registry,
            )
        )

    build_view.assert_called_once_with(state, "shadowheart", memory_provider=ANY)
    fake_runtime.decide.assert_awaited_once()
    assert decision_meta["actor_id"] == "shadowheart"
    assert decision_meta["kind"] == "speak"
    assert events == []
    assert reflections == []


def test_actor_invocation_node_appends_emitted_events_to_pending_events():
    state = {
        "current_speaker": "shadowheart",
        "pending_events": [],
        "entities": {"shadowheart": {"hp": 10}},
    }

    emitted_event = DomainEvent(
        event_id="evt-1",
        event_type="actor_spoke",
        actor_id="shadowheart",
        turn_index=12,
        visibility="party",
        payload={"text": "……"},
    )

    fake_runtime = AsyncMock()
    fake_runtime.decide.return_value = ActorDecision(
        actor_id="shadowheart",
        kind="speak",
        spoken_text="……",
        thought_summary="",
        emitted_events=(emitted_event,),
        requested_reflections=(),
    )

    fake_registry = Mock()
    fake_registry.try_get.return_value = fake_runtime

    fake_memory_service = Mock()
    fake_memory_service.retriever = Mock()

    with patch("core.actors.executor.build_actor_view", return_value=object()), patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        result = asyncio.run(actor_invocation_node(state, actor_registry=fake_registry))

    assert result["actor_invocation_mode"] == "runtime"
    assert result["last_actor_decision"]["actor_id"] == "shadowheart"
    assert result["last_actor_decision"]["kind"] == "speak"
    assert len(result["pending_events"]) == 1
    assert result["pending_events"][0]["event_id"] == "evt-1"
