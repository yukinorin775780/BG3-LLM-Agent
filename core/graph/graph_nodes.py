"""
LangGraph 节点：Input / DM / Mechanics / Generation

叙事工程师实践：逻辑解耦与单一职责
- 每个节点只返回「需要修改的字段」，由 Graph 的 Reducer 自动合并
- 避免节点内手动 copy/append，信任 LangGraph 的状态管理
"""

import copy
import os
import re
from typing import Callable, Dict, Any
import yaml
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from core.graph.graph_state import GameState
from core.llm.dm import analyze_intent
from core.systems import mechanics
from core.systems.inventory import get_registry, format_inventory_dict_to_display_list


def _build_item_lore(state: Any) -> str:
    """收集场上所有物品并生成 LLM 可用的物品知识库文本"""
    registry = get_registry()
    known_items = set()
    entities = state.get("entities", {})
    for ent in entities.values():
        inv = ent.get("inventory", {})
        if isinstance(inv, list):
            for item in inv:
                if isinstance(item, dict) and item.get("id"):
                    known_items.add(item["id"])
                elif isinstance(item, str):
                    known_items.add(item)
        else:
            for item_id in (inv or {}).keys():
                known_items.add(item_id)
    player_inv = state.get("player_inventory", {})
    if isinstance(player_inv, dict):
        known_items.update(player_inv.keys())
    if not known_items:
        return ""
    item_lore = "\n\n[CRITICAL KNOWLEDGE: ITEM DATABASE]\nHere is the real data for the items currently in the game. Use their translated names and respect their effects/descriptions:\n"
    for item_id in known_items:
        data = registry.get(item_id)
        item_lore += f"- ID: {item_id} | Name: {data.get('name')} | Desc: {data.get('description')} | Effect: {data.get('effect', 'None')}\n"
    return item_lore
from config import settings
from langchain_openai import ChatOpenAI
from core.engine import generate_dialogue, parse_ai_response
from core.engine.physics import apply_physics
from core.tools.npc_tools import check_target_inventory, execute_physical_action
from core.utils.text_processor import clean_npc_dialogue, format_history_message, parse_llm_json

# 全局开关：设为 True 时打印发给大模型的 Payload（调试用）
DEBUG_AI_PAYLOAD = False

# =============================================================================
# Node 1: Input 输入处理
# =============================================================================


def _entity_snapshot(v: Dict[str, Any]) -> Dict[str, Any]:
    """
    从实体数据提取快照，保留 hp/affection/inventory 及三维状态机字段（shar_faith, memory_awakening）。
    确保 LangGraph 状态持久化时，影心的 Persona 状态机数值不丢失。
    """
    out: Dict[str, Any] = {
        "hp": v.get("hp", 20),
        "active_buffs": list(v.get("active_buffs", [])),
        "affection": v.get("affection", 0),
        "inventory": dict(v.get("inventory", {})),
    }
    if "shar_faith" in v:
        out["shar_faith"] = v["shar_faith"]
    if "memory_awakening" in v:
        out["memory_awakening"] = v["memory_awakening"]
    return out


def _parse_inventory(inv_raw: Any) -> Dict[str, int]:
    """
    智能解析背包：兼容「纯字符串」和「字典」两种格式。
    - 纯字符串: ["healing_potion", "mysterious_artifact"] -> 每项 count=1
    - 字典: [{id: "healing_potion", count: 2}] -> 按 id/count 解析
    """
    inv_dict: Dict[str, int] = {}
    if not isinstance(inv_raw, list):
        return inv_dict
    for item in inv_raw:
        if isinstance(item, str):
            inv_dict[item] = inv_dict.get(item, 0) + 1
        elif isinstance(item, dict):
            iid = item.get("id")
            cnt = item.get("count", 1)
            if iid:
                inv_dict[iid] = inv_dict.get(iid, 0) + cnt
    return inv_dict


