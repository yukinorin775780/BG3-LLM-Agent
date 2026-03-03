"""
LangGraph 节点：Input / DM / Mechanics / Generation

叙事工程师实践：逻辑解耦与单一职责
- 每个节点只返回「需要修改的字段」，由 Graph 的 Reducer 自动合并
- 避免节点内手动 copy/append，信任 LangGraph 的状态管理
"""

from typing import Callable
from langchain_core.messages import HumanMessage, AIMessage
from core.graph.graph_state import GameState
from core.llm.dm import analyze_intent
from core.systems import mechanics
from core.systems.inventory import get_registry, Inventory, format_inventory_dict_to_display_list
from core.engine import generate_dialogue, parse_ai_response


# =============================================================================
# Node 1: Input 输入处理
# =============================================================================


def input_node(state: GameState) -> dict:
    """
    处理斜杠命令（/give, /use, /add, /flag）。
    
    解耦原则：直接返回需要修改的字段，不手动合并。
    - player_inventory / npc_inventory: 返回完整新 dict，Graph 覆盖
    - journal_events: 返回 [新事件]，merge_events Reducer 自动累加
    - 保持命令逻辑清晰，状态更新交给框架
    """
    user_input = state.get("user_input", "").strip()
    base = {
        "intent": "pending",
        "is_probing_secret": False,  # [核心修复] 每次输入前强制洗刷上一轮的禁忌状态
    }

    if not user_input:
        return base

    if not user_input.startswith("/"):
        return base

    parts = user_input.split()
    command = parts[0].lower()
    player_inv = state.get("player_inventory", {})
    npc_inv = state.get("npc_inventory", {})

    # --- /GIVE <item> ---
    if command == "/give" and len(parts) > 1:
        item_key = parts[1]
        if player_inv.get(item_key, 0) > 0:
            new_p = dict(player_inv)
            new_p[item_key] = new_p[item_key] - 1
            if new_p[item_key] <= 0:
                del new_p[item_key]
            new_n = dict(npc_inv)
            new_n[item_key] = new_n.get(item_key, 0) + 1
            response_text = f"[SYSTEM] You gave {item_key} to Shadowheart."
            return {
                "player_inventory": new_p,
                "npc_inventory": new_n,
                "relationship": state.get("relationship", 0) + 2,
                "journal_events": [f"Player gave {item_key} to NPC."],
                "final_response": response_text,
                "intent": "gift_given",
                "is_probing_secret": False,
                "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
            }
        response_text = f"[SYSTEM] You don't have {item_key}."
        return {
            "final_response": response_text,
            "intent": "command_done",
            "is_probing_secret": False,
            "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
        }

    # --- /USE <item> ---
    if command == "/use" and len(parts) > 1:
        item_key = parts[1]
        if player_inv.get(item_key, 0) > 0:
            item_data = get_registry().get(item_key)
            effect = mechanics.apply_item_effect(item_key, item_data)
            new_p = dict(player_inv)
            new_p[item_key] = new_p[item_key] - 1
            if new_p[item_key] <= 0:
                del new_p[item_key]
            response_text = f"[SYSTEM] You used {item_key}: {effect['message']}"
            return {
                "player_inventory": new_p,
                "journal_events": [f"Player used {item_key}: {effect['message']}"],
                "final_response": response_text,
                "intent": "item_used",
                "is_probing_secret": False,
                "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
            }
        response_text = f"[SYSTEM] You don't have {item_key}."
        return {
            "final_response": response_text,
            "intent": "command_done",
            "is_probing_secret": False,
            "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
        }

    # --- /ADD <item> (开发者指令) ---
    if command == "/add" and len(parts) > 1:
        item_key = parts[1]
        new_p = dict(player_inv)
        new_p[item_key] = new_p.get(item_key, 0) + 1
        response_text = f"[SYSTEM] DevMode: Added {item_key} to your inventory."
        return {
            "player_inventory": new_p,
            "final_response": response_text,
            "intent": "command_done",
            "is_probing_secret": False,
            "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
        }

    # --- /FLAG <key> <value> (开发者指令：动态修改标志位) ---
    if command == "/flag" and len(parts) > 2:
        flag_key = parts[1]
        flag_val_str = parts[2].lower()
        flag_val = True if flag_val_str in ("true", "1", "yes", "on") else False

        new_flags = dict(state.get("flags", {}))
        new_flags[flag_key] = flag_val

        response_text = f"[SYSTEM] DevMode: Flag '{flag_key}' set to {flag_val}."
        return {
            "flags": new_flags,
            "final_response": response_text,
            "intent": "command_done",
            "is_probing_secret": False,
            "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
        }

    # --- 未知命令 ---
    response_text = "[SYSTEM] Unknown command."
    return {
        "final_response": response_text,
        "intent": "command_done",
        "is_probing_secret": False,
        "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
    }


