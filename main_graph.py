# main_graph.py (Update for Day 2)
from langgraph.graph import StateGraph, START, END
from core.graph_state import GameState
from core.graph_nodes import input_node, dm_node
from core import inventory


def build_graph():
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("input_processing", input_node)
    builder.add_node("dm_analysis", dm_node)

    # 2. Add Edges (Linear for now)
    # Input -> DM -> END
    builder.add_edge(START, "input_processing")
    builder.add_edge("input_processing", "dm_analysis")
    builder.add_edge("dm_analysis", END)

    return builder.compile()


if __name__ == "__main__":
    print("🤖 Initializing LangGraph (Day 2)...")
    inventory.init_registry("config/items.yaml")  # So /use healing_potion has effect data
    graph = build_graph()

    # Test Case 1: Normal Chat
    print("\n--- TEST 1: Chat ---")
    state1 = {
        "user_input": "I pull out my sword and attack!",
        "messages": [],
        "relationship": 0,
        "player_inventory": {},
        "npc_inventory": {},
        "flags": {},
        "npc_state": {},
        "journal_events": [],
    }
    res1 = graph.invoke(GameState(**state1))
    print(f"📥 Input: {state1['user_input']}")
    print(f"🔍 Intent Detected: {res1.get('intent')}")

    # Test Case 2: Command
    print("\n--- TEST 2: Command ---")
    state2 = {
        "user_input": "/use healing_potion",
        "messages": [],
        "relationship": 0,
        "player_inventory": {"healing_potion": 1},  # Player has potion
        "npc_inventory": {},
        "flags": {},
        "npc_state": {},
        "journal_events": [],
    }
    res2 = graph.invoke(GameState(**state2))
    print(f"📥 Input: {state2['user_input']}")
    print(f"📦 Inventory Left: {res2['player_inventory']}")  # Should be empty
    print(f"🔍 Intent: {res2.get('intent')}")