def load_default_entities() -> Dict[str, Dict[str, Any]]:
    """
    从 characters/*.yaml 动态加载所有角色的出厂初始状态（Data-Driven Design）。
    返回 {entity_id: {hp, active_buffs, affection, inventory}}。
    """
    chars_dir = os.path.join(os.path.dirname(__file__), "..", "..", "characters")
    entities: Dict[str, Dict[str, Any]] = {}
    for fname in sorted(os.listdir(chars_dir) if os.path.isdir(chars_dir) else []):
        if not fname.endswith(".yaml"):
            continue
        entity_id = fname[:-5]
        yaml_path = os.path.join(chars_dir, fname)
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            data = data or {}
            base = data.get("base_stats") or {}
            inv_raw = data.get("inventory") or []
            inv_dict = _parse_inventory(inv_raw)
            entity_data: Dict[str, Any] = {
                "hp": base.get("hp", 20),
                "active_buffs": [],
                "affection": base.get("affection", 0),
                "inventory": inv_dict,
            }
            # 三维状态机：从 YAML base_stats 注入 shar_faith / memory_awakening（仅影心等配置了该字段的角色）
            if "shar_faith" in base:
                entity_data["shar_faith"] = base["shar_faith"]
            if "memory_awakening" in base:
                entity_data["memory_awakening"] = base["memory_awakening"]
            entities[entity_id] = entity_data
        except Exception:
            entities[entity_id] = {"hp": 20, "active_buffs": [], "affection": 0, "inventory": {}}
    return entities


# 模块加载时构建默认实体（从 YAML 驱动）
default_entities = load_default_entities()

# 世界级出厂默认（角色无关）
FACTORY_DEFAULT = {
    "player_inventory": {"healing_potion": 2},
    "turn_count": 0,
    "time_of_day": "晨曦 (Morning)",
    "flags": {},
}


