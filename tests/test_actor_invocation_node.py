import asyncio
from unittest.mock import ANY, AsyncMock, Mock, patch

from core.actors.contracts import ActorDecision
from core.actors.executor import invoke_actor_runtime
from core.actors.registry import get_default_actor_registry
from core.eval.telemetry import InMemoryTelemetrySink, telemetry_scope
from core.events.models import DomainEvent
from core.graph.nodes.actor_invocation import actor_invocation_node
from core.graph.nodes.event_drain import event_drain_node
from core.memory.models import MemorySnippet


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
    assert result["actor_invocation_reason"] == "runtime_enabled"
    assert result["last_actor_decision"]["actor_id"] == "shadowheart"
    assert result["last_actor_decision"]["kind"] == "speak"
    assert len(result["pending_events"]) == 1
    assert result["pending_events"][0]["event_id"] == "evt-1"


def test_actor_invocation_node_falls_back_when_runtime_missing():
    state = {
        "current_speaker": "astarion",
        "pending_events": [],
        "reflection_queue": [],
    }
    fake_registry = Mock()
    fake_registry.try_get.return_value = None
    fake_registry.get.side_effect = KeyError("Unknown actor runtime")

    result = asyncio.run(actor_invocation_node(state, actor_registry=fake_registry))

    assert result["actor_invocation_mode"] == "fallback"
    assert result["actor_invocation_reason"] == "runtime_missing"
    assert "pending_events" not in result
    assert "reflection_queue" not in result


def test_actor_invocation_node_falls_back_when_actor_id_missing():
    result = asyncio.run(actor_invocation_node({"current_speaker": "  "}, actor_registry=Mock()))

    assert result["actor_invocation_mode"] == "fallback"
    assert result["actor_invocation_reason"] == "actor_id_missing"


def test_actor_invocation_node_falls_back_and_emits_telemetry_when_runtime_failed():
    state = {
        "current_speaker": "shadowheart",
        "entities": {"shadowheart": {"hp": 10}},
    }
    fake_runtime = AsyncMock()
    fake_runtime.decide.side_effect = RuntimeError("boom")
    fake_registry = Mock()
    fake_registry.try_get.return_value = fake_runtime
    fake_memory_service = Mock()
    fake_memory_service.retriever = Mock()
    sink = InMemoryTelemetrySink()

    with telemetry_scope(sink), patch("core.actors.executor.build_actor_view", return_value=object()), patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        result = asyncio.run(actor_invocation_node(state, actor_registry=fake_registry))

    assert result["actor_invocation_mode"] == "fallback"
    assert result["actor_invocation_reason"] == "runtime_failed"

    fallback_events = [
        event
        for event in sink.events
        if event.get("event_name") == "actor_runtime_decision"
        and event.get("payload", {}).get("mode") == "fallback"
    ]
    assert fallback_events
    payload = fallback_events[-1]["payload"]
    assert payload["actor_id"] == "shadowheart"
    assert payload["reason"] == "runtime_failed"


