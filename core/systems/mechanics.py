"""
Game Mechanics Module (Model Layer)
Pure logic and calculation functions - no UI dependencies
"""

import ast
import copy
import logging
import random
import re
from typing import Any, Dict, List, Optional

from core.engine.physics import DEBUG_ALWAYS_PASS_CHECKS
from core.systems.dice import roll_d20
from core.systems.inventory import get_registry

logger = logging.getLogger(__name__)

DEFAULT_ATTACK_BONUS = 4
DEFAULT_DAMAGE_BONUS = 2
DEFAULT_DAMAGE_DIE_SIDES = 8
DEFAULT_EQUIPMENT = {"main_hand": None, "ranged": None, "armor": None}
EMPTY_EQUIPMENT = {"main_hand": None, "ranged": None, "armor": None}
LOOTABLE_STATUSES = frozenset({"dead", "open", "opened"})
USE_ITEM_INTENTS = frozenset({"USE_ITEM", "CONSUME"})
MOVE_INTENTS = frozenset({"MOVE", "APPROACH"})
EQUIP_INTENTS = frozenset({"EQUIP", "UNEQUIP"})
PLAYER_TARGET_ALIASES = frozenset({"我", "自己", "玩家", "me", "player"})
PLAYER_SIDE_ENTITY_IDS = frozenset({"player", "astarion", "shadowheart", "laezel"})


def calculate_ability_modifier(ability_score: int) -> int:
    """
    Calculate D&D 5e ability modifier from ability score.
    
    Formula: (ability_score - 10) // 2
    
    Args:
        ability_score: The ability score (typically 1-20)
    
    Returns:
        int: The ability modifier
    """
    return (ability_score - 10) // 2


def get_ability_modifiers(ability_scores: dict) -> dict:
    """
    Calculate all ability modifiers from ability scores.
    
    Args:
        ability_scores: Dictionary of ability scores (e.g., {"STR": 13, "DEX": 14, ...})
    
    Returns:
        dict: Dictionary of ability modifiers with same keys
    """
    return {ability: calculate_ability_modifier(score) for ability, score in ability_scores.items()}


def normalize_ability_name(ability_name: str) -> Optional[str]:
    """
    Normalize ability name to standard format (STR, DEX, CON, INT, WIS, CHA).
    Handles common abbreviations and case variations.
    
    Args:
        ability_name: User input ability name (e.g., "wis", "CHA", "charisma")
    
    Returns:
        Optional[str]: Standardized ability name (STR, DEX, CON, INT, WIS, CHA) or None if not found
    """
    ability_name = ability_name.upper().strip()
    
    # Mapping of common abbreviations to standard names
    ability_map = {
        "STR": "STR", "STRENGTH": "STR",
        "DEX": "DEX", "DEXTERITY": "DEX",
        "CON": "CON", "CONSTITUTION": "CON",
        "INT": "INT", "INTELLIGENCE": "INT",
        "WIS": "WIS", "WISDOM": "WIS",
        "CHA": "CHA", "CHARISMA": "CHA"
    }
    
    return ability_map.get(ability_name)


def _normalize_entity_id(entity_id: Any) -> str:
    return str(entity_id or "").strip().lower()


def _display_entity_name(entity: Dict[str, Any], fallback_id: str) -> str:
    name = str(entity.get("name") or "").strip()
    if name:
        return name
    if fallback_id == "player":
        return "玩家"
    return fallback_id.replace("_", " ").strip().title() or "未知目标"


def _build_player_combatant() -> Dict[str, Any]:
    return {
        "id": "player",
        "name": "玩家",
        "faction": "player",
        "ability_scores": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        "speed": 30,
        "hp": 20,
        "max_hp": 20,
        "ac": 10,
        "status": "alive",
        "inventory": {},
        "equipment": dict(DEFAULT_EQUIPMENT),
        "position": "camp_center",
        "x": 4,
        "y": 9,
        "active_buffs": [],
        "affection": 0,
    }


def _ensure_actor_entity(
    *,
    actor_id: str,
    entities: Dict[str, Any],
    state: Any,
) -> Dict[str, Any]:
    if actor_id == "player":
        existing = entities.get("player")
        if isinstance(existing, dict):
            existing.setdefault("name", "玩家")
            existing.setdefault("faction", "player")
            existing.setdefault(
                "ability_scores",
                {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
            )
            existing.setdefault("speed", 30)
            existing.setdefault("max_hp", existing.get("hp", 20))
            existing.setdefault("status", "alive")
            existing.setdefault("inventory", {})
            _get_equipment(existing)
            return existing

        fallback = state.get("party_status", {}).get("player") if isinstance(state, dict) else None
        player_data = _build_player_combatant()
        if isinstance(fallback, dict):
            player_data["hp"] = int(fallback.get("hp", player_data["hp"]))
            player_data["max_hp"] = int(fallback.get("max_hp", player_data["max_hp"]))
            player_data["status"] = str(fallback.get("status", player_data["status"]))
        entities["player"] = player_data
        return entities["player"]

    actor = entities.get(actor_id)
    if not isinstance(actor, dict):
        actor = {
            "name": actor_id.replace("_", " ").title(),
            "faction": "party" if actor_id in PLAYER_SIDE_ENTITY_IDS else "neutral",
            "ability_scores": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
            "speed": 30,
            "hp": 20,
            "max_hp": 20,
            "status": "alive",
            "inventory": {},
            "equipment": dict(EMPTY_EQUIPMENT),
        }
        entities[actor_id] = actor
    actor.setdefault("max_hp", actor.get("hp", 20))
    actor.setdefault("speed", 30)
    actor.setdefault("status", "alive")
    actor.setdefault("inventory", {})
    _get_equipment(actor)
    return actor


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "").strip().lower())


def _target_text_matches(normalized_query: str, candidate_id: str, candidate_name: str) -> bool:
    if (
        normalized_query in candidate_id
        or normalized_query in candidate_name
        or candidate_id in normalized_query
        or candidate_name in normalized_query
    ):
        return True

    chest_aliases = ("宝箱", "箱子", "铁箱子", "chest")
    if any(alias in normalized_query for alias in chest_aliases):
        return "chest" in candidate_id or "箱" in candidate_name

    goblin_aliases = ("地精", "哥布林", "goblin")
    if any(alias in normalized_query for alias in goblin_aliases):
        return "goblin" in candidate_id or "地精" in candidate_name or "哥布林" in candidate_name

    fire_aliases = ("篝火", "营火", "火堆", "campfire", "fire")
    if any(alias in normalized_query for alias in fire_aliases):
        return (
            "campfire" in candidate_id
            or "篝火" in candidate_name
            or "营火" in candidate_name
            or "火堆" in candidate_name
        )

    return False


def _resolve_target_reference(
    *,
    target_id: str,
    entities: Dict[str, Any],
    environment_objects: Dict[str, Any],
) -> tuple[str, Optional[Dict[str, Any]], str]:
    normalized_target = _normalize_entity_id(target_id)
    if not normalized_target:
        return "", None, ""

    if normalized_target in PLAYER_TARGET_ALIASES:
        normalized_target = "player"

    if normalized_target in entities and isinstance(entities[normalized_target], dict):
        target = entities[normalized_target]
        return normalized_target, target, _display_entity_name(target, normalized_target)

    if normalized_target in environment_objects and isinstance(environment_objects[normalized_target], dict):
        target = environment_objects[normalized_target]
        return normalized_target, target, str(target.get("name") or normalized_target.replace("_", " ").title())

    normalized_query = _normalize_match_text(target_id)
    if not normalized_query:
        return "", None, ""

    search_spaces = (
        ("environment", environment_objects),
        ("entity", entities),
    )
    for _, collection in search_spaces:
        for actual_id, target in collection.items():
            if not isinstance(target, dict):
                continue
            candidate_id = _normalize_match_text(actual_id)
            candidate_name = _normalize_match_text(target.get("name", ""))
            if not any((candidate_id, candidate_name)):
                continue
            if _target_text_matches(normalized_query, candidate_id, candidate_name):
                display_name = (
                    _display_entity_name(target, str(actual_id))
                    if collection is entities
                    else str(target.get("name") or str(actual_id).replace("_", " ").title())
                )
                return str(actual_id).strip().lower(), target, display_name

    return normalized_target, None, normalized_target.replace("_", " ").title()


def _resolve_move_target(
    *,
    target_id: str,
    entities: Dict[str, Any],
    environment_objects: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], str]:
    _, target, target_name = _resolve_target_reference(
        target_id=target_id,
        entities=entities,
        environment_objects=environment_objects,
    )
    return target, target_name


def _move_toward_target(
    *,
    actor_x: int,
    actor_y: int,
    target_x: int,
    target_y: int,
) -> tuple[int, int]:
    dx = target_x - actor_x
    dy = target_y - actor_y

    # 已经与目标相邻（含对角相邻）时，不再移动，避免棋子重叠。
    if abs(dx) <= 1 and abs(dy) <= 1:
        return actor_x, actor_y

    if abs(dx) > abs(dy):
        return target_x - (1 if dx > 0 else -1), target_y

    return target_x, target_y - (1 if dy > 0 else -1)


def _chebyshev_distance(
    *,
    actor_x: int,
    actor_y: int,
    target_x: int,
    target_y: int,
) -> int:
    return max(abs(target_x - actor_x), abs(target_y - actor_y))


def _sign(value: int) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _move_toward_target_with_range(
    *,
    actor_x: int,
    actor_y: int,
    target_x: int,
    target_y: int,
    desired_range: int,
) -> tuple[int, int]:
    desired_range = max(1, int(desired_range or 1))
    if _chebyshev_distance(
        actor_x=actor_x,
        actor_y=actor_y,
        target_x=target_x,
        target_y=target_y,
    ) <= desired_range:
        return actor_x, actor_y

    dx = target_x - actor_x
    dy = target_y - actor_y
    new_x = actor_x
    new_y = actor_y
    if abs(dx) > desired_range:
        new_x = target_x - (_sign(dx) * desired_range)
    if abs(dy) > desired_range:
        new_y = target_y - (_sign(dy) * desired_range)
    return new_x, new_y


