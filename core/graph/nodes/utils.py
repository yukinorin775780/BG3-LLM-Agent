"""
LangGraph 节点共享工具：实体快照、默认实体加载、消息转换、物品知识库等。
"""

from typing import Any, Dict

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
            inv_raw = data.get("inventory") or []
            inv_dict = _parse_inventory(inv_raw)
            entity_data: Dict[str, Any] = {
                "hp": base.get("hp", 20),
                "active_buffs": [],
                "affection": base.get("affection", 0),
                "inventory": inv_dict,
            }
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
