"""
Generation 节点：NPC 台词生成（工厂模式 + ReAct 工具）。

【通过背包内容约束 AI 幻觉】
- 将 state["npc_inventory"] 转为易读清单（如「治疗药水 x2」）并写入 system prompt，
  使角色明确「当前身上有什么」；模板中 [CURRENT INVENTORY] 与 [CRITICAL REALITY CONSTRAINTS]
  均依赖此清单与 has_healing_potion 等标志位。
- 若背包无药水，has_healing_potion=False，模板会强制输出「不得描述喝药水」等约束，
  从而避免 LLM 编造与背包事实不符的喝药/赠物等动作。
- 物品触发器（如玩家说「给你药水」）在本节点内执行，并写回 flags/背包，保证
  下一轮 prompt 中的背包与标志位与真实状态一致。
"""

import copy
import os
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from config import settings
from core.engine import generate_dialogue, parse_ai_response
from core.engine.physics import apply_environment_interaction, apply_physics
from core.graph.graph_state import GameState
from core.graph.nodes.utils import (
    _build_item_lore,
    _message_to_dict,
    _msg_content,
    default_entities,
    first_entity_id,
)
from core.systems.inventory import format_inventory_dict_to_display_list, get_registry
from core.systems.memory_rag import episodic_memory
from core.tools.npc_tools import check_target_inventory
from core.utils.text_processor import clean_npc_dialogue, format_history_message, parse_llm_json

# 全局开关：设为 True 时打印发给大模型的 Payload（调试用）
DEBUG_AI_PAYLOAD = False


def _player_message_suggests_item_offer(text: str) -> bool:
    """玩家是否在口头赠送/递物品（DM 常仍标为 CHAT，但必须走带工具的 Agent）。"""
    if not text or not str(text).strip():
        return False
    t = str(text).strip()
    low = t.lower()
    zh = ("给你", "送你", "拿好", "接着", "喝下", "收下", "接住", "一瓶", "这瓶", "把这", "治疗药水", "药水", "东西给你")
    en = ("give you", "here's", "here is", "take this", "take the", "healing potion", "have a potion")
    return any(k in t for k in zh) or any(k in low for k in en)


def _latest_roll_is_meaningful(latest_roll: Any) -> bool:
    """是否存在需要 NPC 严肃接检定结果的掷骰上下文（空 dict 不视为有检定）。"""
    if latest_roll is None:
        return False
    if not isinstance(latest_roll, dict):
        return bool(latest_roll)
    return bool(latest_roll.get("result")) or bool(latest_roll.get("intent"))


