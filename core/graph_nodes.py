"""
LangGraph 节点：Input / DM / Mechanics / Generation

叙事工程师实践：逻辑解耦与单一职责
- 每个节点只返回「需要修改的字段」，由 Graph 的 Reducer 自动合并
- 避免节点内手动 copy/append，信任 LangGraph 的状态管理
"""

from typing import Callable
from core.graph_state import GameState
from core.dm import analyze_intent
from core import mechanics
from core.inventory import get_registry
from core.dice import roll_d20
from core.engine import generate_dialogue, parse_ai_response


# =============================================================================
# Node 1: Input 输入处理
# =============================================================================


def input_node(state: GameState) -> dict:
    """
    处理斜杠命令（/give, /use）。
    
    解耦原则：直接返回需要修改的字段，不手动合并。
    - player_inventory / npc_inventory: 返回完整新 dict，Graph 覆盖
    - journal_events: 返回 [新事件]，merge_events Reducer 自动累加
    - 保持命令逻辑清晰，状态更新交给框架
    """
    user_input = state.get("user_input", "").strip()
    base = {"intent": "pending"}

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
            return {
                "player_inventory": new_p,
                "npc_inventory": new_n,
                "relationship": state.get("relationship", 0) + 2,
                "journal_events": [f"Player gave {item_key} to NPC."],
                "final_response": f"[SYSTEM] You gave {item_key} to Shadowheart.",
                "intent": "gift_given",
            }
        return {
            "final_response": f"[SYSTEM] You don't have {item_key}.",
            "intent": "command_done",
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
            return {
                "player_inventory": new_p,
                "journal_events": [f"Player used {item_key}: {effect['message']}"],
                "final_response": f"[SYSTEM] You used {item_key}: {effect['message']}",
                "intent": "item_used",
            }
        return {
            "final_response": f"[SYSTEM] You don't have {item_key}.",
            "intent": "command_done",
        }

    # --- 未知命令 ---
    return {
        "final_response": "[SYSTEM] Unknown command.",
        "intent": "command_done",
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
    analysis = analyze_intent(state.get("user_input", ""))
    return {"intent": analysis.get("action_type", "chat")}


# =============================================================================
# Node 3: Mechanics 骰子系统
# =============================================================================


def mechanics_node(state: GameState) -> dict:
    """
    根据意图执行骰子检定。
    
    健壮性：掷骰结果格式化为清晰字符串，放入 journal_events。
    后续 Generation 节点可直接引用这些事件作为叙事上下文。
    使用 merge_events Reducer：只返回 [新事件]，不 copy/append。
    """
    intent = state.get("intent", "chat")
    if intent in ["chat", "command_done", "pending", "gift_given", "item_used"]:
        return {}

    print(f"⚙️ Mechanics Node: Processing {intent}...")
    dc = 12
    modifier = 0
    result = roll_d20(dc, modifier)

    # 清晰、可被下游引用的格式
    outcome_str = (
        f"Skill Check | {intent} | "
        f"Result: {result['result_type'].value} | "
        f"Roll: {result['total']} vs DC {dc}"
    )
    return {"journal_events": [outcome_str]}


# =============================================================================
# Node 4: Generation LLM 生成（工厂模式）
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
        """
        print("🗣️ Generation Node: Shadowheart is speaking...")

        # 从 state 提取上下文，不依赖外部注入
        relationship = state.get("relationship", 0)
        flags = state.get("flags", {})
        npc_inv = state.get("npc_inventory", {})
        journal_events = state.get("journal_events", [])
        summary = state.get("summary", "Graph Mode Testing")

        system_prompt = character.render_prompt(
            relationship_score=relationship,
            flags=flags,
            summary=summary,
            journal_entries=journal_events,
            inventory_items=list(npc_inv.keys()),
            has_healing_potion="healing_potion" in npc_inv,
        )

        # messages 符合 add_messages：从 state 读取，转为 engine 所需格式
        messages = list(state.get("messages", []))
        user_input = state.get("user_input", "")

        if not messages or _msg_content(messages[-1]) != user_input:
            messages.append({"role": "user", "content": user_input})

        history_dicts = [_message_to_dict(m) for m in messages]
        raw_response = generate_dialogue(system_prompt, conversation_history=history_dicts)
        parsed = parse_ai_response(raw_response)

        return {
            "final_response": parsed["text"] or "...",
            "thought_process": parsed.get("thought") or "",
        }

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
