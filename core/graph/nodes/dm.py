"""
DM 分析、多人发言推进、旁白节点。
"""

import asyncio
import copy
import random

from langchain_core.messages import AIMessage

from core.engine import generate_dialogue, parse_ai_response
from core.graph.graph_state import GameState
from core.graph.nodes.utils import _build_item_lore, default_entities, entity_display_name, first_entity_id
from core.llm.dm import analyze_intent
from core.utils.text_processor import format_history_message


def _is_idle_banter_speaker(entity_id: str, entity: dict) -> bool:
    normalized_id = str(entity_id or "").strip().lower()
    if not normalized_id or normalized_id in {"player", "unknown"}:
        return False
    faction = str(entity.get("faction", "")).strip().lower()
    if faction in {"hostile", "neutral"}:
        return False
    status = str(entity.get("status", "alive")).strip().lower()
    if status in {"dead", "downed", "unconscious"}:
        return False
    if entity.get("is_alive") is False:
        return False
    return True


async def dm_node(state: GameState) -> dict:
    """
    分析玩家输入的意图。
    若 intent 为 command_done（系统指令已就地处理），直接跳过，不调用 LLM。
    兼容旧存档中偶发的 gift_given / item_used。
    DM 派发多人发言队列，并结算好感度变化，渲染 BG3 风格提示。
    """
    if state.get("intent") in ("command_done", "gift_given", "item_used"):
        return {}

    idle_intent = str(state.get("intent") or "").strip().lower()
    if idle_intent == "trigger_idle_banter":
        # 挂机闲聊：不调用 analyze_intent，随机一位队友作「主声线」模板；双人台词由 generation 一次 JSON 输出
        entities_raw = dict(state.get("entities") or {})
        if not entities_raw:
            entities_raw = copy.deepcopy(default_entities)
        entities = {k: dict(v) for k, v in entities_raw.items()}
        for k in entities:
            entities[k].setdefault("affection", 0)
            entities[k].setdefault("inventory", {})
            if not isinstance(entities[k].get("inventory"), dict):
                entities[k]["inventory"] = {}
        available_npcs = [
            entity_id
            for entity_id, entity in entities.items()
            if isinstance(entity, dict) and _is_idle_banter_speaker(str(entity_id), entity)
        ]
        if not available_npcs:
            print("🎲 DM Node: Idle banter (AFK) — no valid NPC speakers; skipping.")
            return {}
        current = random.choice(available_npcs)
        print("🎲 DM Node: Idle banter (AFK) — skipping intent LLM, speaker seed:", current)
        return {
            "entities": entities,
            "speaker_queue": [],
            "current_speaker": current,
            "speaker_responses": [],
            "intent": "trigger_idle_banter",
            "intent_context": {
                "difficulty_class": 12,
                "reason": "idle_banter",
                "action_actor": "player",
                "action_target": "",
            },
            "is_probing_secret": False,
        }

    print("🎲 DM Node: Analyzing intent...")
    entities_raw = dict(state.get("entities") or {})
    if not entities_raw:
        entities_raw = copy.deepcopy(default_entities)
    entities = {k: dict(v) for k, v in entities_raw.items()}
    for k in entities:
        entities[k].setdefault("affection", 0)
        entities[k].setdefault("inventory", {})
        if not isinstance(entities[k].get("inventory"), dict):
            entities[k]["inventory"] = {}
    available_npcs = list(entities.keys())
    if not available_npcs:
        available_npcs = ["unknown"]
    available_targets = list(
        dict.fromkeys(
            list(entities.keys()) + list((state.get("environment_objects") or {}).keys())
        )
    )
    fallback_speaker = first_entity_id(entities)
    current_npc_hp = entities.get(fallback_speaker, {}).get("hp", 20) if fallback_speaker != "unknown" else 20
    item_lore = _build_item_lore(state)
    analysis = await asyncio.to_thread(
        analyze_intent,
        state.get("user_input", ""),
        flags=state.get("flags", {}),
        time_of_day=state.get("time_of_day", "晨曦 (Morning)"),
        hp=current_npc_hp,
        available_npcs=available_npcs,
        available_targets=available_targets,
        item_lore=item_lore if item_lore else None,
        active_dialogue_target=state.get("active_dialogue_target"),
    )

    current_dialogue_target = str(state.get("active_dialogue_target") or "").strip().lower() or None
    next_dialogue_target = current_dialogue_target
    analyzed_action = str(analysis.get("action_type", "CHAT") or "CHAT").strip().upper()
    analyzed_target = str(analysis.get("action_target", "") or "").strip().lower()
    if analyzed_action == "START_DIALOGUE":
        next_dialogue_target = analyzed_target or current_dialogue_target
    elif analyzed_action == "DIALOGUE_REPLY":
        next_dialogue_target = current_dialogue_target or analyzed_target
        if not analysis.get("action_target") and next_dialogue_target:
            analysis["action_target"] = next_dialogue_target
    elif bool(analysis.get("clear_active_dialogue_target", False)):
        next_dialogue_target = None

    affection_changes = analysis.get("affection_changes", {})
    from ui.renderer import GameRenderer

    ui = GameRenderer()
    for npc_id, change in affection_changes.items():
        npc_id = str(npc_id).strip().lower()
        if npc_id in entities and isinstance(change, (int, float)) and change != 0:
            current_aff = entities[npc_id].get("affection", 0)
            new_aff = max(-100, min(100, current_aff + int(change)))
            entities[npc_id]["affection"] = new_aff
            npc_name_cn = entity_display_name(npc_id)
            delta = int(change)
            if delta > 0:
                ui.print_system_info(f"💡 [bold green][ {npc_name_cn} 赞同 (Approves) {delta:+d} ][/bold green]")
            else:
                ui.print_system_info(f"💔 [bold red][ {npc_name_cn} 不赞同 (Disapproves) {delta:+d} ][/bold red]")

    responders = analysis.get("responders")
    if isinstance(responders, list) and len(responders) > 0:
        queue = list(responders)
    else:
        queue = [fallback_speaker] if fallback_speaker != "unknown" else []
    current = queue.pop(0) if queue else fallback_speaker
    out = {
        "entities": entities,
        "speaker_queue": queue,
        "current_speaker": current,
        "speaker_responses": [],
        "intent": analysis.get("action_type", "CHAT"),
        "intent_context": {
            "difficulty_class": analysis.get("difficulty_class", 12),
            "reason": analysis.get("reason", ""),
            "action_actor": analysis.get("action_actor", "player"),
            "action_target": analysis.get("action_target", ""),
            "item_id": analysis.get("item_id", ""),
            "spell_id": analysis.get("spell_id", ""),
            "action_spell": analysis.get("spell_id", ""),
        },
        "is_probing_secret": analysis.get("is_probing_secret", False),
        "active_dialogue_target": next_dialogue_target,
    }

    current_flags = dict(state.get("flags", {}))
    flags_changed = analysis.get("flags_changed", {})
    if isinstance(flags_changed, dict) and flags_changed:
        current_flags.update(flags_changed)
        out["flags"] = current_flags
        out["journal_events"] = out.get("journal_events", []) + [
            f"📜 [系统] 剧情世界线已变动: {list(flags_changed.keys())}"
        ]

    # -------------------------------------------------------------------------
    # [V2] 已剥夺 DM 的物理执行权：物品流转与 HP 变动全部由 generation_node 的工具调用完成
    # DM 只负责意图提取、DC 设定和好感度变动，不再调用 apply_physics
    # -------------------------------------------------------------------------
    # item_transfers = analysis.get("item_transfers", [])
    # hp_changes = analysis.get("hp_changes", [])
    # if not isinstance(item_transfers, list):
    #     item_transfers = []
    # if not isinstance(hp_changes, list):
    #     hp_changes = []
    # if item_transfers or hp_changes:
    #     player_inv = dict(state.get("player_inventory", {}))
    #     current_entities = dict(out["entities"])
    #     new_events = apply_physics(current_entities, player_inv, item_transfers, hp_changes)
    #     out["journal_events"] = out.get("journal_events", []) + new_events
    #     out["entities"] = current_entities
    #     if any(t.get("from") == "player" or t.get("to") == "player" for t in item_transfers if isinstance(t, dict)):
    #         out["player_inventory"] = player_inv

    return out