def create_generation_node() -> Callable[[GameState], dict]:
    """
    工厂函数：创建 Generation 节点。
    根据 state["current_speaker"] 动态加载 YAML 灵魂，实现多智能体话语权路由。
    """

    def generation_node(state: GameState) -> dict:
        """
        LLM 生成节点。
        根据 current_speaker 动态加载对应角色，从 state 提取 affection / flags / inventory 等。
        """
        from characters.loader import load_character

        entities = state.get("entities") or copy.deepcopy(default_entities)
        fallback_speaker = first_entity_id(entities)
        speaker = (state.get("current_speaker") or "").strip() or fallback_speaker
        character = load_character(speaker)
        print(f"🗣️ Generation Node: {speaker.capitalize()} is speaking...")
        current_npc_hp = entities.get(speaker, {}).get("hp", 20)
        char_display = character.data.get("name", speaker.capitalize())
        if current_npc_hp <= 0:
            death_msg = f"🩸 {char_display}倒在地上，失去了意识。周围陷入了死寂。"
            prev_responses = list(state.get("speaker_responses", []))
            return {
                "final_response": death_msg,
                "speaker_responses": prev_responses + [(speaker, death_msg)],
                "thought_process": "",
                "messages": [
                    HumanMessage(content=state.get("user_input", "")),
                    AIMessage(
                        content=f"[SYSTEM] {char_display}已经倒在血泊中，失去了意识。你无法再与其交谈。",
                        name=speaker,
                    ),
                ],
            }

        user_input = state.get("user_input", "")
        current_npc = entities.get(speaker, {})
        affection = current_npc.get("affection", 0)
        flags = state.get("flags", {})
        npc_inv = current_npc.get("inventory", state.get("npc_inventory", {}))
        if not isinstance(npc_inv, dict):
            npc_inv = {}
        player_inv = state.get("player_inventory", {})
        journal_events = list(state.get("journal_events", []))
        summary = state.get("summary", "Graph Mode Testing")

        # 多人轮流发言：input_node 每轮开始时清空 speaker_responses。
        # 仅第一位 NPC 应把本回合玩家句写入 messages / LLM history，后续 NPC 只追加自己的 AIMessage。
        prev_responses = list(state.get("speaker_responses", []))
        is_first_npc_of_player_turn = len(prev_responses) == 0

        # Banter 仅用 generate_dialogue，无 bind_tools；须严格限制在「纯闲聊 + 无检定 + 无实体交接」场景
        intent = str(state.get("intent", "chat") or "chat").strip().lower()
        latest_roll = state.get("latest_roll")
        banter_allowed_intents = frozenset({"chat", "banter"})
        needs_full_agent = (
            intent not in banter_allowed_intents
            or _latest_roll_is_meaningful(latest_roll)
            or bool(state.get("is_probing_secret"))
            or _player_message_suggests_item_offer(user_input)
        )

        messages = list(state.get("messages", []))
        is_banter = False
        dm_text = ""
        if not needs_full_agent and messages:
            last_msg = messages[-1]
            last_content = _msg_content(last_msg)
            last_name = getattr(last_msg, "name", None) or (
                last_msg.get("name") if isinstance(last_msg, dict) else None
            )
            if last_name == "DM" or (last_content and last_content.strip().startswith("[DM]:")):
                is_banter = True
                dm_text = last_content.replace("[DM]:", "").strip() if last_content else ""

        if is_banter and dm_text:
            print(f"💬 [Banter Mode] {speaker.capitalize()} 使用极简模板吐槽...")
            from jinja2 import Environment, FileSystemLoader

            _prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "llm", "prompts")
            _banter_env = Environment(loader=FileSystemLoader(_prompts_dir), trim_blocks=True, lstrip_blocks=True)
            banter_tpl = _banter_env.get_template("banter.j2")
            traits = character.data.get("personality", {}).get("traits", []) or []
            core_traits = ", ".join(str(t) for t in traits[:3]) if traits else "mysterious"
            system_prompt = banter_tpl.render(
                npc_name=character.data.get("name", speaker.capitalize()),
                core_traits=core_traits,
                approval=affection,
                dm_text=dm_text,
            )
            history_dicts = [{"role": "user", "content": f"[DM]: {dm_text}"}]
            raw_response = generate_dialogue(system_prompt, conversation_history=history_dicts)
            parsed = parse_ai_response(raw_response)
            clean_text = clean_npc_dialogue(speaker, (parsed.get("text") or "...").strip())
            attributed_msg = format_history_message(speaker, clean_text)
            return {
                "final_response": clean_text,
                "speaker_responses": prev_responses + [(speaker, clean_text)],
                "thought_process": "",
                "messages": [AIMessage(content=attributed_msg, name=speaker)],
            }

        triggers_config = character.data.get("dialogue_triggers", [])
        trigger_result = {"journal_entries": [], "relationship_delta": 0}

        inventory_display_list = format_inventory_dict_to_display_list(npc_inv)
        has_healing_potion = (npc_inv.get("healing_potion", 0) or 0) >= 1

        current_npc_data = entities.get(speaker, {})
        shar_faith = current_npc_data.get("shar_faith")
        memory_awakening = current_npc_data.get("memory_awakening")
        system_prompt = character.render_prompt(
            relationship_score=affection,
            affection=affection,
            flags=flags,
            summary=summary,
            journal_entries=journal_events[-5:] if journal_events else [],
            inventory_items=inventory_display_list,
            has_healing_potion=has_healing_potion,
            time_of_day=state.get("time_of_day", "晨曦 (Morning)"),
            hp=current_npc_data.get("hp", 20),
            active_buffs=current_npc_data.get("active_buffs", []),
            shar_faith=shar_faith,
            memory_awakening=memory_awakening,
        )

        item_lore = _build_item_lore(state)
        if item_lore:
            system_prompt += item_lore

        system_prompt += f"Current Speaker: {speaker}\n"
        system_prompt += f"Player's Current Inventory: {player_inv}\n"

        # --- 【新增】环境感知注入 ---
        loc = state.get("current_location", "Unknown Location")
        env_objs = state.get("environment_objects") or {}
        if not isinstance(env_objs, dict):
            env_objs = {}
        system_prompt += "\n[CURRENT ENVIRONMENT]\n"
        system_prompt += f"You are currently at: {loc}\n"
        if env_objs:
            system_prompt += "Interactive Objects around you:\n"
            for obj_id, obj_data in env_objs.items():
                if not isinstance(obj_data, dict):
                    continue
                system_prompt += (
                    f"- {obj_id} ({obj_data.get('name')}): "
                    f"Status=[{obj_data.get('status')}], Desc=[{obj_data.get('description')}]\n"
                )
        else:
            system_prompt += "There are no notable interactive objects around.\n"
        # ----------------------------

        # --- 【新增】RAG 长期记忆注入 ---
        if user_input and user_input.strip():
            retrieved_memories = episodic_memory.retrieve_relevant_memories(user_input, top_k=2)
            if retrieved_memories:
                system_prompt += "\n[LONG-TERM EPISODIC MEMORIES]\n"
                system_prompt += "These are your past memories related to the current situation:\n"
                for mem in retrieved_memories:
                    system_prompt += f"- {mem}\n"
                system_prompt += "Use these memories to inform your reaction if they are relevant.\n"
        # -------------------------------

        # 【核心修复：将本回合检定结果注入 System Prompt，避免模型看不到 latest_roll】
        # 仅在有实质掷骰数据时注入（与 needs_full_agent 判定一致），避免空 dict 噪声
        if latest_roll and isinstance(latest_roll, dict) and _latest_roll_is_meaningful(latest_roll):
            _roll_result = latest_roll.get("result")
            _roll_result_dict = _roll_result if isinstance(_roll_result, dict) else {}
            is_success = bool(_roll_result_dict.get("is_success", False))
            roll_status = "SUCCESS" if is_success else "FAILURE"
            system_prompt += (
                f"\n🚨 [CRITICAL SYSTEM ALERT]: The player just attempted a skill check "
                f"({latest_roll.get('intent')}). The result was: {roll_status}!\n"
            )
            if not is_success:
                system_prompt += (
                    "Because the roll is a FAILURE, you MUST absolutely reject the player and their item "
                    "in your response. DO NOT ACCEPT IT.\n"
                )

        messages = list(state.get("messages", []))
        if is_first_npc_of_player_turn and user_input:
            if not messages or _msg_content(messages[-1]) != user_input:
                messages.append({"role": "user", "content": user_input})
        # 非首位 NPC：state.messages 已由首位写入 HumanMessage，此处不再重复注入玩家句

        recent_messages = messages[-20:] if len(messages) > 20 else messages
        history_dicts = [_message_to_dict(m) for m in recent_messages]

        # 近因效应：拼在最后一条 User 消息末尾（经 history_dicts 进入 lc_messages；避免先改 messages 以免污染 A-to-A 的 original_text）
        prompt_suffix = "\n*(现在轮到你做出反应了)*"
        # 【终极疗法：利用 JSON 内联动作，打破动作幻觉与拖延症】
        if intent not in ("chat", "banter"):
            prompt_suffix += f"""\n\n🚨 [CRITICAL OVERRIDE - PHYSICAL ACTION REQUIRED]:
Listen carefully, {speaker}: Your text output is ONLY YOUR VOICE. It cannot move items or interact with the world.
If you decide to accept an item OR interact with the environment (like opening a chest or unlocking a door), YOU MUST output the `physical_action` field in your JSON response!

CRITICAL RULE: If the player just rolled a SUCCESSFUL skill check to command you, YOU MUST execute the action IMMEDIATELY in this turn. DO NOT delay it to the next turn, and DO NOT just roleplay doing it in text!

Examples:
1. Taking an item: "physical_action": {{"action_type": "transfer_item", "source_id": "player", "target_id": "{speaker}", "item_id": "healing_potion", "amount": 1}}
2. Interacting with object: "physical_action": {{"action_type": "interact_object", "target_id": "iron_chest", "action_detail": "unlock"}}

IF YOU DO NOT INCLUDE THIS FIELD IN YOUR JSON, YOU ARE JUST STANDING STILL AND DOING NOTHING!"""

        if len(prev_responses) > 0:
            last_speaker_id, last_speaker_text = prev_responses[-1]

            system_prompt += (
                f"\n\n[CRITICAL A-TO-A NOTE: You are part of a group conversation. "
                f"The player just acted, and {last_speaker_id} reacted by saying: '{last_speaker_text}'.\n"
                f"YOUR TASK: Evaluate {last_speaker_id}'s statement based on your personality.\n"
                "- If you STRONGLY DISAGREE, argue with them.\n"
                "- If you AGREE, support or build on their point.\n"
                "- If you think they are being ridiculous, MOCK them.\n"
                "- If the topic is TRIVIAL or you don't care, DO NOT SPEAK. Output ONLY a brief physical action "
                "(e.g., *rolls eyes*, *yawns*, *ignores them*).\n"
                f"React naturally. Address {last_speaker_id} directly if you choose to speak.]"
            )

            if history_dicts and history_dicts[-1]["role"] == "user":
                original_text = history_dicts[-1]["content"]
                history_dicts[-1]["content"] = (
                    f"[事件回顾] 玩家说：{original_text}\n"
                    f"[刚刚发生] {last_speaker_id} 回应道：{last_speaker_text}"
                    + prompt_suffix
                )
        elif history_dicts and history_dicts[-1].get("role") == "user":
            _last_u = history_dicts[-1].get("content") or ""
            history_dicts[-1]["content"] = _last_u + prompt_suffix

        current_entities = {k: dict(v) for k, v in entities.items()}
        for k in current_entities:
            current_entities[k].setdefault("affection", 0)
            current_entities[k].setdefault("inventory", {})
            if not isinstance(current_entities[k].get("inventory"), dict):
                current_entities[k]["inventory"] = {}
        current_entities.setdefault(speaker, {"hp": 20, "active_buffs": [], "affection": 0, "inventory": {}})
        if user_input and triggers_config:
            current_entities[speaker]["inventory"] = dict(npc_inv)
            current_entities[speaker]["affection"] = affection
        player_inv_for_physics = dict(player_inv)

        _raw_env = state.get("environment_objects") or {}
        current_env_objs: dict = {}
        if isinstance(_raw_env, dict):
            for _ek, _ev in _raw_env.items():
                if isinstance(_ev, dict):
                    current_env_objs[_ek] = dict(_ev)

        system_prompt += """

<CRITICAL_SYSTEM_RULES>
You are an autonomous AGENT. YOUR TEXT DESCRIPTIONS DO NOT AFFECT THE PHYSICAL WORLD.

1. PHYSICAL ACTIONS: If you accept an item, give an item, or interact with an environment object (like opening a chest), YOU MUST output the `physical_action` field in your JSON response!
2. CONSISTENCY IS MANDATORY: Your spoken dialogue, text actions, and the `physical_action` JSON field must be 100% aligned.

[CRITICAL DICE RULE - READ CAREFULLY]:
Check the most recent [SYSTEM] or DM events. If a skill check resulted in "FAILURE":
- You MUST explicitly REJECT the player's action in your dialogue and text descriptions.
- You are STRICTLY FORBIDDEN from outputting any `physical_action`.
If a skill check resulted in "SUCCESS", you MUST output the corresponding `physical_action` IMMEDIATELY.
</CRITICAL_SYSTEM_RULES>
"""

        lc_messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        for d in history_dicts:
            if d.get("role") == "user":
                lc_messages.append(HumanMessage(content=d.get("content", "")))
            else:
                lc_messages.append(AIMessage(content=d.get("content", "")))

        llm = ChatOpenAI(
            model=settings.MODEL_NAME,
            api_key=settings.API_KEY,  # type: ignore[arg-type]
            base_url=settings.BASE_URL,
            temperature=0.7,
            max_completion_tokens=500,
        )
        # 主路径仅绑定查询工具，物理动作全面改用内联 JSON 字段
        llm_with_tools = llm.bind_tools([check_target_inventory])

        if DEBUG_AI_PAYLOAD:
            messages_dbg = lc_messages
            print("\n" + "🔥" * 25)
            print("🚨 正在打印发给大模型的最终 Payload...")
            print(f"📊 当前消息总数: {len(messages_dbg)} 条")
            for i, msg in enumerate(messages_dbg):
                msg_type = msg.__class__.__name__
                print(f"\n[{i}] 角色/类型: {msg_type}")
                if msg_type == "SystemMessage":
                    content_str = str(getattr(msg, "content", "") or "")
                    content_preview = content_str.replace("\n", " ")[:100]
                    print(f"    📝 内容预览: {content_preview}...")
                    print(f"    📏 总字符数: {len(content_str)}")
                elif msg_type == "HumanMessage":
                    print(f"    🗣️ 玩家说: {msg.content}")
                elif msg_type == "AIMessage":
                    print(f"    🤖 AI 文本: {repr(msg.content)}")
                    if getattr(msg, "tool_calls", None):
                        print(f"    🔧 携带工具调用意图: {getattr(msg, 'tool_calls', None)}")
                elif msg_type == "ToolMessage":
                    print(f"    ⚙️ 工具执行结果: {msg.content}")
                    print(f"    🔗 绑定的 Tool ID: {getattr(msg, 'tool_call_id', '缺失!')}")
                else:
                    print(f"    ❓ 未知消息内容: {msg.content}")
            print("🔥" * 25 + "\n")

        response = llm_with_tools.invoke(lc_messages)

        from ui.renderer import GameRenderer

        GameRenderer().print_system_info(
            f"🔧 [底层透视] LLM 返回的 tool_calls: {getattr(response, 'tool_calls', [])}"
        )

        tool_physics_events = []
        MAX_ITERATIONS = 5
        iteration_count = 0
        while response.tool_calls:
            iteration_count += 1
            lc_messages.append(response)
            registry = get_registry()
            for tc in response.tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args") or {}
                tool_result_str = "操作失败"

                if tool_name == "check_target_inventory":
                    target = tool_args.get("target_id", "player")
                    keyword = (tool_args.get("item_keyword") or "").lower()
                    if target == "player":
                        inv = player_inv_for_physics
                    else:
                        inv = current_entities.get(target, {}).get("inventory", {})
                    inv = inv or {}
                    found = False
                    for i_id, count in inv.items():
                        if keyword in i_id.lower() or keyword in registry.get_name(i_id).lower():
                            tool_result_str = f"{target} 拥有 {count} 个 {i_id}。"
                            found = True
                            break
                    if not found:
                        tool_result_str = f"{target} 的背包里根本没有找到 '{keyword}'！他在撒谎或两手空空。"

                else:
                    tool_result_str = f"[系统] 未知工具: {tool_name}（物理动作请使用 JSON 中的 physical_action 字段）。"

                tool_msg = ToolMessage(content=tool_result_str, tool_call_id=tc.get("id", ""))
                lc_messages.append(tool_msg)

            if DEBUG_AI_PAYLOAD:
                messages_dbg = lc_messages
                print("\n" + "🔥" * 25)
                print(f"🚨 [ReAct 第 {iteration_count} 轮] 正在打印发给大模型的 Payload (含工具返回)...")
                print(f"📊 当前消息总数: {len(messages_dbg)} 条")
                for i, msg in enumerate(messages_dbg):
                    msg_type = msg.__class__.__name__
                    print(f"\n[{i}] 角色/类型: {msg_type}")
                    if msg_type == "SystemMessage":
                        content_str = str(getattr(msg, "content", "") or "")
                        content_preview = content_str.replace("\n", " ")[:100]
                        print(f"    📝 内容预览: {content_preview}...")
                        print(f"    📏 总字符数: {len(content_str)}")
                    elif msg_type == "HumanMessage":
                        print(f"    🗣️ 玩家说: {msg.content}")
                    elif msg_type == "AIMessage":
                        print(f"    🤖 AI 文本: {repr(msg.content)}")
                        if getattr(msg, "tool_calls", None):
                            print(f"    🔧 携带工具调用意图: {getattr(msg, 'tool_calls', None)}")
                    elif msg_type == "ToolMessage":
                        print(f"    ⚙️ 工具执行结果: {msg.content}")
                        print(f"    🔗 绑定的 Tool ID: {getattr(msg, 'tool_call_id', '缺失!')}")
                    else:
                        print(f"    ❓ 未知消息内容: {msg.content}")
                print("🔥" * 25 + "\n")

            response = llm_with_tools.invoke(lc_messages)

            GameRenderer().print_system_info(
                f"🔧 [底层透视] LLM 返回的 tool_calls (ReAct #{iteration_count}): "
                f"{getattr(response, 'tool_calls', [])}"
            )

            if iteration_count >= MAX_ITERATIONS:
                print("⚠️ [安全拦截] Agent 内部工具调用次数超限 (>=5次)，强制终止循环！")
                break

        if getattr(response, "tool_calls", None) and not (getattr(response, "content", None) or "").strip():
            response = AIMessage(content="*（陷入了深深的沉思，暂时没有回应）*")

        raw_output = str(response.content if hasattr(response, "content") else str(response or ""))

        json_parsed = parse_llm_json(raw_output)

        # --- 调试用：看看大模型到底给的啥 JSON ---
        if DEBUG_AI_PAYLOAD:
            print(f"📦 [底层 JSON 透视] \n{raw_output}\n")
        # ----------------------------------------

        if isinstance(json_parsed, dict) and "reply" in json_parsed:
            raw_text = (json_parsed.get("reply") or "...").strip()
            thought_process = (json_parsed.get("internal_monologue") or "").strip()
            state_changes = json_parsed.get("state_changes") or {}

            # --- 【新增】解析 JSON 内联的物理动作并直接结算 ---
            physical_action = json_parsed.get("physical_action")
            if physical_action and isinstance(physical_action, dict):
                action_type = physical_action.get("action_type")
                if action_type == "transfer_item":
                    # 组装底层的转移意图
                    item_transfers = [{
                        "from": physical_action.get("source_id", "player"),
                        "to": physical_action.get("target_id", speaker),
                        "item_id": physical_action.get("item_id", ""),
                        "count": int(physical_action.get("amount", 1))
                    }]
                    
                    # 强行调用底层的物理引擎结算
                    new_events = apply_physics(current_entities, player_inv_for_physics, item_transfers, [])
                    
                    # 状态回写（终端由 main 回合末统一打印 journal_events）
                    tool_physics_events.extend(new_events)
                elif action_type == "interact_object":
                    _tid = physical_action.get("target_id", "")
                    _detail = (physical_action.get("action_detail") or "").strip() or "open"
                    interaction_events = apply_environment_interaction(
                        current_env_objs, _tid, _detail, speaker
                    )
                    tool_physics_events.extend(interaction_events)
        else:
            parsed = parse_ai_response(raw_output)
            raw_text = (parsed.get("text") or raw_output or "...").strip()
            thought_process = (parsed.get("thought") or "").strip()
            state_changes = {
                "affection_delta": parsed.get("approval", 0),
                "shar_faith_delta": 0,
                "memory_awakening_delta": 0,
            }

        clean_text = clean_npc_dialogue(speaker, raw_text)
        attributed_msg = format_history_message(speaker, clean_text)

        aff_delta = int(state_changes.get("affection_delta", 0))
        shar_delta = int(state_changes.get("shar_faith_delta", 0))
        mem_delta = int(state_changes.get("memory_awakening_delta", 0))
        state_changes_applied = False
        if aff_delta != 0 or shar_delta != 0 or mem_delta != 0:
            ent = current_entities.get(speaker, {})
            ent = dict(ent)
            ent["affection"] = max(-100, min(100, ent.get("affection", 0) + aff_delta))
            if "shar_faith" in ent:
                ent["shar_faith"] = max(0, min(100, ent["shar_faith"] + shar_delta))
            if "memory_awakening" in ent:
                ent["memory_awakening"] = max(0, min(100, ent["memory_awakening"] + mem_delta))
            current_entities[speaker] = ent
            state_changes_applied = True

        out_messages: list[BaseMessage] = [AIMessage(content=attributed_msg, name=speaker)]
        if is_first_npc_of_player_turn and user_input:
            out_messages = [HumanMessage(content=user_input), AIMessage(content=attributed_msg, name=speaker)]

        out = {
            "final_response": clean_text,
            "speaker_responses": prev_responses + [(speaker, clean_text)],
            "thought_process": thought_process,
            "messages": out_messages,
        }
        if state_changes_applied:
            out["entities"] = current_entities
        trigger_journal = trigger_result.get("journal_entries", [])
        if trigger_journal:
            out["journal_events"] = trigger_journal
        if tool_physics_events:
            out["journal_events"] = out.get("journal_events", []) + tool_physics_events
        if tool_physics_events:
            out["entities"] = current_entities
            out["player_inventory"] = player_inv_for_physics
            out["environment_objects"] = current_env_objs
        if user_input and triggers_config:
            out["flags"] = flags
            out["player_inventory"] = player_inv_for_physics
            out["entities"] = current_entities
        return out

    return generation_node


def generation_node(state: GameState) -> dict:
    """
    默认 Generation 节点（向后兼容 main_graph.py 等单测）。
    生产环境应使用 create_generation_node() 动态加载角色。
    """
    return create_generation_node()(state)