def _movement_budget_from_speed(entity: Dict[str, Any]) -> int:
    speed = _coerce_int(entity.get("speed"), 30)
    # Character YAML follows 5e feet; the tactical grid consumes 5 feet per tile.
    return max(1, speed // 5)


def _move_toward_target_with_range_and_budget(
    *,
    actor_x: int,
    actor_y: int,
    target_x: int,
    target_y: int,
    desired_range: int,
    max_steps: int,
) -> tuple[int, int]:
    desired_range = max(1, int(desired_range or 1))
    max_steps = max(0, int(max_steps or 0))
    new_x = actor_x
    new_y = actor_y

    for _ in range(max_steps):
        if _chebyshev_distance(
            actor_x=new_x,
            actor_y=new_y,
            target_x=target_x,
            target_y=target_y,
        ) <= desired_range:
            break

        dx = target_x - new_x
        dy = target_y - new_y
        if abs(dx) > desired_range:
            new_x += _sign(dx)
        if abs(dy) > desired_range:
            new_y += _sign(dy)

    return new_x, new_y


def _auto_approach_actor_to_target(
    *,
    entities: Dict[str, Any],
    state: Any,
    actor_id: str,
    target: Dict[str, Any],
    target_name: str,
    desired_range: int = 1,
    journal_template: str = "🚶 [自动寻路] {actor_name} 走向了 {target_name}。",
) -> List[str]:
    actor = _ensure_actor_entity(actor_id=actor_id, entities=entities, state=state)
    actor_x = _coerce_int(actor.get("x"), 4)
    actor_y = _coerce_int(actor.get("y"), 9)
    target_x = _coerce_int(target.get("x"), actor_x)
    target_y = _coerce_int(target.get("y"), actor_y)

    if _chebyshev_distance(
        actor_x=actor_x,
        actor_y=actor_y,
        target_x=target_x,
        target_y=target_y,
    ) <= max(1, int(desired_range or 1)):
        return []

    new_x, new_y = _move_toward_target_with_range(
        actor_x=actor_x,
        actor_y=actor_y,
        target_x=target_x,
        target_y=target_y,
        desired_range=desired_range,
    )
    actor["x"] = new_x
    actor["y"] = new_y
    actor["position"] = f"靠近 {target_name}"
    actor_name = _display_entity_name(actor, actor_id)
    return [journal_template.format(actor_name=actor_name, target_name=target_name)]


def _resolve_item_id_from_context(intent_context: Dict[str, Any]) -> str:
    return str(
        intent_context.get("item_id")
        or intent_context.get("target_item")
        or intent_context.get("action_target")
        or ""
    ).strip().lower()


def _get_equipment(entity: Dict[str, Any]) -> Dict[str, Any]:
    equipment = entity.setdefault("equipment", dict(EMPTY_EQUIPMENT))
    if not isinstance(equipment, dict):
        equipment = dict(EMPTY_EQUIPMENT)
        entity["equipment"] = equipment
    legacy_weapon = equipment.pop("weapon", None)
    if legacy_weapon and not equipment.get("main_hand"):
        equipment["main_hand"] = legacy_weapon
    equipment.setdefault("main_hand", None)
    equipment.setdefault("ranged", None)
    equipment.setdefault("armor", None)
    return equipment


def _resolve_inventory_for_actor(
    *,
    actor_id: str,
    entities: Dict[str, Any],
    player_inventory: Dict[str, int],
) -> tuple[Dict[str, int], str]:
    if actor_id == "player":
        return player_inventory, "玩家"

    actor = entities.get(actor_id)
    if not isinstance(actor, dict):
        return player_inventory, "玩家"

    actor_inventory = actor.setdefault("inventory", {})
    if not isinstance(actor_inventory, dict):
        actor_inventory = {}
        actor["inventory"] = actor_inventory
    return actor_inventory, _display_entity_name(actor, actor_id)


def _equipment_slot_for_item(item_data: Dict[str, Any]) -> str:
    equip_slot = str(item_data.get("equip_slot", "")).strip().lower()
    if equip_slot in {"main_hand", "ranged", "armor"}:
        return equip_slot
    item_type = str(item_data.get("type", "")).strip().lower()
    if item_type == "weapon":
        return "main_hand"
    if item_type == "armor":
        return "armor"
    return ""


def _get_weapon_profile(attacker: Dict[str, Any]) -> Dict[str, Any]:
    equipment = _get_equipment(attacker)
    weapon_id = str(equipment.get("main_hand") or "").strip().lower()
    if not weapon_id:
        return {
            "id": "unarmed",
            "name": "徒手打击",
            "damage_dice": "1d4",
            "damage_bonus": 0,
            "range": 1,
        }

    item_data = get_registry().get(weapon_id)
    return {
        "id": weapon_id,
        "name": get_registry().get_name(weapon_id),
        "damage_dice": str(item_data.get("damage_dice") or item_data.get("damage") or "1d4"),
        "damage_bonus": _coerce_int(item_data.get("damage_bonus"), 0),
        "range": _coerce_int(item_data.get("range"), 1),
    }


def _is_consumable_item(item_id: str, item_data: Dict[str, Any]) -> bool:
    if item_data.get("equip_slot"):
        return False
    if item_data.get("is_consumable") is True:
        return True
    return str(item_data.get("type", "")).strip().lower() == "consumable"


def _is_alive_entity(entity: Dict[str, Any]) -> bool:
    if not isinstance(entity, dict):
        return False
    if str(entity.get("status", "alive")).strip().lower() in {"dead", "downed", "unconscious"}:
        return False
    return _coerce_int(entity.get("hp"), 1) > 0


def _is_hostile_entity(entity: Dict[str, Any]) -> bool:
    return str(entity.get("faction", "")).strip().lower() == "hostile"


def _is_player_side_entity(entity_id: str, entity: Dict[str, Any]) -> bool:
    normalized_id = _normalize_entity_id(entity_id)
    if normalized_id in PLAYER_SIDE_ENTITY_IDS:
        return True
    faction = str(entity.get("faction", "")).strip().lower()
    return bool(faction and faction not in {"hostile", "neutral"})


def _combatant_ids(entities: Dict[str, Any]) -> List[str]:
    combatants: List[str] = []
    for entity_id, entity in entities.items():
        if not isinstance(entity, dict) or not _is_alive_entity(entity):
            continue
        normalized_id = _normalize_entity_id(entity_id)
        if _is_hostile_entity(entity) or _is_player_side_entity(normalized_id, entity):
            combatants.append(normalized_id)
    return combatants


def _get_ability_score(entity: Dict[str, Any], ability_name: str, default: int = 10) -> int:
    ability_scores = entity.get("ability_scores") or {}
    if isinstance(ability_scores, dict):
        for key, value in ability_scores.items():
            if str(key).strip().upper() == ability_name.upper():
                return _coerce_int(value, default)
    return _coerce_int(entity.get(ability_name.lower()), default)


def _roll_initiative(entities: Dict[str, Any]) -> tuple[List[str], List[Dict[str, Any]], str]:
    entries: List[Dict[str, Any]] = []
    for entity_id in _combatant_ids(entities):
        entity = entities.get(entity_id) or {}
        dex_mod = calculate_ability_modifier(_get_ability_score(entity, "DEX", 10))
        raw_roll = random.randint(1, 20)
        total = raw_roll + dex_mod
        entries.append(
            {
                "id": entity_id,
                "name": _display_entity_name(entity, entity_id),
                "raw_roll": raw_roll,
                "dex_modifier": dex_mod,
                "total": total,
            }
        )

    entries.sort(key=lambda item: item["total"], reverse=True)
    order = [str(item["id"]) for item in entries]
    order_text = ", ".join(f"{item['name']}({item['total']})" for item in entries)
    return order, entries, f"⚔️ 战斗开始！先攻顺序：[{order_text}]"


def _combat_has_live_hostiles(entities: Dict[str, Any]) -> bool:
    return any(
        isinstance(entity, dict) and _is_alive_entity(entity) and _is_hostile_entity(entity)
        for entity in entities.values()
    )


def _combat_has_live_player_side(entities: Dict[str, Any]) -> bool:
    return any(
        isinstance(entity, dict)
        and _is_alive_entity(entity)
        and _is_player_side_entity(str(entity_id), entity)
        for entity_id, entity in entities.items()
    )


def _prune_initiative_order(order: List[str], entities: Dict[str, Any]) -> List[str]:
    pruned: List[str] = []
    for entity_id in order:
        normalized_id = _normalize_entity_id(entity_id)
        entity = entities.get(normalized_id)
        if isinstance(entity, dict) and _is_alive_entity(entity):
            pruned.append(normalized_id)
    return pruned


def _combat_end_event(entities: Dict[str, Any]) -> str:
    if not _combat_has_live_hostiles(entities):
        return "🏁 [战斗结束] 敌对单位已经被肃清。"
    if not _combat_has_live_player_side(entities):
        return "💀 [战斗结束] 队伍已经失去战斗能力。"
    return ""


def _get_active_turn_id(state: Any) -> str:
    initiative_order = state.get("initiative_order") or []
    if not isinstance(initiative_order, list) or not initiative_order:
        return ""
    current_turn_index = _coerce_int(state.get("current_turn_index"), 0)
    if current_turn_index < 0 or current_turn_index >= len(initiative_order):
        current_turn_index = 0
    return _normalize_entity_id(initiative_order[current_turn_index])


def _turn_side_key(entity_id: str, entity: Dict[str, Any]) -> str:
    if _is_hostile_entity(entity):
        return "hostile"
    if _is_player_side_entity(entity_id, entity):
        return "party"
    return "neutral"


def _get_active_turn_block(
    *,
    state: Any,
    entities: Dict[str, Any],
    initiative_order: Optional[List[str]] = None,
    current_turn_index: Optional[int] = None,
) -> List[str]:
    order = initiative_order if initiative_order is not None else list(state.get("initiative_order") or [])
    if not isinstance(order, list) or not order:
        return []
    index = (
        _coerce_int(current_turn_index, 0)
        if current_turn_index is not None
        else _coerce_int(state.get("current_turn_index"), 0)
    )
    if index < 0 or index >= len(order):
        index = 0

    first_id = _normalize_entity_id(order[index])
    first_entity = entities.get(first_id)
    if not isinstance(first_entity, dict) or not _is_alive_entity(first_entity):
        return []
    side_key = _turn_side_key(first_id, first_entity)
    block = [first_id]
    for offset in range(index + 1, len(order)):
        candidate_id = _normalize_entity_id(order[offset])
        candidate = entities.get(candidate_id)
        if not isinstance(candidate, dict) or not _is_alive_entity(candidate):
            break
        if _turn_side_key(candidate_id, candidate) != side_key:
            break
        block.append(candidate_id)
    return block


def _active_block_side(
    *,
    state: Any,
    entities: Dict[str, Any],
    initiative_order: Optional[List[str]] = None,
    current_turn_index: Optional[int] = None,
) -> str:
    block = _get_active_turn_block(
        state=state,
        entities=entities,
        initiative_order=initiative_order,
        current_turn_index=current_turn_index,
    )
    if not block:
        return ""
    entity = entities.get(block[0], {})
    if not isinstance(entity, dict):
        return ""
    return _turn_side_key(block[0], entity)


def _default_turn_resources(entity: Dict[str, Any]) -> Dict[str, int]:
    return {
        "action": 1,
        "bonus_action": 1,
        "movement": _movement_budget_from_speed(entity),
    }


def _ensure_turn_resources_for_block(
    *,
    state: Any,
    entities: Dict[str, Any],
    active_block: List[str],
    force_reset: bool = False,
) -> Dict[str, Dict[str, int]]:
    existing = copy.deepcopy(state.get("turn_resources") or {})
    if not isinstance(existing, dict):
        existing = {}
    for actor_id in active_block:
        actor = entities.get(actor_id, {})
        if (
            force_reset
            or actor_id not in existing
            or not isinstance(existing.get(actor_id), dict)
        ):
            existing[actor_id] = _default_turn_resources(actor if isinstance(actor, dict) else {})
    return existing


def _build_turn_lock_result(
    *,
    state: Any,
    intent: str,
    actor_id: str,
    target_id: str,
    entities: Dict[str, Any],
) -> Dict[str, Any]:
    active_id = _get_active_turn_id(state)
    state_entities = state.get("entities") or {}
    active_entity = (
        state_entities.get(active_id, {}) if isinstance(state_entities, dict) else {}
    )
    actor_entity = entities.get(actor_id, {}) if isinstance(entities, dict) else {}
    active_name = _display_entity_name(active_entity, active_id or "unknown")
    actor_name = _display_entity_name(actor_entity, actor_id or "unknown")
    message = (
        f"[系统驳回] 动作无效！当前是 {active_name} 的回合，"
        f"你不能越权指挥 {actor_name} 行动。"
    )
    return {
        "journal_events": [message],
        "entities": entities,
        "combat_active": bool(state.get("combat_active", False)),
        "initiative_order": list(state.get("initiative_order") or []),
        "current_turn_index": _coerce_int(state.get("current_turn_index"), 0),
        "turn_resources": copy.deepcopy(state.get("turn_resources") or {}),
        "raw_roll_data": _build_action_result(
            intent=intent,
            actor=actor_id,
            target=target_id,
            is_success=False,
            result_type="TURN_LOCKED",
        ),
        "turn_locked": True,
    }


def _reject_if_not_active_turn(
    *,
    state: Any,
    intent: str,
    actor_id: str,
    target_id: str,
    entities: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not bool(state.get("combat_active", False)):
        return None
    initiative_order = list(state.get("initiative_order") or [])
    if not initiative_order:
        return None
    active_block = _get_active_turn_block(
        state=state,
        entities=entities,
        initiative_order=initiative_order,
    )
    if not active_block:
        return None
    if _normalize_entity_id(actor_id) in active_block:
        return None
    return _build_turn_lock_result(
        state=state,
        intent=intent,
        actor_id=_normalize_entity_id(actor_id),
        target_id=target_id,
        entities=entities,
    )


def _build_action_result(
    *,
    intent: str,
    actor: str,
    target: str,
    is_success: bool,
    result_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "intent": intent,
        "actor": actor,
        "target": target,
        "result": {
            "is_success": is_success,
            "result_type": result_type,
        },
    }
    if extra:
        payload.update(extra)
    return payload


def _resolve_loot_destination(
    *,
    actor_id: str,
    entities: Dict[str, Any],
    player_inventory: Dict[str, int],
) -> tuple[Dict[str, int], str]:
    if actor_id == "player":
        return player_inventory, "玩家"

    actor = entities.get(actor_id)
    if not isinstance(actor, dict):
        return player_inventory, "玩家"

    actor_inventory = actor.setdefault("inventory", {})
    if not isinstance(actor_inventory, dict):
        actor_inventory = {}
        actor["inventory"] = actor_inventory
    return actor_inventory, _display_entity_name(actor, actor_id)


def _format_loot_entries(items: Dict[str, int]) -> str:
    registry = get_registry()
    entries: List[str] = []
    for item_id, count in items.items():
        if not item_id:
            continue
        try:
            qty = int(count)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        entries.append(f"{registry.get_name(item_id)} x {qty}")
    return ", ".join(entries)


def _is_unlockable_skill_success(
    *,
    intent: str,
    target_obj: Optional[Dict[str, Any]],
    result: Dict[str, Any],
) -> bool:
    if not bool(result.get("is_success", False)):
        return False

    if not isinstance(target_obj, dict):
        return False

    status = str(target_obj.get("status", "")).strip().lower()
    if status != "locked":
        return False

    normalized_intent = str(intent or "").strip().upper()
    return normalized_intent in {"SLEIGHT_OF_HAND", "ACTION"}


def execute_combat_attack(
    attacker: Dict[str, Any],
    defender: Dict[str, Any],
) -> Dict[str, Any]:
    """
    执行一次最小化 D20 攻击检定。
    规则骨架：1d20 + 4 vs AC；命中后造成 1d8 + 2 伤害，并直接修改 defender.hp/status。
    """
    attacker_id = _normalize_entity_id(attacker.get("id", "player")) or "player"
    defender_id = _normalize_entity_id(defender.get("id", ""))
    attacker_name = _display_entity_name(attacker, attacker_id)
    defender_name = _display_entity_name(defender, defender_id)
    defender_ac = int(defender.get("ac", 10))
    weapon_profile = _get_weapon_profile(attacker)
    weapon_name = str(weapon_profile.get("name") or "徒手打击")
    if str(weapon_profile.get("id") or "") == "unarmed":
        weapon_name = "徒手打击"
    damage_dice = str(weapon_profile.get("damage_dice", "1d4"))
    damage_bonus = _coerce_int(weapon_profile.get("damage_bonus"), 0)

    attack_roll = random.randint(1, 20)
    attack_total = attack_roll + DEFAULT_ATTACK_BONUS
    is_hit = attack_total >= defender_ac
    dice_roll_result = 0
    damage_total = 0

    if is_hit:
        dice_roll_result = parse_dice_string(damage_dice)
        damage_total = dice_roll_result + damage_bonus
        current_hp = int(defender.get("hp", 0))
        max_hp = int(defender.get("max_hp", current_hp))
        new_hp = max(0, current_hp - damage_total)
        defender["hp"] = new_hp
        defender["max_hp"] = max_hp
        defender["status"] = "dead" if new_hp <= 0 else "alive"

    attack_text = (
        f"🎲 [战斗检定] {attacker_name} 使用 {weapon_name} 对 {defender_name} 发起攻击。"
        f"命中检定: {attack_roll}(+{DEFAULT_ATTACK_BONUS}) = {attack_total} vs AC {defender_ac}，"
    )
    if is_hit:
        attack_text += (
            f"命中！造成 {damage_total} 点伤害 "
            f"(伤害骰: {damage_dice}[掷出 {dice_roll_result}] + 加成 {damage_bonus})。"
        )
    else:
        attack_text += "未命中！"

    journal_events = [attack_text]
    if is_hit and defender.get("status") == "dead":
        journal_events.append(f"☠️ [战斗结果] {defender_name} 倒下了。")

    return {
        "journal_events": journal_events,
        "raw_roll_data": {
            "intent": "ATTACK",
            "actor": attacker_id,
            "target": defender_id,
            "weapon": str(weapon_profile.get("id") or "unarmed"),
            "weapon_name": weapon_name,
            "range": int(weapon_profile.get("range", 1)),
            "dc": defender_ac,
            "modifier": DEFAULT_ATTACK_BONUS,
            "damage": {
                "rolls": [dice_roll_result] if dice_roll_result else [],
                "formula": damage_dice,
                "modifier": damage_bonus,
                "total": damage_total,
            },
            "result": {
                "total": attack_total,
                "raw_roll": attack_roll,
                "rolls": [attack_roll],
                "is_success": is_hit,
                "result_type": "HIT" if is_hit else "MISS",
                "target_ac": defender_ac,
            },
        },
    }


def execute_enemy_turn(enemy_id: str, state: Any) -> Dict[str, Any]:
    """
    敌方启发式 AI：寻找最近的玩家侧单位，按速度预算逼近，并在射程内攻击。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    turn_resources = copy.deepcopy(state.get("turn_resources") or {})
    if not isinstance(turn_resources, dict):
        turn_resources = {}
    enemy_id = _normalize_entity_id(enemy_id)
    enemy = entities.get(enemy_id)
    if not isinstance(enemy, dict) or not _is_alive_entity(enemy):
        return {"entities": entities, "journal_events": []}

    enemy_name = _display_entity_name(enemy, enemy_id)
    enemy_x = _coerce_int(enemy.get("x"), 4)
    enemy_y = _coerce_int(enemy.get("y"), 3)
    weapon_profile = _get_weapon_profile(enemy)
    weapon_range = max(1, _coerce_int(weapon_profile.get("range"), 1))
    if enemy_id not in turn_resources or not isinstance(turn_resources.get(enemy_id), dict):
        turn_resources[enemy_id] = _default_turn_resources(enemy)

    target_id = ""
    target_obj: Optional[Dict[str, Any]] = None
    target_distance = 999
    for candidate_id, candidate in entities.items():
        normalized_candidate_id = _normalize_entity_id(candidate_id)
        if normalized_candidate_id == enemy_id:
            continue
        if not isinstance(candidate, dict) or not _is_alive_entity(candidate):
            continue
        if not _is_player_side_entity(normalized_candidate_id, candidate):
            continue
        distance = _chebyshev_distance(
            actor_x=enemy_x,
            actor_y=enemy_y,
            target_x=_coerce_int(candidate.get("x"), enemy_x),
            target_y=_coerce_int(candidate.get("y"), enemy_y),
        )
        if distance < target_distance:
            target_id = normalized_candidate_id
            target_obj = candidate
            target_distance = distance

    if not target_id or not isinstance(target_obj, dict):
        return {
            "entities": entities,
            "journal_events": [f"👹 [敌方回合] {enemy_name} 找不到可攻击目标。"],
        }

    target_name = _display_entity_name(target_obj, target_id)
    journal_events = [f"[敌方AI] {enemy_name} 锁定了 {target_name}。"]
    target_x = _coerce_int(target_obj.get("x"), enemy_x)
    target_y = _coerce_int(target_obj.get("y"), enemy_y)

    if target_distance > weapon_range:
        new_x, new_y = _move_toward_target_with_range_and_budget(
            actor_x=enemy_x,
            actor_y=enemy_y,
            target_x=target_x,
            target_y=target_y,
            desired_range=weapon_range,
            max_steps=_movement_budget_from_speed(enemy),
        )
        if (new_x, new_y) != (enemy_x, enemy_y):
            enemy["x"] = new_x
            enemy["y"] = new_y
            enemy["position"] = f"靠近 {target_name}"
            journal_events.append(
                f"[敌方AI] {enemy_name} 向 {target_name} 逼近至 ({new_x}, {new_y})。"
            )
            enemy_x, enemy_y = new_x, new_y

    final_distance = _chebyshev_distance(
        actor_x=enemy_x,
        actor_y=enemy_y,
        target_x=target_x,
        target_y=target_y,
    )
    raw_roll_data = None
    resource_pool = turn_resources.get(enemy_id, {}) if isinstance(turn_resources, dict) else {}
    if final_distance <= weapon_range and int(resource_pool.get("action", 0) or 0) > 0:
        enemy["id"] = enemy_id
        target_obj["id"] = target_id
        attack_result = execute_combat_attack(attacker=enemy, defender=target_obj)
        journal_events.extend(attack_result.get("journal_events", []))
        raw_roll_data = attack_result.get("raw_roll_data")
        if isinstance(turn_resources, dict):
            resource_pool = dict(resource_pool) if isinstance(resource_pool, dict) else {}
            resource_pool["action"] = max(0, int(resource_pool.get("action", 0) or 0) - 1)
            turn_resources[enemy_id] = resource_pool
    elif final_distance <= weapon_range:
        journal_events.append(
            f"[敌方AI] {enemy_name} 动作点数不足，无法发动攻击。"
        )
    else:
        journal_events.append(
            f"[敌方AI] {enemy_name} 距离过远，原地待命。"
        )

    payload: Dict[str, Any] = {
        "entities": entities,
        "journal_events": journal_events,
    }
    if raw_roll_data:
        payload["raw_roll_data"] = raw_roll_data
    if isinstance(turn_resources, dict):
        payload["turn_resources"] = turn_resources
    return payload


def advance_combat_after_action(state: Any, action_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    玩家/队友动作后推进回合：敌人自动行动，队友暂时待命，直到再次轮到 player。
    """
    if not isinstance(action_result, dict):
        return action_result
    if action_result.get("turn_locked"):
        return action_result

    combat_active = bool(action_result.get("combat_active", state.get("combat_active", False)))
    initiative_order = list(action_result.get("initiative_order") or state.get("initiative_order") or [])
    if not combat_active or not initiative_order:
        return action_result

    entities = copy.deepcopy(action_result.get("entities") or state.get("entities") or {})
    if not isinstance(entities, dict) or not entities:
        return action_result

    journal_events = list(action_result.get("journal_events") or [])
    turn_resources = copy.deepcopy(action_result.get("turn_resources") or state.get("turn_resources") or {})
    if not isinstance(turn_resources, dict):
        turn_resources = {}
    initiative_order = _prune_initiative_order(initiative_order, entities)
    end_event = _combat_end_event(entities)
    if end_event:
        return {
            **action_result,
            "entities": entities,
            "journal_events": journal_events + [end_event],
            "combat_active": False,
            "initiative_order": [],
            "current_turn_index": 0,
        }
    if not initiative_order:
        return {
            **action_result,
            "entities": entities,
            "journal_events": journal_events,
            "combat_active": False,
            "initiative_order": [],
            "current_turn_index": 0,
        }

    current_turn_index = _coerce_int(
        action_result.get("current_turn_index", state.get("current_turn_index", 0)),
        0,
    )
    if action_result.get("skip_advance"):
        current_turn_index %= len(initiative_order)
    else:
        current_turn_index %= len(initiative_order)

    max_iterations = max(1, len(initiative_order) * 2)
    for _ in range(max_iterations):
        initiative_order = _prune_initiative_order(initiative_order, entities)
        end_event = _combat_end_event(entities)
        if end_event:
            return {
                **action_result,
                "entities": entities,
                "journal_events": journal_events + [end_event],
                "combat_active": False,
                "initiative_order": [],
                "current_turn_index": 0,
            }
        if not initiative_order:
            break

        current_turn_index %= len(initiative_order)
        active_block = _get_active_turn_block(
            state=state,
            entities=entities,
            initiative_order=initiative_order,
            current_turn_index=current_turn_index,
        )
        if not active_block:
            current_turn_index = (current_turn_index + 1) % len(initiative_order)
            continue

        block_entities = [entities.get(actor_id, {}) for actor_id in active_block]
        block_side = _turn_side_key(active_block[0], block_entities[0]) if block_entities else "neutral"

        if block_side == "party":
            turn_resources = _ensure_turn_resources_for_block(
                state=action_result,
                entities=entities,
                active_block=active_block,
                force_reset=False,
            )
            all_spent = True
            for actor_id in active_block:
                resources = turn_resources.get(actor_id, {})
                if int(resources.get("action", 0) or 0) > 0 or int(resources.get("bonus_action", 0) or 0) > 0:
                    all_spent = False
                    break
            if all_spent:
                for actor_id in active_block:
                    resources = turn_resources.get(actor_id, {})
                    if isinstance(resources, dict):
                        resources["action"] = 0
                        resources["bonus_action"] = 0
                        turn_resources[actor_id] = resources
                current_turn_index = (current_turn_index + len(active_block)) % len(initiative_order)
                action_result = {**action_result, "turn_resources": turn_resources}
                continue
            break

        if block_side == "hostile":
            turn_resources = _ensure_turn_resources_for_block(
                state=action_result,
                entities=entities,
                active_block=active_block,
                force_reset=True,
            )
            for enemy_id in active_block:
                enemy_result = execute_enemy_turn(
                    enemy_id,
                    {
                        **state,
                        **action_result,
                        "entities": entities,
                        "turn_resources": turn_resources,
                    },
                )
                entities = copy.deepcopy(enemy_result.get("entities") or entities)
                journal_events.extend(enemy_result.get("journal_events", []))
                if "turn_resources" in enemy_result:
                    turn_resources = copy.deepcopy(enemy_result.get("turn_resources") or turn_resources)
            current_turn_index = (current_turn_index + len(active_block)) % len(initiative_order)
            action_result = {**action_result, "turn_resources": turn_resources}
            continue

        current_turn_index = (current_turn_index + len(active_block)) % len(initiative_order)

    return {
        **action_result,
        "entities": entities,
        "journal_events": journal_events,
        "combat_active": True,
        "initiative_order": initiative_order,
        "current_turn_index": current_turn_index if initiative_order else 0,
        "turn_resources": turn_resources,
    }


def execute_end_turn_action(state: Any) -> Dict[str, Any]:
    """
    放弃行动：结束当前行动者的回合。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    turn_resources = copy.deepcopy(state.get("turn_resources") or {})
    if not isinstance(turn_resources, dict):
        turn_resources = {}
    intent_context = state.get("intent_context") or {}
    active_id = _get_active_turn_id(state)
    if not bool(state.get("combat_active", False)) or not active_id:
        return {
            "journal_events": ["[系统提示] 当前不在战斗中，无法结束回合。"],
            "entities": entities,
        }

    requested_actor = _normalize_entity_id(intent_context.get("action_actor", active_id) or active_id)
    action_target = str(intent_context.get("action_target") or "").strip().lower()
    if requested_actor and requested_actor != active_id and action_target not in {"party", "group", "all"}:
        return _build_turn_lock_result(
            state=state,
            intent="END_TURN",
            actor_id=requested_actor,
            target_id="",
            entities=entities,
        )

    active_block = _get_active_turn_block(state=state, entities=entities)
    active_entity = entities.get(active_id, {})
    active_name = _display_entity_name(active_entity, active_id)
    if action_target in {"party", "group", "all"} and active_block:
        for actor_id in active_block:
            resources = turn_resources.get(actor_id, {})
            if isinstance(resources, dict):
                resources["action"] = 0
                resources["bonus_action"] = 0
                turn_resources[actor_id] = resources
        current_turn_index = (state.get("current_turn_index", 0) or 0) + len(active_block)
        return {
            "journal_events": [f"⏭️ [回合] {active_name} 宣布我方结束回合。"],
            "entities": entities,
            "combat_active": True,
            "initiative_order": list(state.get("initiative_order") or []),
            "current_turn_index": int(current_turn_index),
            "turn_resources": turn_resources,
            "skip_advance": True,
            "raw_roll_data": _build_action_result(
                intent="END_TURN",
                actor=active_id,
                target="party",
                is_success=True,
                result_type="PASS_GROUP",
            ),
        }

    if active_block and requested_actor in active_block:
        resources = turn_resources.get(requested_actor, {})
        if isinstance(resources, dict):
            resources["action"] = 0
            resources["bonus_action"] = 0
            turn_resources[requested_actor] = resources
    return {
        "journal_events": [f"⏭️ [回合] {active_name} 选择了待命。"],
        "entities": entities,
        "combat_active": True,
        "initiative_order": list(state.get("initiative_order") or []),
        "current_turn_index": _coerce_int(state.get("current_turn_index"), 0),
        "turn_resources": turn_resources,
        "raw_roll_data": _build_action_result(
            intent="END_TURN",
            actor=active_id,
            target="",
            is_success=True,
            result_type="PASS",
        ),
    }


def execute_attack_action(state: Any) -> Dict[str, Any]:
    """
    从 Graph state 中解析 ATTACK 行为，执行攻击结算并返回新的 entities / journal / latest_roll 数据。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    environment_objects = copy.deepcopy(state.get("environment_objects") or {})
    intent_context = state.get("intent_context") or {}
    attacker_id = _normalize_entity_id(intent_context.get("action_actor", "player")) or "player"
    target_query = str(intent_context.get("action_target", "") or "").strip()
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent="ATTACK",
        actor_id=attacker_id,
        target_id=target_query,
        entities=entities,
    )
    if turn_lock:
        return turn_lock
    target_id, target_obj, target_name = _resolve_target_reference(
        target_id=target_query,
        entities=entities,
        environment_objects=environment_objects,
    )
    if not target_id:
        return {
            "journal_events": ["❌ [战斗检定] 攻击失败：未指定目标。"],
            "entities": entities,
        }
    if target_id not in entities or not isinstance(entities.get(target_id), dict):
        return {
            "journal_events": [f"❌ [战斗检定] 攻击失败：找不到目标 {target_id}。"],
            "entities": entities,
        }

    defender = entities[target_id]
    if str(defender.get("status", "alive")).lower() == "dead":
        defender_name = _display_entity_name(defender, target_id)
        return {
            "journal_events": [f"⚔️ [战斗检定] {defender_name} 已经倒下，无需再次攻击。"],
            "entities": entities,
        }

    raw_attacker = _ensure_actor_entity(actor_id=attacker_id, entities=entities, state=state)
    if not isinstance(raw_attacker, dict):
        return {
            "journal_events": [f"❌ [战斗检定] 攻击失败：找不到攻击者 {attacker_id}。"],
            "entities": entities,
        }

    combat_events: List[str] = []
    combat_fields: Dict[str, Any] = {}
    target_is_hostile = _is_hostile_entity(defender)
    if target_is_hostile and not bool(state.get("combat_active", False)):
        initiative_order, initiative_rolls, initiative_log = _roll_initiative(entities)
        if initiative_order:
            current_turn_index = initiative_order.index(attacker_id) if attacker_id in initiative_order else 0
            combat_fields = {
                "combat_active": True,
                "initiative_order": initiative_order,
                "current_turn_index": current_turn_index,
                "initiative_rolls": initiative_rolls,
            }
            combat_events.append(initiative_log)

    turn_resources = _ensure_turn_resources_for_block(
        state={**state, **combat_fields},
        entities=entities,
        active_block=_get_active_turn_block(
            state={**state, **combat_fields},
            entities=entities,
        ),
        force_reset=False,
    )
    actor_resources = turn_resources.get(attacker_id, {})
    if int(actor_resources.get("action", 0) or 0) <= 0:
        return {
            "journal_events": [f"[系统驳回] 动作资源不足！{_display_entity_name(raw_attacker, attacker_id)} 本回合没有可用动作。"],
            "entities": entities,
            "combat_active": bool(state.get("combat_active", False)) or combat_fields.get("combat_active", False),
            "initiative_order": list(combat_fields.get("initiative_order") or state.get("initiative_order") or []),
            "current_turn_index": _coerce_int(
                combat_fields.get("current_turn_index", state.get("current_turn_index", 0)), 0
            ),
            "turn_resources": turn_resources,
            "raw_roll_data": _build_action_result(
                intent="ATTACK",
                actor=attacker_id,
                target=target_id,
                is_success=False,
                result_type="NO_ACTION",
            ),
            "turn_locked": True,
        }

    weapon_profile = _get_weapon_profile(raw_attacker)
    weapon_move_template = (
        "🚶 [战术走位] {actor_name} 调整步伐，逼近了 {target_name}。"
        if str(weapon_profile.get("id") or "") == "unarmed"
        else (
            f"🚶 [战术走位] {{actor_name}} 拔出 {weapon_profile.get('name', '武器')}，"
            "{target_name} 进入了射程。"
        )
    )
    approach_events = _auto_approach_actor_to_target(
        entities=entities,
        state=state,
        actor_id=attacker_id,
        target=target_obj or defender,
        target_name=target_name or _display_entity_name(defender, target_id),
        desired_range=int(weapon_profile.get("range", 1)),
        journal_template=weapon_move_template,
    )
    attacker = dict(raw_attacker)
    attacker["id"] = attacker_id
    defender["id"] = target_id
    actor_resources = dict(actor_resources) if isinstance(actor_resources, dict) else {}
    actor_resources["action"] = max(0, int(actor_resources.get("action", 0) or 0) - 1)
    turn_resources[attacker_id] = actor_resources

    result = {
        **execute_combat_attack(attacker=attacker, defender=defender),
        "entities": entities,
        "turn_resources": turn_resources,
        **combat_fields,
    }
    attack_events = result.get("journal_events", [])
    result["journal_events"] = attack_events[:1] + approach_events + attack_events[1:] + combat_events
    return result


def execute_loot_action(state: Any) -> Dict[str, Any]:
    """
    处理玩家/队友对死亡实体或已打开目标的搜刮。
    支持 entities 与 environment_objects 作为 loot source。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    environment_objects = copy.deepcopy(state.get("environment_objects") or {})
    player_inventory = copy.deepcopy(state.get("player_inventory") or {})
    intent_context = state.get("intent_context") or {}

    actor_id = _normalize_entity_id(intent_context.get("action_actor", "player")) or "player"
    target_query = str(intent_context.get("action_target", "") or "").strip()
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent="LOOT",
        actor_id=actor_id,
        target_id=target_query,
        entities=entities,
    )
    if turn_lock:
        return turn_lock
    target_id, target_obj, target_name = _resolve_target_reference(
        target_id=target_query,
        entities=entities,
        environment_objects=environment_objects,
    )
    if not target_id:
        return {
            "journal_events": ["❌ [搜刮] 搜刮失败：未指定目标。"],
            "entities": entities,
            "environment_objects": environment_objects,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="LOOT",
                actor=actor_id,
                target=target_id,
                is_success=False,
                result_type="INVALID_TARGET",
            ),
        }

    if not isinstance(target_obj, dict):
        return {
            "journal_events": [f"❌ [搜刮] 搜刮失败：找不到目标 {target_id}。"],
            "entities": entities,
            "environment_objects": environment_objects,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="LOOT",
                actor=actor_id,
                target=target_id,
                is_success=False,
                result_type="NOT_FOUND",
            ),
        }

    target_status = str(target_obj.get("status", "")).strip().lower()
    approach_events = _auto_approach_actor_to_target(
        entities=entities,
        state=state,
        actor_id=actor_id,
        target=target_obj,
        target_name=target_name,
    )
    if target_status not in LOOTABLE_STATUSES:
        return {
            "journal_events": [f"❌ [搜刮] {target_name} 还无法被搜刮。"] + approach_events,
            "entities": entities,
            "environment_objects": environment_objects,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="LOOT",
                actor=actor_id,
                target=target_id,
                is_success=False,
                result_type="NOT_LOOTABLE",
                extra={"status": target_status},
            ),
        }

    source_inventory = target_obj.setdefault("inventory", {})
    if not isinstance(source_inventory, dict):
        source_inventory = {}
        target_obj["inventory"] = source_inventory

    loot_items: Dict[str, int] = {}
    for item_id, count in list(source_inventory.items()):
        if not item_id:
            continue
        try:
            qty = int(count)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        loot_items[item_id] = qty

    destination_inventory, actor_name = _resolve_loot_destination(
        actor_id=actor_id,
        entities=entities,
        player_inventory=player_inventory,
    )

    for item_id, qty in loot_items.items():
        destination_inventory[item_id] = destination_inventory.get(item_id, 0) + qty
    target_obj["inventory"] = {}

    if loot_items:
        items_text = _format_loot_entries(loot_items)
        journal_events = [f"📦 [系统裁定] {actor_name}搜刮了 {target_name}，获得了 {items_text}。"] + approach_events
    else:
        journal_events = [f"📦 [系统裁定] {actor_name}搜刮了 {target_name}，但里面空空如也。"] + approach_events

    return {
        "journal_events": journal_events,
        "entities": entities,
        "environment_objects": environment_objects,
        "player_inventory": player_inventory,
        "raw_roll_data": _build_action_result(
            intent="LOOT",
            actor=actor_id,
            target=target_id,
            is_success=True,
            result_type="SUCCESS",
            extra={"loot_items": loot_items},
        ),
    }


def execute_use_item(state: Any) -> Dict[str, Any]:
    """
    执行物品使用：扣除背包物品，并把效果写回实体状态。
    当前最小闭环聚焦治疗类消耗品。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    player_inventory = copy.deepcopy(state.get("player_inventory") or {})
    intent = str(state.get("intent", "USE_ITEM") or "USE_ITEM").strip().upper()
    intent_context = state.get("intent_context") or {}

    actor_id = _normalize_entity_id(intent_context.get("action_actor", "player")) or "player"
    item_id = str(intent_context.get("item_id") or intent_context.get("target_item") or "").strip()
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent=intent,
        actor_id=actor_id,
        target_id=item_id,
        entities=entities,
    )
    if turn_lock:
        return turn_lock
    if not item_id:
        return {
            "journal_events": ["❌ [物品使用] 使用失败：未指定物品。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent=intent,
                actor=actor_id,
                target="",
                is_success=False,
                result_type="INVALID_ITEM",
            ),
        }

    item_data = get_registry().get_item_data(item_id)
    item_name = get_registry().get_name(item_id)
    if not _is_consumable_item(item_id, item_data):
        logger.warning("拦截了 LLM 试图消耗非消耗品的行为: %s", item_id)
        return {
            "journal_events": [f"❌ [物品使用] {item_name} 不是可消耗物品，不能被使用消耗。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent=intent,
                actor=actor_id,
                target=item_id,
                is_success=False,
                result_type="NOT_CONSUMABLE",
            ),
        }

    if player_inventory.get(item_id, 0) <= 0:
        return {
            "journal_events": [f"❌ [物品使用] 玩家背包里没有 {item_name}。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent=intent,
                actor=actor_id,
                target=item_id,
                is_success=False,
                result_type="ITEM_NOT_FOUND",
            ),
        }

    effect = apply_item_effect(item_id, item_data)

    player_inventory[item_id] = player_inventory.get(item_id, 0) - 1
    if player_inventory[item_id] <= 0:
        del player_inventory[item_id]

    actor = _ensure_actor_entity(actor_id=actor_id, entities=entities, state=state)
    actor_name = _display_entity_name(actor, actor_id)
    journal_events: List[str]

    if effect.get("success") and effect.get("type") == "heal":
        heal_value = int(effect.get("value", 0))
        current_hp = int(actor.get("hp", 0))
        max_hp = int(actor.get("max_hp", current_hp or 20))
        new_hp = min(max_hp, current_hp + heal_value)
        actual_heal = max(0, new_hp - current_hp)
        actor["hp"] = new_hp
        actor["max_hp"] = max_hp
        journal_events = [
            f"🧪 [物品使用] {actor_name}喝下了 {item_name}，恢复了 {actual_heal} 点 HP。"
        ]
    else:
        journal_events = [f"🧪 [物品使用] {actor_name}使用了 {item_name}。"]

    return {
        "journal_events": journal_events,
        "entities": entities,
        "player_inventory": player_inventory,
        "raw_roll_data": _build_action_result(
            intent=intent,
            actor=actor_id,
            target=item_id,
            is_success=bool(effect.get("success", True)),
            result_type=str(effect.get("type", "generic")).upper(),
            extra={"effect": effect},
        ),
    }


