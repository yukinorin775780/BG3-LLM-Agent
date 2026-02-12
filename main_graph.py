import sys
from typing import Literal
from langgraph.graph import StateGraph, START, END
from core.graph_state import GameState
from core.graph_nodes import input_node, dm_node, mechanics_node, generation_node
from langchain_core.messages import HumanMessage

# --- Routers (The Logic Switches) ---


def route_after_input(state: GameState) -> Literal["dm_analysis", "__end__"]:
    """
    Decides where to go after Input Node.
    - If a command was fully handled (e.g., /give), stop logic.
    - If input is pending analysis, go to DM.
    """
    intent = state.get("intent", "pending")
    if intent in ["command_done", "gift_given", "item_used"]:
        # Command handled, no AI generation needed for now (or simple system response)
        # Note: In a full game, we might still want AI reaction to gifts,
        # but for this specific flow, let's say 'command_done' means stop.
        # However, for 'gift_given' or 'item_used', we actually WANT AI reaction.
        if intent in ["gift_given", "item_used"]:
            return "dm_analysis"  # Let DM see it, then Gen reaction
        return "__end__"  # Simple /help or error, just stop

    return "dm_analysis"


def route_after_dm(state: GameState) -> Literal["mechanics_processing", "generation"]:
    """
    Decides where to go after DM Node.
    - Combat/Action -> Mechanics -> Generation
    - Chat/Passive -> Generation (Skip Mechanics)
    """
    intent = state.get("intent", "chat")

    # List of intents that require dice rolls
    action_intents = ["ATTACK", "STEAL", "PERSUASION", "INTIMIDATION", "INSIGHT", "ACTION"]

    if intent in action_intents:
        return "mechanics_processing"

    # Default: Go straight to generation
    return "generation"


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
