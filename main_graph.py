# main_graph.py (Update for Day 3)
from langgraph.graph import StateGraph, START, END
from core.graph_state import GameState
from core.graph_nodes import input_node, dm_node, mechanics_node, generation_node
from langchain_core.messages import HumanMessage


def build_graph():
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("input_processing", input_node)
    builder.add_node("dm_analysis", dm_node)
    builder.add_node("mechanics_processing", mechanics_node)
    builder.add_node("generation", generation_node)

    # 2. Add Edges (Full Linear Pipeline)
    builder.add_edge(START, "input_processing")
    builder.add_edge("input_processing", "dm_analysis")
    builder.add_edge("dm_analysis", "mechanics_processing")
    builder.add_edge("mechanics_processing", "generation")
    builder.add_edge("generation", END)

    return builder.compile()


if __name__ == "__main__":
    print("🤖 Initializing LangGraph (Day 3 - Full Pipeline)...")
    graph = build_graph()

    # Test Case: A Complex Interaction
    print("\n--- TEST: Combat Interaction ---")

    # Simulate a history
    history = [HumanMessage(content="Who are you?")]

    initial_state: GameState = {
        "user_input": "I attempt to steal your artifact!",  # This should trigger Mechanics
        "messages": history,
        "relationship": 10,
        "player_inventory": {},
        "npc_inventory": {"mysterious_artifact": 1},
        "flags": {},
        "npc_state": {"status": "NORMAL"},
        "journal_events": [],
    }

    print(f"📥 User: {initial_state['user_input']}")

    result = graph.invoke(initial_state)

    print("-" * 50)
    print(f"🔍 Intent: {result.get('intent')}")
    print(f"🎲 Events: {result.get('journal_events')}")
    print(f"💭 Thought: {result.get('thought_process')}")
    print(f"🗣️ Shadowheart: {result.get('final_response')}")
    print("-" * 50)
