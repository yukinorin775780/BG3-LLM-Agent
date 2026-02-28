"""
LangGraph 路由逻辑：根据 State 中的 intent 决定下一跳节点。

路由函数返回 Literal 类型，与 add_conditional_edges 的 key 严格对应，
保证类型安全，避免拼写错误导致运行时找不到节点。
"""

from typing import Literal, cast
from core.graph.graph_state import GameState

# 路由目标：与 graph_builder 中节点名严格一致，返回字符串必须在此枚举内
INPUT_ROUTE = Literal["dm_analysis", "__end__"]
DM_ROUTE = Literal["mechanics_processing", "generation"]

_VALID_INPUT_ROUTES: frozenset[str] = frozenset({"dm_analysis", "__end__"})
_VALID_DM_ROUTES: frozenset[str] = frozenset({"mechanics_processing", "generation"})

# PERSUASION/DECEPTION/STEALTH 必须在到达 generation 前经过 mechanics_processing 执行检定
MECHANICS_REQUIRED_INTENTS: tuple[str, ...] = ("PERSUASION", "DECEPTION", "STEALTH")

# 需要掷骰子的动作意图（DM 分析结果），必须包含 MECHANICS_REQUIRED_INTENTS
ACTION_INTENTS: tuple[str, ...] = (
    "ATTACK",
    "STEAL",
    "PERSUASION",
    "DECEPTION",
    "STEALTH",
    "INTIMIDATION",
    "INSIGHT",
    "ACTION",
)
assert set(MECHANICS_REQUIRED_INTENTS).issubset(set(ACTION_INTENTS)), (
    "MECHANICS_REQUIRED_INTENTS must be subset of ACTION_INTENTS"
)


def _validate_input_route(route: str) -> INPUT_ROUTE:
    """类型检查：确保返回的路径在 INPUT_ROUTE 定义范围内。"""
    if route not in _VALID_INPUT_ROUTES:
        raise ValueError(f"Invalid INPUT_ROUTE: {route!r}. Must be one of {_VALID_INPUT_ROUTES}")
    return cast(INPUT_ROUTE, route)


def _validate_dm_route(route: str) -> DM_ROUTE:
    """类型检查：确保返回的路径在 DM_ROUTE 定义范围内。"""
    if route not in _VALID_DM_ROUTES:
        raise ValueError(f"Invalid DM_ROUTE: {route!r}. Must be one of {_VALID_DM_ROUTES}")
    return cast(DM_ROUTE, route)


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
        return _validate_input_route("__end__")
    if intent in ("gift_given", "item_used"):
        return _validate_input_route("dm_analysis")
    return _validate_input_route("dm_analysis")


def route_after_dm(state: GameState) -> DM_ROUTE:
    """
    DM 节点之后的路由：动作意图或话题标签走 Mechanics，其余走 Generation。

    判定逻辑：
    ---------
    1. is_probing_secret 为 True（刺探秘密话题）
       → mechanics_processing
       → 必须经隐性好感度锁判定，再进入 Generation

    2. 动作意图（含 PERSUASION, DECEPTION, STEALTH 等 ACTION_INTENTS）
       → mechanics_processing

    3. 非动作意图（CHAT, gift_given, item_used 等）且非刺探
       → generation
    """
    intent = state.get("intent", "chat")
    is_probing_secret = state.get("is_probing_secret", False)

    if is_probing_secret:
        return _validate_dm_route("mechanics_processing")
    if intent in ACTION_INTENTS:
        return _validate_dm_route("mechanics_processing")
    return _validate_dm_route("generation")


__all__ = ["route_after_input", "route_after_dm", "ACTION_INTENTS", "MECHANICS_REQUIRED_INTENTS"]
