"""
NPC 赛博义体：Function Calling (Tools) 定义
供大模型通过原生工具调用实现物理自治与防诈骗能力
"""

from core.tools.npc_tools import check_target_inventory, execute_physical_action
from core.tools.act4_mvp import (
    Act4ToolPlanner,
    ToolExecutor,
    ToolRegistry,
    execute_act4_diary_truth_tool_sequence,
    get_default_tool_registry,
)

__all__ = [
    "Act4ToolPlanner",
    "ToolExecutor",
    "ToolRegistry",
    "check_target_inventory",
    "execute_act4_diary_truth_tool_sequence",
    "execute_physical_action",
    "get_default_tool_registry",
]
