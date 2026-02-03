"""
BG3 LLM Agent - Main Entry Point (Controller Layer)
Orchestrates game flow using Model (mechanics) and View (renderer) layers
"""

import os
import sys
import json
from typing import Optional
from config import settings
from characters.loader import load_character
from core.engine import generate_dialogue, parse_ai_response, update_summary
from core.dice import roll_d20, CheckResult
from core.dm import analyze_intent
from core import mechanics
from core import quest
from core import inventory
from core.journal import Journal
from ui.renderer import GameRenderer

# 定义记忆文件保存的位置
MEMORY_FILE = os.path.join(settings.SAVE_DIR, "shadowheart_memory.json")

# 角色名称
CHARACTER_NAME = "shadowheart"


def handle_command(user_input: str, attributes: dict, ui: GameRenderer, relationship_score: int = 0, action_type: str = 'NONE') -> Optional[str]:
    """
    Handle user commands (commands starting with '/').
    
    Supported commands:
    - /roll <ability> <dc>: Roll a D20 check with the specified ability modifier
    
    Args:
        user_input: The user's input string
        attributes: Character attributes dictionary containing ability_scores
        ui: GameRenderer instance for UI output
        relationship_score: Current relationship score (for determining advantage/disadvantage)
        action_type: Current action type from DM analysis (for determining advantage/disadvantage)
    
    Returns:
        Optional[str]: Roll result narrative string if a roll occurred, None otherwise
    """
    if not user_input.startswith('/'):
        return None
    
    parts = user_input.split()
    if len(parts) < 2:
        ui.print_error("❌ 命令格式错误。用法: /roll <ability> <dc>")
        ui.print_system_info("   例如: /roll wis 12 或 /roll cha 15")
        return None
    
    command = parts[0].lower()
    
    if command == '/roll':
        if len(parts) < 3:
            ui.print_error("❌ /roll 命令需要两个参数: <ability> <dc>")
            ui.print_system_info("   例如: /roll wis 12 或 /roll cha 15")
            return None
        
        ability_name = parts[1]
        try:
            dc = int(parts[2])
        except ValueError:
            ui.print_error(f"❌ DC 必须是数字，收到: {parts[2]}")
            return None
        
        # Normalize ability name
        normalized_ability = mechanics.normalize_ability_name(ability_name)
        if not normalized_ability:
            ui.print_error(f"❌ 未知的能力值: {ability_name}")
            ui.print_system_info("   支持的能力值: STR, DEX, CON, INT, WIS, CHA")
            return None
        
        # Get ability score and calculate modifier
        ability_scores = attributes.get('ability_scores', {})
        if normalized_ability not in ability_scores:
            ui.print_error(f"❌ 角色没有 {normalized_ability} 能力值")
            return None
        
        ability_score = ability_scores[normalized_ability]
        modifier = mechanics.calculate_ability_modifier(ability_score)
        
        # Determine roll type based on relationship and action
        roll_type = mechanics.determine_roll_type(action_type, relationship_score)
        
        # Visual feedback for advantage/disadvantage
        ui.print_advantage_alert(action_type, roll_type)
        
        # Roll the dice
        result = roll_d20(dc, modifier, roll_type=roll_type)
        
        # Print the result
        ui.print_roll_result(result)
        
        # Generate narrative result string for LLM injection
        roll_summary = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."
        return roll_summary
    
    else:
        ui.print_error(f"❌ 未知命令: {command}")
        ui.print_system_info("   支持的命令: /roll")
        return None




