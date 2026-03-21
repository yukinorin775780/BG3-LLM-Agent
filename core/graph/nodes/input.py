"""
Input / World Tick 节点：斜杠命令与世界心跳。
"""

import copy

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from core.graph.graph_state import GameState
from core.graph.nodes.utils import FACTORY_DEFAULT, _entity_snapshot, default_entities, first_entity_id
from core.systems import mechanics
from core.systems.inventory import get_registry


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

    # --- /GIVE <item> [target] ---
    if command == "/give" and len(parts) > 1:
        item_key = parts[1]
        fallback_target = first_entity_id(entities)
        target = parts[2] if len(parts) >= 3 else fallback_target
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
        response_text = (
            f"[SYSTEM] You don't have {item_key}."
            if player_inv.get(item_key, 0) <= 0
            else f"[SYSTEM] 找不到目标: {target}"
        )
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
        current_messages = state.get("messages", [])
        delete_msgs = []
        for m in current_messages:
            mid = m.get("id") if isinstance(m, dict) else (getattr(m, "id", None) if hasattr(m, "id") else None)
            if mid:
                delete_msgs.append(RemoveMessage(id=mid))
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
            if target in entities_copy:
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
            response_text = f"[SYSTEM] 找不到目标实体: {target}"
            return {
                "player_inventory": player_inv,
                "intent": "command_failed",
                "final_response": response_text,
                "is_probing_secret": False,
            }

        item_data = get_registry().get(item_id)
        effect = mechanics.apply_item_effect(item_id, item_data)
        focus_speaker = (state.get("current_speaker") or "").strip() or first_entity_id(entities)
        return {
            "player_inventory": new_p,
            "speaker_queue": [],
            "current_speaker": focus_speaker,
            "speaker_responses": [],
            "journal_events": [f"Player used {item_id}: {effect['message']}"],
            "final_response": f"[SYSTEM] You used {item_id}: {effect['message']}",
            "intent": "item_used",
            "is_probing_secret": False,
            "messages": [
                HumanMessage(content=user_input),
                AIMessage(content=f"[SYSTEM] You used {item_id}: {effect['message']}"),
            ],
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

    response_text = "[SYSTEM] Unknown command."
    return {
        "final_response": response_text,
        "intent": "command_done",
        "is_probing_secret": False,
        "messages": [HumanMessage(content=user_input), AIMessage(content=response_text)],
    }


def world_tick_node(state: dict) -> dict:
    """世界心跳节点：推进回合数，遍历所有实体结算状态效果"""
    from ui.renderer import GameRenderer

    ui = GameRenderer()
    current_turn = state.get("turn_count", 0) + 1

    time_cycles = ["晨曦 (Morning)", "正午 (Noon)", "黄昏 (Dusk)", "深夜 (Night)"]
    new_time = time_cycles[(current_turn // 3) % 4]
    ui.print_system_info(f"⏳ [World Tick] 回合推进至 {current_turn} | 当前时间: {new_time}")

    entities_in = state.get("entities") or copy.deepcopy(default_entities)
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
                    ui.print_system_info(
                        f"🩸 [Status] {entity_id} 因 {b_id} 受到 {actual_damage} 点伤害！剩余 HP: {current_hp}"
                    )
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
            entity_data["inventory"] = {
                x.get("id", ""): x.get("count", 0) for x in entity_data["inventory"] if x.get("id")
            }
        entities_out[entity_id] = entity_data

    return {
        "turn_count": current_turn,
        "time_of_day": new_time,
        "entities": entities_out,
    }