def test_astarion_runtime_event_is_written_via_event_drain():
    state = {
        "current_speaker": "astarion",
        "user_input": "继续",
        "intent": "CHAT",
        "turn_count": 7,
        "current_location": "camp_center",
        "entities": {
            "astarion": {
                "name": "Astarion",
                "hp": 12,
                "max_hp": 12,
                "inventory": {"dagger": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_center",
            },
            "shadowheart": {
                "name": "Shadowheart",
                "hp": 10,
                "max_hp": 10,
                "inventory": {"private_relic": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_center",
            },
        },
        "pending_events": [],
        "speaker_responses": [],
        "messages": [],
        "flags": {},
    }

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
    assert invocation_patch["actor_invocation_reason"] == "runtime_enabled"
    patched_state = {**state, **invocation_patch}
    drain_patch = event_drain_node(patched_state)

    assert drain_patch["pending_events"] == []
    assert drain_patch["speaker_responses"] == [("astarion", "我听见了。继续。")]


def test_invoke_actor_runtime_uses_actor_scoped_memory_for_astarion():
    state = {
        "user_input": "你还记得吗？",
        "intent": "CHAT",
        "turn_count": 21,
        "current_location": "camp_fire",
        "entities": {
            "astarion": {
                "name": "Astarion",
                "hp": 12,
                "max_hp": 12,
                "inventory": {"dagger": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_fire",
            },
            "shadowheart": {
                "name": "Shadowheart",
                "hp": 10,
                "max_hp": 10,
                "inventory": {"private_relic": 1, "mysterious_artifact": 1},
                "secret_objective": "Protect the artifact.",
                "status": "alive",
                "faction": "party",
                "position": "camp_fire",
            },
        },
        "messages": [],
    }

    class _FakeRetriever:
        def __init__(self):
            self.calls = []

        def retrieve_for_actor(self, query):
            self.calls.append(query)
            return [
                MemorySnippet(
                    memory_id="m-astarion",
                    text="阿斯代伦记得这场谈话。",
                    scope="actor_private",
                    score=0.9,
                    memory_type="belief",
                )
            ]

        def retrieve_for_director(self, query):
            _ = query
            return []

    fake_retriever = _FakeRetriever()
    fake_memory_service = Mock()
    fake_memory_service.retriever = fake_retriever

    fake_runtime = AsyncMock()
    fake_runtime.decide.return_value = ActorDecision(
        actor_id="astarion",
        kind="speak",
        spoken_text="……有点印象。",
        thought_summary="",
        emitted_events=(),
        requested_reflections=(),
    )
    fake_registry = Mock()
    fake_registry.try_get.return_value = fake_runtime

    with patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        decision_meta, events, reflections = asyncio.run(
            invoke_actor_runtime(
                state=state,
                actor_id="astarion",
                registry=fake_registry,
            )
        )

    assert decision_meta["mode"] == "runtime"
    assert events == []
    assert reflections == []
    assert fake_retriever.calls
    assert fake_retriever.calls[0].actor_id == "astarion"

    fake_runtime.decide.assert_awaited_once()
    actor_view = fake_runtime.decide.await_args.args[0]
    assert actor_view.actor_id == "astarion"
    assert actor_view.memory_snippets == ["阿斯代伦记得这场谈话。"]
    assert "shadowheart" in actor_view.other_entities
    assert not hasattr(actor_view.other_entities["shadowheart"], "inventory")


def test_actor_invocation_node_emits_fallback_telemetry_for_astarion_runtime_missing():
    state = {
        "current_speaker": "astarion",
        "pending_events": [],
    }
    fake_registry = Mock()
    fake_registry.try_get.return_value = None
    fake_registry.get.side_effect = KeyError("Unknown actor runtime")
    sink = InMemoryTelemetrySink()

    with telemetry_scope(sink):
        result = asyncio.run(actor_invocation_node(state, actor_registry=fake_registry))

    assert result["actor_invocation_mode"] == "fallback"
    assert result["actor_invocation_reason"] == "runtime_missing"

    fallback_events = [
        event
        for event in sink.events
        if event.get("event_name") == "actor_runtime_decision"
        and event.get("payload", {}).get("mode") == "fallback"
    ]
    assert fallback_events
    payload = fallback_events[-1]["payload"]
    assert payload["actor_id"] == "astarion"
    assert payload["reason"] == "runtime_missing"


def test_actor_invocation_node_default_registry_marks_unenabled_actor_as_fallback():
    state = {
        "current_speaker": "gribbo",
        "pending_events": [],
    }

    result = asyncio.run(
        actor_invocation_node(
            state,
            actor_registry=get_default_actor_registry(),
        )
    )

    assert result["actor_invocation_mode"] == "fallback"
    assert result["actor_invocation_reason"] == "runtime_missing"


def test_laezel_runtime_event_is_written_via_event_drain():
    state = {
        "current_speaker": "laezel",
        "user_input": "继续",
        "intent": "CHAT",
        "turn_count": 7,
        "current_location": "camp_center",
        "entities": {
            "laezel": {
                "name": "Laezel",
                "hp": 13,
                "max_hp": 13,
                "inventory": {"longsword": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_center",
            },
            "shadowheart": {
                "name": "Shadowheart",
                "hp": 10,
                "max_hp": 10,
                "inventory": {"private_relic": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_center",
            },
            "astarion": {
                "name": "Astarion",
                "hp": 12,
                "max_hp": 12,
                "inventory": {"private_dagger": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_center",
            },
        },
        "pending_events": [],
        "speaker_responses": [],
        "messages": [],
        "flags": {},
    }

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
    assert invocation_patch["actor_invocation_reason"] == "runtime_enabled"
    patched_state = {**state, **invocation_patch}
    drain_patch = event_drain_node(patched_state)

    assert drain_patch["pending_events"] == []
    assert drain_patch["speaker_responses"] == [("laezel", "我听见了。继续。")]


def test_invoke_actor_runtime_uses_actor_scoped_memory_for_laezel():
    state = {
        "user_input": "你怎么看？",
        "intent": "CHAT",
        "turn_count": 22,
        "current_location": "camp_fire",
        "entities": {
            "laezel": {
                "name": "Laezel",
                "hp": 13,
                "max_hp": 13,
                "inventory": {"longsword": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_fire",
            },
            "shadowheart": {
                "name": "Shadowheart",
                "hp": 10,
                "max_hp": 10,
                "inventory": {"private_relic": 1},
                "secret_objective": "Protect the artifact.",
                "status": "alive",
                "faction": "party",
                "position": "camp_fire",
            },
            "astarion": {
                "name": "Astarion",
                "hp": 12,
                "max_hp": 12,
                "inventory": {"private_dagger": 1},
                "secret_objective": "Hide vampiric nature.",
                "status": "alive",
                "faction": "party",
                "position": "camp_fire",
            },
        },
        "messages": [],
    }

    class _FakeRetriever:
        def __init__(self):
            self.calls = []

        def retrieve_for_actor(self, query):
            self.calls.append(query)
            return [
                MemorySnippet(
                    memory_id="m-laezel",
                    text="莱埃泽尔记得上次交锋。",
                    scope="actor_private",
                    score=0.9,
                    memory_type="belief",
                )
            ]

        def retrieve_for_director(self, query):
            _ = query
            return []

    fake_retriever = _FakeRetriever()
    fake_memory_service = Mock()
    fake_memory_service.retriever = fake_retriever

    fake_runtime = AsyncMock()
    fake_runtime.decide.return_value = ActorDecision(
        actor_id="laezel",
        kind="speak",
        spoken_text="哼。",
        thought_summary="",
        emitted_events=(),
        requested_reflections=(),
    )
    fake_registry = Mock()
    fake_registry.try_get.return_value = fake_runtime

    with patch(
        "core.actors.executor.get_default_memory_service",
        return_value=fake_memory_service,
    ):
        decision_meta, events, reflections = asyncio.run(
            invoke_actor_runtime(
                state=state,
                actor_id="laezel",
                registry=fake_registry,
            )
        )

    assert decision_meta["mode"] == "runtime"
    assert events == []
    assert reflections == []
    assert fake_retriever.calls
    assert fake_retriever.calls[0].actor_id == "laezel"

    fake_runtime.decide.assert_awaited_once()
    actor_view = fake_runtime.decide.await_args.args[0]
    assert actor_view.actor_id == "laezel"
    assert actor_view.memory_snippets == ["莱埃泽尔记得上次交锋。"]
    assert "shadowheart" in actor_view.other_entities
    assert "astarion" in actor_view.other_entities
    assert not hasattr(actor_view.other_entities["shadowheart"], "inventory")
    assert not hasattr(actor_view.other_entities["astarion"], "inventory")


def test_actor_invocation_marker_survives_event_drain_patch_merge():
    state = {
        "current_speaker": "shadowheart",
        "user_input": "继续",
        "intent": "CHAT",
        "turn_count": 9,
        "current_location": "camp_center",
        "entities": {
            "shadowheart": {
                "name": "Shadowheart",
                "hp": 10,
                "max_hp": 10,
                "inventory": {"healing_potion": 1},
                "status": "alive",
                "faction": "party",
                "position": "camp_center",
            }
        },
        "pending_events": [],
        "speaker_responses": [],
        "messages": [],
        "flags": {},
    }

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
    assert invocation_patch["actor_invocation_reason"] == "runtime_enabled"
    merged_state = {**state, **invocation_patch}
    drain_patch = event_drain_node(merged_state)
    merged_state.update(drain_patch)

    assert merged_state["actor_invocation_mode"] == "runtime"
    assert merged_state["actor_invocation_reason"] == "runtime_enabled"