def execute_equip_action(state: Any) -> Dict[str, Any]:
    """
    装备物品：从执行者背包/玩家全局背包移入实体 equipment 槽位。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    player_inventory = copy.deepcopy(state.get("player_inventory") or {})
    intent_context = state.get("intent_context") or {}
    actor_id = _normalize_entity_id(intent_context.get("action_actor", "player")) or "player"
    item_id = _resolve_item_id_from_context(intent_context)
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent="EQUIP",
        actor_id=actor_id,
        target_id=item_id,
        entities=entities,
    )
    if turn_lock:
        return turn_lock

    actor = _ensure_actor_entity(actor_id=actor_id, entities=entities, state=state)
    actor_inventory, actor_name = _resolve_inventory_for_actor(
        actor_id=actor_id,
        entities=entities,
        player_inventory=player_inventory,
    )

    if not item_id:
        return {
            "journal_events": ["❌ [装备] 装备失败：未指定物品。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="EQUIP",
                actor=actor_id,
                target="",
                is_success=False,
                result_type="INVALID_ITEM",
            ),
        }

    item_data = get_registry().get(item_id)
    item_name = get_registry().get_name(item_id)
    slot = _equipment_slot_for_item(item_data)
    if not slot:
        return {
            "journal_events": [f"❌ [装备] {item_name} 不能被装备。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="EQUIP",
                actor=actor_id,
                target=item_id,
                is_success=False,
                result_type="NOT_EQUIPPABLE",
            ),
        }

    if int(actor_inventory.get(item_id, 0) or 0) <= 0:
        return {
            "journal_events": [f"❌ [装备] {actor_name} 的背包里没有 {item_name}。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="EQUIP",
                actor=actor_id,
                target=item_id,
                is_success=False,
                result_type="ITEM_NOT_FOUND",
            ),
        }

    equipment = _get_equipment(actor)
    previous_item = str(equipment.get(slot) or "").strip().lower()
    if previous_item:
        actor_inventory[previous_item] = int(actor_inventory.get(previous_item, 0) or 0) + 1

    actor_inventory[item_id] = int(actor_inventory.get(item_id, 0) or 0) - 1
    if actor_inventory[item_id] <= 0:
        del actor_inventory[item_id]
    equipment[slot] = item_id

    swap_text = f"，并卸下了 {get_registry().get_name(previous_item)}" if previous_item else ""
    return {
        "journal_events": [f"🛡️ [装备系统] {actor_name} 装备了 {item_name}{swap_text}。"],
        "entities": entities,
        "player_inventory": player_inventory,
        "raw_roll_data": _build_action_result(
            intent="EQUIP",
            actor=actor_id,
            target=item_id,
            is_success=True,
            result_type="SUCCESS",
            extra={"slot": slot},
        ),
    }


def execute_unequip_action(state: Any) -> Dict[str, Any]:
    """
    卸下装备：从 equipment 槽位移回执行者背包/玩家全局背包。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    player_inventory = copy.deepcopy(state.get("player_inventory") or {})
    intent_context = state.get("intent_context") or {}
    actor_id = _normalize_entity_id(intent_context.get("action_actor", "player")) or "player"
    requested_item_id = _resolve_item_id_from_context(intent_context)
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent="UNEQUIP",
        actor_id=actor_id,
        target_id=requested_item_id,
        entities=entities,
    )
    if turn_lock:
        return turn_lock

    actor = _ensure_actor_entity(actor_id=actor_id, entities=entities, state=state)
    actor_inventory, actor_name = _resolve_inventory_for_actor(
        actor_id=actor_id,
        entities=entities,
        player_inventory=player_inventory,
    )
    equipment = _get_equipment(actor)

    slot = ""
    item_id = ""
    if requested_item_id:
        for candidate_slot in ("main_hand", "ranged", "armor"):
            if str(equipment.get(candidate_slot) or "").strip().lower() == requested_item_id:
                slot = candidate_slot
                item_id = requested_item_id
                break
    else:
        for candidate_slot in ("main_hand", "ranged", "armor"):
            candidate_item = str(equipment.get(candidate_slot) or "").strip().lower()
            if candidate_item:
                slot = candidate_slot
                item_id = candidate_item
                break

    if not slot or not item_id:
        return {
            "journal_events": [f"❌ [装备] {actor_name} 没有可卸下的装备。"],
            "entities": entities,
            "player_inventory": player_inventory,
            "raw_roll_data": _build_action_result(
                intent="UNEQUIP",
                actor=actor_id,
                target=requested_item_id,
                is_success=False,
                result_type="NOT_EQUIPPED",
            ),
        }

    equipment[slot] = None
    actor_inventory[item_id] = int(actor_inventory.get(item_id, 0) or 0) + 1
    item_name = get_registry().get_name(item_id)
    return {
        "journal_events": [f"🧳 [装备系统] {actor_name} 卸下了 {item_name}。"],
        "entities": entities,
        "player_inventory": player_inventory,
        "raw_roll_data": _build_action_result(
            intent="UNEQUIP",
            actor=actor_id,
            target=item_id,
            is_success=True,
            result_type="SUCCESS",
            extra={"slot": slot},
        ),
    }


