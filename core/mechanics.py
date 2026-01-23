"""
Game Mechanics Module (Model Layer)
Pure logic and calculation functions - no UI dependencies
"""

import ast
from typing import Optional


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


def get_ability_for_action(action_type: str) -> str:
    """
    Map action type to the corresponding ability score.
    
    Args:
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
    
    Returns:
        str: Ability score abbreviation (STR, DEX, CON, INT, WIS, CHA)
    """
    action_to_ability = {
        "DECEPTION": "CHA",
        "PERSUASION": "CHA",
        "INTIMIDATION": "CHA",
        "INSIGHT": "WIS",
        "ATTACK": "STR",  # Default to STR, could be weapon-dependent
        "NONE": "CHA"  # Default fallback
    }
    return action_to_ability.get(action_type, "CHA")


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


def process_dialogue_triggers(user_input: str, triggers_config: list, flags: dict, ui=None, player_inv=None, npc_inv=None) -> list[str]:
    """
    Process dialogue triggers based on user input and update flags/inventory accordingly.
    
    This function checks user input against configured triggers and applies
    their effects (flag updates and inventory transfers). Returns system messages to display.
    
    Args:
        user_input: The current user input message
        triggers_config: List of trigger configurations from YAML
        flags: Persistent world-state flags dictionary (modified in place)
        ui: Optional UI renderer for displaying messages
        player_inv: Optional player inventory object
        npc_inv: Optional NPC inventory object
    
    Returns:
        list[str]: List of system messages to display (empty if no triggers matched)
    """
    if not user_input or not triggers_config:
        return []
    
    message_lower = user_input.lower()
    system_messages = []
    
    for trigger in triggers_config:
        trigger_type = trigger.get("trigger_type")
        if trigger_type == "keyword_match":
            keywords = trigger.get("keywords", [])
            if any(keyword.lower() in message_lower for keyword in keywords):
                # Apply all effects
                effects = trigger.get("effects", [])
                for effect_str in effects:
                    # Handle flag updates
                    if "flags." in effect_str:
                        update_flags(effect_str, flags)
                    # Handle inventory transfers
                    elif effect_str.startswith("inventory.give:"):
                        item_name = effect_str.split(":", 1)[1].strip()
                        if player_inv and npc_inv:
                            if player_inv.remove(item_name):
                                npc_inv.add(item_name)
                                if ui:
                                    ui.print_system_info(f"🎒 Item Transferred: {item_name} (Player -> NPC)")
                            else:
                                if ui:
                                    ui.print_system_info(f"❌ Transaction Failed: You don't have {item_name}")
                
                # Collect system message if provided
                system_message = trigger.get("system_message")
                if system_message:
                    system_messages.append(system_message)
    
    return system_messages


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
