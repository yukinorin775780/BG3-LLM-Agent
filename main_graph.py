import sys
from langgraph.graph import StateGraph, START, END
from core.graph_state import GameState
from core.graph_routers import route_after_input, route_after_dm
from core.graph_nodes import input_node, dm_node, mechanics_node, generation_node
from langchain_core.messages import HumanMessage


# --- Graph Builder ---


def build_graph():
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("input_processing", input_node)
    builder.add_node("dm_analysis", dm_node)
    builder.add_node("mechanics_processing", mechanics_node)
    builder.add_node("generation", generation_node)

    # 2. Add Edges & Routing

    # Start -> Input
    builder.add_edge(START, "input_processing")

    # Input -> (Conditional) -> DM or END
    builder.add_conditional_edges(
        "input_processing",
        route_after_input,
        {
            "dm_analysis": "dm_analysis",
            "__end__": END,
        },
    )

    # DM -> (Conditional) -> Mechanics or Generation
    builder.add_conditional_edges(
        "dm_analysis",
        route_after_dm,
        {
            "mechanics_processing": "mechanics_processing",
            "generation": "generation",
        },
    )

    # Mechanics -> Generation (Linear)
    builder.add_edge("mechanics_processing", "generation")

    # Generation -> END
    builder.add_edge("generation", END)

    return builder.compile()


if __name__ == "__main__":
    print("🤖 Initializing LangGraph (Day 4 - Smart Routing)...")
    graph = build_graph()

    # TEST 1: Simple Chat (Should SKIP Mechanics)
    print("\n--- TEST 1: Simple Chat (Expect: Skip Mechanics) ---")
    state1: GameState = {
        "user_input": "Hello Shadowheart.",
        "messages": [],
        "relationship": 0,
        "player_inventory": {},
        "npc_inventory": {},
        "flags": {},
        "npc_state": {},
        "journal_events": [],
    }
    # Invoke
    for step in graph.stream(state1):
        # Stream prints the active node name
        print(f" -> Executed: {list(step.keys())[0]}")

    # TEST 2: Action (Should HIT Mechanics)
    print("\n--- TEST 2: Action (Expect: Hit Mechanics) ---")
    state2: GameState = {
        "user_input": "I attack you with my sword!",
        "messages": [],
        "relationship": 0,
        "player_inventory": {},
        "npc_inventory": {},
        "flags": {},
        "npc_state": {},
        "journal_events": [],
    }
    for step in graph.stream(state2):
        print(f" -> Executed: {list(step.keys())[0]}")
