"""
Static tactical map loader (YAML-driven).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import yaml


MAP_DB: Dict[str, Dict[str, Any]] = {}
_LOADED = False


def _default_maps_path() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "maps.yaml")
    )


def _normalize_map_id(map_id: Any) -> str:
    return str(map_id or "").strip().lower().replace(" ", "_").replace("-", "_")


def _normalize_coord(coord: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(coord, (list, tuple)) or len(coord) != 2:
        return None
    try:
        return int(coord[0]), int(coord[1])
    except (TypeError, ValueError):
        return None


def _build_blocked_tiles(obstacles: List[Dict[str, Any]]) -> List[List[int]]:
    blocked: set[Tuple[int, int]] = set()
    for obstacle in obstacles:
        if not isinstance(obstacle, dict):
            continue
        if not bool(obstacle.get("blocks_movement", False)):
            continue
        for raw_coord in obstacle.get("coordinates", []) or []:
            coord = _normalize_coord(raw_coord)
            if coord is None:
                continue
            blocked.add(coord)
    return [[x, y] for x, y in sorted(blocked)]


def load_maps(filepath: Optional[str] = None, *, force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    global _LOADED
    if _LOADED and not force_reload:
        return MAP_DB

    target_path = filepath or _default_maps_path()
    MAP_DB.clear()
    if not os.path.exists(target_path):
        _LOADED = True
        return MAP_DB

    with open(target_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    if isinstance(raw_data, dict):
        for raw_map_id, raw_map_data in raw_data.items():
            map_id = _normalize_map_id(raw_map_id)
            if not map_id or not isinstance(raw_map_data, dict):
                continue
            obstacles: List[Dict[str, Any]] = []
            for raw_obstacle in raw_map_data.get("obstacles", []) or []:
                if not isinstance(raw_obstacle, dict):
                    continue
                normalized_obstacle = {
                    "type": str(raw_obstacle.get("type", "obstacle")).strip().lower() or "obstacle",
                    "coordinates": [],
                    "blocks_movement": bool(raw_obstacle.get("blocks_movement", False)),
                    "blocks_los": bool(raw_obstacle.get("blocks_los", False)),
                }
                for raw_coord in raw_obstacle.get("coordinates", []) or []:
                    coord = _normalize_coord(raw_coord)
                    if coord is None:
                        continue
                    normalized_obstacle["coordinates"].append([coord[0], coord[1]])
                obstacles.append(normalized_obstacle)

            width = int(raw_map_data.get("width", 15))
            height = int(raw_map_data.get("height", 15))
            MAP_DB[map_id] = {
                "id": map_id,
                "name": str(raw_map_data.get("name") or raw_map_id),
                "width": max(1, width),
                "height": max(1, height),
                "obstacles": obstacles,
                "blocked_movement_tiles": _build_blocked_tiles(obstacles),
            }

    _LOADED = True
    return MAP_DB


def get_map_data(map_id: str) -> Dict[str, Any]:
    load_maps()
    resolved_id = _normalize_map_id(map_id)
    if not resolved_id:
        return {}
    return dict(MAP_DB.get(resolved_id, {}))

