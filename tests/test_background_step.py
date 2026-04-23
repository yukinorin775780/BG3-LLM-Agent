import asyncio
from unittest.mock import AsyncMock, Mock, patch

from core.application.game_service import GameService


class _AsyncContextManager:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


class _FakeGraph:
    def __init__(self, state):
        self.state = state
        self.ainvoke_calls = []
        self.aupdate_calls = []

    async def aget_state(self, config):
        _ = config

        class Snapshot:
            values = self.state

        return Snapshot()

    async def aupdate_state(self, config, payload, as_node):
        _ = (config, as_node)
        self.aupdate_calls.append(dict(payload))
        self.state.update(payload)

    async def ainvoke(self, payload, config):
        _ = config
        self.ainvoke_calls.append(dict(payload))
        return self.state


def test_background_step_only_processes_reflection_path():
    state = {
        "entities": {"shadowheart": {"hp": 10, "faction": "party"}},
        "journal_events": [],
        "speaker_responses": [],
        "messages": [],
        "pending_events": [],
        "reflection_queue": [],
    }
    graph = _FakeGraph(state)

    service = GameService(
        saver_factory=Mock(return_value=_AsyncContextManager(object())),
        graph_builder=Mock(return_value=graph),
        initial_state_factory=Mock(return_value=state),
    )

    reflection_patch = {
        "reflection_queue": [],
        "pending_events": [
            {
                "event_id": "evt-1",
                "event_type": "actor_belief_updated",
                "actor_id": "shadowheart",
                "turn_index": 1,
                "visibility": "private",
                "payload": {"belief": "trust+"},
            }
        ],
    }
    event_patch = {
        "pending_events": [],
        "journal_events": ["🧠 [认知] shadowheart 的内部信念发生了变化。"],
    }

    with patch(
        "core.application.game_service.run_reflection_tick",
        new=AsyncMock(return_value=reflection_patch),
    ), patch(
        "core.application.game_service.event_drain_node",
        return_value=event_patch,
    ):
        asyncio.run(
            service.process_chat_turn(
                user_input="",
                intent="process_reflections",
                session_id="session-1",
            )
        )

    assert graph.ainvoke_calls == []
    assert len(graph.aupdate_calls) == 1
    persisted = graph.aupdate_calls[0]
    assert persisted["pending_events"] == []
    assert persisted["reflection_queue"] == []
    assert "journal_events" in persisted
