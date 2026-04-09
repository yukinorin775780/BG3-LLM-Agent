"""
LangGraph 路由逻辑：根据 State 中的 intent 决定下一跳节点。

路由函数返回 Literal 类型，与 add_conditional_edges 的 key 严格对应，
保证类型安全，避免拼写错误导致运行时找不到节点。
"""

import random
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
    "LOOT",
    "USE_ITEM",
    "CONSUME",
    "MOVE",
    "APPROACH",
    "STEAL",
    "PERSUASION",
    "DECEPTION",
    "STEALTH",
    "INTIMIDATION",
    "INSIGHT",
    "PERCEPTION",
    "INVESTIGATION",
    "SLEIGHT_OF_HAND",
    "ATHLETICS",
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
    Input 节点之后的路由（与 graph_builder 中 input→world_tick 的实装对照用）。

    纯系统指令（含 /give、/use 成功）使用 intent=command_done，直接 __end__，不进入 DM。
    其余意图进入 dm_analysis（实际主程序在 graph_builder 中先经 world_tick 再到 dm_analysis）。
    """
    intent = state.get("intent", "pending")
    if intent == "command_done":
        return _validate_input_route("__end__")
    return _validate_input_route("dm_analysis")


def route_after_dm(state: GameState) -> DM_ROUTE:
    """
    DM 节点之后的路由：动作意图或话题标签走 Mechanics，其余走 Generation。

    判定逻辑：
    ---------
    1. is_probing_secret 为 True（刺探秘密话题）
       → mechanics_processing（照常掷骰；叙事由 LLM + story_rules 处理）

    2. 动作意图（含 PERSUASION, DECEPTION, STEALTH 等 ACTION_INTENTS）
       → mechanics_processing

    3. 非动作意图（如 CHAT）且非刺探
       → generation
    """
    intent_raw = state.get("intent", "chat")
    intent = str(intent_raw).strip().upper() if intent_raw else "CHAT"
    is_probing_secret = state.get("is_probing_secret", False)

    if is_probing_secret:
        return _validate_dm_route("mechanics_processing")
    if intent in ACTION_INTENTS:
        return _validate_dm_route("mechanics_processing")
    return _validate_dm_route("generation")


# -----------------------------------------------------------------------------
# V3: DM 旁白系统路由 (route_after_mechanics)
# -----------------------------------------------------------------------------

# 社交类意图 (交给 NPC 节点)
SOCIAL_INTENTS = frozenset(
    {"chat", "persuasion", "intimidation", "deception", "performance", "insight"}
)

# 环境与动作类技能 (交给 DM 旁白节点)
ENVIRONMENTAL_SKILLS = frozenset({
    "perception", "investigation", "stealth", "athletics", "acrobatics",
    "sleight_of_hand", "survival", "nature", "medicine", "history", "religion", "arcana",
})

MECHANICS_ROUTE = Literal["generation", "narration"]


def route_after_mechanics(state: GameState) -> MECHANICS_ROUTE:
    """
    在 Mechanics Node 掷骰子结算后，决定接下来的叙事权归谁。
    - 社交博弈 → generation (NPC 说话)
    - 环境探索 / 物理动作 → narration (DM 旁白)
    """
    intent = str(state.get("intent", "chat")).lower()
    intent_context = state.get("intent_context") or {}
    skill = str(intent_context.get("skill", "")).lower()

    # 对人社交博弈 → NPC 说话
    if intent in SOCIAL_INTENTS:
        return "generation"

    # 环境探索或物理动作 → DM 旁白
    if intent in ENVIRONMENTAL_SKILLS:
        return "narration"
    if skill and skill in ENVIRONMENTAL_SKILLS:
        return "narration"

    # 战斗等 → DM 旁白
    if intent in ("attack", "cast_spell", "loot", "use_item", "consume", "move", "approach"):
        return "narration"

    # 默认兜底交还给 NPC
    return "generation"


# -----------------------------------------------------------------------------
# V3: 旁白后随机吐槽路由 (route_after_narration)
# -----------------------------------------------------------------------------

NARRATION_ROUTE = Literal["generation", "__end__"]


def route_after_narration(state: GameState) -> NARRATION_ROUTE:
    """
    DM 旁白结束后的路由：决定是否触发同伴吐槽 (Banter)。
    普通操作 30% 概率触发；大成功(20)或大失败(1) 100% 触发。
    """
    # 若 DM 已排出后续发言 NPC，必须进入 generation，不能被随机吐槽判定短路到 __end__
    if state.get("speaker_queue"):
        return "generation"

    latest_roll = state.get("latest_roll", {}) or {}
    result = latest_roll.get("result", {}) or {}
    raw_roll = result.get("raw_roll") if isinstance(result, dict) else None
    total = result.get("total", 10) if isinstance(result, dict) else latest_roll.get("total", 10)
    roll_value = raw_roll if raw_roll is not None else total

    try:
        roll_value = int(roll_value)
    except (TypeError, ValueError):
        roll_value = 10

    # 大成功(20)或大失败(1)，100% 吐槽
    if roll_value >= 18 or roll_value <= 5:
        return "generation"

    # 普通情况，30% 概率触发吐槽
    if random.random() < 0.3:
        return "generation"

    return "__end__"


__all__ = [
    "route_after_input",
    "route_after_dm",
    "route_after_mechanics",
    "route_after_narration",
    "ACTION_INTENTS",
    "MECHANICS_REQUIRED_INTENTS",
    "SOCIAL_INTENTS",
    "ENVIRONMENTAL_SKILLS",
]
