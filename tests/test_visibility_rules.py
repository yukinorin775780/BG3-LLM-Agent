from dataclasses import asdict

from core.actors.builders import build_actor_view
from core.actors.visibility import (
    build_recent_public_events,
    build_visible_history,
    filter_flags_for_actor,
)
from core.actors.views import VisibleMessage


def test_filter_flags_for_actor_only_keeps_public_prefixes():
    flags = {
        "world_lab_unlocked": True,
        "quest_found_key": False,
        "combat_active": True,
        "public_hint_seen": True,
        "director_only": True,
        "shadowheart_private_doubt": True,
    }

    visible = filter_flags_for_actor(flags, "shadowheart")

    assert visible == {
        "world_lab_unlocked": True,
        "quest_found_key": False,
        "combat_active": True,
        "public_hint_seen": True,
    }


def test_build_visible_history_normalizes_to_visible_message():
    messages = [
        {"role": "user", "content": "你是谁？"},
        {"role": "assistant", "name": "gribbo", "content": "[gribbo]: 离远点。"},
    ]

    visible_history = build_visible_history(messages, actor_id="gribbo", limit=12)

    assert len(visible_history) == 2
    assert all(isinstance(item, VisibleMessage) for item in visible_history)
    assert visible_history[1].speaker_id == "gribbo"
    assert visible_history[1].content == "离远点。"


def test_build_recent_public_events_returns_tail_slice():
    events = [f"event-{idx}" for idx in range(1, 11)]
    assert build_recent_public_events(events, limit=4) == [
        "event-7",
        "event-8",
        "event-9",
        "event-10",
    ]


def test_actor_view_never_contains_speaker_queue():
    state = {
        "speaker_queue": ["astarion", "shadowheart"],
        "messages": [],
        "entities": {
            "shadowheart": {
                "name": "Shadowheart",
                "hp": 10,
                "max_hp": 10,
                "inventory": {"healing_potion": 1},
                "affection": 10,
                "active_buffs": [],
                "position": "camp_center",
                "status": "alive",
                "faction": "party",
            }
        },
    }

    actor_view = build_actor_view(state, "shadowheart")
    serialized = asdict(actor_view)

    assert "speaker_queue" not in serialized