def input_node(state: GameState) -> dict:
    """
    处理斜杠命令（/give, /use, /add, /reset 等）。
    
    解耦原则：直接返回需要修改的字段，不手动合并。
    - player_inventory / entities: 返回完整新 dict，Graph 覆盖
    - journal_events: 返回 [新事件]，merge_events Reducer 自动累加
    """
    user_input = state.get("user_input", "").strip()
    entities = state.get("entities") or copy.deepcopy(default_entities)
    base = {
        "intent": "pending",
        "speaker_queue": [],
        "current_speaker": "",
        "speaker_responses": [],
        "is_probing_secret": False,
        "turn_count": state.get("turn_count", 0),
        "time_of_day": state.get("time_of_day", "晨曦 (Morning)"),
        "entities": entities,
    }

    if not user_input:
        return base

    if not user_input.startswith("/"):
        return base

    parts = user_input.split()
    command = parts[0].lower()
    player_inv = state.get("player_inventory", {})
    npc_inv = state.get("npc_inventory", {})

    # --- /GIVE <item> [target] ---
    if command == "/give" and len(parts) > 1:
        item_key = parts[1]
        target = parts[2] if len(parts) >= 3 else "shadowheart"
        if player_inv.get(item_key, 0) > 0 and target in entities:
            new_p = dict(player_inv)
            new_p[item_key] = new_p[item_key] - 1
            if new_p[item_key] <= 0:
                del new_p[item_key]
            new_entities = {}
            for k, v in entities.items():
                new_entities[k] = _entity_snapshot(v)
            new_entities[target]["inventory"][item_key] = new_entities[target]["inventory"].get(item_key, 0) + 1
            new_entities[target]["affection"] = new_entities[target]["affection"] + 2
            response_text = f"[SYSTEM] You gave {item_key} to {target}."
            return {
                "player_inventory": new_p,
                "entities": new_entities,
                "speaker_queue": [],
                "current_speaker": target,
                "speaker_responses": [],
                "journal_events": [f"Player gave {item_key} to {target}."],
                "final_response": response_text,
                "intent": "gift_given",
                "is_probing_secret": False,
                "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
            }
        response_text = f"[SYSTEM] You don't have {item_key}." if player_inv.get(item_key, 0) <= 0 else f"[SYSTEM] 找不到目标: {target}"
        return {
            "final_response": response_text,
            "intent": "command_done",
            "is_probing_secret": False,
            "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
        }

    # --- /ADD <item_id> (开发者指令：刷物品) ---
    if command == "/add" and len(parts) >= 2:
        item_id = parts[1]
        new_p = dict(player_inv)
        new_p[item_id] = new_p.get(item_id, 0) + 1
        return {
            "player_inventory": new_p,
            "intent": "dev_command",
            "final_response": f"[SYSTEM] DevMode: 获得了 {item_id}。",
            "is_probing_secret": False,
        }

    # --- /RESET (开发者指令：世界重置) ---
    if command == "/reset":
        fresh_entities = copy.deepcopy(default_entities)
        # 核心修复：遍历当前所有历史记忆，生成 LangGraph 专属的删除指令
        current_messages = state.get("messages", [])
        delete_msgs = []
        for m in current_messages:
            mid = m.get("id") if isinstance(m, dict) else (getattr(m, "id", None) if hasattr(m, "id") else None)
            if mid:
                delete_msgs.append(RemoveMessage(id=mid))
        # 若 message 无 id，兜底使用 REMOVE_ALL_MESSAGES 清空
        if not delete_msgs:
            messages_update = [RemoveMessage(id=REMOVE_ALL_MESSAGES)]
        else:
            messages_update = delete_msgs
        return {
            "entities": fresh_entities,
            "player_inventory": dict(FACTORY_DEFAULT["player_inventory"]),
            "turn_count": 0,
            "time_of_day": "晨曦 (Morning)",
            "flags": dict(FACTORY_DEFAULT["flags"]),
            "messages": messages_update,
            "intent": "dev_command",
            "final_response": "[SYSTEM] 🌍 世界线已重置 (World Reset)。实体状态与历史记忆已全部归零。",
            "is_probing_secret": False,
        }

    # --- /WAIT (等待一回合) ---
    if command == "/wait":
        return {
            "intent": "system_wait",
            "final_response": "⏳ 时间流逝……周围静悄悄的。",
            "is_probing_secret": False,
        }

    # --- /BUFF <target> <status_id> <duration> <value> (开发者指令：加状态) ---
    if command == "/buff" and len(parts) >= 5:
        target = parts[1]
        buff_id = parts[2]
        duration = int(parts[3])
        value = int(parts[4])

        raw = state.get("entities") or entities
        entities_copy = {k: _entity_snapshot(v) for k, v in entities.items()}
        for k, v in raw.items():
            if k not in entities_copy:
                entities_copy[k] = {"hp": 20, "active_buffs": [], "affection": 0, "inventory": {}}
            entities_copy[k].update(_entity_snapshot(v))
        if target in entities_copy:
            new_buffs = list(entities_copy[target].get("active_buffs", []))
            new_buffs.append({"id": buff_id, "duration": duration, "value": value})
            entities_copy[target]["active_buffs"] = new_buffs
            response_text = f"[SYSTEM] DevMode: 给 {target} 施加状态 '{buff_id}'，持续 {duration} 回合。"
        else:
            response_text = f"[SYSTEM] 找不到目标实体: {target}"

        return {
            "entities": entities_copy,
            "intent": "dev_command",
            "final_response": response_text,
            "is_probing_secret": False,
        }

    # --- /USE <item_id> [target] (玩家动作：使用物品) ---
    if command == "/use" and len(parts) >= 2:
        item_id = parts[1]
        target = parts[2] if len(parts) >= 3 else "player"

        if player_inv.get(item_id, 0) <= 0:
            return {
                "intent": "command_failed",
                "final_response": f"[SYSTEM] 你的背包里没有 '{item_id}'。",
                "is_probing_secret": False,
            }

        new_p = dict(player_inv)
        new_p[item_id] = new_p[item_id] - 1
        if new_p[item_id] <= 0:
            del new_p[item_id]

        if item_id == "healing_potion":
            raw = state.get("entities") or entities
            entities_copy = {k: _entity_snapshot(v) for k, v in entities.items()}
            for k, v in raw.items():
                if k not in entities_copy:
                    entities_copy[k] = {"hp": 20, "active_buffs": [], "affection": 0, "inventory": {}}
                entities_copy[k].update(_entity_snapshot(v))
            if target == "player":
                return {
                    "player_inventory": new_p,
                    "intent": "item_used",
                    "messages": [HumanMessage(content="*你喝下了一瓶治疗药水。*")],
                    "final_response": "",
                    "is_probing_secret": False,
                }
            elif target in entities_copy:
                current_hp = entities_copy[target].get("hp", 20)
                entities_copy[target]["hp"] = min(20, current_hp + 10)
                action_msg = f"*你强行掰开 {target} 的嘴，灌下了治疗药水。生命值恢复了。*"
                return {
                    "entities": entities_copy,
                    "player_inventory": new_p,
                    "speaker_queue": [],
                    "current_speaker": target,
                    "speaker_responses": [],
                    "intent": "item_used",
                    "messages": [HumanMessage(content=action_msg)],
                    "final_response": "",
                    "is_probing_secret": False,
                }
            else:
                response_text = f"[SYSTEM] 找不到目标实体: {target}"
                return {
                    "player_inventory": player_inv,
                    "intent": "command_failed",
                    "final_response": response_text,
                    "is_probing_secret": False,
                }

        # 其他物品：走通用效果
        item_data = get_registry().get(item_id)
        effect = mechanics.apply_item_effect(item_id, item_data)
        return {
            "player_inventory": new_p,
            "speaker_queue": [],
            "current_speaker": "shadowheart",
            "speaker_responses": [],
            "journal_events": [f"Player used {item_id}: {effect['message']}"],
            "final_response": f"[SYSTEM] You used {item_id}: {effect['message']}",
            "intent": "item_used",
            "is_probing_secret": False,
            "messages": [HumanMessage(content=user_input), AIMessage(content=f"[SYSTEM] You used {item_id}: {effect['message']}")],
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
# Node 1.5: World Tick 世界心跳
# =============================================================================


def world_tick_node(state: dict) -> dict:
    """世界心跳节点：推进回合数，遍历所有实体结算状态效果"""
    from ui.renderer import GameRenderer

    ui = GameRenderer()
    current_turn = state.get("turn_count", 0) + 1

    time_cycles = ["晨曦 (Morning)", "正午 (Noon)", "黄昏 (Dusk)", "深夜 (Night)"]
    new_time = time_cycles[(current_turn // 3) % 4]
    ui.print_system_info(f"⏳ [World Tick] 回合推进至 {current_turn} | 当前时间: {new_time}")

    default_entities = {
        "shadowheart": {"hp": 20, "active_buffs": []},
        "astarion": {"hp": 20, "active_buffs": []},
    }
    entities_in = state.get("entities", default_entities) or {}
    entities_out = {}

    for entity_id, entity_data in entities_in.items():
        entity_data = dict(entity_data)
        current_hp = entity_data.get("hp", 20)
        buffs = list(entity_data.get("active_buffs", []))
        surviving_buffs = []

        for buff in buffs:
            b_id = buff["id"]
            b_val = buff.get("value", 0)

            if b_id in ["poisoned", "burning", "bleeding"]:
                old_hp = current_hp
                current_hp = max(0, current_hp - b_val)
                actual_damage = old_hp - current_hp
                if actual_damage > 0:
                    ui.print_system_info(f"🩸 [Status] {entity_id} 因 {b_id} 受到 {actual_damage} 点伤害！剩余 HP: {current_hp}")
            elif b_id in ["regeneration"]:
                current_hp = min(20, current_hp + b_val)
                ui.print_system_info(f"✨ [Status] {entity_id} 因 {b_id} 恢复 {b_val} 点生命！剩余 HP: {current_hp}")

            buff["duration"] -= 1
            if buff["duration"] > 0:
                surviving_buffs.append(buff)
            else:
                ui.print_system_info(f"💨 [Status] {entity_id} 的 {b_id} 状态已解除。")

        entity_data["hp"] = max(0, current_hp)
        entity_data["active_buffs"] = surviving_buffs
        entity_data.setdefault("affection", 0)
        entity_data.setdefault("inventory", {})
        if isinstance(entity_data.get("inventory"), list):
            entity_data["inventory"] = {x.get("id", ""): x.get("count", 0) for x in entity_data["inventory"] if x.get("id")}
        entities_out[entity_id] = entity_data

    return {
        "turn_count": current_turn,
        "time_of_day": new_time,
        "entities": entities_out,
    }


# =============================================================================
# Node 2: DM 意图分析
# =============================================================================


def dm_node(state: GameState) -> dict:
    """
    分析玩家输入的意图。
    若 intent 已被 Input 处理（command_done / gift_given / item_used），直接跳过。
    DM 派发多人发言队列，并结算好感度变化，渲染 BG3 风格提示。
    """
    if state.get("intent") in ["command_done", "gift_given", "item_used"]:
        return {}

    print("🎲 DM Node: Analyzing intent...")
    entities_raw = state.get("entities", {})
    entities = {k: dict(v) for k, v in entities_raw.items()}
    for k in entities:
        entities[k].setdefault("affection", 0)
        entities[k].setdefault("inventory", {})
        if not isinstance(entities[k].get("inventory"), dict):
            entities[k]["inventory"] = {}
    available_npcs = list(entities.keys()) if entities else ["shadowheart", "astarion"]
    current_npc_hp = entities.get("shadowheart", {}).get("hp", 20)
    item_lore = _build_item_lore(state)
    analysis = analyze_intent(
        state.get("user_input", ""),
        flags=state.get("flags", {}),
        time_of_day=state.get("time_of_day", "晨曦 (Morning)"),
        hp=current_npc_hp,
        available_npcs=available_npcs,
        item_lore=item_lore if item_lore else None,
    )

    # 好感度物理结算与 BG3 风格 UI 渲染
    affection_changes = analysis.get("affection_changes", {})
    _npc_name_cn = {"shadowheart": "影心", "astarion": "阿斯代伦"}
    from ui.renderer import GameRenderer
    ui = GameRenderer()
    for npc_id, change in affection_changes.items():
        npc_id = str(npc_id).strip().lower()
        if npc_id in entities and isinstance(change, (int, float)) and change != 0:
            current_aff = entities[npc_id].get("affection", 0)
            new_aff = max(-100, min(100, current_aff + int(change)))
            entities[npc_id]["affection"] = new_aff
            npc_name_cn = _npc_name_cn.get(npc_id, npc_id.capitalize())
            delta = int(change)
            if delta > 0:
                ui.print_system_info(f"💡 [bold green][ {npc_name_cn} 赞同 (Approves) {delta:+d} ][/bold green]")
            else:
                ui.print_system_info(f"💔 [bold red][ {npc_name_cn} 不赞同 (Disapproves) {delta:+d} ][/bold red]")

    queue = list(analysis.get("responders", ["shadowheart"]))
    current = queue.pop(0) if queue else "shadowheart"
    out = {
        "entities": entities,
        "speaker_queue": queue,
        "current_speaker": current,
        "speaker_responses": [],
        "intent": analysis.get("action_type", "CHAT"),
        "intent_context": {
            "difficulty_class": analysis.get("difficulty_class", 12),
            "reason": analysis.get("reason", ""),
        },
        "is_probing_secret": analysis.get("is_probing_secret", False),
    }

    # 提取并合并剧情状态 (Flags)
    current_flags = dict(state.get("flags", {}))
    flags_changed = analysis.get("flags_changed", {})
    if isinstance(flags_changed, dict) and flags_changed:
        current_flags.update(flags_changed)
        out["flags"] = current_flags
        out["journal_events"] = out.get("journal_events", []) + [f"📜 [系统] 剧情世界线已变动: {list(flags_changed.keys())}"]

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
    if "raw_roll_data" in result:
        out["latest_roll"] = result["raw_roll_data"]
    if result.get("relationship_delta", 0) != 0:
        entities = state.get("entities", {})
        speaker = state.get("current_speaker", "shadowheart")
        current_aff = (entities.get(speaker, {}) or {}).get("affection", 0)
        new_entities = {k: _entity_snapshot(v) for k, v in entities.items()}
        new_entities.setdefault(speaker, {"hp": 20, "active_buffs": [], "affection": 0, "inventory": {}})
        new_entities[speaker]["affection"] = current_aff + result["relationship_delta"]
        out["entities"] = new_entities
    return out


# =============================================================================
# Node 3.5: Narration DM 旁白 (V3)
# =============================================================================


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

    # 【关键】格式化为带标签的历史消息，必须通过 messages 传递，让后续 NPC 能看见
    attributed_msg = format_history_message("DM", narration_text)

    return {
        "messages": [AIMessage(content=attributed_msg, name="DM")],  # 触发 add_messages reducer 追加
        "final_response": narration_text,
        # 不覆盖 current_speaker，保留 dm 设定的 NPC，让 generation 接力发声
    }


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


def create_generation_node() -> Callable[[GameState], dict]:
    """
    工厂函数：创建 Generation 节点。
    根据 state["current_speaker"] 动态加载 YAML 灵魂，实现多智能体话语权路由。
    """

    def generation_node(state: GameState) -> dict:
        """
        LLM 生成节点。
        根据 current_speaker 动态加载对应角色，从 state 提取 relationship / flags / inventory 等。
        """
        from characters.loader import load_character

        speaker = state.get("current_speaker", "shadowheart") or "shadowheart"
        character = load_character(speaker)
        print(f"🗣️ Generation Node: {speaker.capitalize()} is speaking...")

        # 濒死拦截：当前 NPC HP <= 0 时不走 LLM
        entities = state.get("entities", {})
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
                    AIMessage(content=f"[SYSTEM] {char_display}已经倒在血泊中，失去了意识。你无法再与她交谈。"),
                ],
            }

        user_input = state.get("user_input", "")
        entities = state.get("entities", {})
        current_npc = entities.get(speaker, {})
        relationship = current_npc.get("affection", 0)
        flags = state.get("flags", {})
        npc_inv = current_npc.get("inventory", state.get("npc_inventory", {}))
        if not isinstance(npc_inv, dict):
            npc_inv = {}
        player_inv = state.get("player_inventory", {})
        journal_events = list(state.get("journal_events", []))
        summary = state.get("summary", "Graph Mode Testing")

        # -------------------------------------------------------------------------
        # 0. Banter 模式检测：紧接 DM 旁白后，使用极简模板节省 Token
        # -------------------------------------------------------------------------
        messages = list(state.get("messages", []))
        is_banter = False
        dm_text = ""
        if messages:
            last_msg = messages[-1]
            last_content = _msg_content(last_msg)
            last_name = getattr(last_msg, "name", None) or (last_msg.get("name") if isinstance(last_msg, dict) else None)
            if last_name == "DM" or (last_content and last_content.strip().startswith("[DM]:")):
                is_banter = True
                dm_text = last_content.replace("[DM]:", "").strip() if last_content else ""

        if is_banter and dm_text:
            print(f"💬 [Banter Mode] {speaker.capitalize()} 使用极简模板吐槽...")
            from jinja2 import Environment, FileSystemLoader
            _prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "llm", "prompts")
            _banter_env = Environment(loader=FileSystemLoader(_prompts_dir), trim_blocks=True, lstrip_blocks=True)
            banter_tpl = _banter_env.get_template("banter.j2")
            traits = character.data.get("personality", {}).get("traits", []) or []
            core_traits = ", ".join(str(t) for t in traits[:3]) if traits else "mysterious"
            system_prompt = banter_tpl.render(
                npc_name=character.data.get("name", speaker.capitalize()),
                core_traits=core_traits,
                approval=relationship,
                dm_text=dm_text,
            )
            history_dicts = [{"role": "user", "content": f"[DM]: {dm_text}"}]
            raw_response = generate_dialogue(system_prompt, conversation_history=history_dicts)
            parsed = parse_ai_response(raw_response)
            clean_text = clean_npc_dialogue(speaker, (parsed.get("text") or "...").strip())
            attributed_msg = format_history_message(speaker, clean_text)
            prev_responses = list(state.get("speaker_responses", []))
            return {
                "final_response": clean_text,
                "speaker_responses": prev_responses + [(speaker, clean_text)],
                "thought_process": "",
                "messages": [AIMessage(content=attributed_msg, name=speaker)],
            }

        # -------------------------------------------------------------------------
        # [V2] 已移除 YAML 正则触发器，物品流转完全由 LLM 工具调用 (execute_physical_action) 负责
        # -------------------------------------------------------------------------
        triggers_config = character.data.get("dialogue_triggers", [])
        trigger_result = {"journal_entries": [], "relationship_delta": 0}

        # -------------------------------------------------------------------------
        # 2. 背包感知：用 inventory 模块逻辑将 npc_inventory 转为易读字符串列表
        # -------------------------------------------------------------------------
        inventory_display_list = format_inventory_dict_to_display_list(npc_inv)

        # -------------------------------------------------------------------------
        # 3. 关键标志位：has_healing_potion 必须与背包事实一致，用于约束幻觉
        # -------------------------------------------------------------------------
        has_healing_potion = (npc_inv.get("healing_potion", 0) or 0) >= 1

        # -------------------------------------------------------------------------
        # 4. 注入提示词：把当前背包、标志位、时间、HP、Buff、三维状态机 传入 render_prompt。
        # 三维状态机：shar_faith（莎尔信仰度）、memory_awakening（记忆觉醒度），仅影心等角色有该字段。
        # -------------------------------------------------------------------------
        current_npc_data = entities.get(speaker, {})
        shar_faith = current_npc_data.get("shar_faith")  # 若不存在则为 None，模板不注入信仰/记忆逻辑
        memory_awakening = current_npc_data.get("memory_awakening")
        system_prompt = character.render_prompt(
            relationship_score=relationship,
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

        # 动态物品知识库注入 (Item Database Injection)
        item_lore = _build_item_lore(state)
        if item_lore:
            system_prompt += item_lore

        # messages 符合 add_messages：从 state 读取，转为 engine 所需格式（banter 模式已提前 return）
        messages = list(state.get("messages", []))
        if not messages or _msg_content(messages[-1]) != user_input:
            messages.append({"role": "user", "content": user_input})

        # 核心记忆机制：滑动窗口截断，只保留最近的 20 条对话记录，防止上下文核爆
        recent_messages = messages[-20:] if len(messages) > 20 else messages
        history_dicts = [_message_to_dict(m) for m in recent_messages]

        # 终极 Agent-to-Agent (A-to-A) 交叉辩论补丁
        prev_responses = list(state.get("speaker_responses", []))
        if len(prev_responses) > 0:
            first_speaker_id = prev_responses[0][0]
            last_speaker_id, last_speaker_text = prev_responses[-1]

            # 1. A-to-A 思想钢印：自然反应矩阵（同意/反驳/嘲讽/无视）
            system_prompt += f"\n\n[CRITICAL A-TO-A NOTE: You are part of a group conversation. The player just acted, and {last_speaker_id} reacted by saying: '{last_speaker_text}'.\nYOUR TASK: Evaluate {last_speaker_id}'s statement based on your personality.\n- If you STRONGLY DISAGREE, argue with them.\n- If you AGREE, support or build on their point.\n- If you think they are being ridiculous, MOCK them.\n- If the topic is TRIVIAL or you don't care, DO NOT SPEAK. Output ONLY a brief physical action (e.g., *rolls eyes*, *yawns*, *ignores them*).\nReact naturally. Address {last_speaker_id} directly if you choose to speak.]"

            # 2. 动作旁白重构：让大模型清晰感知到当前的对话焦点已经转移到了上一个 NPC 身上
            if history_dicts and history_dicts[-1]["role"] == "user":
                original_text = history_dicts[-1]["content"]
                history_dicts[-1]["content"] = f"[事件回顾] 玩家说：{original_text}\n[刚刚发生] {last_speaker_id} 回应道：{last_speaker_text}\n*(现在轮到你做出反应了)*"

        # 预构建 current_entities 与 player_inv_for_physics，供 ReAct 工具拦截器使用
        current_entities = {k: dict(v) for k, v in entities.items()}
        for k in current_entities:
            current_entities[k].setdefault("affection", 0)
            current_entities[k].setdefault("inventory", {})
            if not isinstance(current_entities[k].get("inventory"), dict):
                current_entities[k]["inventory"] = {}
        current_entities.setdefault(speaker, {"hp": 20, "active_buffs": [], "affection": 0, "inventory": {}})
        if user_input and triggers_config:
            current_entities[speaker]["inventory"] = dict(npc_inv)
            current_entities[speaker]["affection"] = relationship
        player_inv_for_physics = dict(player_inv)

        # 【近因效应】在 System Prompt 最末尾注入强约束，强制模型优先输出 tool_calls
        system_prompt += """

<CRITICAL_SYSTEM_RULES>
You are an AGENT operating in a stateful game world.
When the player attempts an action that interacts with the physical world (e.g., giving an item, moving, attacking), YOU MUST NOT JUST DESCRIBE IT.
You MUST output a tool_call (e.g., `check_target_inventory`).
DO NOT generate narrative text for item transfers until the tool returns a success status.

[CRITICAL DICE RULE]: Check the most recent [SYSTEM] or DM events. If a skill check resulted in "FAILURE", you MUST absolutely REFUSE the player's request or let their attempt fail miserably in your dialogue. DO NOT bypass the failure to help the player!
</CRITICAL_SYSTEM_RULES>
"""

        # 构建 LangChain 消息列表
        lc_messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        for d in history_dicts:
            if d.get("role") == "user":
                lc_messages.append(HumanMessage(content=d.get("content", "")))
            else:
                lc_messages.append(AIMessage(content=d.get("content", "")))

        # 绑定工具并调用 LLM
        llm = ChatOpenAI(
            model=settings.MODEL_NAME,
            api_key=settings.API_KEY, # type: ignore[arg-type]
            base_url=settings.BASE_URL,
            temperature=0.7,
            max_completion_tokens=500,
        )
        llm_with_tools = llm.bind_tools([check_target_inventory, execute_physical_action])

        # =====================================================================
        # 🚨 [DEBUG] 拦截大模型输入前的消息队列 (Messages X光机) 🚨
        # =====================================================================
        if DEBUG_AI_PAYLOAD:
            messages = lc_messages
            print("\n" + "🔥" * 25)
            print("🚨 正在打印发给大模型的最终 Payload...")
            print(f"📊 当前消息总数: {len(messages)} 条")
            for i, msg in enumerate(messages):
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
        # =====================================================================

        response = llm_with_tools.invoke(lc_messages)

        # ReAct 微循环：拦截 tool_calls -> 执行工具 -> 追加 ToolMessage -> 再次 invoke，直到无工具调用
        tool_physics_events = []
        MAX_ITERATIONS = 5  # 安全锁：防止幻觉导致无限工具调用
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

                elif tool_name == "execute_physical_action":
                    action_type = tool_args.get("action_type", "")
                    source_id = tool_args.get("source_id", "")
                    target_id = tool_args.get("target_id", "player")
                    item_id = tool_args.get("item_id", "")
                    amount = int(tool_args.get("amount", 1))

                    item_transfers = []
                    hp_changes = []
                    if action_type == "transfer_item":
                        item_transfers.append({"from": source_id, "to": target_id, "item_id": item_id, "count": amount})
                    elif action_type == "heal":
                        hp_changes.append({"target": target_id, "amount": amount, "reason": "healed"})
                    elif action_type == "damage":
                        hp_changes.append({"target": target_id, "amount": -amount, "reason": "damaged"})

                    new_events = apply_physics(current_entities, player_inv_for_physics, item_transfers, hp_changes)
                    journal_events.extend(new_events)
                    tool_physics_events.extend(new_events)
                    # 【关键修复】将物理引擎的真实反馈（哪怕是失败报错）原封不动地传回给大模型
                    if new_events:
                        tool_result_str = "\n".join(new_events)
                    else:
                        tool_result_str = "动作未产生任何效果。"

                tool_msg = ToolMessage(content=tool_result_str, tool_call_id=tc.get("id", ""))
                lc_messages.append(tool_msg)

            # 将工具执行结果喂给大模型，继续下一轮
            # =====================================================================
            # 🚨 [DEBUG] ReAct 第 N 轮：打印含 ToolMessage 的 Payload
            # =====================================================================
            if DEBUG_AI_PAYLOAD:
                messages = lc_messages
                print("\n" + "🔥" * 25)
                print(f"🚨 [ReAct 第 {iteration_count} 轮] 正在打印发给大模型的 Payload (含工具返回)...")
                print(f"📊 当前消息总数: {len(messages)} 条")
                for i, msg in enumerate(messages):
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
            # =====================================================================

            response = llm_with_tools.invoke(lc_messages)

            # 安全拦截：超过最大迭代次数强制跳出
            if iteration_count >= MAX_ITERATIONS:
                print("⚠️ [安全拦截] Agent 内部工具调用次数超限 (>=5次)，强制终止循环！")
                break

        # 兜底：若最后一次 response 仍只有 tool_calls 而无文本，塞入默认回复
        if getattr(response, "tool_calls", None) and not (getattr(response, "content", None) or "").strip():
            response = AIMessage(content="*（陷入了深深的沉思，暂时没有回应）*")

        raw_output = str(response.content if hasattr(response, "content") else str(response or ""))

        # -------------------------------------------------------------------------
        # 结构化 JSON 解析：优先尝试解析三维状态机输出（reply + internal_monologue + state_changes）
        # 解析失败时回退到旧版 parse_ai_response（正则解析 [THOUGHT]/[APPROVAL] 等）
        # -------------------------------------------------------------------------
        json_parsed = parse_llm_json(raw_output)
        if isinstance(json_parsed, dict) and "reply" in json_parsed:
            # 成功解析 JSON：提取 reply 作为台词，internal_monologue 作为内心独白
            raw_text = (json_parsed.get("reply") or "...").strip()
            thought_process = (json_parsed.get("internal_monologue") or "").strip()
            state_changes = json_parsed.get("state_changes") or {}
        else:
            # 回退：旧版正则解析（兼容 Banter 或 LLM 未按 JSON 输出时）
            parsed = parse_ai_response(raw_output)
            raw_text = (parsed.get("text") or raw_output or "...").strip()
            thought_process = (parsed.get("thought") or "").strip()
            # 旧版 approval 映射为 affection_delta
            state_changes = {"affection_delta": parsed.get("approval", 0), "shar_faith_delta": 0, "memory_awakening_delta": 0}

        clean_text = clean_npc_dialogue(speaker, raw_text)
        attributed_msg = format_history_message(speaker, clean_text)

        # -------------------------------------------------------------------------
        # 状态机流转：将 state_changes 写回 current_entities[speaker]，实现三维数值持久化
        # LangGraph 状态不灭，更新后的实体会在下一回合被 DM/Mechanics 等节点读取
        # -------------------------------------------------------------------------
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

        # 合并触发器产生的剧情事件到 journal，并写回 flags/背包/好感度
        prev_responses = list(state.get("speaker_responses", []))
        out = {
            "final_response": clean_text,
            "speaker_responses": prev_responses + [(speaker, clean_text)],
            "thought_process": thought_process,
            "messages": [HumanMessage(content=user_input), AIMessage(content=attributed_msg, name=speaker)],
        }
        if state_changes_applied:
            out["entities"] = current_entities  # 状态机更新必须写回，供后续回合持久化
        trigger_journal = trigger_result.get("journal_entries", [])
        if trigger_journal:
            out["journal_events"] = trigger_journal
        if tool_physics_events:
            out["journal_events"] = out.get("journal_events", []) + tool_physics_events
        if tool_physics_events:
            out["entities"] = current_entities
            out["player_inventory"] = player_inv_for_physics
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
