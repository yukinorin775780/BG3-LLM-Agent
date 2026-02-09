"""
LangGraph state definition for the BG3 Agent.
GameState is the shared memory (baton) passed between graph nodes.
"""

from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages


class GameState(TypedDict, total=False):
    """
    The central state object for the BG3 Agent Graph.
    This 'baton' is passed between all nodes (Input -> Reason -> Act -> Output).
    """

    # Conversation History (LangGraph automatically handles appending with add_messages)
    messages: Annotated[List[Any], add_messages]

    # Input Processing
    user_input: str
    intent: str  # e.g., "attack", "talk", "trade", "command"

    # RPG State Data
    character_name: str
    relationship: int
    npc_state: Dict[str, Any]  # e.g. {"status": "SILENT", "duration": 2}

    # Inventories (Simple Dicts for Graph transmission)
    player_inventory: Dict[str, int]
    npc_inventory: Dict[str, int]

    # Quest & World
    flags: Dict[str, bool]
    journal_events: List[str]  # New events to be logged this turn

    # Output to Renderer
    final_response: str
    thought_process: str  # The inner monologue content