def execute_move_action(state: Any) -> Dict[str, Any]:
    """
    极简移动：玩家/角色朝目标方向最多移动 3 格，并停在目标邻近格。
    """
    entities = copy.deepcopy(state.get("entities") or {})
    environment_objects = copy.deepcopy(state.get("environment_objects") or {})
    intent = str(state.get("intent", "MOVE") or "MOVE").strip().upper()
    intent_context = state.get("intent_context") or {}

    actor_id = _normalize_entity_id(intent_context.get("action_actor", "player")) or "player"
    target_query = str(intent_context.get("action_target", "") or "").strip()
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent=intent,
        actor_id=actor_id,
        target_id=target_query,
        entities=entities,
    )
    if turn_lock:
        return turn_lock
    target_id, target, target_name = _resolve_target_reference(
        target_id=target_query,
        entities=entities,
        environment_objects=environment_objects,
    )
    if not target_id:
        return {
            "journal_events": ["❌ [空间移动] 移动失败：未指定目标。"],
            "entities": entities,
            "raw_roll_data": _build_action_result(
                intent=intent,
                actor=actor_id,
                target="",
                is_success=False,
                result_type="INVALID_TARGET",
            ),
        }

    actor = _ensure_actor_entity(actor_id=actor_id, entities=entities, state=state)
    if not isinstance(target, dict):
        return {
            "journal_events": [f"❌ [空间移动] 移动失败：找不到目标 {target_id}。"],
            "entities": entities,
            "raw_roll_data": _build_action_result(
                intent=intent,
                actor=actor_id,
                target=target_id,
                is_success=False,
                result_type="NOT_FOUND",
            ),
        }

    actor_x = _coerce_int(actor.get("x"), 4)
    actor_y = _coerce_int(actor.get("y"), 9)
    target_x = _coerce_int(target.get("x"), actor_x)
    target_y = _coerce_int(target.get("y"), actor_y)
    new_x, new_y = _move_toward_target(
        actor_x=actor_x,
        actor_y=actor_y,
        target_x=target_x,
        target_y=target_y,
    )
    actor["x"] = new_x
    actor["y"] = new_y
    actor["position"] = f"靠近 {target_name}"
    actor_name = _display_entity_name(actor, actor_id)

    return {
        "journal_events": [f"🚶 [空间移动] {actor_name}移动到了 {target_name} 附近。"],
        "entities": entities,
        "raw_roll_data": _build_action_result(
            intent=intent,
            actor=actor_id,
            target=target_id,
            is_success=True,
            result_type="SUCCESS",
            extra={"destination": {"x": new_x, "y": new_y}},
        ),
    }


