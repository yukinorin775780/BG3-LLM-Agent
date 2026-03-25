"""
BG3 LLM Agent - V2 Main Entry Point

完全基于 LangGraph 状态机与 SqliteSaver 的极简主循环。
支持异步（asyncio）与流式输出（astream），实时追踪节点执行。
"""

import asyncio
import copy
import json
import os
import sys

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import START

from config import settings
from core import inventory
from core.graph.graph_builder import build_graph
from core.graph.nodes.utils import default_entities
from core.systems.memory_rag import episodic_memory
from ui.renderer import GameRenderer


def _speaker_display_name(speaker_id: str) -> str:
    """从 current_speaker 映射为中文显示名。"""
    _names = {"shadowheart": "影心", "astarion": "阿斯代伦", "dm": "Dungeon Master"}
    return _names.get((speaker_id or "").strip().lower(), (speaker_id or "未知").capitalize())


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
    # 挂载全局物品数据库
    if not inventory.init_registry("config/items.yaml"):
        print("⚠️ 警告: 物品数据库加载失败，将使用默认回退(Fallback)数据。")
    else:
        print("✅ 物品数据库加载成功！")

    ui = GameRenderer()
    ui.clear_screen()
    ui.show_title("BG3 LLM Agent - V2 (LangGraph)")

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
            snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
            prev_values = snapshot.values if hasattr(snapshot, "values") else {}
        except Exception:
            prev_values = {}
        if not isinstance(prev_values, dict):
            prev_values = {}

        # --- 【新增】检测空存档并执行"创世"初始化 ---
        if not (prev_values or {}).get("entities"):
            init_player_inv: dict = {"healing_potion": 2}
            if os.path.exists("data/player.json"):
                try:
                    with open("data/player.json", "r", encoding="utf-8") as f:
                        p_data = json.load(f)
                        inv = p_data.get("inventory", init_player_inv)
                        init_player_inv = dict(inv) if isinstance(inv, dict) else init_player_inv
                except Exception:
                    pass

            initial_state = {
                "entities": copy.deepcopy(default_entities),
                "player_inventory": init_player_inv,
                "turn_count": 0,
                "time_of_day": "晨曦 (Morning)",
                "flags": {},
                "messages": [],
                "journal_events": [],
            }
            await graph.aupdate_state(config, initial_state, as_node=START)  # type: ignore[arg-type]

            snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
            prev_values = snapshot.values if hasattr(snapshot, "values") else {}
            if not isinstance(prev_values, dict):
                prev_values = {}
        # ---------------------------------------------

        prev_journal_len = len((prev_values or {}).get("journal_events") or [])

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
                name = getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else None)

                if not content:
                    continue

                if role in ("human", "user"):
                    ui.print(f"[dim]You > {content}[/dim]")
                elif role in ("ai", "assistant"):
                    label = _speaker_display_name(name or "")
                    ui.print(f"[dim]{label} > {content}[/dim]")
            ui.print_rule("💬 新的对话", style="info")
        else:
            ui.print_rule("💬 新的对话", style="info")

        # -------------------------------------------------------------------------
        # 极简主循环（异步 + 流式）
        # -------------------------------------------------------------------------
        while True:
            try:
                # 获取当前最新状态并展示仪表盘
                current_snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
                current_state = current_snapshot.values if hasattr(current_snapshot, "values") else {}

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

                # --- 【新增】硬重置指令 ---
                if user_input.strip().lower() == "/reset":
                    ui.print_system_info("💥 正在执行世界重置 (灭世协议)...")

                    episodic_memory.clear_all_memories()

                    if os.path.exists("memory.db"):
                        try:
                            os.remove("memory.db")
                            ui.print_system_info("🗑️ 短期状态存档 (memory.db) 已销毁。")
                        except Exception as e:
                            ui.print_error(f"删除存档失败: {e}")

                    ui.print_rule("世界已重置，请重新运行 `python main.py` 开启新时间线", style="warning")
                    break
                # -------------------------

                # 核心调用：使用异步流实时监听节点执行
                state_input = {"user_input": user_input.strip()}
                ui.print_system_info("⚙️ 引擎开始运转...")
                rendered_in_stream = False  # 标记是否已在流中渲染对话，避免结尾重复
                async for update in graph.astream(state_input, config=config, stream_mode="updates"):  # type: ignore[arg-type]
                    for node_name, node_state in update.items():
                        # 实时打印当前刚刚执行完毕的节点，实现真正的"流式跟踪"
                        ui.print_system_info(f"⚡ [流式追踪] 节点 `{node_name}` 执行完毕")

                        # 0. 临时 Debug：透视 DM 排出的发言队列
                        if node_name == "dm_analysis":
                            if node_state and isinstance(node_state, dict):
                                queue = node_state.get("speaker_queue", [])
                                if queue:
                                    ui.print_system_info(f"👀 [Debug] DM 排出的发言队列: {queue}")

                        # 1. DM 旁白节点完成 → 立即渲染 DM 面板
                        elif node_name == "narration":
                            dm_text = node_state.get("final_response", "")
                            if dm_text:
                                ui.print_dm_narration(dm_text)
                                rendered_in_stream = True

                        # 2. NPC 生成节点完成 → 立即渲染 NPC 面板
                        elif node_name == "generation":
                            npc_text = node_state.get("final_response", "")
                            # 从节点返回的 speaker_responses 队列末尾提取真正的说话人
                            speaker_responses = node_state.get("speaker_responses", [])
                            if speaker_responses and len(speaker_responses) > 0:
                                speaker = speaker_responses[-1][0]
                            else:
                                speaker = node_state.get("current_speaker", "shadowheart") or "shadowheart"
                            if npc_text:
                                display_name = _speaker_display_name(speaker)
                                await ui.print_npc_response_stream(display_name, npc_text, char_delay=0.03)
                                rendered_in_stream = True

                        # 3. 骰子动画
                        if "mechanics" in node_name and "latest_roll" in node_state:
                            roll_info = node_state["latest_roll"]
                            await ui.show_dice_roll_animation(
                                intent=roll_info.get("intent", "ACTION"),
                                dc=roll_info.get("dc", 10),
                                modifier=roll_info.get("modifier", 0),
                                roll_data=roll_info.get("result", {})
                            )

                # 循环结束后，获取最终状态用于渲染对话和最终日志
                snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
                result_state = snapshot.values if hasattr(snapshot, "values") else {}

                # 系统日志增量渲染
                curr_journal = result_state.get("journal_events") or []
                new_journal = curr_journal[prev_journal_len:]
                for line in new_journal:
                    ui.print_system_info(line)
                prev_journal_len = len(curr_journal)

                # AI 回复渲染（若流中已渲染 narration/generation，则跳过避免重复）
                if not rendered_in_stream:
                    if result_state.get("intent") in ("system_wait", "command_done", "command_failed", "dev_command"):
                        ai_text = result_state.get("final_response") or _get_last_ai_content(result_state.get("messages") or [])
                        if ai_text:
                            ui.print_system_info(ai_text)
                    else:
                        responses = result_state.get("speaker_responses") or []
                        if responses:
                            for speaker_id, text in responses:
                                display_name = _speaker_display_name(speaker_id)
                                await ui.print_npc_response_stream(display_name, text, char_delay=0.03)
                        else:
                            ai_text = result_state.get("final_response") or _get_last_ai_content(result_state.get("messages") or [])
                            if ai_text:
                                speaker = result_state.get("current_speaker", "shadowheart") or "shadowheart"
                                display_name = _speaker_display_name(speaker)
                                await ui.print_npc_response_stream(display_name, ai_text, char_delay=0.03)

                # --- 【新增】RAG 记忆自动沉淀 (Memory Consolidation) ---
                user_input_for_memory = (user_input or "").strip()
                turn_events = new_journal
                turn_responses = result_state.get("speaker_responses", [])

                if user_input_for_memory and (len(user_input_for_memory) > 5 or turn_events):
                    print("\n🧠 [系统] 正在将本轮交互沉淀为长期记忆...")

                    turn_summary_prompt = f"玩家说：{user_input_for_memory}\n"
                    if turn_events:
                        turn_summary_prompt += f"发生的事件：{', '.join(turn_events)}\n"
                    for speaker, resp in turn_responses:
                        turn_summary_prompt += f"{speaker} 回应：{resp}\n"

                    summary_llm = ChatOpenAI(
                        model=settings.MODEL_NAME,
                        api_key=settings.API_KEY,  # type: ignore[arg-type]
                        base_url=settings.BASE_URL,
                        temperature=0.3,
                    )

                    extract_sys_prompt = (
                        "你是一个记忆提取器。请阅读以下跑团游戏中的一轮交互，判断是否发生了值得长期记住的事件"
                        "（例如：物品的赠送/抢夺、好感度的明显改变、角色吐露了心声或秘密、重大的冲突）。\n"
                        "如果值得记住，请将其浓缩为一句极其精简的第三人称客观描述（不多于50字），例如：'玩家强行给了莱埃泽尔一瓶药水，遭到阿斯代伦的嘲讽。'\n"
                        "如果只是无意义的闲聊，请严格输出 'NONE'。"
                    )

                    try:
                        summary_msg = summary_llm.invoke(
                            [
                                SystemMessage(content=extract_sys_prompt),
                                HumanMessage(content=turn_summary_prompt),
                            ]
                        )
                        raw_out = summary_msg.content
                        if isinstance(raw_out, list):
                            memory_text = "".join(
                                str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in raw_out
                            ).strip()
                        else:
                            memory_text = str(raw_out or "").strip()

                        if memory_text and memory_text != "NONE":
                            episodic_memory.add_memory(
                                text=memory_text,
                                speaker="system",
                                metadata={"turn": result_state.get("turn_count", 0)},
                            )
                    except Exception as e:
                        print(f"⚠️ 记忆沉淀失败: {e}")
                # --------------------------------------------------------

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
