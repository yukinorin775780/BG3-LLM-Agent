"""
NPC 赛博义体 (Tools)：使用 LangChain @tool 定义 Schema
实际执行逻辑在 Graph Node 中结合 GameState 拦截并执行
"""

from langchain_core.tools import tool


@tool
def check_target_inventory(target_id: str, item_keyword: str) -> str:
    """
    当玩家声称要给你某物，或你需要确认目标是否有某物时调用此工具。
    target_id: 目标的ID，通常为 "player"。
    item_keyword: 物品的名称或关键词，例如 "药水"、"金币"。
    """
    pass  # 实际逻辑将在 Graph Node 中结合 GameState 拦截并执行


@tool
def execute_physical_action(
    action_type: str,
    target_id: str,
    item_id: str = "",
    amount: int = 1,
) -> str:
    """
    在核实无误后，执行实质性的物理动作。
    action_type: 只能是 'give_item' (给你物品), 'take_item' (拿走物品), 'heal' (治疗), 'damage' (伤害)。
    target_id: 动作的对象，例如 "player"。
    item_id: 物品ID（如果是物品转移）。
    amount: 数量或血量变动值。
    """
    pass  # 同样在 Graph Node 中拦截执行
