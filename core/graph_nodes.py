"""
LangGraph nodes: Input (slash commands) and DM (intent analysis).
Migrated from InputHandler and DM logic for the graph-based flow.
"""

from core.graph_state import GameState
from core.dm import analyze_intent
from core import mechanics
from core.inventory import get_registry


def input_node(state: GameState) -> dict:
    """
    Node 1: Handles slash commands.
    Updates inventory/stats directly if a command is detected.
    """
    user_input = state.get("user_input", "").strip()
    result_updates = {
        "journal_events": [],
        "intent": "pending",
    }

    # Pass-through if empty
    if not user_input:
        return result_updates

    # --- Command Handling ---
    if user_input.startswith("/"):
        parts = user_input.split()
        command = parts[0].lower()

        # /GIVE
        if command == "/give" and len(parts) > 1:
            item_key = parts[1]
            player_inv = state["player_inventory"]
            # Check logic (simplified for graph)
            if player_inv.get(item_key, 0) > 0:
                # Execute transfer
                new_p_inv = player_inv.copy()
                new_n_inv = state["npc_inventory"].copy()

                new_p_inv[item_key] -= 1
                if new_p_inv[item_key] == 0:
                    del new_p_inv[item_key]
                new_n_inv[item_key] = new_n_inv.get(item_key, 0) + 1

                # Update State
                result_updates["player_inventory"] = new_p_inv
                result_updates["npc_inventory"] = new_n_inv
                result_updates["relationship"] = state["relationship"] + 2  # Bonus for gift
                result_updates["journal_events"].append(f"Player gave {item_key} to NPC.")
                result_updates["final_response"] = f"[SYSTEM] You gave {item_key} to Shadowheart."
                result_updates["intent"] = "gift_given"  # Special intent for reaction

            else:
                result_updates["final_response"] = f"[SYSTEM] You don't have {item_key}."
                result_updates["intent"] = "command_done"

        # /USE
        elif command == "/use" and len(parts) > 1:
            item_key = parts[1]
            player_inv = state["player_inventory"]

            if player_inv.get(item_key, 0) > 0:
                # Get Effect
                item_data = get_registry().get(item_key)
                effect = mechanics.apply_item_effect(item_key, item_data)

                # Remove Item
                new_p_inv = player_inv.copy()
                new_p_inv[item_key] -= 1
                if new_p_inv[item_key] == 0:
                    del new_p_inv[item_key]

                result_updates["player_inventory"] = new_p_inv
                result_updates["journal_events"].append(f"Player used {item_key}: {effect['message']}")
                result_updates["final_response"] = f"[SYSTEM] You used {item_key}: {effect['message']}"
                result_updates["intent"] = "item_used"  # Special intent for reaction

            else:
                result_updates["final_response"] = f"[SYSTEM] You don't have {item_key}."
                result_updates["intent"] = "command_done"

        else:
            result_updates["final_response"] = "[SYSTEM] Unknown command."
            result_updates["intent"] = "command_done"

        return result_updates

    # If not a command, just pass through
    return result_updates


def dm_node(state: GameState) -> dict:
    """
    Node 2: Analyzes intent if not already handled.
    """
    if state.get("intent") in ["command_done", "gift_given", "item_used"]:
        return {}  # No changes needed

    # Call the DM Brain
    user_input = state.get("user_input", "")
    print("🎲 DM Node: Analyzing intent...")

    analysis = analyze_intent(user_input)
    # analysis returns {'action_type': '...', 'difficulty_class': ...}

    return {
        "intent": analysis.get("action_type", "chat"),
    }
