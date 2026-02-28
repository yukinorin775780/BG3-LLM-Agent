"""
BG3 LLM Agent - V1 Main Entry Point (Archived)
Pre-LangGraph era. Uses MemoryManager and InputHandler.
"""

import os
import sys
from typing import Optional
from config import settings
from characters.loader import load_character
from core.dice import CheckResult, roll_d20
from core.dm import analyze_intent
from core import mechanics
from core import quest
from core import inventory
from core.journal import Journal
from ui.renderer import GameRenderer
from core.graph_builder import build_graph
from core.graph_state import GameState

# V1 Legacy imports (from same package)
from archive.v1_legacy.engine import generate_dialogue, parse_ai_response, update_summary
from archive.v1_legacy.memory import MemoryManager
from archive.v1_legacy.input_handler import InputHandler

CHARACTER_NAME = "shadowheart"


def load_player_profile():
    player_file = os.path.join(settings.SAVE_DIR, "player.json")
    if not os.path.exists(player_file):
        return {"name": "Tav", "race": "Human", "class": "Adventurer", "level": 1, "ability_scores": {}}
    import json
    with open(player_file, "r", encoding="utf-8") as f:
        return json.load(f)


class GameSession:
    """V1 Game Session - uses LangGraph but with MemoryManager/InputHandler."""

    def __init__(self, ui, input_handler, player_data, character, attributes,
                 situational_bonuses, dialogue_triggers, quests_config, player_inventory):
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
        self._graph_thread_id = "shadowheart_default"
        self.relationship_score = 0
        self.conversation_history: list = []
        self.npc_state = {"status": "NORMAL", "duration": 0}
        self.flags: dict = {}
        self.summary = ""
        self.journal = Journal()
        self.running = True

    def init_from_memory(self, memory_data: dict) -> None:
        self._graph_thread_id = memory_data.get("thread_id", "shadowheart_default")
        self.relationship_score = memory_data.get("relationship_score", 0)
        self.conversation_history = memory_data.get("history", [])
        self.npc_state = memory_data.get("npc_state", {"status": "NORMAL", "duration": 0})
        self.flags = memory_data.get("flags", {})
        self.summary = memory_data.get("summary", "")
        self.journal = Journal.from_dict(memory_data.get("journal"))
        saved_player_inv = memory_data.get("inventory_player", {})
        saved_npc_inv = memory_data.get("inventory_npc", {})
        if saved_player_inv:
            self.player_inventory.from_dict(saved_player_inv)
        if saved_npc_inv:
            self.character.inventory.from_dict(saved_npc_inv)

    def build_memory_data(self) -> dict:
        return {
            "thread_id": self._graph_thread_id,
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
        if not user_input:
            return "continue"
        if user_input.lower() in ["quit", "exit", "退出", "q"]:
            self.running = False
            return "quit"

        state_payload: GameState = {
            "messages": self.conversation_history,
            "user_input": user_input,
            "character_name": self.attributes["name"],
            "relationship": self.relationship_score,
            "npc_state": self.npc_state,
            "player_inventory": self.player_inventory.to_dict(),
            "npc_inventory": self.character.inventory.to_dict(),
            "flags": self.flags,
            "journal_events": [],
        }

        config = {"configurable": {"thread_id": self._graph_thread_id}}
        try:
            with self.ui.create_spinner("[brain]Shadowheart is thinking (Graph V3)...[/brain]", spinner="dots"):
                result = self.graph.invoke(state_payload, config=config)
        except Exception as e:
            self.ui.print_error(f"Graph Error: {e}")
            return "continue"

        for event in result.get("journal_events", []):
            self.ui.print_system_info(f"🎲 {event}")
            self.journal.add_entry(event, len(self.conversation_history) // 2)

        if result.get("thought_process"):
            self.ui.print_inner_thought(result["thought_process"])

        if result.get("final_response"):
            self.ui.print_npc_response("Shadowheart", result["final_response"])

        self.relationship_score = result.get("relationship", self.relationship_score)
        self.npc_state = result.get("npc_state", self.npc_state)
        self.flags = result.get("flags", self.flags)

        if "player_inventory" in result:
            self.player_inventory.from_dict(result["player_inventory"])
        if "npc_inventory" in result:
            self.character.inventory.from_dict(result["npc_inventory"])

        self.conversation_history.append({"role": "user", "content": user_input})
        if result.get("final_response"):
            self.conversation_history.append({"role": "assistant", "content": result["final_response"]})

        return "continue"


def main():
    ui = GameRenderer()
    ui.clear_screen()
    ui.show_title("BG3 LLM Agent - Refactored Engine")

    memory_mgr = MemoryManager()
    inventory.init_registry("config/items.yaml")

    try:
        player_data = load_player_profile()
        character = load_character(CHARACTER_NAME)
        attributes = character.data
        memory_data = memory_mgr.load(default_relationship=attributes.get("relationship", 0))
        ui.print_system_info(f"✓ System Ready. Character: {attributes['name']}")
    except Exception as e:
        ui.print_error(f"❌ Initialization Failed: {e}")
        return

    input_handler = InputHandler(ui)
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

    session.init_from_memory(memory_data)

    if memory_data.get("history"):
        ui.print_system_info(f"🧠 Memories loaded. Relationship: {session.relationship_score}")

    ui.print_rule("💬 Start Game (Type '/use healing_potion' to test items)", style="info")

    while session.running:
        try:
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

            memory_mgr.save(session.build_memory_data())

        except KeyboardInterrupt:
            break
        except Exception as e:
            ui.print_error(f"❌ Runtime Error: {e}")
            import traceback
            traceback.print_exc()

    memory_mgr.save(session.build_memory_data())
    ui.print("\n[info]Game Saved. Goodbye![/info]")


if __name__ == "__main__":
    main()
