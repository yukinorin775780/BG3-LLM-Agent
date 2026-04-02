"""
Game Mechanics Module (Model Layer)
Pure logic and calculation functions - no UI dependencies
"""

import ast
import random
import re
from typing import Any, Dict, List, Optional

from core.engine.physics import DEBUG_ALWAYS_PASS_CHECKS
from core.systems.dice import roll_d20


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
    "STEAL",
    "ACTION",
    "PERCEPTION",
    "INVESTIGATION",
    "SLEIGHT_OF_HAND",
    "ATHLETICS",
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
        "STEAL": "DEX",
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

    action_actor = str(intent_context.get("action_actor", "player") or "player").strip().lower()

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
    ]
    if DEBUG_ALWAYS_PASS_CHECKS:
        journal_lines.append("  [DEV MODE] 自动大成功")
    if stat_mod != 0:
        journal_lines.append(f"  [Attribute modifier ({ability_name}): {stat_mod:+d}]")
    if rel_mod != 0:
        journal_lines.append(f"  [Affection modifier: {rel_mod:+d} (affection={affection})]")

    return {
        "journal_events": journal_lines,
        "raw_roll_data": {
            "intent": intent,
            "actor": action_actor,
            "dc": dc,
            "modifier": modifier,
            "result": result,
        },
    }


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
