"""游戏系统/规则层：骰子、背包、机制、任务。"""

from core.systems.dice import CheckResult, roll_d20, get_check_result_text
from core.systems.inventory import (
    ItemRegistry,
    Inventory,
    get_registry,
    format_inventory_dict_to_display_list,
    init_registry,
)
from core.systems.mechanics import (
    execute_skill_check,
    process_dialogue_triggers,
    apply_item_effect,
    check_condition,
)
from core.systems.quest import QuestManager

__all__ = [
    "CheckResult",
    "roll_d20",
    "get_check_result_text",
    "ItemRegistry",
    "Inventory",
    "get_registry",
    "format_inventory_dict_to_display_list",
    "init_registry",
    "execute_skill_check",
    "process_dialogue_triggers",
    "apply_item_effect",
    "check_condition",
    "QuestManager",
]
