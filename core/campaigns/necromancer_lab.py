from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


INTRO_SEEN_FLAG = "necromancer_lab_intro_seen"
ACT3_CHOICE_SIDE_WITH_ASTARION = "side_with_astarion"
ACT3_CHOICE_REBUKE_ASTARION = "rebuke_astarion"

_ACT3_SIDE_MARKERS = (
    "阿斯代伦说得对",
    "顺着阿斯代伦",
    "我同意阿斯代伦",
    "一起嘲笑",
    "和阿斯代伦一起嘲笑",
    "side with astarion",
    "sided with astarion",
    "mock gribbo",
)
_ACT3_REBUKE_MARKERS = (
    "阿斯代伦，闭嘴",
    "阿斯代伦闭嘴",
    "训斥阿斯代伦",
    "别拱火",
    "别再嘲笑",
    "rebuke astarion",
    "shut up astarion",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _flag_bool(raw_value: Any) -> bool:
    if isinstance(raw_value, dict):
        return bool(raw_value.get("value", False))
    return bool(raw_value)


def _map_id(state: Dict[str, Any]) -> str:
    map_data = _safe_dict(state.get("map_data"))
    return _normalize_id(map_data.get("id"))


def detect_lab_act3_choice(state: Dict[str, Any]) -> str:
    """
    Detect deterministic Act3 branch choice for necromancer_lab.
    Returns:
      - side_with_astarion
      - rebuke_astarion
      - "" (not an Act3 choice)
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return ""

    intent_context = _safe_dict(normalized_state.get("intent_context"))
    explicit_choice = _normalize_id(
        intent_context.get("act3_choice")
        or intent_context.get("choice")
    )
    if explicit_choice in {
        ACT3_CHOICE_SIDE_WITH_ASTARION,
        ACT3_CHOICE_REBUKE_ASTARION,
    }:
        return explicit_choice

    active_target = _normalize_id(
        normalized_state.get("active_dialogue_target")
        or intent_context.get("action_target")
    )
    if active_target != "gribbo":
        return ""

    user_input = str(normalized_state.get("user_input") or "")
    normalized_input = user_input.strip().lower()
    if not normalized_input:
        return ""

    if any(marker in user_input or marker in normalized_input for marker in _ACT3_SIDE_MARKERS):
        return ACT3_CHOICE_SIDE_WITH_ASTARION
    if any(marker in user_input or marker in normalized_input for marker in _ACT3_REBUKE_MARKERS):
        return ACT3_CHOICE_REBUKE_ASTARION
    return ""


def _should_trigger_intro(state: Dict[str, Any]) -> bool:
    if _map_id(state) != "necromancer_lab":
        return False
    flags = _safe_dict(state.get("flags"))
    if _flag_bool(flags.get(INTRO_SEEN_FLAG)):
        return False
    entities = _safe_dict(state.get("entities"))
    if "astarion" not in entities or "shadowheart" not in entities:
        return False
    return True


def _append_tense_status(shadowheart: Dict[str, Any]) -> None:
    effects = _safe_list(shadowheart.get("status_effects"))
    for effect in effects:
        if isinstance(effect, dict) and _normalize_id(effect.get("type")) == "tense":
            current_duration = int(effect.get("duration") or 0)
            effect["duration"] = max(current_duration, 3)
            shadowheart["status_effects"] = effects
            return
    effects.append({"type": "tense", "duration": 3})
    shadowheart["status_effects"] = effects


def _astarion_detects_trap(entities: Dict[str, Any]) -> bool:
    astarion = _safe_dict(entities.get("astarion"))
    if not astarion:
        return False
    if _normalize_id(astarion.get("status")) == "dead":
        return False
    ability_scores = _safe_dict(astarion.get("ability_scores"))
    dex = int(ability_scores.get("DEX") or 0)
    wis = int(ability_scores.get("WIS") or 0)
    # Deterministic threshold: high DEX scout with baseline awareness.
    return dex >= 16 and wis >= 10


def _shadowheart_senses_necromancy(entities: Dict[str, Any]) -> bool:
    shadowheart = _safe_dict(entities.get("shadowheart"))
    if not shadowheart:
        return False
    if _normalize_id(shadowheart.get("status")) == "dead":
        return False
    ability_scores = _safe_dict(shadowheart.get("ability_scores"))
    wis = int(ability_scores.get("WIS") or 0)
    return wis >= 14


def detect_lab_intro_awareness(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build deterministic Act1 intro awareness patch for necromancer_lab.
    Returns None when intro should not trigger.
    """
    normalized_state = _safe_dict(state)
    if not _should_trigger_intro(normalized_state):
        return None

    flags = copy.deepcopy(_safe_dict(normalized_state.get("flags")))
    entities = copy.deepcopy(_safe_dict(normalized_state.get("entities")))
    journal_events = list(_safe_list(normalized_state.get("journal_events")))

    flags[INTRO_SEEN_FLAG] = True
    flags["world_necromancer_lab_intro_entered"] = True

    journal_events.append("🧪 [实验室] 空气里弥漫着刺鼻的化学与腐败气味。")

    if _astarion_detects_trap(entities):
        flags["astarion_detected_gas_trap"] = {
            "value": True,
            "visibility": {
                "scope": "actor",
                "actors": ["astarion"],
                "reason": "trap_awareness",
            },
        }
        flags["world_necromancer_lab_trap_warned"] = True
        journal_events.append("🗣️ [Astarion] 小心，前面有毒气机关的痕迹。")

    if _shadowheart_senses_necromancy(entities):
        flags["shadowheart_senses_necromancy"] = {
            "value": True,
            "visibility": {
                "scope": "actor",
                "actors": ["shadowheart"],
                "reason": "necromancy_residue",
            },
        }
        shadowheart = _safe_dict(entities.get("shadowheart"))
        if shadowheart:
            _append_tense_status(shadowheart)
            entities["shadowheart"] = shadowheart
        journal_events.append("🗣️ [Shadowheart] 这里有死灵残留……我感觉很不对劲。")

    patch: Dict[str, Any] = {
        "flags": flags,
        "entities": entities,
        "journal_events": journal_events,
    }
    return patch
