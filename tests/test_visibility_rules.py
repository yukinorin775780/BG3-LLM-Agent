from dataclasses import asdict

from core.actors.builders import build_actor_view
from core.actors.visibility import (
    build_recent_public_events,
    build_visible_history,
    filter_environment_objects_for_actor,
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


def test_filter_flags_for_actor_supports_actor_scoped_policy():
    flags = {
        "shadowheart_artifact_secret": {
            "value": True,
            "visibility": {
                "scope": "actor",
                "actors": ["shadowheart"],
                "reason": "personal_secret",
            },
        }
    }

    shadowheart_visible = filter_flags_for_actor(flags, "shadowheart")
    astarion_visible = filter_flags_for_actor(flags, "astarion")

    assert shadowheart_visible == {"shadowheart_artifact_secret": True}
    assert astarion_visible == {}


def test_filter_flags_for_actor_supports_party_policy_for_party_members():
    flags = {
        "party_mercy_path_known": {
            "value": True,
            "visibility": {"scope": "party"},
        }
    }
    state = {
        "entities": {
            "shadowheart": {"faction": "party", "status": "alive"},
            "astarion": {"faction": "party", "status": "alive"},
            "goblin_1": {"faction": "hostile", "status": "alive"},
        }
    }

    shadowheart_visible = filter_flags_for_actor(flags, "shadowheart", state=state)
    astarion_visible = filter_flags_for_actor(flags, "astarion", state=state)
    goblin_visible = filter_flags_for_actor(flags, "goblin_1", state=state)

    assert shadowheart_visible == {"party_mercy_path_known": True}
    assert astarion_visible == {"party_mercy_path_known": True}
    assert goblin_visible == {}


def test_filter_flags_for_actor_hidden_scope_requires_reveal_condition():
    flags = {
        "artifact_secret_revealed_note": {
            "value": True,
            "visibility": {
                "scope": "hidden",
                "reveal_when": {"flag": "world_artifact_revealed", "equals": True},
            },
        },
        "world_artifact_revealed": False,
    }

    hidden_before_reveal = filter_flags_for_actor(flags, "shadowheart")
    assert hidden_before_reveal == {"world_artifact_revealed": False}

    flags["world_artifact_revealed"] = True
    visible_after_reveal = filter_flags_for_actor(flags, "shadowheart")
    assert visible_after_reveal == {
        "artifact_secret_revealed_note": True,
        "world_artifact_revealed": True,
    }


def test_filter_flags_for_actor_does_not_leak_policy_metadata():
    flags = {
        "shadowheart_artifact_secret": {
            "value": True,
            "visibility": {
                "scope": "actor",
                "actors": ["shadowheart"],
                "reason": "personal_secret",
            },
            "hidden_metadata": {"origin": "quest_db"},
        }
    }

    visible = filter_flags_for_actor(flags, "shadowheart")

    assert visible == {"shadowheart_artifact_secret": True}
    assert isinstance(visible["shadowheart_artifact_secret"], bool)


def test_filter_environment_objects_for_actor_supports_visibility_policy():
    state = {
        "entities": {
            "shadowheart": {"faction": "party", "status": "alive"},
            "astarion": {"faction": "party", "status": "alive"},
        },
        "flags": {"world_hidden_door_revealed": False},
        "environment_objects": {
            "artifact_altar": {
                "name": "Artifact Altar",
                "status": "idle",
                "visibility": {"scope": "actor", "actors": ["shadowheart"]},
            },
            "party_map_marker": {
                "name": "Party Marker",
                "status": "active",
                "visibility": {"scope": "party"},
            },
            "hidden_door": {
                "name": "Hidden Door",
                "status": "sealed",
                "visibility": {
                    "scope": "hidden",
                    "reveal_when": {"flag": "world_hidden_door_revealed", "equals": True},
                },
            },
        },
    }

    shadowheart_visible = filter_environment_objects_for_actor(state, "shadowheart")
    astarion_visible = filter_environment_objects_for_actor(state, "astarion")

    assert "artifact_altar" in shadowheart_visible
    assert "artifact_altar" not in astarion_visible
    assert "party_map_marker" in shadowheart_visible
    assert "party_map_marker" in astarion_visible
    assert "hidden_door" not in shadowheart_visible

    state["flags"]["world_hidden_door_revealed"] = True
    shadowheart_visible_after_reveal = filter_environment_objects_for_actor(state, "shadowheart")
    assert "hidden_door" in shadowheart_visible_after_reveal
    assert "visibility" not in shadowheart_visible_after_reveal["artifact_altar"]


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
