from typing import Optional, Dict, Any
from core import mechanics
from core.dice import roll_d20
from core.inventory import Inventory, get_registry
from core.journal import Journal


class InputHandler:
    """
    Handles player slash-commands (e.g., /give, /use, /roll).
    Decouples command logic from the main game loop.
    """

    def __init__(self, ui):
        self.ui = ui

    def handle(self,
               user_input: str,
               context: Dict[str, Any]) -> Optional[str]:
        """
        Process user input if it is a command.

        Args:
            user_input: The raw input string.
            context: A dictionary containing game state required for commands:
                     - 'attributes': NPC attributes (for stats/checks)
                     - 'player_data': Player profile
                     - 'player_inventory': Player's Inventory object
                     - 'npc_inventory': NPC's Inventory object
                     - 'journal': Journal object
                     - 'turn_count': Current turn number
                     - 'relationship_score': Current relationship
                     - 'action_type': Current DM-analyzed action (for roll context)

        Returns:
            - None: If input is NOT a command.
            - str: The result string (System Message or Log) to be fed into the LLM/Journal.
                   Returns error strings directly to UI without returning to LLM.
        """
        if not user_input.startswith('/'):
            return None

        parts = user_input.split()
        command = parts[0].lower()

        # Extract context
        player_inv: Inventory = context.get('player_inventory')
        npc_inv: Inventory = context.get('npc_inventory')
        journal: Journal = context.get('journal')
        turn_count: int = context.get('turn_count', 0)

        # --- COMMAND: /GIVE <ITEM> ---
        if command == '/give':
            if len(parts) < 2:
                self.ui.print_error("❌ Usage: /give <item_key>")
                return "Command error: Missing item key."

            item_key = parts[1].strip()
            if not player_inv or not player_inv.has(item_key):
                self.ui.print_error(f"❌ You don't have '{item_key}'.")
                return "You don't have that item."

            # Transfer logic
            player_inv.remove(item_key)
            if npc_inv:
                npc_inv.add(item_key)

            # Log & Return System Message
            journal.add_entry(f"Player gave '{item_key}' to Shadowheart.", turn_count)
            return f"[SYSTEM] Player gave you: {item_key}. It is now in your [CURRENT INVENTORY]."

        # --- COMMAND: /USE <ITEM> ---
        elif command == '/use':
            if len(parts) < 2:
                self.ui.print_error("❌ Usage: /use <item_key>")
                return "Command error: Missing item key."

            item_key = parts[1].strip()
            if not player_inv or not player_inv.has(item_key):
                self.ui.print_error(f"❌ You don't have '{item_key}'.")
                return "You don't have that item."

            # Data-Driven Effect Logic
            registry = get_registry()
            item_data = registry.get(item_key)

            # Apply effect using mechanics engine
            effect_result = mechanics.apply_item_effect(item_key, item_data)

            # Remove item (consume it)
            player_inv.remove(item_key)

            # Log result
            log_msg = f"Player used {item_key}. Effect: {effect_result['message']}"
            journal.add_entry(log_msg, turn_count)

            # UI Feedback
            self.ui.print_action_effect(f"You used {item_key}: {effect_result['message']}")

            # Return system message for AI to react
            return f"[SYSTEM] Player used item: {item_key}. ({effect_result['message']})"

        # --- COMMAND: /ROLL <ABILITY> <DC> ---
        elif command == '/roll':
            if len(parts) < 3:
                self.ui.print_error("❌ Usage: /roll <ability> <dc>")
                return "Command error: Invalid args."

            ability_name = parts[1]
            try:
                dc = int(parts[2])
            except ValueError:
                self.ui.print_error("❌ DC must be a number.")
                return "Command error: DC not a number."

            normalized_ability = mechanics.normalize_ability_name(ability_name)
            if not normalized_ability:
                self.ui.print_error(f"❌ Unknown ability: {ability_name}")
                return "Command error: Unknown ability."

            # Use NPC attributes for stats (matching original logic),
            # or could switch to player_data if implemented.
            attributes = context.get('attributes', {})
            ability_scores = attributes.get('ability_scores', {})

            if normalized_ability not in ability_scores:
                self.ui.print_error(f"❌ Character missing stat: {normalized_ability}")
                return "Command error: Missing stat."

            ability_score = ability_scores[normalized_ability]
            modifier = mechanics.calculate_ability_modifier(ability_score)

            # Determine advantage/disadvantage
            action_type = context.get('action_type', 'NONE')
            relationship_score = context.get('relationship_score', 0)
            roll_type = mechanics.determine_roll_type(action_type, relationship_score)

            self.ui.print_advantage_alert(action_type, roll_type)

            # Execute Roll
            result = roll_d20(dc, modifier, roll_type=roll_type)
            self.ui.print_roll_result(result)

            return f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."

        else:
            self.ui.print_error(f"❌ Unknown command: {command}")
            return "Unknown command."
