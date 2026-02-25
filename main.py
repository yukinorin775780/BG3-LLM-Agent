"""
BG3 LLM Agent - Main Entry Point (Controller Layer)
Orchestrates game flow using Model (mechanics) and View (renderer) layers.
Refactored to use MemoryManager and InputHandler.
"""

import os
import sys
from typing import Optional
from config import settings
from characters.loader import load_character
from core.engine import generate_dialogue, parse_ai_response, update_summary
from core.dice import CheckResult, roll_d20
from core.dm import analyze_intent
from core import mechanics
from core import quest
from core import inventory
from core.journal import Journal
from ui.renderer import GameRenderer

# New Core Modules
from core.memory import MemoryManager
from core.input_handler import InputHandler
from core.graph_builder import build_graph
from core.graph_state import GameState

# Character Config
CHARACTER_NAME = "shadowheart"


def load_player_profile():
    """Load player profile from data/player.json."""
    player_file = os.path.join(settings.SAVE_DIR, "player.json")
    if not os.path.exists(player_file):
        # Fallback if file doesn't exist
        return {"name": "Tav", "race": "Human", "class": "Adventurer", "level": 1, "ability_scores": {}}

    import json

    with open(player_file, "r", encoding="utf-8") as f:
        return json.load(f)


class GameSession:
    """
    Holds game state and handles one turn of input. Keeps main loop clean.
    Now delegates commands to InputHandler.
    """

    def __init__(
        self,
        ui: GameRenderer,
        input_handler: InputHandler,  # Injected Dependency
        player_data: Optional[dict],
        character,
        attributes: dict,
        situational_bonuses: list,
        dialogue_triggers: list,
        quests_config: list,
        player_inventory: inventory.Inventory,
    ):
        self.ui = ui
        self.input_handler = input_handler
        self.graph = build_graph()
        self.player_data = player_data
        self.character = character
        self.attributes = attributes
        self.situational_bonuses = situational_bonuses
        self.dialogue_triggers = dialogue_triggers
        self.quests_config = quests_config
        self.player_inventory = player_inventory

        # Runtime State (Loaded from Memory)
        self._graph_thread_id = "shadowheart_default"  # LangGraph Checkpointer 会话 ID
        self.relationship_score = 0
        self.conversation_history: list = []
        self.npc_state = {"status": "NORMAL", "duration": 0}
        self.flags: dict = {}
        self.summary = ""
        self.journal = Journal()
        self.running = True

    def init_from_memory(self, memory_data: dict) -> None:
        """Load state from memory dict."""
        # 若存档中有 thread_id，用于 LangGraph Checkpointer 加载对应会话
        self._graph_thread_id = memory_data.get("thread_id", "shadowheart_default")
        self.relationship_score = memory_data.get("relationship_score", 0)
        self.conversation_history = memory_data.get("history", [])
        self.npc_state = memory_data.get("npc_state", {"status": "NORMAL", "duration": 0})
        self.flags = memory_data.get("flags", {})
        self.summary = memory_data.get("summary", "")
        self.journal = Journal.from_dict(memory_data.get("journal"))

        # Restore Inventories
        saved_player_inv = memory_data.get("inventory_player", {})
        saved_npc_inv = memory_data.get("inventory_npc", {})
        if saved_player_inv:
            self.player_inventory.from_dict(saved_player_inv)
        if saved_npc_inv:
            self.character.inventory.from_dict(saved_npc_inv)

    def build_memory_data(self) -> dict:
        """Build dict for persistence."""
        return {
            "thread_id": self._graph_thread_id,  # 供下次启动时恢复 Checkpoint 会话
            "relationship_score": self.relationship_score,
            "history": self.conversation_history,
            "npc_state": self.npc_state,
            "flags": self.flags,
            "summary": self.summary,
            "inventory_player": self.player_inventory.to_dict(),
            "inventory_npc": self.character.inventory.to_dict(),
            "journal": self.journal.to_dict(),
        }

    def turn(self, user_input: str) -> Optional[str]:
        """
        Process one user input. Returns "quit", "continue", or None (turn done).
        Uses LangGraph pipeline: Input -> DM -> Mechanics -> Generation.
        """
        if not user_input:
            return "continue"
        if user_input.lower() in ["quit", "exit", "退出", "q"]:
            self.running = False
            return "quit"

        # 1. Build State Dict (Map GameSession attributes to GameState keys)
        state_payload: GameState = {
            "messages": self.conversation_history,
            "user_input": user_input,
            "character_name": self.attributes["name"],
            "relationship": self.relationship_score,
            "npc_state": self.npc_state,
            "player_inventory": self.player_inventory.to_dict(),
            "npc_inventory": self.character.inventory.to_dict(),
            "flags": self.flags,
            "journal_events": [],  # Reset per turn
        }

        # 2. Invoke Graph（带 thread_id 以加载对应 Checkpoint 存档）
        # Checkpointer 通过 thread_id 区分会话，同一 thread_id 会从上次 checkpoint 恢复
        thread_id = getattr(self, "_graph_thread_id", "shadowheart_default")
        config = {"configurable": {"thread_id": thread_id}}
        try:
            with self.ui.create_spinner("[brain]Shadowheart is thinking (Graph V3)...[/brain]", spinner="dots"):
                result = self.graph.invoke(state_payload, config=config)
        except Exception as e:
            self.ui.print_error(f"Graph Error: {e}")
            return "continue"

        # 3. Process Results (Update UI & Internal State from Graph Output)

        # A. Logs (Mechanics Dice Rolls)
        for event in result.get("journal_events", []):
            self.ui.print_system_info(f"🎲 {event}")
            self.journal.add_entry(event, len(self.conversation_history) // 2)

        # B. Thoughts & Speech
        if result.get("thought_process"):
            self.ui.print_inner_thought(result["thought_process"])

        if result.get("final_response"):
            self.ui.print_npc_response("Shadowheart", result["final_response"])

        # C. Update State (Relationship, Status, Flags)
        self.relationship_score = result.get("relationship", self.relationship_score)
        self.npc_state = result.get("npc_state", self.npc_state)
        self.flags = result.get("flags", self.flags)

        # D. Update Inventory (Graph might have modified them via InputNode)
        if "player_inventory" in result:
            self.player_inventory.from_dict(result["player_inventory"])
        if "npc_inventory" in result:
            self.character.inventory.from_dict(result["npc_inventory"])

        # E. Update History (Append the turn)
        self.conversation_history.append({"role": "user", "content": user_input})
        if result.get("final_response"):
            self.conversation_history.append({"role": "assistant", "content": result["final_response"]})

        return "continue"

    def _generate_reaction(self, user_input: str, original_input: Optional[str] = None, is_system: bool = False):
        """Helper to call LLM and handle response parsing."""
        if original_input is None:
            original_input = user_input

        journal_data = self.journal.get_recent_entries(5)
        inventory_data = self.character.inventory.list_item_names()

        system_prompt = self.character.render_prompt(
            self.relationship_score,
            flags=self.flags,
            summary=self.summary,
            journal_entries=journal_data,
            inventory_items=inventory_data,
            has_healing_potion=self.character.inventory.has("healing_potion"),
        )

        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": user_input})

        with self.ui.create_spinner("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
            response = generate_dialogue(system_prompt, conversation_history=messages)

        # Parse & Apply Results
        parsed = parse_ai_response(response)

        if parsed["approval"] != 0:
            self._update_relationship(parsed["approval"])

        if parsed["new_state"] and parsed["new_state"] != self.npc_state["status"]:
            self._set_state(parsed["new_state"], 3)
            self.ui.print_state_effect(parsed["new_state"], 3, f"State changed to {parsed['new_state']}")

        # Handle NPC Action (Self-Use)
        if parsed.get("action") == "USE_POTION":
            if self.character.inventory.has("healing_potion"):
                # Use the same mechanic as player /use
                item_data = inventory.get_registry().get("healing_potion")
                effect = mechanics.apply_item_effect("healing_potion", item_data)

                self.character.inventory.remove("healing_potion")
                self.ui.print_action_effect(f"Shadowheart drinks potion: {effect['message']}")
                self.journal.add_entry("Shadowheart used a Healing Potion.", 0)
            else:
                self.ui.print_system_info("AI tried to use potion but has none.")

        # Render Output
        if parsed.get("thought"):
            self.ui.print_inner_thought(parsed["thought"])

        cleaned_response = parsed["text"]
        if cleaned_response:
            self.ui.print_npc_response("Shadowheart", cleaned_response)
        else:
            self.ui.print_npc_response("Shadowheart", "...")

        # Update History
        if not is_system:
            # Only add user input if it wasn't a hidden system message
            self.conversation_history.append({"role": "user", "content": original_input})
        self.conversation_history.append({"role": "assistant", "content": cleaned_response})

        # Summarization Check
        if len(self.conversation_history) > settings.MAX_HISTORY:
            self._consolidate_memory()

        return None

    def _update_relationship(self, delta: int):
        self.relationship_score += delta
        self.relationship_score = max(-100, min(100, self.relationship_score))
        self.ui.print_relationship_change(delta, self.relationship_score)

    def _set_state(self, status: str, duration: int):
        self.npc_state["status"] = status
        self.npc_state["duration"] = duration

    def _tick_state(self):
        new_status, new_dur = mechanics.update_npc_state(self.npc_state["status"], self.npc_state["duration"])
        self.npc_state["status"] = new_status
        self.npc_state["duration"] = new_dur
        if new_status == "NORMAL":
            self.ui.print_state_effect("NORMAL", 0, "状态恢复")

    def _consolidate_memory(self):
        messages = self.conversation_history[:4]
        with self.ui.create_spinner("📝 Consolidating memories...", spinner="dots"):
            self.summary = update_summary(self.summary, messages)
        self.conversation_history = self.conversation_history[4:]
        self.ui.print_system_info("🧠 Memory Consolidated.")


def main():
    ui = GameRenderer()
    ui.clear_screen()
    ui.show_title("BG3 LLM Agent - Refactored Engine")

    # 1. Init Infrastructure
    memory_mgr = MemoryManager()
    inventory.init_registry("config/items.yaml")

    # 2. Load Data
    try:
        player_data = load_player_profile()
        character = load_character(CHARACTER_NAME)
        attributes = character.data

        # Load Memory (Persistent State)
        memory_data = memory_mgr.load(default_relationship=attributes.get("relationship", 0))

        ui.print_system_info(f"✓ System Ready. Character: {attributes['name']}")
    except Exception as e:
        ui.print_error(f"❌ Initialization Failed: {e}")
        return

    # 3. Init Session & Handlers
    input_handler = InputHandler(ui)

    # Initialize Player Inventory (Default)
    player_inventory = inventory.Inventory()
    player_inventory.add("healing_potion", 2)
    player_inventory.add("gold_coin", 10)

    session = GameSession(
        ui=ui,
        input_handler=input_handler,
        player_data=player_data,
        character=character,
        attributes=attributes,
        situational_bonuses=attributes.get("situational_bonuses", []),
        dialogue_triggers=attributes.get("dialogue_triggers", []),
        quests_config=character.quests,
        player_inventory=player_inventory,
    )

    # Apply Loaded State
    session.init_from_memory(memory_data)

    # Show Dashboard
    if memory_data.get("history"):
        ui.print_system_info(f"🧠 Memories loaded. Relationship: {session.relationship_score}")

    ui.print_rule("💬 Start Game (Type '/use healing_potion' to test items)", style="info")

    # 4. Main Loop
    while session.running:
        try:
            # Refresh Dashboard
            active_quests = quest.QuestManager.check_quests(character.quests, session.flags)
            ui.print(ui.show_dashboard(
                player_data["name"],
                attributes["name"],
                session.relationship_score,
                session.npc_state,
                active_quests,
                session.player_inventory,
                session.character.inventory,
                session.journal.get_recent_entries(3),
            ))
            ui.print()

            user_input = ui.input_prompt()
            result = session.turn(user_input)

            if result == "quit":
                break

            # Auto-Save after every turn
            memory_mgr.save(session.build_memory_data())

        except KeyboardInterrupt:
            break
        except Exception as e:
            ui.print_error(f"❌ Runtime Error: {e}")
            import traceback

            traceback.print_exc()

    # Exit Save
    memory_mgr.save(session.build_memory_data())
    ui.print("\n[info]Game Saved. Goodbye![/info]")


if __name__ == "__main__":
    main()
