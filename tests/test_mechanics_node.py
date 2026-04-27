from core.graph.nodes.mechanics import mechanics_node
from core.systems.world_init import get_initial_world_state


def test_mechanics_node_propagates_demo_cleared_from_interact_result():
    state = get_initial_world_state(map_id="necromancer_lab")
    state["intent"] = "INTERACT"
    state["intent_context"] = {
        "action_actor": "player",
        "action_target": "heavy_oak_door_1",
    }
    state["entities"]["player"]["x"] = 13
    state["entities"]["player"]["y"] = 11
    state["player_inventory"]["heavy_iron_key"] = 1

    result = mechanics_node(state)

    assert result["entities"]["heavy_oak_door_1"]["is_open"] is True
    assert result["demo_cleared"] is True