# =============================================================================
# Node 2: DM 意图分析
# =============================================================================


def dm_node(state: GameState) -> dict:
    """
    分析玩家输入的意图。
    若 intent 已被 Input 处理（command_done / gift_given / item_used），直接跳过。
    """
    if state.get("intent") in ["command_done", "gift_given", "item_used"]:
        return {}

    print("🎲 DM Node: Analyzing intent...")
    analysis = analyze_intent(state.get("user_input", ""), flags=state.get("flags", {}))
    return {
        "intent": analysis.get("action_type", "CHAT"),
        "intent_context": {
            "difficulty_class": analysis.get("difficulty_class", 12),
            "reason": analysis.get("reason", ""),
        },
        "is_probing_secret": analysis.get("is_probing_secret", False),
    }


# =============================================================================
# Node 3: Mechanics 骰子系统
# =============================================================================


def mechanics_node(state: GameState) -> dict:
    """
    根据意图执行技能检定（PERSUASION/DECEPTION/STEALTH/INSIGHT 等）。
    若 is_probing_secret 为 True，优先走隐性好感度锁判定。
    
    调用 mechanics.execute_skill_check，使用动态 DC（来自 intent_context）、
    好感度修正、失败降好感，并将掷骰明细与结果写入 journal_events。
    """
    intent = state.get("intent", "chat")
    is_probing_secret = state.get("is_probing_secret", False)
    # 非动作意图且非刺探秘密时跳过（如纯 CHAT）
    if intent in ["chat", "CHAT", "command_done", "pending", "gift_given", "item_used"] and not is_probing_secret:
        return {}

    print(f"⚙️ Mechanics Node: Processing {intent} (is_probing_secret={is_probing_secret})...")
    result = mechanics.execute_skill_check(state)

    out = {"journal_events": result.get("journal_events", [])}
    if result.get("relationship_delta", 0) != 0:
        rel = state.get("relationship", 0)
        out["relationship"] = rel + result["relationship_delta"]
    return out


# =============================================================================
# Node 4: Generation LLM 生成（工厂模式）
# =============================================================================
#
# 【通过背包内容约束 AI 幻觉】
# - 将 state["npc_inventory"] 转为易读清单（如「治疗药水 x2」）并写入 system prompt，
#   使角色明确「当前身上有什么」；模板中 [CURRENT INVENTORY] 与 [CRITICAL REALITY CONSTRAINTS]
#   均依赖此清单与 has_healing_potion 等标志位。
# - 若背包无药水，has_healing_potion=False，模板会强制输出「不得描述喝药水」等约束，
#   从而避免 LLM 编造「影心喝下药水」等与事实不符的动作。
# - 物品触发器（如玩家说「给你药水」）在本节点内执行，并写回 flags/背包，保证
#   下一轮 prompt 中的背包与标志位与真实状态一致。
# =============================================================================


