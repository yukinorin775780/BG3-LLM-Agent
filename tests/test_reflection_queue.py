import asyncio
from unittest.mock import AsyncMock, Mock

from core.actors.contracts import ReflectionRequest
from core.events.models import DomainEvent
from core.graph.nodes.event_drain import drain_reflection_queue


def test_drain_reflection_queue_processes_requests_in_priority_order():
    request_low = ReflectionRequest(
        actor_id="shadowheart",
        reason="after_small_talk",
        priority=1,
        source_turn=10,
        payload={},
    )
    request_high = ReflectionRequest(
        actor_id="shadowheart",
        reason="after_secret_reveal",
        priority=10,
        source_turn=11,
        payload={},
    )

    fake_runtime = AsyncMock()
    fake_runtime.reflect.side_effect = [
        (
            DomainEvent(
                "evt-high",
                "actor_belief_updated",
                "shadowheart",
                11,
                "private",
                {"belief": "trust+"},
            ),
        ),
        (
            DomainEvent(
                "evt-low",
                "actor_belief_updated",
                "shadowheart",
                10,
                "private",
                {"belief": "idle"},
            ),
        ),
    ]

    fake_registry = Mock()
    fake_registry.try_get.return_value = fake_runtime

    state = {
        "reflection_queue": [request_low, request_high],
        "pending_events": [],
    }

    result = asyncio.run(drain_reflection_queue(state, actor_registry=fake_registry))

    assert result["reflection_queue"] == []
    assert [evt["event_id"] for evt in result["pending_events"]] == ["evt-high", "evt-low"]
