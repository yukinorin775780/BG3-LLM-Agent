from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional


INTRO_SEEN_FLAG = "necromancer_lab_intro_seen"
ACT3_CHOICE_SIDE_WITH_ASTARION = "side_with_astarion"
ACT3_CHOICE_REBUKE_ASTARION = "rebuke_astarion"
ACT4_POST_COMBAT_BANTER = "act4_post_combat_banter"

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
_ACT4_BANTER_MARKERS = (
    "离开",
    "撤离",
    "快走",
    "继续前进",
    "准备开门",
    "escape",
    "move out",
    "open the door",
    "let's go",
)
_KEY_GUIDANCE_DOOR_IDS = frozenset({"door_b_to_d", "heavy_oak_door_1"})
_KEY_GUIDANCE_DOOR_MARKERS = (
    "door_b_to_d",
    "heavy_oak_door_1",
    "实验室门",
    "实验室重门",
    "重门",
    "lab door",
    "laboratory door",
)
_KEY_GUIDANCE_KEY_MARKERS = (
    "lab_key",
    "heavy_iron_key",
    "钥匙",
    "key",
)
_KEY_GUIDANCE_QUESTION_MARKERS = (
    "怎么",
    "怎么办",
    "在哪",
    "哪里",
    "接下来",
    "去哪",
    "能不能",
    "能进",
    "能打开",
    "可以打开",
    "现在能",
    "下一步",
    "how",
    "where",
    "what next",
    "can we",
    "should we",
)
_KEY_GUIDANCE_STUDY_FLAGS = (
    "room_c_secret_study_discovered",
    "room_c_secret_study_entered",
    "world_room_c_secret_study_discovered",
    "world_room_c_secret_study_entered",
    "necromancer_lab_secret_study_discovered",
    "necromancer_lab_secret_study_entered",
)
_DIARY_NEGOTIATION_MARKERS = (
    "日记",
    "药",
    "灵药",
    "药剂",
    "死灵",
    "狂暴",
    "实验",
    "事故",
    "解药",
    "钥匙",
    "真相",
    "diary",
    "elixir",
    "potion",
    "necromancy",
    "experiment",
    "antidote",
    "key",
    "truth",
)
_STUDY_CHEST_ALIASES = (
    "study_chest",
    "chest_1",
    "书房箱子",
    "书房的箱子",
    "书房宝箱",
    "战利品箱",
)
_STUDY_CHEST_ACTION_MARKERS = (
    "搜刮",
    "打开",
    "翻",
    "搜",
    "拿",
    "拾取",
    "loot",
    "open",
)
_TRAP_AWARENESS_MARKERS = (
    "陷阱",
    "机关",
    "毒气",
    "压力板",
    "喷口",
    "小心",
    "往前",
    "走廊",
    "前面",
    "trap",
    "poison",
    "gas",
    "pressure plate",
    "vent",
    "corridor",
    "ahead",
)
_ASTARION_MEMORY_ACTOR_MARKERS = (
    "阿斯代伦",
    "astarion",
)
_ASTARION_MEMORY_COLLAB_MARKERS = (
    "帮忙",
    "帮我",
    "建议",
    "怎么看",
    "你怎么看",
    "陷阱",
    "解除",
    "拆除",
    "钥匙",
    "门",
    "实验室",
    "gribbo",
    "怎么办",
    "help",
    "advice",
    "what do you think",
    "trap",
    "disarm",
    "key",
    "door",
    "lab",
)
_GRIBBO_MERCY_STANCE_MARKERS = (
    "怎么办",
    "怎么处理",
    "处理他",
    "队友怎么看",
    "该不该",
    "放不放",
    "饶不饶",
    "处置",
    "should we",
    "what should",
)
_GRIBBO_MERCY_CHOICE_MARKERS = (
    "mercy",
    "spare",
    "forgive",
    "放过",
    "饶了",
    "饶他",
    "不杀",
    "留他一命",
)
_GRIBBO_EXECUTE_CHOICE_MARKERS = (
    "execute",
    "kill",
    "finish him",
    "处决",
    "杀了",
    "解决他",
    "别留活口",
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


def _inventory_count(inventory: Mapping[str, Any], item_id: str) -> int:
    try:
        return int(inventory.get(item_id) or 0)
    except (TypeError, ValueError):
        return 0


def _object_payload(state: Mapping[str, Any], object_id: str) -> Dict[str, Any]:
    normalized_id = _normalize_id(object_id)
    for bucket_name in ("entities", "environment_objects"):
        bucket = _safe_dict(state.get(bucket_name))
        item = _safe_dict(bucket.get(normalized_id))
        if item:
            return item

    map_data = _safe_dict(state.get("map_data"))
    raw_env = map_data.get("environment_objects")
    if isinstance(raw_env, dict):
        return _safe_dict(raw_env.get(normalized_id))
    if isinstance(raw_env, list):
        for item in raw_env:
            payload = _safe_dict(item)
            if _normalize_id(payload.get("id")) == normalized_id:
                return payload
    return {}


def _door_is_open(state: Mapping[str, Any]) -> bool:
    for door_id in _KEY_GUIDANCE_DOOR_IDS:
        payload = _object_payload(state, door_id)
        if not payload:
            continue
        if bool(payload.get("is_open", False)):
            return True
        if _normalize_id(payload.get("status")) in {"open", "opened"}:
            return True
    return False


def _looks_like_key_guidance_request(
    *,
    state: Mapping[str, Any],
    user_input: str,
) -> bool:
    text = str(user_input or "").strip()
    if not text:
        return False
    lowered = text.lower()
    has_question_shape = any(marker in text or marker in lowered for marker in _KEY_GUIDANCE_QUESTION_MARKERS)
    if not has_question_shape:
        return False

    has_door_hint = ("门" in text) or ("door" in lowered) or any(
        marker in text or marker in lowered for marker in _KEY_GUIDANCE_DOOR_MARKERS
    )
    has_key_hint = any(marker in text or marker in lowered for marker in _KEY_GUIDANCE_KEY_MARKERS)
    has_next_step_hint = any(marker in text or marker in lowered for marker in ("接下来", "去哪", "下一步", "what next"))
    return has_door_hint or has_key_hint or has_next_step_hint


def detect_key_guidance_context(
    state: Mapping[str, Any],
    user_input: str,
    actor_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Detect read-only key-aware companion guidance for the necromancer lab door.
    This helper only observes world/inventory state and never mutates it.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None
    if _door_is_open(normalized_state):
        return None
    if not _looks_like_key_guidance_request(state=normalized_state, user_input=user_input):
        return None

    flags = _safe_dict(normalized_state.get("flags"))
    player_inventory = _safe_dict(normalized_state.get("player_inventory"))
    has_lab_key = (
        _inventory_count(player_inventory, "lab_key") > 0
        or _inventory_count(player_inventory, "heavy_iron_key") > 0
    )
    secret_study_found = any(_flag_bool(flags.get(flag)) for flag in _KEY_GUIDANCE_STUDY_FLAGS)
    diary_read = _flag_bool(flags.get("necromancer_lab_diary_read"))
    diary_decoded = _flag_bool(flags.get("necromancer_lab_diary_decoded")) or _flag_bool(
        flags.get("necromancer_lab_key_hint_known")
    )

    return {
        "topic": "lab_key",
        "door_id": "door_b_to_d",
        "legacy_door_id": "heavy_oak_door_1",
        "actor_id": _normalize_id(actor_id),
        "has_lab_key": has_lab_key,
        "secret_study_found": secret_study_found,
        "diary_read": diary_read,
        "diary_decoded": diary_decoded,
        "missing_key_hint": "缺少 lab_key：先找 room_c_secret_study，读 necromancer_diary，再搜刮 study_chest；也可以尝试撬锁。",
        "has_key_hint": "lab_key 已在背包里：去打开 door_b_to_d / 实验室门。",
        "lockpick_hint": "如果暂时找不到钥匙，可以让擅长手上功夫的人尝试撬锁。",
    }


def _is_gribbo_target(state: Mapping[str, Any]) -> bool:
    intent_context = _safe_dict(state.get("intent_context"))
    target = _normalize_id(
        state.get("active_dialogue_target")
        or state.get("target")
        or intent_context.get("action_target")
    )
    return target == "gribbo"


def _dynamic_state_value(entity: Mapping[str, Any], state_key: str, default: int = 0) -> int:
    dynamic_states = _safe_dict(entity.get("dynamic_states"))
    payload = dynamic_states.get(state_key)
    raw_value = payload.get("current_value", payload.get("value", default)) if isinstance(payload, dict) else payload
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _dynamic_state_bool(entity: Mapping[str, Any], state_key: str) -> bool:
    dynamic_states = _safe_dict(entity.get("dynamic_states"))
    payload = dynamic_states.get(state_key)
    if isinstance(payload, dict):
        return _flag_bool(payload.get("current_value", payload.get("value", False)))
    return _flag_bool(payload)


def _decoded_diary_from_memory(state: Mapping[str, Any]) -> bool:
    runtime_state = _safe_dict(state.get("actor_runtime_state"))
    memory_texts: List[str] = []
    for bucket_id in ("player", "__party_shared__"):
        bucket = _safe_dict(runtime_state.get(bucket_id))
        memory_texts.extend(str(item) for item in _safe_list(bucket.get("memory_notes")))
    joined = "\n".join(memory_texts)
    if not joined:
        return False
    has_diary_truth = ("我读懂了" in joined or "队伍确认" in joined or "diary" in joined.lower())
    has_gribbo_context = "Gribbo" in joined or "gribbo" in joined.lower()
    has_leverage_context = any(token in joined for token in ("heavy_iron_key", "解药", "药剂", "毒气陷阱"))
    return has_diary_truth and has_gribbo_context and has_leverage_context


def detect_diary_negotiation_context(
    state: Mapping[str, Any],
    user_input: str,
) -> Optional[Dict[str, Any]]:
    """
    Detect read-only Act2 diary leverage during Gribbo negotiation.
    Returns context for both decoded and non-decoded cases; callers decide whether to branch.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None
    if not _is_gribbo_target(normalized_state):
        return None

    text = str(user_input or "").strip()
    lowered = text.lower()
    if not text or not any(marker in text or marker in lowered for marker in _DIARY_NEGOTIATION_MARKERS):
        return None

    flags = _safe_dict(normalized_state.get("flags"))
    decoded_diary = (
        _flag_bool(flags.get("necromancer_lab_diary_decoded"))
        or _flag_bool(flags.get("necromancer_lab_antidote_formula_fragment_known"))
        or _flag_bool(flags.get("necromancer_lab_key_hint_known"))
        or _decoded_diary_from_memory(normalized_state)
    )
    evidence = []
    if decoded_diary:
        evidence.append("necromancer_diary")
        if _flag_bool(flags.get("necromancer_lab_antidote_formula_fragment_known")):
            evidence.append("antidote_fragment")
        if _flag_bool(flags.get("necromancer_lab_key_hint_known")):
            evidence.append("key_hint")

    gribbo = _safe_dict(_safe_dict(normalized_state.get("entities")).get("gribbo"))
    patience = _dynamic_state_value(gribbo, "patience", default=10)
    fear = _dynamic_state_value(gribbo, "fear", default=0)
    paranoia = _dynamic_state_value(gribbo, "paranoia", default=0)
    return {
        "topic": "gribbo_elixir_truth",
        "decoded_diary": decoded_diary,
        "evidence": evidence,
        "target_actor_id": "gribbo",
        "patience_current": patience,
        "fear_current": fear,
        "paranoia_current": paranoia,
        "pressure_hint": "用 necromancer_diary 中的死灵狂暴灵药真相压迫 Gribbo，但不要直接赠送钥匙或强制开战。",
    }


def detect_study_chest_loot_context(
    state: Mapping[str, Any],
    user_input: str,
) -> Optional[Dict[str, Any]]:
    """
    Detect a small Necromancer Lab study chest loot/open request.
    This only resolves the target and never mutates state.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None

    text = str(user_input or "").strip()
    lowered = text.lower()
    if not text:
        return None
    if not any(marker in text or marker in lowered for marker in _STUDY_CHEST_ACTION_MARKERS):
        return None
    if any(marker in text or marker in lowered for marker in _STUDY_CHEST_ALIASES):
        return {
            "topic": "study_chest_lab_key",
            "target_id": "chest_1",
            "alias_ids": ["study_chest"],
            "item_id": "lab_key",
        }
    return None


def detect_trap_awareness_context(
    state: Mapping[str, Any],
    user_input: str,
    intent_context: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Detect the Necromancer Lab poison-trap awareness beat.
    This helper is read-only: it reports whether Astarion can warn/disarm and
    whether the trap is already revealed, disarmed, or triggered.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None

    entities = _safe_dict(normalized_state.get("entities"))
    astarion = _safe_dict(entities.get("astarion"))
    if not astarion or _normalize_id(astarion.get("status")) in {"dead", "downed", "unconscious"}:
        return None
    if astarion.get("is_alive") is False:
        return None

    flags = _safe_dict(normalized_state.get("flags"))
    detected_flag = _flag_bool(flags.get("astarion_detected_gas_trap"))
    revealed = _flag_bool(flags.get("necromancer_lab_poison_trap_revealed"))
    disarmed = _flag_bool(flags.get("necromancer_lab_poison_trap_disarmed"))
    triggered = _flag_bool(flags.get("necromancer_lab_poison_trap_triggered"))
    trap = _object_payload(normalized_state, "gas_trap_1")
    trap_status = _normalize_id(trap.get("status"))
    if trap_status in {"disabled", "disarmed"}:
        disarmed = True
    if trap_status == "triggered":
        triggered = True
    # Do not treat `is_hidden=false` alone as full narrative reveal. The UI can
    # use that for projection, but Act2 reveal must come from Astarion's signal
    # or an explicit trap status/flag so metadata does not leak early.
    if trap_status == "revealed":
        revealed = True

    can_detect = detected_flag or _astarion_detects_trap(entities)
    ctx = _safe_dict(intent_context)
    target = _normalize_id(ctx.get("action_target") or normalized_state.get("target"))
    text = str(user_input or "").strip()
    lowered = text.lower()
    explicit_trap_target = target in {"gas_trap_1", "poison_trap_1", "poison_trap_2", "trap"}
    looks_relevant = explicit_trap_target or any(
        marker in text or marker in lowered for marker in _TRAP_AWARENESS_MARKERS
    )
    if not looks_relevant:
        return None

    return {
        "topic": "poison_trap",
        "trap_id": "gas_trap_1",
        "actor_id": "astarion",
        "can_detect": bool(can_detect),
        "can_disarm": bool(can_detect and not disarmed and not triggered),
        "revealed": bool(revealed),
        "disarmed": bool(disarmed),
        "triggered": bool(triggered),
    }


def _coordinate_from_payload(payload: Mapping[str, Any]) -> Optional[tuple[int, int]]:
    if "x" in payload and "y" in payload:
        try:
            return int(payload.get("x")), int(payload.get("y"))
        except (TypeError, ValueError):
            return None

    position = payload.get("position")
    if isinstance(position, (list, tuple)) and len(position) == 2:
        try:
            return int(position[0]), int(position[1])
        except (TypeError, ValueError):
            return None
    return None


def _chebyshev_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]))


