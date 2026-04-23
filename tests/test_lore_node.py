from core.graph.nodes.lore import lore_node


def _build_read_state(int_score: int) -> dict:
    return {
        "intent": "READ",
        "intent_context": {
            "action_actor": "player",
            "action_target": "journal_1",
        },
        "entities": {
            "player": {
                "name": "玩家",
                "ability_scores": {
                    "STR": 10,
                    "DEX": 10,
                    "CON": 10,
                    "INT": int_score,
                    "WIS": 10,
                    "CHA": 10,
                },
                "hp": 20,
                "max_hp": 20,
                "status": "alive",
            }
        },
        "environment_objects": {
            "journal_1": {
                "id": "journal_1",
                "type": "readable",
                "name": "残破的实验日志",
                "lore_id": "necromancer_journal_1",
                "x": 6,
                "y": 10,
            }
        },
    }


def test_lore_node_with_low_int_obscures_password(monkeypatch):
    monkeypatch.setattr("core.graph.nodes.lore.settings.API_KEY", None)
    state = _build_read_state(8)

    result = lore_node(state)
    text = "\n".join(result.get("journal_events", []))
    action_segment = text.split("\n\n", 1)[1] if "\n\n" in text else text

    assert "📜 [原文]" in text
    assert "📖 [动作]" in text
    assert "💬 [独白]" in text
    assert "米尔寇的叹息" not in action_segment
    assert "Myrkul's Breath" not in action_segment
    assert ("看懂" in text) or ("混乱" in text) or ("只言片语" in text)


def test_lore_node_with_high_int_reveals_password(monkeypatch):
    monkeypatch.setattr("core.graph.nodes.lore.settings.API_KEY", None)
    state = _build_read_state(16)

    result = lore_node(state)
    text = "\n".join(result.get("journal_events", []))

    assert "📜 [原文]" in text
    assert "📖 [动作]" in text
    assert "💬 [独白]" in text
    assert "米尔寇的叹息" in text
    assert "Myrkul's Breath" in text


def test_lore_node_diary_generates_narration_and_monologue(monkeypatch):
    monkeypatch.setattr("core.graph.nodes.lore.settings.API_KEY", None)
    state = {
        "intent": "READ",
        "intent_context": {
            "action_actor": "astarion",
            "action_target": "necromancer_diary",
        },
        "entities": {
            "astarion": {
                "name": "阿斯代伦 (Astarion)",
                "ability_scores": {"INT": 16},
                "attributes": {
                    "personality": {
                        "traits": ["傲慢", "毒舌", "精于观察"]
                    }
                },
                "hp": 15,
                "max_hp": 15,
                "status": "alive",
            }
        },
        "environment_objects": {
            "necromancer_diary": {
                "id": "necromancer_diary",
                "type": "readable",
                "name": "沾满血污的日记本",
                "lore_id": "necromancer_diary_1",
                "x": 15,
                "y": 3,
            }
        },
    }

    result = lore_node(state)
    text = "\n".join(result.get("journal_events", []))
    assert "📜 [原文]" in text
    assert "📖 [动作]" in text
    assert "Gribbo" in text
    assert "铁钥匙" in text
    assert "💬 [独白]" in text
