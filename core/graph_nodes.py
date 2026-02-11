"""
LangGraph nodes: Input (slash commands) and DM (intent analysis).
Migrated from InputHandler and DM logic for the graph-based flow.
"""

from core.graph_state import GameState
from core.dm import analyze_intent
from core import mechanics
from core.inventory import get_registry
from core.dice import roll_d20, CheckResult
from core.engine import generate_dialogue, parse_ai_response
from characters.loader import load_character


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
            player_inv = state.get("player_inventory", {})
            # Check logic (simplified for graph)
            if player_inv.get(item_key, 0) > 0:
                # Execute transfer
                new_p_inv = player_inv.copy()
                new_n_inv = state.get("npc_inventory", {}).copy()

                new_p_inv[item_key] -= 1
                if new_p_inv[item_key] == 0:
                    del new_p_inv[item_key]
                new_n_inv[item_key] = new_n_inv.get(item_key, 0) + 1

                # Update State
                result_updates["player_inventory"] = new_p_inv
                result_updates["npc_inventory"] = new_n_inv
                result_updates["relationship"] = state.get("relationship", 0) + 2  # Bonus for gift
                result_updates["journal_events"].append(f"Player gave {item_key} to NPC.")
                result_updates["final_response"] = f"[SYSTEM] You gave {item_key} to Shadowheart."
                result_updates["intent"] = "gift_given"  # Special intent for reaction

            else:
                result_updates["final_response"] = f"[SYSTEM] You don't have {item_key}."
                result_updates["intent"] = "command_done"

        # /USE
        elif command == "/use" and len(parts) > 1:
            item_key = parts[1]
            player_inv = state.get("player_inventory", {})

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


def mechanics_node(state: GameState) -> dict:
    """
    Node 3: Mechanics Engine.
    Executes dice rolls based on the intent analyzed by DM.
    """
    intent = state.get("intent", "chat")

    # Skip if no mechanics needed
    if intent in ["chat", "command_done", "pending", "gift_given", "item_used"]:
        return {}

    print(f"⚙️ Mechanics Node: Processing {intent}...")

    # Simple DC logic for V3 prototype (can be expanded later)
    dc = 12
    modifier = 0  # In full version, get from player stats

    # Roll the Dice
    result = roll_d20(dc, modifier)

    # Format outcome
    outcome_str = f"Action: {intent} | Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})"

    # Add to journal so Generation Node sees it
    new_events = state.get("journal_events", []).copy()
    new_events.append(outcome_str)

    return {
        "journal_events": new_events,
    }


def generation_node(state: GameState) -> dict:
    """
    Node 4: LLM Generation.
    Synthesizes everything (Input -> DM -> Mechanics) into a response.
    """
    print("🗣️ Generation Node: Shadowheart is speaking...")

    # 1. Load Character (In a real app, cache this)
    char = load_character("shadowheart")

    # 2. Render Prompt
    recent_logs = state.get("journal_events", [])

    system_prompt = char.render_prompt(
        relationship_score=state.get("relationship", 0),
        flags=state.get("flags", {}),
        summary="Graph Mode Testing",
        journal_entries=recent_logs,
        inventory_items=list(state.get("npc_inventory", {}).keys()),
        has_healing_potion="healing_potion" in state.get("npc_inventory", {}),
    )

    # 3. Call LLM
    history = list(state.get("messages", []))
    user_input = state.get("user_input", "")

    # If the user input isn't in history yet, we treat it as the latest turn
    if not history or _msg_content(history[-1]) != user_input:
        history.append({"role": "user", "content": user_input})

    # Engine expects list of dicts with "role" ("user"/"assistant") and "content"
    history_dicts = [_message_to_dict(m) for m in history]

    raw_response = generate_dialogue(system_prompt, conversation_history=history_dicts)
    parsed = parse_ai_response(raw_response)

    # 4. Return Updates
    return {
        "final_response": parsed["text"],
        "thought_process": parsed.get("thought") or "",
    }


def _msg_content(m) -> str:
    """Get content from a message (dict or LangChain message)."""
    if isinstance(m, dict):
        return m.get("content", "")
    return getattr(m, "content", "")


def _message_to_dict(m) -> dict:
    """Convert a message to engine format: {role: 'user'|'assistant', content: str}."""
    if isinstance(m, dict):
        role = m.get("role", "user")
        return {"role": role if role in ("user", "assistant") else "user", "content": m.get("content", "")}
    role = getattr(m, "type", "human")
    role = "user" if role == "human" else "assistant" if role == "ai" else "user"
    return {"role": role, "content": getattr(m, "content", "")}