# -----------------------------------------------------------------------------
# 技能检定类型与属性映射
# -----------------------------------------------------------------------------
# 支持的检定类型：PERSUASION(劝说), DECEPTION(欺瞒), STEALTH(隐匿), INSIGHT(洞悉),
# INTIMIDATION(威吓), ATTACK(攻击), STEAL(偷窃), ACTION(通用动作)。
# 每种检定映射到 D&D 5e 属性，用于后续扩展（如玩家属性修正）。
# -----------------------------------------------------------------------------

SKILL_CHECK_TYPES = (
    "PERSUASION",
    "DECEPTION",
    "STEALTH",
    "INTIMIDATION",
    "INSIGHT",
    "ATTACK",
    "LOOT",
    "STEAL",
    "ACTION",
    "PERCEPTION",
    "INVESTIGATION",
    "SLEIGHT_OF_HAND",
    "ATHLETICS",
    "USE_ITEM",
    "CONSUME",
    "EQUIP",
    "UNEQUIP",
    "MOVE",
    "APPROACH",
)


def get_ability_for_action(action_type: str) -> str:
    """
    将检定类型映射到 D&D 5e 属性。
    """
    key = str(action_type or "").strip().upper()
    action_to_ability = {
        "PERSUASION": "CHA",
        "DECEPTION": "CHA",
        "INTIMIDATION": "CHA",
        "STEALTH": "DEX",
        "INSIGHT": "WIS",
        "PERCEPTION": "WIS",
        "INVESTIGATION": "INT",
        "SLEIGHT_OF_HAND": "DEX",
        "ATHLETICS": "STR",
        "ATTACK": "STR",
        "LOOT": "DEX",
        "STEAL": "DEX",
        "USE_ITEM": "DEX",
        "CONSUME": "CON",
        "EQUIP": "DEX",
        "UNEQUIP": "DEX",
        "MOVE": "DEX",
        "APPROACH": "DEX",
        "ACTION": "CHA",
        "NONE": "CHA",
    }
    return action_to_ability.get(key, "CHA")


