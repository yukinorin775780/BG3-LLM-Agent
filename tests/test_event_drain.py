from core.events.models import DomainEvent
from core.graph.nodes.event_drain import event_drain_node


def test_event_drain_turns_actor_spoke_event_into_messages_and_responses():
    state = {
        "pending_events": [
            DomainEvent(
                event_id="evt-1",
                event_type="actor_spoke",
                actor_id="shadowheart",
                turn_index=12,
                visibility="party",
                payload={"text": "别碰那个圣徽。"},
            )
        ],
        "speaker_responses": [],
        "messages": [],
    }

    result = event_drain_node(state)

    assert result["pending_events"] == []
    assert result["speaker_responses"] == [("shadowheart", "别碰那个圣徽。")]
    assert len(result["messages"]) == 1


def test_event_drain_turns_world_flag_changed_event_into_flags_patch():
    state = {
        "pending_events": [
            DomainEvent(
                event_id="evt-2",
                event_type="world_flag_changed",
                actor_id="director",
                turn_index=12,
                visibility="world",
                payload={"flag": "world_artifact_revealed", "value": True},
            )
        ],
        "flags": {},
    }

    result = event_drain_node(state)

    assert result["pending_events"] == []
    assert result["flags"]["world_artifact_revealed"] is True
