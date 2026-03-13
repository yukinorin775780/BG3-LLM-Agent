"""
物理引擎：物品流转与生命值变动的底层结算。
V3 架构：从 dm_node 抽离，单一职责。
"""

from typing import Dict, List, Any

from core.systems.inventory import get_registry


def apply_physics(
    current_entities: dict,
    player_inventory: dict,
    item_transfers: list,
    hp_changes: list,
) -> List[str]:
    """
    处理实体的物理结算，包括物品转移、消耗、环境掉落以及生命值变动。
    直接修改传入的 current_entities 与 player_inventory 字典。
    返回产生的 journal_events 列表。
    """
    journal_events: List[str] = []
    registry = get_registry()

    # 1. 处理物品转移 (Item Transfers)
    for transfer in item_transfers:
        if not isinstance(transfer, dict):
            continue
        src = transfer.get("from", "player")
        dst = transfer.get("to")
        item_id = transfer.get("item_id")
        count = int(transfer.get("count", 1))

        if not item_id or count <= 0:
            continue

        # --- 世界掉落 (World Drop) 逻辑 ---
        if src == "world" and dst and count > 0:
            item_name = registry.get_name(item_id)
            if dst == "player":
                player_inventory[item_id] = player_inventory.get(item_id, 0) + count
                journal_events.append(f"✨ [环境发现] {dst} 获得了 {count}x {item_name}")
            elif dst in current_entities:
                dst_inv = current_entities[dst].setdefault("inventory", {})
                if not isinstance(dst_inv, dict):
                    dst_inv = {}
                    current_entities[dst]["inventory"] = dst_inv
                dst_inv[item_id] = dst_inv.get(item_id, 0) + count
                journal_events.append(f"✨ [环境发现] {dst} 获得了 {count}x {item_name}")
            continue
        # ------------------------------------------

        # 获取源背包（player 用 player_inventory，NPC 用 entities）
        src_inv: Dict[str, int] = {}
        if src == "player":
            src_inv = player_inventory
        elif src in current_entities:
            inv = current_entities[src].setdefault("inventory", {})
            if not isinstance(inv, dict):
                inv = {}
                current_entities[src]["inventory"] = inv
            src_inv = inv
        else:
            continue

        item_name = registry.get_name(item_id)
        has_enough = src_inv.get(item_id, 0) >= count

        if has_enough:
            # 1. 扣除来源物品
            src_inv[item_id] = src_inv.get(item_id, 0) - count
            if src_inv[item_id] <= 0:
                del src_inv[item_id]

            # 2. 增加目标物品（若不是被消耗）
            if dst == "consumed":
                journal_events.append(f"💥 [物品消耗] {src} 使用了 {count}x {item_name}")
            elif dst == "player":
                player_inventory[item_id] = player_inventory.get(item_id, 0) + count
                journal_events.append(f"📦 [物品流转] {src} 将 {count}x {item_name} 交给了 {dst}")
            elif dst in current_entities:
                dst_inv = current_entities[dst].setdefault("inventory", {})
                if not isinstance(dst_inv, dict):
                    dst_inv = {}
                    current_entities[dst]["inventory"] = dst_inv
                dst_inv[item_id] = dst_inv.get(item_id, 0) + count
                journal_events.append(f"📦 [物品流转] {src} 将 {count}x {item_name} 交给了 {dst}")
            else:
                journal_events.append(f"❌ [动作失败] 无效的目标: {dst}")
        else:
            journal_events.append(f"❌ [动作失败] {src} 并没有足够的 {item_name}！")

    # 2. 处理生命值变动 (HP Changes)
    for change in hp_changes:
        if not isinstance(change, dict):
            continue
        target = change.get("target")
        amount = int(change.get("amount", 0))
        if not target or amount == 0:
            continue
        # 支持 player：若不在 entities 中则创建
        if target == "player" and target not in current_entities:
            current_entities["player"] = {
                "hp": 20,
                "max_hp": 20,
                "affection": 0,
                "inventory": {},
                "active_buffs": [],
            }
        if target not in current_entities:
            continue
        ent = current_entities[target]
        current_hp = ent.get("hp", 20)
        base_stats = ent.get("base_stats") or {}
        max_hp = ent.get("max_hp", base_stats.get("hp", 20))
        new_hp = max(0, min(current_hp + amount, max_hp))
        ent["hp"] = new_hp
        action_word = "恢复了" if amount > 0 else "失去了"
        color_icon = "💚" if amount > 0 else "🩸"
        journal_events.append(
            f"{color_icon} [状态变动] {target} {action_word} {abs(amount)} 点 HP (当前: {new_hp}/{max_hp})"
        )

    return journal_events