def get_player_modifier(player_data: dict, ability_name: str) -> Optional[int]:
    """
    Get player's ability modifier for a given ability.
    
    Args:
        player_data: Player profile dictionary containing ability_scores
        ability_name: Ability score abbreviation (STR, DEX, CON, INT, WIS, CHA)
    
    Returns:
        Optional[int]: Ability modifier, or None if ability not found
    """
    if player_data is None:
        return None
    
    ability_scores = player_data.get('ability_scores', {})
    if ability_name not in ability_scores:
        return None
    
    ability_score = ability_scores[ability_name]
    return calculate_ability_modifier(ability_score)


def determine_roll_type(action_type: str, relationship_score: int) -> str:
    """
    Determine roll type (normal/advantage/disadvantage) based on action and relationship.
    
    Args:
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
        relationship_score: Current relationship score with the NPC
    
    Returns:
        str: 'normal', 'advantage', or 'disadvantage'
    """
    # Advantage: PERSUASION or DECEPTION with high relationship (>= 30)
    if action_type in ["PERSUASION", "DECEPTION"] and relationship_score >= 30:
        return 'advantage'
    
    # Disadvantage: Low relationship (<= -20)
    if relationship_score <= -20:
        return 'disadvantage'
    
    return 'normal'


# -----------------------------------------------------------------------------
# 好感度与掷骰（仅修正骰子，不自动改 affection）
# -----------------------------------------------------------------------------
#
# PERSUASION/DECEPTION 时按 affection 每 20 点 ±1 骰子修正；advantage/disadvantage 亦由 affection 阈值决定。
# 检定成败不再扣减 affection——情感波动由 DM 分析与 NPC/LLM 输出自行表达。
# 动态 DC 来自 intent_context["difficulty_class"]，掷骰明细写入 journal_events。
# -----------------------------------------------------------------------------


