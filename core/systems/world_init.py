"""
空存档创世：统一生成初始世界状态，供 CLI (main) 与 API (server) 复用。
"""

import copy
import json
import os
from typing import Any, Dict

from core.graph.nodes.utils import default_entities
from core.systems.maps import get_map_data


def _build_initial_entities() -> Dict[str, Any]:
    """
    基于默认实体表构建初始场景实体，并确保战斗测试怪物存在。
    """
    entities = copy.deepcopy(default_entities)
    entities.setdefault(
        "player",
        {
            "name": "玩家",
            "faction": "player",
            "ability_scores": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
            "speed": 30,
            "hp": 20,
            "max_hp": 20,
            "ac": 10,
            "status": "alive",
            "inventory": {},
            "equipment": {"main_hand": None, "ranged": None, "armor": None},
            "position": "camp_center",
            "x": 4,
            "y": 9,
            "active_buffs": [],
            "affection": 0,
        },
    )
    entities.setdefault(
        "goblin_1",
        {
            "name": "地精巡逻兵",
            "faction": "hostile",
            "ability_scores": {"STR": 8, "DEX": 14, "CON": 10, "INT": 10, "WIS": 8, "CHA": 8},
            "speed": 30,
            "hp": 7,
            "max_hp": 7,
            "ac": 15,
            "status": "alive",
            "inventory": {
                "gold_coin": 5,
                "scimitar": 1,
            },
            "equipment": {"main_hand": None, "ranged": None, "armor": None},
            "position": "camp_center",
            "x": 4,
            "y": 3,
            "active_buffs": [],
            "affection": 0,
        },
    )
    astarion = entities.get("astarion")
    if isinstance(astarion, dict):
        equipment = astarion.setdefault("equipment", {})
        if isinstance(equipment, dict):
            if not equipment.get("main_hand"):
                equipment["main_hand"] = "rusty_dagger"
            if not equipment.get("ranged"):
                equipment["ranged"] = "shortbow"
            equipment.setdefault("armor", None)
    return entities


def get_initial_world_state() -> Dict[str, Any]:
    """
    生成一个全新的、初始化的游戏世界状态（空存档创世）。
    """
    print("🌱 检测到空存档，正在生成初始世界状态...")

    # 尝试加载玩家本地背包
    init_player_inv: Dict[str, Any] = {"healing_potion": 2}
    if os.path.exists("data/player.json"):
        try:
            with open("data/player.json", "r", encoding="utf-8") as f:
                p_data = json.load(f)
                inv = p_data.get("inventory", init_player_inv)
                init_player_inv = dict(inv) if isinstance(inv, dict) else init_player_inv
        except Exception as e:
            print(f"⚠️ 无法读取 player.json，使用默认背包: {e}")

    # 构建并返回完整的初始状态字典
    map_data = get_map_data("goblin_camp")
    return {
        "entities": _build_initial_entities(),
        "map_data": map_data,
        "player_inventory": init_player_inv,
        "turn_count": 0,
        "combat_active": False,
        "initiative_order": [],
        "current_turn_index": 0,
        "turn_resources": {},
        "time_of_day": "晨曦 (Morning)",
        "flags": {},
        "messages": [],
        "journal_events": [],
        "current_location": "幽暗地域营地 (Underdark Camp)",
        "environment_objects": {
            "camp_center": {
                "name": "营地中央",
                "status": "open",
                "description": "开阔的聚落中心，可作为语义地标 (Semantic Waypoint)。",
                "x": 4,
                "y": 5,
            },
            "camp_fire": {
                "name": "篝火",
                "status": "burning",
                "description": "燃烧着的篝火，靠近可取暖。",
                "x": 4,
                "y": 6,
            },
            "iron_chest": {
                "name": "沉重的铁箱子",
                "status": "locked",
                "description": "一个上了锁的铁箱子，看起来很结实。(DC 15)",
                "inventory": {
                    "gold_coin": 50,
                    "rusty_dagger": 1,
                    "burnt_map": 1,
                },
                "x": 6,
                "y": 2,
            },
        },
    }