def detect_poison_trap_trigger_context(
    state: Mapping[str, Any],
    user_input: str,
    intent_context: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Detect the explicit Act2 poison-trap trigger action.
    This helper is read-only; mechanics owns mutation and journal writes.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None

    ctx = _safe_dict(intent_context)
    target = _normalize_id(ctx.get("action_target") or normalized_state.get("target"))
    source = _normalize_id(ctx.get("source") or normalized_state.get("source"))
    intent = _normalize_id(normalized_state.get("intent")).upper()
    text = str(user_input or normalized_state.get("user_input") or "").strip()
    lowered = text.lower()
    explicit_target = target in {"gas_trap_1", "poison_trap_1", "poison_trap_2", "poison_trap"}
    explicit_source = source == "trap_trigger"
    explicit_intent = intent == "TRIGGER_TRAP"
    explicit_text = "gas_trap_1" in lowered and any(
        marker in lowered or marker in text
        for marker in ("trigger", "trigger_trap", "trap_trigger", "触发", "踩中")
    )
    if not (explicit_target or explicit_source or explicit_intent or explicit_text):
        return None

    flags = _safe_dict(normalized_state.get("flags"))
    trap = _object_payload(normalized_state, "gas_trap_1")
    trap_status = _normalize_id(trap.get("status"))
    if _flag_bool(flags.get("necromancer_lab_poison_trap_disarmed")):
        return None
    if _flag_bool(flags.get("necromancer_lab_poison_trap_triggered")):
        return None
    if trap_status in {"disabled", "disarmed", "triggered"}:
        return None

    trap_coord = _coordinate_from_payload(trap)
    radius = 0
    try:
        radius = max(0, int(trap.get("trigger_radius") or 0))
    except (TypeError, ValueError):
        radius = 0

    affected_actor_ids: List[str] = []
    entities = _safe_dict(normalized_state.get("entities"))
    if trap_coord is not None:
        for actor_id in ("player", "astarion", "shadowheart", "laezel"):
            actor = _safe_dict(entities.get(actor_id))
            if not actor:
                continue
            if _normalize_id(actor.get("status")) in {"dead", "downed", "unconscious"}:
                continue
            if actor.get("is_alive") is False:
                continue
            actor_coord = _coordinate_from_payload(actor)
            if actor_coord is None:
                continue
            if _chebyshev_distance(trap_coord, actor_coord) <= radius:
                affected_actor_ids.append(actor_id)

    if not affected_actor_ids:
        affected_actor_ids.append("player")

    return {
        "topic": "poison_trap_trigger",
        "trap_id": "gas_trap_1",
        "trigger_actor_id": _normalize_id(ctx.get("action_actor")) or "player",
        "affected_actor_ids": affected_actor_ids,
    }


def _astarion_memory_notes(state: Mapping[str, Any]) -> str:
    runtime_state = _safe_dict(state.get("actor_runtime_state"))
    astarion_state = _safe_dict(runtime_state.get("astarion"))
    return "\n".join(str(item) for item in _safe_list(astarion_state.get("memory_notes")))


def _detect_astarion_history_type(state: Mapping[str, Any]) -> str:
    flags = _safe_dict(state.get("flags"))
    notes = _astarion_memory_notes(state)
    notes_lower = notes.lower()

    sided_flag = flags.get("necromancer_lab_player_sided_with_astarion")
    if sided_flag is True:
        return "sided_with_player"
    if (
        sided_flag is False
        and "necromancer_lab_player_sided_with_astarion" in flags
        and _flag_bool(flags.get("necromancer_lab_astarion_mocked_gribbo"))
    ):
        return "rebuked_by_player"

    if any(token in notes for token in ("训斥", "闭嘴", "记住这笔账", "羞辱")) or any(
        token in notes_lower for token in ("rebuke", "humiliat", "insult")
    ):
        return "rebuked_by_player"
    if any(token in notes for token in ("一起嘲笑", "默契", "同调", "满意")) or any(
        token in notes_lower for token in ("side_with", "sided", "complicit")
    ):
        return "sided_with_player"
    return ""


def detect_astarion_memory_echo_context(
    state: Mapping[str, Any],
    user_input: str,
    intent_context: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Detect whether Astarion should surface Act3 relationship memory.
    The helper is read-only and never blocks the requested action.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None

    memory_type = _detect_astarion_history_type(normalized_state)
    if not memory_type:
        return None

    ctx = _safe_dict(intent_context)
    text = str(user_input or "").strip()
    lowered = text.lower()
    target = _normalize_id(
        ctx.get("action_target")
        or normalized_state.get("target")
        or normalized_state.get("active_dialogue_target")
    )
    actor = _normalize_id(ctx.get("action_actor") or normalized_state.get("current_speaker"))
    responders = ctx.get("responders")
    responder_hits = isinstance(responders, list) and "astarion" in {
        _normalize_id(item) for item in responders
    }
    mentions_astarion = any(marker in text or marker in lowered for marker in _ASTARION_MEMORY_ACTOR_MARKERS)
    needs_astarion = (
        target == "astarion"
        or actor == "astarion"
        or responder_hits
        or mentions_astarion
        or bool(ctx.get("key_guidance_context"))
        or bool(ctx.get("trap_awareness_context"))
    )
    collaboration = any(marker in text or marker in lowered for marker in _ASTARION_MEMORY_COLLAB_MARKERS)
    if not needs_astarion or not collaboration:
        return None

    return {
        "topic": "memory_echo",
        "actor_id": "astarion",
        "memory_type": memory_type,
        "severity": "resentful" if memory_type == "rebuked_by_player" else "complicit",
        "should_block_action": False,
    }


def _gribbo_in_mercy_window(state: Mapping[str, Any]) -> bool:
    flags = _safe_dict(state.get("flags"))
    if _flag_bool(flags.get("necromancer_lab_gribbo_mercy_window")):
        return True
    if _flag_bool(flags.get("necromancer_lab_gribbo_defeated")):
        return True
    if _flag_bool(flags.get("world_necromancer_lab_gribbo_defeated")):
        return True
    gribbo = _safe_dict(_safe_dict(state.get("entities")).get("gribbo"))
    if not gribbo:
        return False
    status = _normalize_id(gribbo.get("status"))
    if status in {"defeated", "pleading"}:
        return True
    return _dynamic_state_bool(gribbo, "mercy_window")


def _detect_gribbo_mercy_choice(user_input: str) -> str:
    text = str(user_input or "").strip()
    lowered = text.lower()
    if not text:
        return ""
    if any(marker in text or marker in lowered for marker in _GRIBBO_EXECUTE_CHOICE_MARKERS):
        return "execute"
    if any(marker in text or marker in lowered for marker in _GRIBBO_MERCY_CHOICE_MARKERS):
        return "mercy"
    return ""


def detect_gribbo_mercy_context(
    state: Mapping[str, Any],
    user_input: str,
    intent_context: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Detect the post-defeat Gribbo mercy choice encounter.
    This helper is read-only; callers decide whether to ask for stances or resolve a choice.
    """
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return None

    entities = _safe_dict(normalized_state.get("entities"))
    if not _safe_dict(entities.get("gribbo")):
        return None
    flags = _safe_dict(normalized_state.get("flags"))
    if _flag_bool(flags.get("necromancer_lab_gribbo_mercy_resolved")):
        return None
    if not _gribbo_in_mercy_window(normalized_state):
        return None

    ctx = _safe_dict(intent_context)
    text = str(user_input or "").strip()
    lowered = text.lower()
    target = _normalize_id(
        ctx.get("action_target")
        or normalized_state.get("target")
        or normalized_state.get("active_dialogue_target")
    )
    asks_for_stance = any(marker in text or marker in lowered for marker in _GRIBBO_MERCY_STANCE_MARKERS)
    explicit_choice = _normalize_id(ctx.get("gribbo_mercy_choice") or ctx.get("choice"))
    choice = explicit_choice if explicit_choice in {"mercy", "execute"} else _detect_gribbo_mercy_choice(text)
    if asks_for_stance and explicit_choice not in {"mercy", "execute"}:
        choice = ""
    if not choice and not asks_for_stance and target not in {"gribbo", ""}:
        return None
    if not choice and not asks_for_stance:
        return None

    diary_decoded = (
        _flag_bool(flags.get("necromancer_lab_diary_decoded"))
        or _flag_bool(flags.get("necromancer_lab_antidote_formula_fragment_known"))
        or _flag_bool(flags.get("necromancer_lab_key_hint_known"))
        or _decoded_diary_from_memory(normalized_state)
    )
    memory_type = _detect_astarion_history_type(normalized_state) or "none"
    return {
        "topic": "gribbo_mercy",
        "target_id": "gribbo",
        "phase": "resolution" if choice else "stance",
        "choice": choice,
        "diary_decoded": bool(diary_decoded),
        "astarion_memory_type": memory_type,
        "available_choices": ["mercy", "execute"],
        "party_summary": "Gribbo 可能是实验受害者。" if diary_decoded else "Gribbo 已失去战斗能力。",
    }


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


def detect_lab_act4_post_combat_banter(state: Dict[str, Any]) -> bool:
    normalized_state = _safe_dict(state)
    if _map_id(normalized_state) != "necromancer_lab":
        return False

    flags = _safe_dict(normalized_state.get("flags"))
    if _flag_bool(flags.get("necromancer_lab_post_combat_banter_done")):
        return False
    if not _flag_bool(flags.get("world_necromancer_lab_gribbo_defeated")):
        return False

    player_inventory = _safe_dict(normalized_state.get("player_inventory"))
    if int(player_inventory.get("heavy_iron_key") or 0) <= 0:
        return False

    intent_context = _safe_dict(normalized_state.get("intent_context"))
    if bool(intent_context.get("act4_post_combat_banter")):
        return True

    user_input = str(normalized_state.get("user_input") or "")
    normalized_input = user_input.strip().lower()
    if not normalized_input:
        return False
    return any(marker in user_input or marker in normalized_input for marker in _ACT4_BANTER_MARKERS)


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