def load_memory(default_relationship_score=0, ui: Optional[GameRenderer] = None):
    """
    从本地文件读取记忆，支持优先级系统。
    
    优先级（从高到低）：
    1. 记忆文件中的 relationship_score（如果存在）
    2. 传入的 default_relationship_score（通常来自 YAML 配置）
    3. 默认值 0
    
    Args:
        default_relationship_score: 默认关系值，通常从 YAML 配置文件中读取
        ui: Optional GameRenderer instance for UI output
    
    Returns:
        dict: 包含 relationship_score 和 history 的字典
    """
    # 尝试从记忆文件读取
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # 如果是空文件，使用默认值
                    if ui:
                        ui.print_system_info(f"🧠 记忆文件为空，使用 YAML 配置的关系值: {default_relationship_score}")
                    return {
                        "relationship_score": default_relationship_score,
                        "history": [],
                        "npc_state": {"status": "NORMAL", "duration": 0},
                        "flags": {},
                        "summary": "",
                        "inventory_player": {},
                        "inventory_npc": {},
                        "journal": []
                    }
                
                data = json.loads(content)
                
                # 向后兼容：如果文件是列表格式（旧格式），转换为新格式
                if isinstance(data, list):
                    if ui:
                        ui.print_system_info("🧠 检测到旧格式记忆文件，正在转换...")
                        ui.print_system_info(f"💕 使用 YAML 配置的关系值: {default_relationship_score}")
                    return {
                        "relationship_score": default_relationship_score,
                        "history": data,
                        "npc_state": {"status": "NORMAL", "duration": 0},
                        "flags": {},
                        "summary": "",
                        "inventory_player": {},
                        "inventory_npc": {},
                        "journal": []
                    }
                
                # 新格式：包含 relationship_score 和 history
                if isinstance(data, dict):
                    # 优先使用记忆文件中的关系值，如果没有则使用默认值
                    relationship_score = data.get("relationship_score")
                    if relationship_score is None:
                        # 记忆文件中没有关系值，使用 YAML 配置的值
                        relationship_score = default_relationship_score
                        if ui:
                            ui.print_system_info(f"🧠 记忆文件中没有关系值，使用 YAML 配置: {relationship_score}")
                    else:
                        # 使用记忆文件中的关系值（最高优先级）
                        if ui:
                            ui.print_system_info(f"🧠 成功唤醒记忆，共读取 {len(data.get('history', []))} 条往事...")
                            ui.print_system_info(f"💕 当前关系值（来自记忆）: {relationship_score}/100")
                    
                    history = data.get("history", [])
                    # Get npc_state or use default
                    npc_state = data.get("npc_state", {"status": "NORMAL", "duration": 0})
                    flags = data.get("flags", {})
                    summary = data.get("summary", "")
                    # Get inventory data for persistence
                    inventory_player = data.get("inventory_player", {})
                    inventory_npc = data.get("inventory_npc", {})
                    journal = data.get("journal", [])
                    return {
                        "relationship_score": relationship_score,
                        "history": history,
                        "npc_state": npc_state,
                        "flags": flags,
                        "summary": summary,
                        "inventory_player": inventory_player,
                        "inventory_npc": inventory_npc,
                        "journal": journal
                    }
                
                # 如果格式不对，使用默认值
                if ui:
                    ui.print_warning(f"⚠️ 记忆文件格式错误，使用 YAML 配置的关系值: {default_relationship_score}")
                return {
                    "relationship_score": default_relationship_score,
                    "history": [],
                    "npc_state": {"status": "NORMAL", "duration": 0},
                    "flags": {},
                    "summary": "",
                    "inventory_player": {},
                    "inventory_npc": {},
                    "journal": []
                }
                
        except Exception as e:
            # 记忆文件读取失败，使用 YAML 配置的值
            if ui:
                ui.print_warning(f"⚠️ 记忆文件读取失败，使用 YAML 配置的关系值: {default_relationship_score} ({e})")
            return {
                "relationship_score": default_relationship_score,
                "history": [],
                "npc_state": {"status": "NORMAL", "duration": 0},
                "flags": {},
                "summary": "",
                "inventory_player": {},
                "inventory_npc": {},
                "journal": []
            }
    
    # 记忆文件不存在，使用 YAML 配置的值
    if ui:
        ui.print_system_info(f"🧠 未找到记忆文件，使用 YAML 配置的关系值: {default_relationship_score}")
    return {
        "relationship_score": default_relationship_score,
        "history": [],
        "npc_state": {"status": "NORMAL", "duration": 0},
        "flags": {},
        "summary": "",
        "inventory_player": {},
        "inventory_npc": {},
        "journal": []
    }


