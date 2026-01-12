"""
D&D 5th Edition Dice Rolling Module
Handles D20 System dice mechanics for Baldur's Gate 3 RPG Agent
"""

import random
from enum import Enum
from typing import Dict, Any


class CheckResult(Enum):
    """Enumeration of possible check result types"""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CRITICAL_SUCCESS = "CRITICAL_SUCCESS"
    CRITICAL_FAILURE = "CRITICAL_FAILURE"


def roll_d20(dc: int, modifier: int = 0) -> Dict[str, Any]:
    """
    Simulates rolling a 20-sided die (D20) with D&D 5e mechanics.
    
    Rules:
    - Natural 20: Automatic success (CRITICAL SUCCESS), regardless of DC
    - Natural 1: Automatic failure (CRITICAL FAILURE)
    - Otherwise: Total = Raw Roll + Modifier. Success if Total >= DC
    
    Args:
        dc: Difficulty Class (target number to beat)
        modifier: Modifier to add to the roll (e.g., ability modifier, proficiency bonus)
    
    Returns:
        Dictionary containing:
            - total: Final calculated score (raw_roll + modifier)
            - raw_roll: The dice roll result (1-20)
            - is_success: Boolean indicating if the check succeeded
            - result_type: CheckResult enum value
            - log_str: Pre-formatted string for UI display
    """
    # Roll the die
    raw_roll = random.randint(1, 20)
    
    # Calculate total (for display purposes, even if crit rules override)
    total = raw_roll + modifier
    
    # Determine result based on D&D 5e rules
    if raw_roll == 20:
        # Natural 20: Critical Success (automatic success)
        result_type = CheckResult.CRITICAL_SUCCESS
        is_success = True
        log_str = f"🎲 ({raw_roll}) + {modifier:+d} = {total} vs DC {dc} [CRITICAL SUCCESS]"
    elif raw_roll == 1:
        # Natural 1: Critical Failure (automatic failure)
        result_type = CheckResult.CRITICAL_FAILURE
        is_success = False
        log_str = f"🎲 ({raw_roll}) + {modifier:+d} = {total} vs DC {dc} [CRITICAL FAILURE]"
    else:
        # Normal roll: compare total to DC
        is_success = total >= dc
        if is_success:
            result_type = CheckResult.SUCCESS
            log_str = f"🎲 ({raw_roll}) + {modifier:+d} = {total} vs DC {dc} [SUCCESS]"
        else:
            result_type = CheckResult.FAILURE
            log_str = f"🎲 ({raw_roll}) + {modifier:+d} = {total} vs DC {dc} [FAILURE]"
    
    return {
        "total": total,
        "raw_roll": raw_roll,
        "is_success": is_success,
        "result_type": result_type,
        "log_str": log_str
    }


def get_check_result_text(result_dict: Dict[str, Any]) -> str:
    """
    Generates a narrative description prompt based on the check result.
    This text can be injected into the LLM prompt to influence the narrative.
    
    Args:
        result_dict: Dictionary returned from roll_d20() function
    
    Returns:
        str: Narrative description of the check result
    """
    result_type = result_dict.get("result_type")
    
    if result_type == CheckResult.CRITICAL_SUCCESS:
        return "Check Result: CRITICAL SUCCESS! The action succeeds brilliantly."
    elif result_type == CheckResult.SUCCESS:
        return "Check Result: SUCCESS. The action succeeds."
    elif result_type == CheckResult.CRITICAL_FAILURE:
        return "Check Result: CRITICAL FAILURE! The action fails catastrophically."
    elif result_type == CheckResult.FAILURE:
        return "Check Result: FAILURE. The action fails."
    else:
        return "Check Result: Unknown result."
