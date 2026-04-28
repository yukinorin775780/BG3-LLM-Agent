from core.graph.nodes.input import input_node


def _base_state():
    return {
        "entities": {},
        "player_inventory": {},
        "journal_events": [],
        "map_data": {"id": "necromancer_lab"},
    }


def test_input_node_demotes_stale_read_unknown_to_chat_gribbo_for_act3_choice_text():
    state = {
        **_base_state(),
        "user_input": "阿斯代伦说得对，我们一起嘲笑 Gribbo。",
        "intent": "READ",
        "target": "unknown",
        "source": "",
    }

    patch = input_node(state)

    assert patch["intent"] == "CHAT"
    assert patch["target"] == "gribbo"
    assert patch["intent_context"]["action_target"] == "gribbo"


def test_input_node_demotes_stale_read_unknown_to_pending_for_plain_text():
    state = {
        **_base_state(),
        "user_input": "我观察四周有没有陷阱。",
        "intent": "READ",
        "target": "unknown",
        "source": "",
    }

    patch = input_node(state)

    assert patch["intent"] == "pending"
    assert patch["target"] == "unknown"


def test_input_node_keeps_read_with_explicit_target():
    state = {
        **_base_state(),
        "user_input": "阅读 日记",
        "intent": "READ",
        "target": "necromancer_diary",
        "source": "interaction",
    }

    patch = input_node(state)

    assert patch["intent"] == "READ"
    assert patch["target"] == "necromancer_diary"
