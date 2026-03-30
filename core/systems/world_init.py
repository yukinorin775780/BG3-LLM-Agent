"""
空存档创世：统一生成初始世界状态，供 CLI (main) 与 API (server) 复用。
"""

import copy
import json
import os
from typing import Any, Dict

from core.graph.nodes.utils import default_entities


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
    return {
        "entities": copy.deepcopy(default_entities),
        "player_inventory": init_player_inv,
        "turn_count": 0,
        "time_of_day": "晨曦 (Morning)",
        "flags": {},
        "messages": [],
        "journal_events": [],
        "current_location": "幽暗地域营地 (Underdark Camp)",
        "environment_objects": {
            "iron_chest": {
                "name": "沉重的铁箱子",
                "status": "locked",
                "description": "一个上了锁的铁箱子，看起来很结实。(DC 15)",
            }
        },
    }
