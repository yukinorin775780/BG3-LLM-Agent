"""
Minimal "Hello World" LangGraph implementation to verify the setup.
Echo graph: data flows in and out without touching real game logic.
"""

import sys
from langgraph.graph import StateGraph, START, END
from core.graph_state import GameState


def process_input(state: GameState):
    """A simple node that processes user input."""
    print("\n--- [Node: Process Input] Executing ---")
    user_text = state.get("user_input", "")

    # Simple logic for testing: Echo the input
    response = f"Shadowheart (Graph) hears you say: '{user_text}'"

    # We return ONLY the keys we want to update
    return {"final_response": response}


def build_graph():
    """Constructs the RPG Graph."""
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("process_input", process_input)

    # 2. Add Edges
    builder.add_edge(START, "process_input")
    builder.add_edge("process_input", END)

    # 3. Compile
    return builder.compile()


if __name__ == "__main__":
    print("🤖 Initializing LangGraph...")
    try:
        graph = build_graph()

        # Initial State (Simulating what main.py would pass in)
        initial_state: GameState = {
            "user_input": "Hello, are you there?",
            "messages": [],
            "intent": "",
            "character_name": "Shadowheart",
            "relationship": 0,
            "npc_state": {"status": "NORMAL"},
            "player_inventory": {"gold_coin": 10},
            "npc_inventory": {},
            "flags": {},
            "journal_events": [],
            "final_response": "",
            "thought_process": "",
        }

        print(f"📥 Input: {initial_state['user_input']}")

        # Invoke the graph
        result = graph.invoke(initial_state)

        print(f"📤 Output: {result.get('final_response')}")
        print("✅ LangGraph Test Passed!")

    except ImportError as e:
        print("❌ Import Error: Please run 'pip install langgraph langchain-core'")
        print(e)
    except Exception as e:
        print(f"❌ Runtime Error: {e}")
