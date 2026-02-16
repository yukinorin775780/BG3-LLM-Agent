"""
LangGraph state definition for the BG3 Agent.
GameState is the shared memory (baton) passed between graph nodes.

Uses operator and Annotated reducers for enhanced state merge semantics:
- messages: add_messages (LangGraph standard for conversation flow)
- journal_events: merge_events (accumulate event lists across nodes)
"""

import operator
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages


def merge_events(left: List[str], right: List[str]) -> List[str]:
    """
    Reducer: Merge journal event lists by concatenation.
    When multiple nodes append events (e.g. InputNode + MechanicsNode),
    the final state accumulates all events in order.
    """
    return operator.add(left or [], right or [])


class GameState(TypedDict, total=False):
    """
    The central state object for the BG3 Agent Graph.
    This 'baton' is passed between all nodes (Input -> DM -> Mechanics -> Generation).

    Field categories:
    -----------------
    [PERSISTENT - 持久化存档数据]
    Survive across turns; saved/loaded by MemoryManager.

    [TRANSIENT - 单轮瞬时上下文]
    Scoped to one invoke; derived from or produced within the turn.
    """

    # -------------------------------------------------------------------------
    # Conversation History
    # LangGraph standard: add_messages handles append/dedupe for chat flow.
    # [PERSISTENT] Persisted as history in saves.
    # -------------------------------------------------------------------------
    messages: Annotated[List[Any], add_messages]

    # -------------------------------------------------------------------------
    # Input Processing [TRANSIENT]
    # -------------------------------------------------------------------------
    user_input: str         # Raw player input this turn
    intent: str             # DM-analyzed intent (e.g. "ATTACK", "CHAT", "gift_given")

    # -------------------------------------------------------------------------
    # RPG State [PERSISTENT]
    # -------------------------------------------------------------------------
    character_name: str
    relationship: int       # Relationship score (-100..100)
    npc_state: Dict[str, Any]  # e.g. {"status": "SILENT", "duration": 2}

    # -------------------------------------------------------------------------
    # Inventories [PERSISTENT]
    # Dict[str, int]: item_id -> quantity
    # -------------------------------------------------------------------------
    player_inventory: Dict[str, int]
    npc_inventory: Dict[str, int]

    # -------------------------------------------------------------------------
    # Quest & World [PERSISTENT]
    # -------------------------------------------------------------------------
    flags: Dict[str, bool]

    # -------------------------------------------------------------------------
    # Journal Events [TRANSIENT within turn]
    # merge_events reducer: nodes append events; final state = accumulated list.
    # Consumed by GenerationNode for context; flushed per turn by main.py.
    # -------------------------------------------------------------------------
    journal_events: Annotated[List[str], merge_events]

    # -------------------------------------------------------------------------
    # Output to Renderer [TRANSIENT]
    # -------------------------------------------------------------------------
    final_response: str      # Spoken dialogue to display
    thought_process: str     # Inner monologue content