def save_memory(memory_data, ui: Optional[GameRenderer] = None):
    """把记忆写入本地文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        if ui:
            ui.print_system_info("💾 记忆已固化至莎尔的卷轴中。")
    except Exception as e:
        if ui:
            ui.print_error(f"❌ 存档失败: {e}")


def load_player_profile():
    """
    Load player profile from data/player.json.
    
    Returns:
        dict: Player profile data
    
    Raises:
        FileNotFoundError: If player.json doesn't exist
        json.JSONDecodeError: If JSON is malformed
    """
    player_file = os.path.join(settings.SAVE_DIR, "player.json")
    if not os.path.exists(player_file):
        raise FileNotFoundError(f"Player profile not found: {player_file}")
    
    with open(player_file, 'r', encoding='utf-8') as f:
        player_data = json.load(f)
    
    return player_data


class GameSession:
    """
    Holds game state and handles one turn of input. Keeps main loop clean.
    """

    def __init__(
        self,
        ui: GameRenderer,
        player_data: Optional[dict],
        character,
        attributes: dict,
        situational_bonuses: list,
        dialogue_triggers: list,
        quests_config: list,
        player_inventory: inventory.Inventory,
    ):
        self.ui = ui
        self.player_data = player_data
        self.character = character
        self.attributes = attributes
        self.situational_bonuses = situational_bonuses
        self.dialogue_triggers = dialogue_triggers
        self.quests_config = quests_config
        self.player_inventory = player_inventory

        self.relationship_score = 0
        self.conversation_history: list = []
        self.npc_state = {"status": "NORMAL", "duration": 0}
        self.flags: dict = {}
        self.summary = ""
        self.journal = Journal()
        self.running = True

    def init_from_memory(self, memory_data: dict) -> None:
        """Load state from memory dict. Handles missing 'journal' gracefully."""
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
        """Build dict for save_memory. Journal saved via to_dict()."""
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

        if user_input.startswith("/"):
            roll_result = handle_command(
                user_input, self.attributes, self.ui, self.relationship_score, "NONE"
            )
            if roll_result is not None:
                self.ui.print_system_info("💡 Roll result stored. Type your dialogue to use it.")
            return "continue"

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
                new_status, new_duration = mechanics.update_npc_state(
                    self.npc_state["status"], self.npc_state["duration"]
                )
                self.npc_state["status"] = new_status
                self.npc_state["duration"] = new_duration
                if new_status == "NORMAL":
                    self.ui.print_state_effect("NORMAL", 0, "状态恢复")
                return "skip_generation"

            if effect == "auto_success":
                auto_success = True
                self.ui.print_state_effect(current_status, duration, description)
                new_status, new_duration = mechanics.update_npc_state(
                    self.npc_state["status"], self.npc_state["duration"]
                )
                self.npc_state["status"] = new_status
                self.npc_state["duration"] = new_duration
                if new_status == "NORMAL":
                    self.ui.print_state_effect("NORMAL", 0, "状态恢复")

        # DM analysis
        try:
            with self.ui.create_spinner("[dm]🎲 DM is analyzing fate...[/dm]", spinner="dots"):
                intent_data = analyze_intent(user_input)
            action_type = intent_data["action_type"]
            dc = intent_data["difficulty_class"]
            self.ui.print_dm_analysis(action_type, dc)
        except Exception as e:
            self.ui.print_error(f"⚠️ [DM] 意图分析失败: {e}")
            action_type = "NONE"
            dc = 0

        rule_dc = mechanics.calculate_passive_dc(action_type, self.attributes)
        if rule_dc is not None:
            dc = rule_dc
            self.ui.print_system_info(f"🛡️ DC Auto-Calculated: {dc} (Based on Shadowheart's Stats)")

        system_info = None
        turn_count = len(self.conversation_history) // 2 + 1

        if action_type != "NONE" and dc > 0:
            if auto_success:
                system_info = f"Action: {action_type} | Result: CRITICAL SUCCESS (Auto). She is vulnerable."
                self.ui.print_auto_success(action_type)
                self.journal.add_entry(
                    f"Player rolled CRITICAL SUCCESS (Auto) on [{action_type}]!", turn_count
                )
                self.relationship_score += 1
                self.relationship_score = max(-100, min(100, self.relationship_score))
                self.ui.print_system_info("💕 Relationship +1 (Vulnerable State Bonus)")
            elif self.player_data is None:
                self.ui.print_error("⚠️ Player profile not loaded. Cannot perform auto-roll.")
            else:
                ability_name = mechanics.get_ability_for_action(action_type)
                player_ability_scores = self.player_data.get("ability_scores", {})
                if ability_name not in player_ability_scores:
                    self.ui.print_error(f"⚠️ Player doesn't have {ability_name} ability score.")
                else:
                    ability_score = player_ability_scores[ability_name]
                    modifier = mechanics.calculate_ability_modifier(ability_score)
                    bonus, reason = mechanics.get_situational_bonus(
                        self.conversation_history,
                        action_type,
                        self.situational_bonuses,
                        self.flags,
                        user_input,
                    )
                    if bonus != 0:
                        modifier += bonus
                        self.ui.print_situational_bonus(bonus, reason)
                    roll_type = mechanics.determine_roll_type(action_type, self.relationship_score)
                    self.ui.print_advantage_alert(action_type, roll_type)
                    result = roll_d20(dc, modifier, roll_type=roll_type)
                    self.ui.print_roll_result(result)

                    if result["result_type"] == CheckResult.CRITICAL_SUCCESS:
                        self.npc_state = {"status": "VULNERABLE", "duration": 3}
                        self.ui.print_critical_state_change(
                            CheckResult.CRITICAL_SUCCESS, "VULNERABLE", 3
                        )
                        self.journal.add_entry(
                            f"Player rolled CRITICAL SUCCESS on [{action_type}]! (Rolled {result['total']} vs DC {dc})",
                            turn_count,
                        )
                    elif result["result_type"] == CheckResult.CRITICAL_FAILURE:
                        self.npc_state = {"status": "SILENT", "duration": 2}
                        self.ui.print_critical_state_change(
                            CheckResult.CRITICAL_FAILURE, "SILENT", 2
                        )
                        self.journal.add_entry(
                            f"Player rolled CRITICAL FAILURE on [{action_type}]! (Rolled {result['total']} vs DC {dc})",
                            turn_count,
                        )
                    system_info = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."

        trigger_messages = mechanics.process_dialogue_triggers(
            user_input,
            self.dialogue_triggers,
            self.flags,
            ui=self.ui,
            player_inv=self.player_inventory,
            npc_inv=self.character.inventory,
        )
        for msg in trigger_messages:
            self.ui.print_system_info(msg)
            self.journal.add_entry(msg, turn_count)

        journal_data = self.journal.get_recent_entries(5)
        inventory_data = self.character.inventory.list_item_names()
        system_prompt = self.character.render_prompt(
            self.relationship_score,
            flags=self.flags,
            summary=self.summary,
            journal_entries=journal_data,
            inventory_items=inventory_data,
        )
        messages_to_send = self.conversation_history.copy()
        if system_info is not None:
            user_content_for_llm = f"[SYSTEM INFO: {system_info}]\n\n{user_input}"
        else:
            user_content_for_llm = user_input
        messages_to_send.append({"role": "user", "content": user_content_for_llm})

        with self.ui.create_spinner("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
            response = generate_dialogue(system_prompt, conversation_history=messages_to_send)

        parsed = parse_ai_response(response)
        approval_change = parsed["approval"]
        new_state = parsed["new_state"]
        cleaned_response = parsed["cleaned_text"]

        if approval_change != 0:
            self.relationship_score += approval_change
            self.relationship_score = max(-100, min(100, self.relationship_score))
            self.ui.print_relationship_change(approval_change, self.relationship_score)

        if new_state and new_state != self.npc_state["status"]:
            self.npc_state["status"] = new_state
            self.npc_state["duration"] = 3
            self.ui.print_state_effect(
                new_state, 3, f"Shadowheart decided to change state to {new_state}!"
            )
            self.journal.add_entry(
                f"Shadowheart chose to enter state: {new_state} (duration 3).",
                turn_count,
            )

        if cleaned_response:
            self.ui.print_npc_response("Shadowheart", cleaned_response)
        else:
            self.ui.print_npc_response("Shadowheart", "（没有回应）")

        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": cleaned_response})

        if len(self.conversation_history) > settings.MAX_HISTORY:
            messages_to_summarize = self.conversation_history[:4]
            with self.ui.create_spinner("📝 Consolidating memories...", spinner="dots"):
                self.summary = update_summary(self.summary, messages_to_summarize)
            self.conversation_history = self.conversation_history[4:]
            self.ui.print_system_info(
                f"🧠 Memory Consolidated: {self.summary[:100]}..."
                if len(self.summary) > 100
                else f"🧠 Memory Consolidated: {self.summary}"
            )

        return None  # turn done


def main():
    """Main function to load attributes and generate dialogue"""
    # Initialize UI renderer
    ui = GameRenderer()
    
    # Clear screen and show title
    ui.clear_screen()
    ui.show_title("BG3 LLM Agent - Shadowheart Dialogue Generator")
    
    # Load player profile
    with ui.create_spinner("[info]Loading player profile...[/info]", spinner="dots"):
        try:
            player_data = load_player_profile()
            ui.print_system_info(f"✓ Loaded player profile: {player_data['name']}")
            ui.print(f"  - {player_data['race']} {player_data['class']} (Level {player_data['level']})")
            ui.print()
        except Exception as e:
            ui.print_error(f"⚠️ Failed to load player profile: {e}")
            ui.print_system_info("  Continuing without player profile...")
            player_data = None
            ui.print()
    
    # Initialize Item Registry and Player Inventory
    inventory.init_registry("config/items.yaml")
    player_inventory = inventory.Inventory()
    player_inventory.add("healing_potion", 2)  # Start with 2 healing potions
    player_inventory.add("gold_coin", 10)      # Start with 10 gold coins
    
    # Load character
    with ui.create_spinner("[info]Loading Shadowheart's attributes...[/info]", spinner="dots"):
        character = load_character(CHARACTER_NAME)
        attributes = character.data  # 保留对原始数据的引用，用于显示
        situational_bonuses = attributes.get('situational_bonuses', [])
        dialogue_triggers = attributes.get('dialogue_triggers', [])
        quests_config = character.quests
    ui.print_system_info(f"✓ Loaded attributes for {attributes['name']}")
    ui.print(f"  - {attributes['race']} {attributes['class']} (Level {attributes['level']})")
    ui.print(f"  - Deity: {attributes['deity']}")
    ui.print()
    
    # Display key attributes
    ui.print_system_info("Key Attributes:")
    ability_modifiers = mechanics.get_ability_modifiers(attributes['ability_scores'])
    for ability, score in attributes['ability_scores'].items():
        modifier = ability_modifiers[ability]
        ui.print(f"  {ability}: {score} (+{modifier:+d})")
    ui.print()
    
    # Generate initial greeting
    try:
        # 1. 【关键修改】启动时尝试加载旧记忆
        # 优先级：记忆文件 > YAML 配置 > 默认值 0
        # 从 YAML 配置中获取初始关系值作为默认值
        default_relationship = attributes.get("relationship", 0)
        memory_data = load_memory(default_relationship_score=default_relationship, ui=ui)

        session = GameSession(
            ui=ui,
            player_data=player_data,
            character=character,
            attributes=attributes,
            situational_bonuses=situational_bonuses,
            dialogue_triggers=dialogue_triggers,
            quests_config=quests_config,
            player_inventory=player_inventory,
        )
        session.init_from_memory(memory_data)

        if memory_data.get("inventory_player"):
            ui.print_system_info(
                f"🎒 Player inventory restored: {player_inventory.count_unique_items()} item types"
            )
        if memory_data.get("inventory_npc"):
            ui.print_system_info(
                f"🎒 NPC inventory restored: {character.inventory.count_unique_items()} item types"
            )

        journal_data = session.journal.get_recent_entries(5)
        inventory_data = character.inventory.list_item_names()
        system_prompt = character.render_prompt(
            session.relationship_score,
            flags=session.flags,
            summary=session.summary,
            journal_entries=journal_data,
            inventory_items=inventory_data,
        )
        player_name = player_data["name"] if player_data else "Unknown"
        active_quests = quest.QuestManager.check_quests(quests_config, session.flags)
        ui.print(
            ui.show_dashboard(
                player_name,
                attributes["name"],
                session.relationship_score,
                session.npc_state,
                active_quests,
                player_inventory,
                character.inventory,
                session.journal.get_recent_entries(3),
            )
        )
        ui.print()

        if not session.conversation_history:
            with ui.create_spinner("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
                dialogue = generate_dialogue(
                    system_prompt, conversation_history=session.conversation_history
                )
            parsed = parse_ai_response(dialogue)
            session.relationship_score += parsed["approval"]
            session.relationship_score = max(-100, min(100, session.relationship_score))
            if parsed["new_state"] and parsed["new_state"] != session.npc_state["status"]:
                session.npc_state["status"] = parsed["new_state"]
                session.npc_state["duration"] = 3
                ui.print_state_effect(
                    parsed["new_state"], 3,
                    f"Shadowheart decided to change state to {parsed['new_state']}!",
                )
                session.journal.add_entry(
                    f"Shadowheart chose to enter state: {parsed['new_state']} (duration 3).",
                    1,
                )
            cleaned_dialogue = parsed["cleaned_text"]
            ui.print_npc_response("Shadowheart", cleaned_dialogue, "Looking at you warily")
            session.conversation_history.append({"role": "assistant", "content": cleaned_dialogue})
        else:
            ui.print_npc_response(
                "Shadowheart", "*Nods slightly acknowledging your return*", "Remembers you"
            )

        ui.print_rule("💬 开始与影心对话（输入 'quit' 或 'exit' 退出并存档）", style="info")

        while session.running:
            try:
                active_quests = quest.QuestManager.check_quests(quests_config, session.flags)
                ui.print(
                    ui.show_dashboard(
                        player_name,
                        attributes["name"],
                        session.relationship_score,
                        session.npc_state,
                        active_quests,
                        player_inventory,
                        character.inventory,
                        session.journal.get_recent_entries(3),
                    )
                )
                ui.print()

                user_input = ui.input_prompt()
                result = session.turn(user_input)

                if result == "quit":
                    save_memory(session.build_memory_data(), ui=ui)
                    ui.print("\n[info]再见！[/info]")
                    break
                if result == "skip_generation":
                    save_memory(session.build_memory_data(), ui=ui)
                    continue
                if result == "continue":
                    continue

                save_memory(session.build_memory_data(), ui=ui)

            except KeyboardInterrupt:
                save_memory(session.build_memory_data(), ui=ui)
                ui.print("\n\n[info]再见！[/info]")
                break
            except Exception as e:
                ui.print(f"\n[error]❌ 错误: {e}[/error]")
                ui.print_system_info("请重试...\n")
        
    except ImportError as e:
        ui.print_error(f"❌ 导入错误: {e}")
        ui.print_system_info("\n请安装必要的依赖包:")
        ui.print("  pip install dashscope python-dotenv rich")
        
        ui.print_system_info("\n要使用百炼 API，你需要:")
        ui.print("1. 安装 dashscope 包: pip install dashscope")
        ui.print("2. 在项目根目录创建 .env 文件")
        ui.print("3. 添加你的 API key: BAILIAN_API_KEY=your-api-key")
        ui.print_system_info("\n或者使用模拟响应进行测试:")
        
        # Fallback mock dialogue
        ui.print()
        ui.print_rule("Mock Dialogue (API not configured)", style="info")
        ui.print_npc_response("Shadowheart", 
            'Shar\'s will be done. I sense there\'s more to you than meets the eye, '
            'just as there is more to me. Trust is earned, not given freely.')
        ui.print_rule("", style="info")
        
    except Exception as e:
        ui.print_error(f"❌ 意外错误: {e}")
        ui.print_error(f"错误类型: {type(e).__name__}")
        import traceback
        ui.print_error("\n详细错误信息:")
        ui.print(traceback.format_exc())


if __name__ == "__main__":
    main()

