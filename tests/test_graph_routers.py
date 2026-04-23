from core.graph.graph_routers import route_after_dm


def test_route_after_dm_routes_read_to_lore_processing():
    route = route_after_dm({"intent": "READ", "is_probing_secret": False})
    assert route == "lore_processing"


def test_route_after_dm_routes_interact_with_readable_to_lore_processing():
    route = route_after_dm(
        {
            "intent": "INTERACT",
            "is_probing_secret": False,
            "intent_context": {"action_target": "necromancer_diary"},
            "environment_objects": {
                "necromancer_diary": {"id": "necromancer_diary", "type": "readable"}
            },
        }
    )
    assert route == "lore_processing"
