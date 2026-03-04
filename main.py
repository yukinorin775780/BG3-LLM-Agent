"""
BG3 LLM Agent - V2 Main Entry Point

完全基于 LangGraph 状态机与 SqliteSaver 的极简主循环。
支持异步（asyncio）与流式输出（astream），实时追踪节点执行。
"""

import asyncio
import sys
from core import inventory
from core.graph.graph_builder import build_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from ui.renderer import GameRenderer

# 角色名（用于 UI 显示）
NPC_NAME = "影心"


def _get_last_ai_content(messages: list) -> str:
    """从 messages 中提取最后一条 AI 消息的内容。"""
    if not messages:
        return ""
    for m in reversed(messages):
        role = getattr(m, "type", None) or (m.get("type") if isinstance(m, dict) else None)
        if role in ("ai", "assistant"):
            return getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else "")
        if isinstance(m, dict) and m.get("role") == "assistant":
            return m.get("content", "")
    return ""


async def main_async():
    # -------------------------------------------------------------------------
    # 初始化
    # -------------------------------------------------------------------------
    ui = GameRenderer()
    ui.clear_screen()
    ui.show_title("BG3 LLM Agent - V2 (LangGraph)")
    inventory.init_registry("config/items.yaml")

    # -------------------------------------------------------------------------
    # 挂载引擎与配置存档（AsyncSqliteSaver 跨会话记忆）
    # -------------------------------------------------------------------------
    thread_id = "sean_save_01"
    config = {"configurable": {"thread_id": thread_id}}
    async with AsyncSqliteSaver.from_conn_string("memory.db") as saver:
        graph = build_graph(checkpointer=saver)

        # -------------------------------------------------------------------------
        # 获取初始状态（注意：此处必须改为 await graph.aget_state）
        # -------------------------------------------------------------------------
        try:
            snapshot = await graph.aget_state(config)
            prev_values = snapshot.values if hasattr(snapshot, "values") else {}
        except Exception:
            prev_values = {}
        prev_journal_len = len(prev_values.get("journal_events") or [])

        ui.print_system_info(f"✓ 存档: {thread_id}")
        ui.print()

        # -------------------------------------------------------------------------
        # 渲染历史聊天记录 (只读展示)
        # -------------------------------------------------------------------------
        history_messages = prev_values.get("messages", [])
        if history_messages:
            ui.print_rule("📜 历史对话记录", style="dim")
            for m in history_messages:
                # 兼容 LangChain 对象或字典格式
                role = getattr(m, "type", None) or (m.get("type") if isinstance(m, dict) else None)
                content = getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else "")

                if not content:
                    continue

                if role in ("human", "user"):
                    ui.print(f"[dim]You > {content}[/dim]")
                elif role in ("ai", "assistant"):
                    ui.print(f"[dim]影心 > {content}[/dim]")
            ui.print_rule("💬 新的对话", style="info")
        else:
            ui.print_rule("💬 新的对话", style="info")

        # -------------------------------------------------------------------------
        # 极简主循环（异步 + 流式）
        # -------------------------------------------------------------------------
        while True:
            try:
                # 获取当前最新状态并展示仪表盘
                current_snapshot = await graph.aget_state(config)
                current_state = current_snapshot.values if hasattr(current_snapshot, "values") else {}

                ui.print_rule("📊 战术状态面板", style="bold blue")
                ui.show_dashboard(current_state)
                ui.print()

                user_input = ui.input_prompt()

                # 空输入
                if not user_input or not user_input.strip():
                    continue

                # 退出指令
                if user_input.strip().lower() in ("/quit", "quit", "exit", "退出", "q"):
                    ui.print_system_info("再见。")
                    break

                # 核心调用：使用异步流实时监听节点执行
                state_input = {"user_input": user_input.strip()}
                ui.print_system_info("⚙️ 引擎开始运转...")
                async for update in graph.astream(state_input, config=config, stream_mode="updates"):
                    for node_name, node_state in update.items():
                        # 实时打印当前刚刚执行完毕的节点，实现真正的"流式跟踪"
                        ui.print_system_info(f"⚡ [流式追踪] 节点 `{node_name}` 执行完毕")

                # 循环结束后，获取最终状态用于渲染对话和最终日志
                snapshot = await graph.aget_state(config)
                result_state = snapshot.values if hasattr(snapshot, "values") else {}

                # 系统日志增量渲染
                curr_journal = result_state.get("journal_events") or []
                new_journal = curr_journal[prev_journal_len:]
                for line in new_journal:
                    ui.print_system_info(line)
                prev_journal_len = len(curr_journal)

                # AI 回复渲染（优先用 final_response，否则从 messages 提取）
                ai_text = result_state.get("final_response") or _get_last_ai_content(result_state.get("messages") or [])
                if ai_text:
                    # 如果是等待或系统指令，用普通颜色打印，不进 NPC 边框
                    if result_state.get("intent") in ("system_wait", "command_done", "command_failed", "dev_command"):
                        ui.print_system_info(ai_text)
                    else:
                        await ui.print_npc_response_stream(NPC_NAME, ai_text, char_delay=0.03)

                ui.print()

            except KeyboardInterrupt:
                ui.print()
                ui.print_system_info("已中断。再见。")
                break
            except Exception as e:
                ui.print_error(f"❌ 错误: {e}")
                import traceback
                traceback.print_exc()
                ui.print()


if __name__ == "__main__":
    asyncio.run(main_async())