def calculate_relationship_modifier(relationship: int, action_type: str) -> int:
    """
    根据好感度计算骰子修正值。仅对 PERSUASION、DECEPTION 生效。
    
    规则：好感度每 20 点，骰子点数 +1（向下取整）。负好感同理（每 -20 点 -1）。
    
    Args:
        relationship: 当前 relationship 分数 (-100..100)
        action_type: 检定类型，仅 PERSUASION/DECEPTION 会应用此修正
    
    Returns:
        int: 修正值，如 relationship=40 且 PERSUASION 则返回 2
    """
    if action_type not in ("PERSUASION", "DECEPTION"):
        return 0
    return relationship // 20


# -----------------------------------------------------------------------------
# 意图(How)与话题(What)分离 —— 彻底解决 LLM 分类冲突
# -----------------------------------------------------------------------------
#
# 【问题】若将 PROBE_SECRET 混入 action_type，会出现维度冲突：
# - 玩家「用劝说口吻刺探神器」→ PERSUASION 还是 PROBE_SECRET？LLM 难以二选一。
# - 玩家「边撒谎边问莎尔信仰」→ DECEPTION 与刺探话题同时成立，单维分类必然丢失信息。
#
# 【方案】action_type 保持纯粹的机制动作（How：如何互动），is_probing_secret 独立表示
# 话题标签（What：是否触碰核心隐私）。两者正交，LLM 可同时输出：
# - action_type=PERSUASION, is_probing_secret=true → 用劝说方式刺探
# - action_type=DECEPTION, is_probing_secret=true → 用欺瞒方式刺探
#
# 【V2】is_probing_secret 仅作 DM 标签写入 state；检定始终走正常骰子，叙事由 LLM + story_rules 决定。
# -----------------------------------------------------------------------------


def execute_skill_check(state: Any) -> Dict[str, Any]:
    """
    执行技能检定，返回客观掷骰结果。支持多角色的属性提取（intent_context.action_actor）。
    """
    intent_raw = state.get("intent", "ACTION")
    intent = str(intent_raw).strip().upper() if intent_raw else "ACTION"
    intent_context = state.get("intent_context") or {}
    environment_objects = copy.deepcopy(state.get("environment_objects") or {})
    entities = copy.deepcopy(state.get("entities") or {})
    target_query = str(intent_context.get("action_target", "") or "").strip()
    actual_target_id, target_obj, target_name = _resolve_target_reference(
        target_id=target_query,
        entities=entities,
        environment_objects=environment_objects,
    )

    action_actor = str(intent_context.get("action_actor", "player") or "player").strip().lower()
    turn_lock = _reject_if_not_active_turn(
        state=state,
        intent=intent,
        actor_id=action_actor,
        target_id=target_query,
        entities=entities,
    )
    if turn_lock:
        return turn_lock
    approach_events: List[str] = []
    if intent in {"SLEIGHT_OF_HAND", "ACTION", "ATHLETICS"} and isinstance(target_obj, dict):
        approach_events = _auto_approach_actor_to_target(
            entities=entities,
            state=state,
            actor_id=action_actor,
            target=target_obj,
            target_name=target_name,
        )

    _entities_map = state.get("entities") or {}
    if not isinstance(_entities_map, dict):
        _entities_map = {}

    _speaker_fb = next(iter(_entities_map), None) if _entities_map else None
    speaker = (state.get("current_speaker") or "").strip().lower() or (_speaker_fb or "unknown")
    affection = (_entities_map.get(speaker, {}) or {}).get("affection", 0)

    dc = intent_context.get("difficulty_class")
    if dc is None or (isinstance(dc, (int, float)) and dc <= 0):
        dc = 12
    dc = int(dc)

    ability_name = get_ability_for_action(intent)
    stat_mod = 0

    if action_actor != "player":
        try:
            from characters.loader import load_character

            char = load_character(action_actor)
            score = (char.data.get("ability_scores") or {}).get(ability_name, 10)
            stat_mod = calculate_ability_modifier(int(score))
        except Exception as e:
            print(f"⚠️ 无法读取 {action_actor} 的属性，默认修正为 +0 ({e})")
            stat_mod = 0
    else:
        # 玩家执行：未来可从 player.json / entities['player'] 读取；当前暂定 +2 作为熟练补偿占位
        stat_mod = 2

    rel_mod = calculate_relationship_modifier(affection, intent)
    modifier = stat_mod + rel_mod

    roll_type = determine_roll_type(intent, affection)
    result = roll_d20(dc=dc, modifier=modifier, roll_type=roll_type)

    rolls_str = str(result.get("rolls", [result.get("raw_roll", "?")]))
    total = result.get("total", 0)
    result_type = result.get("result_type")
    result_val = result_type.value if result_type is not None and hasattr(result_type, "value") else str(result_type)

    actor_display = action_actor.capitalize()
    journal_lines = [
        f"Skill Check | {actor_display} uses {intent} ({ability_name}) | DC {dc} | "
        f"Roll {rolls_str} + {modifier:+d} = {total} vs DC {dc} | "
        f"Result: {result_val}",
    ] + approach_events
    if DEBUG_ALWAYS_PASS_CHECKS:
        journal_lines.append("  [DEV MODE] 自动大成功")
    if stat_mod != 0:
        journal_lines.append(f"  [Attribute modifier ({ability_name}): {stat_mod:+d}]")
    if rel_mod != 0:
        journal_lines.append(f"  [Affection modifier: {rel_mod:+d} (affection={affection})]")

    payload: Dict[str, Any] = {
        "journal_events": journal_lines,
        "entities": entities,
        "raw_roll_data": {
            "intent": intent,
            "actor": action_actor,
            "target": actual_target_id,
            "dc": dc,
            "modifier": modifier,
            "result": result,
        },
    }

    if _is_unlockable_skill_success(
        intent=intent,
        target_obj=target_obj,
        result=result,
    ):
        target_id = actual_target_id
        target_obj = environment_objects[target_id]
        target_obj["status"] = "opened"
        target_name = str(target_obj.get("name") or target_id.replace("_", " ").title())
        journal_lines.append(f"🔓 [场景交互] 随着咔哒一声，{target_name} 被解锁了！")
        payload["environment_objects"] = environment_objects
    return payload


def calculate_passive_dc(action_type: str, npc_attributes: dict) -> Optional[int]:
    """
    Calculate passive DC based on NPC's stats (Phase 1: Rules Overrule).
    
    This function calculates the DC that the player must beat based on the NPC's
    actual ability scores, overriding the DM AI's DC estimate.
    
    Args:
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
        npc_attributes: NPC character attributes dictionary containing ability_scores
    
    Returns:
        Optional[int]: Calculated DC if applicable, None to use DM's default DC
    """
    # Get NPC's WIS modifier
    ability_scores = npc_attributes.get('ability_scores', {})
    wis_score = ability_scores.get('WIS', 10)
    wis_mod = calculate_ability_modifier(wis_score)
    
    # Calculate passive DC based on action type
    if action_type == "DECEPTION":
        # Passive Insight: 10 + WIS modifier (detecting lies)
        return 10 + wis_mod
    elif action_type == "PERSUASION":
        # Passive Insight/Skepticism: 10 + WIS modifier (judging honesty)
        return 10 + wis_mod
    elif action_type == "INTIMIDATION":
        # Passive Willpower: 10 + WIS modifier (resisting threats)
        return 10 + wis_mod
    else:
        # For other action types, use DM's default DC
        return None


def check_condition(condition_str: str, flags: dict) -> bool:
    """
    Safely evaluate a simple condition string against flags.
    
    Supports formats like: "flags.some_flag == True"
    Returns True for empty/None conditions.
    Handles "True" as a special case (always returns True).
    """
    if not condition_str or not condition_str.strip():
        return True
    
    # Handle "True" as a special case (always active conditions)
    if str(condition_str).strip() == "True":
        return True
    
    condition = condition_str.strip()
    operator = None
    if "==" in condition:
        lhs, rhs = condition.split("==", 1)
        operator = "=="
    elif "!=" in condition:
        lhs, rhs = condition.split("!=", 1)
        operator = "!="
    else:
        return False
    
    lhs = lhs.strip()
    rhs = rhs.strip()
    if not lhs.startswith("flags."):
        return False
    
    key = lhs[len("flags."):].strip()
    if not key:
        return False
    
    try:
        rhs_value = ast.literal_eval(rhs)
    except Exception:
        rhs_value = rhs.strip('"').strip("'")
    
    current_value = flags.get(key)
    if operator == "==":
        return current_value == rhs_value
    return current_value != rhs_value


def update_flags(effect_str: str, flags: dict) -> dict:
    """
    Apply a flag update string to the flags dict in place.
    
    Supports formats like: "flags.some_flag = True"
    """
    if not effect_str or not effect_str.strip():
        return flags
    
    effect = effect_str.strip()
    if "=" not in effect:
        return flags
    
    lhs, rhs = effect.split("=", 1)
    lhs = lhs.strip()
    rhs = rhs.strip()
    if not lhs.startswith("flags."):
        return flags
    
    key = lhs[len("flags."):].strip()
    if not key:
        return flags
    
    try:
        rhs_value = ast.literal_eval(rhs)
    except Exception:
        rhs_value = rhs.strip('"').strip("'")

    old_value = flags.get(key)
    flags[key] = rhs_value
    if old_value != rhs_value:
        print(f"[flags] {key}: {old_value} -> {rhs_value}")
    return flags


