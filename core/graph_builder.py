"""
LangGraph application factory.
Builds and compiles the RPG agent graph with conditional routing.
"""

from langgraph.graph import StateGraph, START, END
from core.graph_state import GameState
from core.graph_routers import route_after_input, route_after_dm
from characters.loader import load_character
from core.graph_nodes import input_node, dm_node, mechanics_node, create_generation_node


# --- Graph Builder ---


def build_graph():
    """Build and compile the LangGraph application."""
    builder = StateGraph(GameState)

    # 1. Add Nodes
    builder.add_node("input_processing", input_node)
    builder.add_node("dm_analysis", dm_node)
    builder.add_node("mechanics_processing", mechanics_node)
    builder.add_node("generation", create_generation_node(load_character("shadowheart")))  # type: ignore[arg-type]

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


__all__ = ["build_graph"]