def advance_speaker_node(state: GameState) -> dict:
    """从 speaker_queue 弹出下一位，设为 current_speaker，实现多人连续发言。"""
    queue = list(state.get("speaker_queue", []))
    if not queue:
        return {}
    next_speaker = queue[0]
    remaining = queue[1:]
    return {"current_speaker": next_speaker, "speaker_queue": remaining}


def narration_node(state: GameState) -> dict:
    """
    DM 旁白节点 (V3): 负责渲染客观环境、动作结果，不再由 NPC 强行抢戏。
    使用 LLM 生成客观旁白，并严格锚定机制结果（掷骰 / DC / 成败）。
    """
    print("🎙️ [路由追踪] 进入 DM 旁白节点 (Narration Node)")

    latest_roll = state.get("latest_roll", {})
    roll_result = latest_roll.get("result", {}) if isinstance(latest_roll, dict) else {}
    intent = str((latest_roll or {}).get("intent", state.get("intent", "action"))).lower()
    dc = (latest_roll or {}).get("dc", "?")
    total = roll_result.get("total", "?") if isinstance(roll_result, dict) else "?"
    is_success = bool(roll_result.get("is_success", False)) if isinstance(roll_result, dict) else False
    rolls = roll_result.get("rolls", []) if isinstance(roll_result, dict) else []
    rolls_text = str(rolls if isinstance(rolls, list) and rolls else [roll_result.get("raw_roll", "?")])

    user_input = (state.get("user_input", "") or "").strip()
    time_of_day = state.get("time_of_day", "未知时段")
    journal_tail = list(state.get("journal_events", []))[-3:]
    journal_text = "\n".join(journal_tail) if journal_tail else "无"
    outcome = "成功" if is_success else "失败"

    system_prompt = (
        "你是桌游主持人 DM。请根据给定事实输出一段中文旁白，必须客观、简洁、具体。\n"
        "硬性规则：\n"
        "1) 只能依据已给事实，不得杜撰新道具/新人物/新结果。\n"
        "2) 必须与检定结果一致（成功就给有效发现或推进；失败就给受阻或无收获）。\n"
        "3) 输出 1-2 句，不要加前缀标签，不要输出思维过程。\n"
        f"时间：{time_of_day}\n"
        f"动作意图：{intent}\n"
        f"玩家输入：{user_input or '（无）'}\n"
        f"检定：Roll {rolls_text} -> Total {total} vs DC {dc}，结果：{outcome}\n"
        f"最近系统日志：\n{journal_text}\n"
    )

    fallback_text = (
        "你谨慎地检查了周围，线索逐渐浮出水面。"
        if is_success
        else "你反复确认了周围情况，但这次没有得到有价值的发现。"
    )
    try:
        raw_response = generate_dialogue(
            system_prompt,
            conversation_history=[{"role": "user", "content": user_input or "继续"}],
        )
        parsed = parse_ai_response(raw_response)
        narration_text = (parsed.get("text") or "").strip() or fallback_text
    except Exception:
        narration_text = fallback_text

    attributed_msg = format_history_message("DM", narration_text)

    return {
        "messages": [AIMessage(content=attributed_msg, name="DM")],
        "final_response": narration_text,
    }
