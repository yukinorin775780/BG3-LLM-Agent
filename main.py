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
        self.player_data = player_data
        self.character = character
        self.attributes = attributes
        self.situational_bonuses = situational_bonuses
        self.dialogue_triggers = dialogue_triggers
        self.quests_config = quests_config
        self.player_inventory = player_inventory

        # Runtime State (Loaded from Memory)
        self.relationship_score = 0
        self.conversation_history: list = []
        self.npc_state = {"status": "NORMAL", "duration": 0}
        self.flags: dict = {}
        self.summary = ""
        self.journal = Journal()
        self.running = True

    def init_from_memory(self, memory_data: dict) -> None:
        """Load state from memory dict."""
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
        """
        if not user_input:
            return "continue"

        if user_input.lower() in ["quit", "exit", "退出", "q"]:
            self.running = False
            return "quit"

        # --- 1. COMMAND PHASE (/give, /use, /roll) ---
        if user_input.startswith("/"):
            turn_count = len(self.conversation_history) // 2 + 1

            # Build Context for Handler
            context = {
                "attributes": self.attributes,
                "player_data": self.player_data,
                "player_inventory": self.player_inventory,
                "npc_inventory": self.character.inventory,
                "journal": self.journal,
                "turn_count": turn_count,
                "relationship_score": self.relationship_score,
                "action_type": "NONE",  # Default for manual rolls
            }

            # Delegate to InputHandler
            cmd_result = self.input_handler.handle(user_input, context)

            # Case A: Not a command (shouldn't happen due to check) or Error
            if cmd_result is None or cmd_result.startswith("Command error") or cmd_result.startswith("You don't have"):
                # Errors are already printed by InputHandler
                return "continue"

            # Case B: System Injection (e.g., Gift given, Item used)
            if cmd_result.startswith("[SYSTEM]"):
                # Inject prompt and generate NPC reaction immediately
                return self._generate_reaction(user_input=cmd_result, is_system=True)

            # Case C: Info Message (e.g., Roll result)
            self.ui.print_system_info(f"💡 {cmd_result}")
            self.ui.print_system_info("   (Type your dialogue to continue...)")
            return "continue"

        # --- 2. STATE PHASE (Status Effects) ---
        states_config = self.attributes.get("states", {})
        current_status = self.npc_state.get("status", "NORMAL")
        state_config = states_config.get(current_status)
        auto_success = False

        if state_config and self.npc_state.get("duration", 0) > 0:
            duration = self.npc_state["duration"]
            description = state_config.get("description", current_status)
            effect = state_config.get("effect")

            if effect == "skip_generation":
                self.ui.print_state_effect(current_status, duration, description)
                self.ui.print_npc_response("Shadowheart", state_config.get("message", ""))
                self._tick_state()
                return "skip_generation"

            if effect == "auto_success":
                auto_success = True
                self.ui.print_state_effect(current_status, duration, description)
                self._tick_state()

        # --- 3. DM PHASE (Intent Analysis) ---
        action_type = "NONE"
        dc = 0
        try:
            with self.ui.create_spinner("[dm]🎲 DM is analyzing fate...[/dm]", spinner="dots"):
                intent_data = analyze_intent(user_input)
            action_type = intent_data["action_type"]
            dc = intent_data["difficulty_class"]
            self.ui.print_dm_analysis(action_type, dc)
        except Exception as e:
            self.ui.print_error(f"⚠️ [DM] Analysis failed: {e}")

        # Passive Rules Override
        rule_dc = mechanics.calculate_passive_dc(action_type, self.attributes)
        if rule_dc is not None:
            dc = rule_dc
            self.ui.print_system_info(f"🛡️ DC Auto-Calculated: {dc} (Stats)")

        # --- 4. MECHANICS PHASE (Rolling) ---
        system_info = None
        turn_count = len(self.conversation_history) // 2 + 1

        if action_type != "NONE" and dc > 0:
            if auto_success:
                system_info = f"Action: {action_type} | Result: CRITICAL SUCCESS (Auto)."
                self.ui.print_auto_success(action_type)
                self._update_relationship(1)
            elif self.player_data:
                # Calculate Modifiers
                ability_name = mechanics.get_ability_for_action(action_type)
                player_scores = self.player_data.get("ability_scores", {})

                if ability_name in player_scores:
                    modifier = mechanics.calculate_ability_modifier(player_scores[ability_name])

                    # Situational Bonuses
                    bonus, reason = mechanics.get_situational_bonus(
                        self.conversation_history, action_type, self.situational_bonuses, self.flags, user_input
                    )
                    if bonus != 0:
                        modifier += bonus
                        self.ui.print_situational_bonus(bonus, reason)

                    # Roll
                    roll_type = mechanics.determine_roll_type(action_type, self.relationship_score)
                    self.ui.print_advantage_alert(action_type, roll_type)
                    result = roll_d20(dc, modifier, roll_type=roll_type)
                    self.ui.print_roll_result(result)

                    # Critical Effects
                    if result["result_type"] == CheckResult.CRITICAL_SUCCESS:
                        self._set_state("VULNERABLE", 3)
                        self.ui.print_critical_state_change(CheckResult.CRITICAL_SUCCESS, "VULNERABLE", 3)
                    elif result["result_type"] == CheckResult.CRITICAL_FAILURE:
                        self._set_state("SILENT", 2)
                        self.ui.print_critical_state_change(CheckResult.CRITICAL_FAILURE, "SILENT", 2)

                    system_info = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."

        # --- 5. TRIGGER PHASE (Flags & Events) ---
        trigger_messages = mechanics.process_dialogue_triggers(
            user_input, self.dialogue_triggers, self.flags, self.ui, self.player_inventory, self.character.inventory
        )
        for msg in trigger_messages:
            self.journal.add_entry(msg, turn_count)

        # --- 6. GENERATION PHASE (LLM) ---
        # Prepare context for AI
        context_input = f"[SYSTEM INFO: {system_info}]\n\n{user_input}" if system_info else user_input
        return self._generate_reaction(user_input=context_input, original_input=user_input)

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
