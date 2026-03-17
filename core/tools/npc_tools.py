"""
NPC 赛博义体 (Tools)：使用 LangChain @tool 定义 Schema
实际执行逻辑在 Graph Node 中结合 GameState 拦截并执行
"""

from langchain_core.tools import tool


@tool
def check_target_inventory(target_id: str, item_keyword: str) -> str:
    """
    核实目标角色的背包中是否包含某物。当玩家声称要给你某物时，必须先调用此工具验证目标（通常是 player）包里到底有没有该物品。

    target_id: 目标的ID，通常为 "player"（要核实的是玩家的背包）。
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

    action_type: 只能是 'give_item' (你给物品), 'take_item' (你拿走物品), 'heal' (治疗), 'damage' (伤害)。
    target_id: 动作的对象，例如 "player"。
    item_id: 物品ID（如果是物品转移）。
    amount: 数量或血量变动值。

    🚨 CRITICAL PERSPECTIVE RULES FOR 'give_item' and 'take_item':
    - YOU are the NPC executing this tool. The perspective is YOURS.
    - If the player is giving YOU an item (or you are accepting an item from the player): action_type MUST be 'take_item'. You are taking it from them.
    - If YOU are giving the player an item: action_type MUST be 'give_item'.
    DO NOT mix up who is giving and who is receiving!
    """
    pass  # 同样在 Graph Node 中拦截执行
