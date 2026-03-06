"""
LangGraph 应用工厂。
构建并编译 RPG Agent 图，支持条件路由与 Checkpointer 持久化。
Checkpointer 由调用方（如 main.py）创建并传入，支持 AsyncSqliteSaver 等异步实现。
"""

from langgraph.graph import StateGraph, START, END
from core.graph.graph_state import GameState
from core.graph.graph_routers import route_after_dm


def route_after_input(state: dict) -> str:
    """拦截开发者指令，防止世界时间流逝"""
    intent = state.get("intent", "")
    if intent in ("dev_command", "command_failed"):
        return "__end__"
    return "world_tick"


def route_after_tick(state: dict) -> str:
    """只短路 system_wait；聊天和 action_use 进入 DM 判定和大模型反应"""
    if state.get("intent") == "system_wait":
        return "__end__"
    return "dm_analysis"


def route_after_generation(state: dict) -> str:
    """多人发言队列：若 speaker_queue 非空，继续让下一位发言"""
    if state.get("speaker_queue"):
        return "advance_speaker"
    return "__end__"
from core.graph.graph_nodes import (
    input_node,
    world_tick_node,
    dm_node,
    mechanics_node,
    create_generation_node,
    advance_speaker_node,
)


# -----------------------------------------------------------------------------
# Checkpointer 与 GameState 协同说明
# -----------------------------------------------------------------------------
#
# LangGraph 的 Checkpointer 会在每个「超级步」（super-step）结束时，
# 将当前 State 序列化并写入 SQLite。我们的 GameState 包含：
#   - messages: 对话历史（add_messages 累加）
#   - relationship, npc_state, player_inventory, npc_inventory, flags
#   - journal_events（merge_events 累加）
#
# 通过 thread_id 区分不同存档：
#   - config = {"configurable": {"thread_id": "shadowheart_save_1"}}
#   - 同一 thread_id 的 invoke 会从上次 checkpoint 恢复 messages 等状态
#   - 不同 thread_id 则开启全新会话
#
# 注意：在 V2 架构中，SqliteSaver (Checkpointer) 作为唯一的 Single Source of Truth，
# 统一接管了 messages、relationship、inventory 等所有业务状态的跨会话持久化。
# 彻底废弃了原有的 JSON 文件读写方案。
# -----------------------------------------------------------------------------


# --- Graph Builder ---


def build_graph(checkpointer=None):
    """
    构建并编译 LangGraph 应用。
    使用传入的 Checkpointer 启用持久化与 thread_id 会话隔离。
    若未传入 checkpointer，则编译为无持久化图。
    """
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("input_processing", input_node)
    builder.add_node("world_tick", world_tick_node)  # type: ignore[arg-type]
    builder.add_node("dm_analysis", dm_node)
    builder.add_node("mechanics_processing", mechanics_node)
    builder.add_node("generation", create_generation_node())  # type: ignore[arg-type]
    builder.add_node("advance_speaker", advance_speaker_node)

    # 2. Add Edges & Routing
    builder.add_edge(START, "input_processing")
    builder.add_conditional_edges(
        "input_processing",
        route_after_input,
        {"__end__": END, "world_tick": "world_tick"},
    )
    builder.add_conditional_edges(
        "world_tick",
        route_after_tick,
        {"dm_analysis": "dm_analysis", "__end__": END},
    )
    builder.add_conditional_edges(
        "dm_analysis",
        route_after_dm,
        {"mechanics_processing": "mechanics_processing", "generation": "generation"},
    )
    builder.add_edge("mechanics_processing", "generation")
    builder.add_conditional_edges(
        "generation",
        route_after_generation,
        {"advance_speaker": "advance_speaker", "__end__": END},
    )
    builder.add_edge("advance_speaker", "generation")

    # 3. Compile
    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


__all__ = ["build_graph"]
