from core.systems.maps import get_map_data, load_maps
from core.systems.world_init import get_initial_world_state


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
    assert "heavy_oak_door_1" in map_data["environment_objects"]
    assert "gas_trap_1" in map_data["environment_objects"]
    assert "chest_1" in map_data["environment_objects"]
    assert "necromancer_diary" in map_data["environment_objects"]


def test_world_init_builds_entities_from_prefab_spawns():
    state = get_initial_world_state(map_id="necromancer_lab")
    entities = state["entities"]

    assert state["map_data"]["id"] == "necromancer_lab"

    player = entities["player"]
    gribbo = entities["gribbo"]
    heavy_oak_door_1 = entities["heavy_oak_door_1"]
    gas_trap_1 = entities["gas_trap_1"]

    assert player["x"] == 2 and player["y"] == 2

    assert gribbo["name"] == "Gribbo"
    assert gribbo["faction"] == "neutral"
    assert gribbo["x"] == 4 and gribbo["y"] == 9

    assert heavy_oak_door_1["entity_type"] == "door"
    assert heavy_oak_door_1["x"] == 14 and heavy_oak_door_1["y"] == 11
    assert heavy_oak_door_1["is_open"] is False

    assert gas_trap_1["entity_type"] == "trap"
    assert gas_trap_1["x"] == 4 and gas_trap_1["y"] == 6
