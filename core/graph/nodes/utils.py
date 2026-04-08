"""
LangGraph 节点共享工具：实体快照、默认实体加载、消息转换、物品知识库等。
"""

import copy
from typing import Any, Dict, Optional

import os
import yaml

from core.systems.inventory import get_registry


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
    item_lore = (
        "\n\n[CRITICAL KNOWLEDGE: ITEM DATABASE]\n"
        "Here is the real data for the items currently in the game. "
        "Use their translated names and respect their effects/descriptions:\n"
    )
    for item_id in known_items:
        data = registry.get(item_id)
        item_lore += (
            f"- ID: {item_id} | Name: {data.get('name')} | "
            f"Desc: {data.get('description')} | Effect: {data.get('effect', 'None')}\n"
        )
    return item_lore


def _entity_snapshot(v: Dict[str, Any]) -> Dict[str, Any]:
    """
    从实体数据提取快照，保留 hp/affection/inventory 及三维状态机字段（shar_faith, memory_awakening）。
    确保 LangGraph 状态持久化时，各角色 Persona 状态机数值不丢失。
    """
    out: Dict[str, Any] = {
        "name": v.get("name", ""),
        "faction": v.get("faction", "neutral"),
        "hp": v.get("hp", 20),
        "max_hp": v.get("max_hp", v.get("hp", 20)),
        "ac": v.get("ac", 10),
        "status": v.get("status", "alive"),
        "active_buffs": list(v.get("active_buffs", [])),
        "affection": v.get("affection", 0),
        "inventory": dict(v.get("inventory", {})),
        "position": v.get("position", "camp_center"),
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
    返回 {entity_id: {hp, active_buffs, affection, inventory, position, ...}}。
    """
    # core/graph/nodes/utils.py -> 项目根目录需向上三级
    chars_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "characters")
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
            combat = data.get("combat") or {}
            inv_raw = data.get("inventory") or []
            inv_dict = _parse_inventory(inv_raw)
            max_hp = base.get("max_hp", base.get("hp", combat.get("hit_points", 20)))
            entity_data: Dict[str, Any] = {
                "name": data.get("name", entity_id.replace("_", " ").title()),
                "faction": base.get("faction", "neutral"),
                "hp": base.get("hp", max_hp),
                "max_hp": max_hp,
                "ac": base.get("ac", combat.get("armor_class", 10)),
                "status": base.get("status", "alive"),
                "active_buffs": [],
                "affection": base.get("affection", 0),
                "inventory": inv_dict,
                "position": base.get("position", "camp_center"),
            }
            if "shar_faith" in base:
                entity_data["shar_faith"] = base["shar_faith"]
            if "memory_awakening" in base:
                entity_data["memory_awakening"] = base["memory_awakening"]
            entities[entity_id] = entity_data
        except Exception:
            entities[entity_id] = {
                "name": entity_id.replace("_", " ").title(),
                "faction": "neutral",
                "hp": 20,
                "max_hp": 20,
                "ac": 10,
                "status": "alive",
                "active_buffs": [],
                "affection": 0,
                "inventory": {},
                "position": "camp_center",
            }
    return entities


# 模块加载时构建默认实体（从 YAML 驱动）
default_entities = load_default_entities()


def merge_entities_with_defaults(raw_entities: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    与 input_node 一致：把 characters/*.yaml 中尚未出现在存档里的 NPC 补进 entities，
    避免多智能体路由下某轮只有部分 key 时，下游误用「缺键→0 好感」的假数据。
    """
    if not raw_entities:
        entities = copy.deepcopy(default_entities)
    else:
        entities = copy.deepcopy(raw_entities)
    if not isinstance(entities, dict):
        return copy.deepcopy(default_entities)
    for npc_id, default_data in default_entities.items():
        if npc_id not in entities:
            entities[npc_id] = copy.deepcopy(default_data)
    # 旧存档缺战斗字段时补默认值，避免 UI 与 mechanics 在旧状态上缺关键键。
    for npc_id, ent in list(entities.items()):
        if not isinstance(ent, dict):
            continue
        defaults = default_entities.get(npc_id, {})
        ent.setdefault("name", defaults.get("name", npc_id.replace("_", " ").title()))
        ent.setdefault("faction", defaults.get("faction", "neutral"))
        ent.setdefault("max_hp", defaults.get("max_hp", ent.get("hp", 20)))
        ent.setdefault("ac", defaults.get("ac", 10))
        ent.setdefault("status", defaults.get("status", "alive"))
        ent.setdefault("position", defaults.get("position", "camp_center"))
        ent.setdefault("active_buffs", [])
        ent.setdefault("inventory", {})
    return entities


def overlay_entity_state(state_entities: Optional[Dict[str, Any]], node_entities: Dict[str, Any]) -> Dict[str, Any]:
    """
    以进入本节点时的 state.entities 为基准（含 DM 刚写入的好感度），再叠加本节点算出的变更。
    仅覆盖 node_entities 中出现的 NPC id，避免本节点漏拷贝其它角色导致好感度被「冲掉」。
    """
    out: Dict[str, Any] = {}
    for k, v in (state_entities or {}).items():
        if isinstance(v, dict):
            out[k] = copy.deepcopy(v)
    for k, v in (node_entities or {}).items():
        if isinstance(v, dict):
            out[k] = copy.deepcopy(v)
    return out

# 世界级出厂默认（角色无关）
FACTORY_DEFAULT = {
    "player_inventory": {"healing_potion": 2},
    "turn_count": 0,
    "time_of_day": "晨曦 (Morning)",
    "flags": {},
}


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


def first_entity_id(entities: Any) -> str:
    """
    当未设置 current_speaker 时的软回退：取 entities 的第一个 key（插入顺序）。
    空字典返回 \"unknown\".
    """
    if not isinstance(entities, dict) or not entities:
        return "unknown"
    return next(iter(entities.keys()))


def entity_display_name(entity_id: str) -> str:
    """从 characters/<id>.yaml 的 name 字段读取展示名；若无文件则格式化 id。"""
    eid = (entity_id or "").strip()
    if not eid or eid == "unknown":
        return eid or "unknown"
    try:
        from characters.loader import CharacterLoader

        data = CharacterLoader().load_character(eid)
        if isinstance(data, dict) and data.get("name"):
            return str(data["name"])
    except (FileNotFoundError, OSError, ValueError, TypeError, KeyError):
        pass
    return eid.replace("_", " ").strip().title() or "unknown"