def create_generation_node(character) -> Callable[[GameState], dict]:
    """
    工厂函数：创建 Generation 节点，注入已加载的角色。
    
    叙事工程师实践：节点内不实例化 load_character，由 Graph 构建时注入。
    避免每次 invoke 都重新加载 YAML，同时保持节点纯函数语义。
    """

    def generation_node(state: GameState) -> dict:
        """
        LLM 生成节点。
        直接从 state 提取 relationship / flags / npc_inventory / journal_events，
        符合 add_messages 规范：messages 由 Graph 管理，本节点只读取。

        背包与幻觉约束：
        - 从 state["npc_inventory"] 得到易读清单并注入 prompt，使角色「知道」自己身上有什么。
        - has_healing_potion 等标志位与背包严格一致，避免 AI 在没药水时描述喝药水等幻觉。
        - 对话中的「给予物品」等触发器会在此处执行，并写回 flags / 背包状态。
        """
        print("🗣️ Generation Node: Shadowheart is speaking...")

        user_input = state.get("user_input", "")
        relationship = state.get("relationship", 0)
        flags = state.get("flags", {})
        npc_inv = state.get("npc_inventory", {})
        player_inv = state.get("player_inventory", {})
        journal_events = list(state.get("journal_events", []))
        summary = state.get("summary", "Graph Mode Testing")

        # -------------------------------------------------------------------------
        # 1. 物品触发器：玩家在对话中提及「给你药水」等时，自动转移物品、更新 flags、
        #    累加 approval_change 到 relationship，并生成 journal_entries 供本轮合并
        # -------------------------------------------------------------------------
        triggers_config = character.data.get("dialogue_triggers", [])
        trigger_result = {"journal_entries": [], "relationship_delta": 0}
        if user_input and triggers_config:
            player_inv_obj = Inventory()
            player_inv_obj.from_dict(player_inv)
            npc_inv_obj = Inventory()
            npc_inv_obj.from_dict(npc_inv)
            trigger_result = mechanics.process_dialogue_triggers(
                user_input, triggers_config, flags,
                ui=None, player_inv=player_inv_obj, npc_inv=npc_inv_obj
            )
            player_inv = player_inv_obj.to_dict()
            npc_inv = npc_inv_obj.to_dict()
            relationship = relationship + trigger_result.get("relationship_delta", 0)

        # -------------------------------------------------------------------------
        # 2. 背包感知：用 inventory 模块逻辑将 npc_inventory 转为易读字符串列表
        #    这样 prompt 里显示的是「治疗药水 x2」而非 "healing_potion"，减少歧义。
        # -------------------------------------------------------------------------
        inventory_display_list = format_inventory_dict_to_display_list(npc_inv)

        # -------------------------------------------------------------------------
        # 3. 关键标志位：has_healing_potion 必须与背包事实一致，用于约束幻觉
        #    模板中会据此输出 [CRITICAL REALITY CONSTRAINTS]：
        #    - 无药水时明确禁止描述「喝药水」等动作，只能拒绝或说「没有了」。
        # -------------------------------------------------------------------------
        has_healing_potion = (npc_inv.get("healing_potion", 0) or 0) >= 1

        # -------------------------------------------------------------------------
        # 4. 注入提示词：把当前背包清单与标志位传入 render_prompt，确保影心
        #    「知道」自己身上有什么，从而只描述实际拥有的物品行为，避免幻觉。
        # -------------------------------------------------------------------------
        system_prompt = character.render_prompt(
            relationship_score=relationship,
            flags=flags,
            summary=summary,
            journal_entries=journal_events,
            inventory_items=inventory_display_list,
            has_healing_potion=has_healing_potion,
        )

        # messages 符合 add_messages：从 state 读取，转为 engine 所需格式
        messages = list(state.get("messages", []))
        if not messages or _msg_content(messages[-1]) != user_input:
            messages.append({"role": "user", "content": user_input})

        history_dicts = [_message_to_dict(m) for m in messages]
        raw_response = generate_dialogue(system_prompt, conversation_history=history_dicts)
        parsed = parse_ai_response(raw_response)
        text = parsed["text"] or "..."

        # 合并触发器产生的剧情事件到 journal，并写回 flags/背包/好感度
        out = {
            "final_response": text,
            "thought_process": parsed.get("thought") or "",
            "messages": [HumanMessage(content=user_input), AIMessage(content=text)],
        }
        trigger_journal = trigger_result.get("journal_entries", [])
        if trigger_journal:
            out["journal_events"] = trigger_journal
        if user_input and triggers_config:
            out["flags"] = flags
            out["player_inventory"] = player_inv
            out["npc_inventory"] = npc_inv
            if trigger_result.get("relationship_delta", 0) != 0:
                out["relationship"] = relationship
        return out

    return generation_node


def generation_node(state: GameState) -> dict:
    """
    默认 Generation 节点（向后兼容 main_graph.py 等单测）。
    生产环境应使用 create_generation_node(char) 注入角色。
    """
    from characters.loader import load_character
    char = load_character("shadowheart")
    return create_generation_node(char)(state)


# =============================================================================
# 消息格式转换（add_messages 兼容）
# =============================================================================


def _msg_content(m) -> str:
    """从 dict 或 LangChain message 提取 content。"""
    if isinstance(m, dict):
        return m.get("content", "")
    return getattr(m, "content", "")


def _message_to_dict(m) -> dict:
    """转为 engine 格式：{role: 'user'|'assistant', content: str}。"""
    if isinstance(m, dict):
        role = m.get("role", "user")
        role = role if role in ("user", "assistant") else "user"
        return {"role": role, "content": m.get("content", "")}
    role = getattr(m, "type", "human")
    role = "user" if role == "human" else "assistant" if role == "ai" else "user"
    return {"role": role, "content": getattr(m, "content", "")}
