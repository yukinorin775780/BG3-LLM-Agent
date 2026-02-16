"""
LangGraph 路由逻辑：根据 State 中的 intent 决定下一跳节点。

路由函数返回 Literal 类型，与 add_conditional_edges 的 key 严格对应，
保证类型安全，避免拼写错误导致运行时找不到节点。
"""

from typing import Literal
from core.graph_state import GameState

# 路由目标：与 graph_builder 中节点名严格一致
INPUT_ROUTE = Literal["dm_analysis", "__end__"]
DM_ROUTE = Literal["mechanics_processing", "generation"]

# 需要掷骰子的动作意图（DM 分析结果）
# 这些意图必须经过 Mechanics 节点执行 D20 检定
ACTION_INTENTS: tuple[str, ...] = (
    "ATTACK",
    "STEAL",
    "PERSUASION",
    "INTIMIDATION",
    "INSIGHT",
    "ACTION",
)


def route_after_input(state: GameState) -> INPUT_ROUTE:
    """
    Input 节点之后的路由：指令已处理则分流，否则进 DM。

    判定逻辑：
    ---------
    1. command_done：/help、未知命令、物品不足等简单错误
       → 直接结束（__end__），无需 LLM 反应

    2. gift_given / item_used：/give、/use 成功
       → 进入 dm_analysis，再经 route_after_dm 到 generation
       → 需要 AI 对赠送/使用行为做出叙事反应

    3. pending：非斜杠输入，或空输入
       → 进入 dm_analysis，由 DM 分析意图（ATTACK/CHAT 等）
    """
    intent = state.get("intent", "pending")

    if intent == "command_done":
        return "__end__"

    if intent in ("gift_given", "item_used"):
        return "dm_analysis"

    return "dm_analysis"


def route_after_dm(state: GameState) -> DM_ROUTE:
    """
    DM 节点之后的路由：动作意图走 Mechanics，其余走 Generation。

    判定逻辑：
    ---------
    1. 动作意图（ATTACK, STEAL, PERSUASION, INTIMIDATION, INSIGHT, ACTION）
       → mechanics_processing
       → 需要掷骰子计算成功率，结果写入 journal_events
       → Mechanics 执行后再进入 Generation（骰子结果作为叙事上下文）

    2. 非动作意图（CHAT, NONE, gift_given, item_used 等）
       → generation
       → 纯对话或已由 Input 处理的物品交互，无需骰子
       → 直接由 LLM 生成回复
    """
    intent = state.get("intent", "chat")

    if intent in ACTION_INTENTS:
        return "mechanics_processing"

    return "generation"


__all__ = ["route_after_input", "route_after_dm", "ACTION_INTENTS"]