def get_situational_bonus(
    history: list,
    action_type: str,
    rules_config: list,
    flags: dict,
    current_message: str = ""
) -> tuple[int, str]:
    """
    Calculate situational bonus based on conversation context (Data-Driven Rules).
    
    This function checks the current user message (and optionally history) for keywords
    defined in rules_config that indicate shared context or past bonds, which grant bonuses
    to social skill checks.
    
    Args:
        history: List of conversation history dicts with 'role' and 'content' keys
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
        rules_config: List of situational bonus rules loaded from config
        flags: Persistent world-state flags dictionary
        current_message: The current user input message (optional, checked first)
    
    Returns:
        tuple[int, str]: (bonus, reason) - bonus amount and explanation
    """
    # Check current message first, then fall back to last message in history
    message_to_check = current_message
    
    if not message_to_check:
        # Get the last user message from history
        for msg in reversed(history):
            if msg.get('role') == 'user':
                message_to_check = msg.get('content', '')
                break
    
    if not message_to_check:
        return (0, "")
    
    # Convert to lowercase for matching
    message_lower = message_to_check.lower()
    
    total_bonus = 0
    reasons = []
    
    for rule in rules_config or []:
        condition = rule.get("condition")
        if not check_condition(condition, flags):
            continue
        
        applicable_actions = rule.get("applicable_actions", [])
        if "ALL" not in applicable_actions and action_type not in applicable_actions:
            continue
        
        trigger_type = rule.get("trigger_type")
        if trigger_type == "keyword_match":
            keywords = rule.get("keywords", [])
            if any(keyword in message_lower for keyword in keywords):
                total_bonus += rule.get("bonus_value", 0)
                description = rule.get("description")
                if description:
                    reasons.append(description)
    
    return (total_bonus, ", ".join(reasons))


# -----------------------------------------------------------------------------
# 对话触发器：对话即交互（Dialogue as Interaction）
# -----------------------------------------------------------------------------
#
# 【AI Narrative Engineer 与叙事一致性】
# 在叙事驱动游戏中，玩家的「对话」不应只是文本输出，而应能直接推动世界状态：
# 说「给你药水」即完成物品转移，说「我发现了秘密」即解锁剧情 flag。这样：
# 1) 叙事与机制一致：对话内容与后续剧情/背包/好感度严格同步，避免「说了不算」的割裂；
# 2) 下一轮生成有据可查：所有触发的剧情事件写入 journal_events，LLM 在 [RECENT MEMORIES]
#    中能看到「刚刚发生的重大转折」，从而生成连贯的后续反应；
# 3) 好感度与关键行为绑定：通过触发器配置中的 approval_change，将「给予剧情物品」等
#    行为直接映射为 relationship 变化，使数值与叙事选择一致。
#
# 调用方（如 generation_node）须将本函数对 flags / player_inv / npc_inv 的原地修改
# 写回 state，并合并返回的 journal_entries、relationship_delta，以保持全局状态一致。
# -----------------------------------------------------------------------------


def process_dialogue_triggers(
    user_input: str,
    triggers_config: list,
    flags: dict,
    ui=None,
    player_inv=None,
    npc_inv=None,
) -> Dict[str, Any]:
    """
    根据玩家输入匹配对话触发器，执行效果并返回需合并进 state 的结果。
    
    **触发后果（增强）**：
    - **Flags**：按 effects 中的 "flags.xxx = value" 原地修改传入的 flags，调用方须将
      同一 dict 写回 state["flags"]。
    - **背包**：通过 inventory.give:item_id 从 player_inv 移除、向 npc_inv 增加，实现
      「对话即物品转移」；调用方须将修改后的 player_inv.to_dict() / npc_inv.to_dict()
      写回 state["player_inventory"] 与 state["npc_inventory"]，确保 Generation 下一轮
      能基于最新背包生成（避免幻觉）。
    
    **好感度**：触发器配置可含 approval_change（整数）。所有在本轮匹配的触发器的
    approval_change 会累加，通过返回值 relationship_delta 交给调用方加算到
    state["relationship"]，实现「剧情物品转交」等行为直接影响关系分数。
    
    **日志**：每个被触发的触发器都会产生一条 journal 条目（优先用 system_message，
    否则用 trigger id / description），通过返回值 journal_entries 交给调用方合并进
    state["journal_events"]，保证下一轮对话中 [RECENT MEMORIES] 能引用这些重大转折。
    
    Args:
        user_input: 当前玩家输入文本。
        triggers_config: YAML 中的 dialogue_triggers 列表，每项可含：
            - trigger_type, keywords, effects
            - system_message: 写入 journal 的剧情描述（可选）
            - approval_change: 本触发对 relationship 的加减值（可选，默认 0）
        flags: 世界状态 flag 字典，**原地修改**。
        ui: 可选 UI，用于打印转移结果等。
        player_inv: 可选玩家背包对象（Inventory），**原地修改**（转移时 remove）。
        npc_inv: 可选 NPC 背包对象（Inventory），**原地修改**（转移时 add）。
    
    Returns:
        dict:
            - journal_entries: list[str]，本轮触发的剧情事件，应合并进 state["journal_events"]；
            - relationship_delta: int，本轮触发器带来的 relationship 变化总和，应加算到 state["relationship"]。
    """
    if not user_input or not triggers_config:
        return {"journal_entries": [], "relationship_delta": 0}

    message_lower = user_input.lower()
    journal_entries: List[str] = []
    relationship_delta = 0

    for trigger in triggers_config:
        trigger_type = trigger.get("trigger_type")
        if trigger_type != "keyword_match":
            continue

        keywords = trigger.get("keywords", [])
        if not any(keyword.lower() in message_lower for keyword in keywords):
            continue

        # ---------- 本触发器已匹配：执行效果（直接操作 flags 与背包）----------
        effects = trigger.get("effects", [])
        for effect_str in effects:
            # 更新世界状态 flag，调用方将同一 flags 写回 state["flags"]
            if "flags." in effect_str:
                update_flags(effect_str, flags)
            # 物品转移：直接修改 player_inv / npc_inv，调用方须将 to_dict() 写回 state
            elif effect_str.startswith("inventory.give:"):
                item_id = effect_str.split(":", 1)[1].strip()
                if player_inv and npc_inv:
                    from core.systems.inventory import get_registry
                    registry = get_registry()
                    item_name = registry.get_name(item_id)
                    if player_inv.remove(item_id):
                        npc_inv.add(item_id)
                        if ui:
                            ui.print_system_info(f"🎒 Item Transferred: {item_name} (Player -> NPC)")
                    else:
                        if ui:
                            ui.print_system_info(f"❌ Transaction Failed: You don't have {item_name}")

        # 好感度：配置中的 approval_change 累加，由调用方加算到 state["relationship"]
        delta = trigger.get("approval_change", 0)
        if isinstance(delta, int):
            relationship_delta += delta

        # 日志：每条触发都生成一条 journal，确保下一轮 [RECENT MEMORIES] 可见
        system_message = trigger.get("system_message")
        if system_message:
            journal_entries.append(system_message)
        else:
            trigger_id = trigger.get("id", "unknown")
            desc = trigger.get("description", "")
            journal_entries.append(f"[Story Trigger] {trigger_id}: {desc or 'triggered'}")

    return {"journal_entries": journal_entries, "relationship_delta": relationship_delta}


def update_npc_state(current_status: str, duration: int) -> tuple[str, int]:
    """
    Update NPC state by decrementing duration and resetting to NORMAL if needed.
    
    Args:
        current_status: Current NPC status ("NORMAL", "SILENT", "VULNERABLE")
        duration: Current duration (number of turns remaining)
    
    Returns:
        tuple[str, int]: (new_status, new_duration)
    """
    if duration <= 0:
        return ("NORMAL", 0)
    
    new_duration = duration - 1
    if new_duration <= 0:
        return ("NORMAL", 0)
    
    return (current_status, new_duration)


# =========================================
# Item Effect Logic (Data-Driven)
# =========================================

def parse_dice_string(dice_str: str) -> int:
    """
    Parse generic dice strings like '2d4+2', '1d8', or fixed numbers '5'.
    Returns the calculated result.
    """
    # 1. Fixed number
    if str(dice_str).isdigit():
        return int(dice_str)

    # 2. Dice formula: XdY(+/-)Z
    match = re.match(r'(\d+)d(\d+)(?:([+-])(\d+))?', dice_str)
    if not match:
        return 0

    num_dice = int(match.group(1))
    sides = int(match.group(2))
    operator = match.group(3)
    modifier = int(match.group(4)) if match.group(4) else 0

    total = sum(random.randint(1, sides) for _ in range(num_dice))

    if operator == '-':
        total -= modifier
    else:
        total += modifier

    return total


def apply_item_effect(item_id: str, item_data: dict) -> dict:
    """
    Executes the effect defined in the item's YAML configuration.

    Args:
        item_id: The ID of the item (e.g., 'healing_potion')
        item_data: The dictionary from items.yaml (contains 'effect', 'name', etc.)

    Returns:
        dict: Result of the application
        {
            "success": bool,
            "message": str, # Description for UI/Log
            "value": int,   # Numeric value (if applicable, like HP healed)
            "type": str     # Effect type (e.g., 'heal', 'buff')
        }
    """
    effect_str = item_data.get("effect")
    item_name = item_data.get("name", item_id)

    if not effect_str:
        return {
            "success": False,
            "message": f"{item_name} has no usage effect.",
            "value": 0,
            "type": "none"
        }

    # Effect Type 1: Healing (Format: "heal:2d4+2")
    if effect_str.startswith("heal:"):
        dice_formula = effect_str.split(":")[1]
        heal_amount = parse_dice_string(dice_formula)

        return {
            "success": True,
            "message": f"restores {heal_amount} HP.",
            "value": heal_amount,
            "type": "heal"
        }

    # Future Effect Types can be added here (e.g., "buff:strength", "damage:fire")

    # Default fallback
    return {
        "success": True,
        "message": "used successfully.",
        "value": 0,
        "type": "generic"
    }
