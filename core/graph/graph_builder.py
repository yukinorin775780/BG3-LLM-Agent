"""
LangGraph 应用工厂。
构建并编译 RPG Agent 图，支持条件路由与 SQLite 持久化。
"""

import os
import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from core.graph.graph_state import GameState
from core.graph.graph_routers import route_after_input, route_after_dm
from characters.loader import load_character
from core.graph.graph_nodes import input_node, dm_node, mechanics_node, create_generation_node


# -----------------------------------------------------------------------------
# 持久化：SQLite Checkpointer
# -----------------------------------------------------------------------------

# 项目根目录（graph_builder 在 core/graph/ 下，上两级为根）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MEMORY_DB_PATH = os.path.join(_PROJECT_ROOT, "memory.db")

# 全局连接与 Checkpointer（单例，避免重复创建）
_sqlite_conn = None
_memory_saver = None


def get_memory_db_path() -> str:
    """返回 memory.db 的完整路径（项目根目录）。"""
    return _MEMORY_DB_PATH


def get_checkpointer():
    """
    获取或创建 SqliteSaver 实例。
    在项目根目录生成 memory.db，用于 LangGraph 的 Checkpoint 持久化。
    check_same_thread=False 允许多线程访问（如 main loop 与 UI）。
    若未安装 langgraph-checkpoint-sqlite，抛出 ImportError。
    """
    if SqliteSaver is None:
        raise ImportError(
            "langgraph-checkpoint-sqlite 未安装。运行: pip install langgraph-checkpoint-sqlite"
        )
    global _sqlite_conn, _memory_saver
    if _memory_saver is not None:
        return _memory_saver

    os.makedirs(_PROJECT_ROOT, exist_ok=True)
    _sqlite_conn = sqlite3.connect(_MEMORY_DB_PATH, check_same_thread=False)
    _memory_saver = SqliteSaver(_sqlite_conn)
    return _memory_saver


def init_checkpointer():
    """
    显式初始化 Checkpointer（可选）。
    若 main.py 启动时希望提前创建 DB，可调用此函数。
    否则 build_graph() 内部会按需创建。
    """
    return get_checkpointer()


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
# main.py 启动时建议：
#   1. 从 MemoryManager 或用户选择获取 thread_id（如 "shadowheart_default"）
#   2. graph.invoke(state_payload, config={"configurable": {"thread_id": thread_id}})
#   3. 首次 invoke 时传入完整 state_payload；后续 invoke 若需恢复，可传 None 并从
#      graph.get_state(config) 获取当前状态（用于 UI 展示）
#
# 注意：在 V2 架构中，SqliteSaver (Checkpointer) 作为唯一的 Single Source of Truth，
# 统一接管了 messages、relationship、inventory 等所有业务状态的跨会话持久化。
# 彻底废弃了原有的 JSON 文件读写方案。
# -----------------------------------------------------------------------------


# --- Graph Builder ---


def build_graph():
    """
    构建并编译 LangGraph 应用。
    使用 SqliteSaver 作为 Checkpointer，启用持久化与 thread_id 会话隔离。
    """
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("input_processing", input_node)
    builder.add_node("dm_analysis", dm_node)
    builder.add_node("mechanics_processing", mechanics_node)
    builder.add_node("generation", create_generation_node(load_character("shadowheart")))  # type: ignore[arg-type]

    # 2. Add Edges & Routing
    builder.add_edge(START, "input_processing")
    builder.add_conditional_edges(
        "input_processing",
        route_after_input,
        {"dm_analysis": "dm_analysis", "__end__": END},
    )
    builder.add_conditional_edges(
        "dm_analysis",
        route_after_dm,
        {"mechanics_processing": "mechanics_processing", "generation": "generation"},
    )
    builder.add_edge("mechanics_processing", "generation")
    builder.add_edge("generation", END)

    # 3. Compile（若已安装 langgraph-checkpoint-sqlite 则启用持久化）
    # Checkpointer 会将每步的 GameState 写入 memory.db，
    # 配合 config["configurable"]["thread_id"] 实现多存档隔离
    if SqliteSaver is not None:
        memory_saver = get_checkpointer()
        return builder.compile(checkpointer=memory_saver)
    return builder.compile()


__all__ = [
    "build_graph",
    "get_checkpointer",
    "get_memory_db_path",
    "init_checkpointer",
]
