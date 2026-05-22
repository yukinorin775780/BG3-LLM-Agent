import json
from pathlib import Path

import yaml

from core.systems.maps import get_map_data, load_maps
from core.systems.world_init import get_initial_world_state

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tiled_properties(obj: dict) -> dict:
    return {
        str(prop.get("name")): prop.get("value")
        for prop in obj.get("properties", [])
        if isinstance(prop, dict) and prop.get("name") is not None
    }


def _find_tiled_interactable(map_json: dict, name: str) -> dict:
    for layer in map_json.get("layers") or []:
        if str(layer.get("name") or "").lower() != "interactables":
            continue
        for obj in layer.get("objects") or []:
            if str(obj.get("name") or "") == name:
                return obj
    raise AssertionError(f"missing Tiled interactable {name}")


def test_world_init_necromancer_lab_uses_requested_map_id():
    state = get_initial_world_state(map_id="necromancer_lab")
    assert state["map_data"]["id"] == "necromancer_lab"


def test_necromancer_lab_current_location_not_goblin_camp():
    state = get_initial_world_state(map_id="necromancer_lab")
    current_location = str(state.get("current_location") or "")
    assert "地精营地边缘" not in current_location
    assert "地精营地" not in current_location


def test_necromancer_lab_entities_include_gribbo_and_exit_door_alias():
    state = get_initial_world_state(map_id="necromancer_lab")
    entities = state["entities"]
    map_data = state["map_data"]
    env = map_data.get("environment_objects") or {}
    door_meta = env.get("heavy_oak_door_1") or {}

    assert "gribbo" in entities
    assert "heavy_oak_door_1" in entities
    assert "exit_door" in (door_meta.get("alias_ids") or [])


def test_necromancer_lab_final_exit_yaml_and_tiled_coordinates_match():
    yaml_map = yaml.safe_load(
        (REPO_ROOT / "data/maps/necromancer_lab.yaml").read_text(encoding="utf-8")
    )
    json_map = json.loads(
        (REPO_ROOT / "web_ui/assets/maps/necromancer_lab.json").read_text(encoding="utf-8")
    )
    yaml_exit = next(
        obj for obj in yaml_map["environment_objects"] if obj.get("id") == "heavy_oak_door_1"
    )
    tiled_exit = _find_tiled_interactable(json_map, "exit_door")
    tiled_props = _tiled_properties(tiled_exit)
    tile_x = int(tiled_exit["x"] // json_map["tilewidth"])
    tile_y = int(tiled_exit["y"] // json_map["tileheight"])

    assert yaml_exit["position"] == [18, 3]
    assert yaml_exit["position"] != [14, 11]
    assert [tile_x, tile_y] == [18, 3]
    assert yaml_exit["position"] == [tile_x, tile_y]
    assert yaml_exit["alias_ids"] == ["exit_door"]
    assert tiled_props["alias_id"] == "heavy_oak_door_1"
    assert tiled_props["key_required"] == "heavy_iron_key"
    assert tiled_props["room_id"] == "room_exit"


def test_necromancer_lab_map_instance_is_loaded_from_maps_directory():
    load_maps(force_reload=True)
    map_data = get_map_data("necromancer_lab")

    assert map_data["id"] == "necromancer_lab"
    assert map_data["name"] == "死灵法师的废弃实验室"
    assert map_data["width"] == 20
    assert map_data["height"] == 14
    assert map_data["player_start"] == [2, 2]
    assert isinstance(map_data.get("spawns"), list)
    assert len(map_data["spawns"]) == 1
    assert "door_a_to_b" in map_data["environment_objects"]
    assert "heavy_oak_door_1" in map_data["environment_objects"]
    assert "door_b_to_d" in map_data["environment_objects"]
    assert "gas_trap_1" in map_data["environment_objects"]
    assert "chest_1" in map_data["environment_objects"]
    assert "necromancer_diary" in map_data["environment_objects"]


def test_world_init_builds_entities_from_prefab_spawns():
    state = get_initial_world_state(map_id="necromancer_lab")
    entities = state["entities"]

    assert state["map_data"]["id"] == "necromancer_lab"

    player = entities["player"]
    gribbo = entities["gribbo"]
    door_a_to_b = entities["door_a_to_b"]
    heavy_oak_door_1 = entities["heavy_oak_door_1"]
    door_b_to_d = entities["door_b_to_d"]
    gas_trap_1 = entities["gas_trap_1"]

    assert player["x"] == 2 and player["y"] == 2

    assert gribbo["name"] == "Gribbo"
    assert gribbo["faction"] == "neutral"
    assert gribbo["x"] == 4 and gribbo["y"] == 9

    assert door_a_to_b["entity_type"] == "door"
    assert door_a_to_b["x"] == 3 and door_a_to_b["y"] == 2
    assert door_a_to_b["is_open"] is False
    assert door_a_to_b["is_locked"] is False

    assert heavy_oak_door_1["entity_type"] == "door"
    assert heavy_oak_door_1["x"] == 18 and heavy_oak_door_1["y"] == 3
    assert heavy_oak_door_1["is_open"] is False

    assert door_b_to_d["entity_type"] == "door"
    assert door_b_to_d["x"] == 5 and door_b_to_d["y"] == 7
    assert door_b_to_d["is_locked"] is True
    assert door_b_to_d["key_required"] == "lab_key"

    assert gas_trap_1["entity_type"] == "trap"
    assert gas_trap_1["x"] == 4 and gas_trap_1["y"] == 6


def test_necromancer_lab_state_does_not_include_goblin_camp_enemies():
    state = get_initial_world_state(map_id="necromancer_lab")
    entities = state["entities"]
    assert "goblin_1" not in entities
    assert "goblin_archer" not in entities
    assert "goblin_shaman" not in entities


def test_goblin_camp_default_still_includes_goblin_enemies():
    state = get_initial_world_state()
    entities = state["entities"]
    assert "goblin_1" in entities
    assert "goblin_archer" in entities
    assert "goblin_shaman" in entities
