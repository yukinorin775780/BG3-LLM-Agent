import copy

from core.actors.builders import build_actor_view
from core.campaigns.necromancer_lab import detect_lab_intro_awareness
from core.systems.world_init import get_initial_world_state


def _build_lab_state() -> dict:
    state = get_initial_world_state(map_id="necromancer_lab")
    state["flags"] = {}
    state["journal_events"] = []
    return state


def test_detect_lab_intro_awareness_returns_patch_for_necromancer_lab():
    state = _build_lab_state()

    patch = detect_lab_intro_awareness(state)

    assert patch is not None
    flags = patch["flags"]
    assert flags["necromancer_lab_intro_seen"] is True
    assert flags["world_necromancer_lab_intro_entered"] is True
    assert flags["astarion_detected_gas_trap"]["value"] is True
    assert flags["astarion_detected_gas_trap"]["visibility"]["scope"] == "actor"
    assert flags["astarion_detected_gas_trap"]["visibility"]["actors"] == ["astarion"]
    assert flags["shadowheart_senses_necromancy"]["value"] is True
    assert flags["shadowheart_senses_necromancy"]["visibility"]["scope"] == "actor"
    assert flags["shadowheart_senses_necromancy"]["visibility"]["actors"] == ["shadowheart"]

    shadowheart_effects = patch["entities"]["shadowheart"]["status_effects"]
    assert any(effect.get("type") == "tense" for effect in shadowheart_effects)

    events = patch["journal_events"]
    assert any("刺鼻" in line for line in events)
    assert any("Astarion" in line and ("陷阱" in line or "机关" in line) for line in events)
    assert any("Shadowheart" in line and "死灵" in line for line in events)


def test_detect_lab_intro_awareness_noop_for_seen_or_non_lab():
    seen_state = _build_lab_state()
    seen_state["flags"]["necromancer_lab_intro_seen"] = True
    assert detect_lab_intro_awareness(seen_state) is None

    non_lab_state = _build_lab_state()
    non_lab_state["map_data"]["id"] = "goblin_camp"
    assert detect_lab_intro_awareness(non_lab_state) is None


def test_actor_view_visibility_after_lab_intro_does_not_leak_hidden_trap_metadata():
    state = _build_lab_state()
    patch = detect_lab_intro_awareness(state)
    assert patch is not None

    merged = copy.deepcopy(state)
    merged["flags"] = patch["flags"]
    merged["entities"] = patch["entities"]
    merged["journal_events"] = patch["journal_events"]

    astarion_view = build_actor_view(merged, "astarion")
    shadowheart_view = build_actor_view(merged, "shadowheart")
    laezel_view = build_actor_view(merged, "laezel")

    assert astarion_view.visible_flags["astarion_detected_gas_trap"] is True
    assert "shadowheart_senses_necromancy" not in astarion_view.visible_flags

    assert shadowheart_view.visible_flags["shadowheart_senses_necromancy"] is True
    assert "astarion_detected_gas_trap" not in shadowheart_view.visible_flags

    assert "astarion_detected_gas_trap" not in laezel_view.visible_flags
    assert "shadowheart_senses_necromancy" not in laezel_view.visible_flags

    assert "gas_trap_1" not in astarion_view.visible_environment_objects
    assert "gas_trap_1" not in shadowheart_view.visible_environment_objects
    assert "gas_trap_1" not in laezel_view.visible_environment_objects
