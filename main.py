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
from core.engine import generate_dialogue, parse_approval_change, update_summary
from core.dice import roll_d20, CheckResult
from core.dm import analyze_intent
from core import mechanics
from core import quest
from core import inventory
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
                        "summary": ""
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
                        "summary": ""
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
                    return {
                        "relationship_score": relationship_score,
                        "history": history,
                        "npc_state": npc_state,
                        "flags": flags,
                        "summary": summary
                    }
                
                # 如果格式不对，使用默认值
                if ui:
                    ui.print_warning(f"⚠️ 记忆文件格式错误，使用 YAML 配置的关系值: {default_relationship_score}")
                return {
                    "relationship_score": default_relationship_score,
                    "history": [],
                    "npc_state": {"status": "NORMAL", "duration": 0},
                    "flags": {}
                }
                
        except Exception as e:
            # 记忆文件读取失败，使用 YAML 配置的值
            if ui:
                ui.print_warning(f"⚠️ 记忆文件读取失败，使用 YAML 配置的关系值: {default_relationship_score} ({e})")
            return {
                "relationship_score": default_relationship_score,
                "history": [],
                "npc_state": {"status": "NORMAL", "duration": 0},
                "flags": {}
            }
    
    # 记忆文件不存在，使用 YAML 配置的值
    if ui:
        ui.print_system_info(f"🧠 未找到记忆文件，使用 YAML 配置的关系值: {default_relationship_score}")
    return {
        "relationship_score": default_relationship_score,
        "history": [],
        "npc_state": {"status": "NORMAL", "duration": 0},
        "flags": {}
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
    
    # Initialize Player Inventory
    player_inventory = inventory.Inventory()
    player_inventory.add("Healing Potion")
    player_inventory.add("Gold Coin (10)")
    
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
        default_relationship = attributes.get('relationship', 0)
        memory_data = load_memory(default_relationship_score=default_relationship, ui=ui)
        relationship_score = memory_data["relationship_score"]
        conversation_history = memory_data["history"]
        npc_state = memory_data.get("npc_state", {"status": "NORMAL", "duration": 0})
        flags = memory_data.get("flags", {})
        summary = memory_data.get("summary", "")
        
        # 2. 生成 System Prompt（使用 Character 对象的 render_prompt 方法）
        system_prompt = character.render_prompt(relationship_score, flags=flags, summary=summary)
        
        # Display dashboard
        player_name = player_data['name'] if player_data else "Unknown"
        active_quests = quest.QuestManager.check_quests(quests_config, flags)
        ui.print(ui.show_dashboard(player_name, attributes['name'], relationship_score, npc_state, active_quests, player_inventory, character.inventory))
        ui.print()
        
        # 如果是新对话（没记忆），生成并打印开场白
        if not conversation_history:
            with ui.create_spinner("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
                # 生成初始问候（使用空的对话历史）
                dialogue = generate_dialogue(system_prompt, conversation_history=conversation_history)
            
            # 解析 approval change（初始问候通常不会有变化，但为了统一处理）
            approval_change, cleaned_dialogue = parse_approval_change(dialogue)
            
            # 更新关系值
            relationship_score += approval_change
            
            # 清理引号
            if cleaned_dialogue:
                cleaned_dialogue = cleaned_dialogue.strip('"').strip("'")
            
            # Display NPC dialogue in a panel
            ui.print_npc_response("Shadowheart", cleaned_dialogue, "Looking at you warily")
            
            # 把初始问候加入对话历史（存储清理后的文本）
            conversation_history.append({"role": "assistant", "content": cleaned_dialogue})
        else:
            # 如果有记忆，显示不同的开场白
            ui.print_npc_response("Shadowheart", "*Nods slightly acknowledging your return*", "Remembers you")
        
        # Start interactive conversation
        ui.print_rule("💬 开始与影心对话（输入 'quit' 或 'exit' 退出并存档）", style="info")
        
        while True:
            try:
                states_config = attributes.get('states', {})

                # Check quests and update dashboard
                active_quests = quest.QuestManager.check_quests(quests_config, flags)
                ui.print(ui.show_dashboard(player_name, attributes['name'], relationship_score, npc_state, active_quests, player_inventory, character.inventory))
                ui.print()
                
                # ==========================================
                # Step 1: Get User Input
                # ==========================================
                user_input = ui.input_prompt()
                
                if not user_input:
                    continue
                
                # ==========================================
                # Step 2: Command Interceptor
                # ==========================================
                if user_input.lower() in ['quit', 'exit', '退出', 'q']:
                    # Exit command
                    memory_data = {
                        "relationship_score": relationship_score,
                        "history": conversation_history,
                        "npc_state": npc_state,
                        "flags": flags,
                        "summary": summary
                    }
                    save_memory(memory_data, ui=ui)
                    ui.print("\n[info]再见！[/info]")
                    break
                
                if user_input.startswith('/'):
                    # Handle commands (e.g., /roll)
                    current_action = 'NONE'  # Commands don't use DM analysis
                    roll_result = handle_command(user_input, attributes, ui, relationship_score, current_action)
                    if roll_result is not None:
                        # Store the roll result for injection into next dialogue
                        ui.print_system_info("💡 Roll result stored. Type your dialogue to use it.")
                    continue  # Skip the rest of the loop for commands
                
                # ==========================================
                # Step 3: STATE CHECK (Before Normal Dialogue)
                # ==========================================
                auto_success = False

                current_status = npc_state.get("status", "NORMAL")
                state_config = states_config.get(current_status)
                if state_config and npc_state.get("duration", 0) > 0:
                    duration = npc_state["duration"]
                    description = state_config.get("description", current_status)
                    effect = state_config.get("effect")
                    if effect == "skip_generation":
                        ui.print_state_effect(current_status, duration, description)
                        ui.print_npc_response("Shadowheart", state_config.get("message", ""))

                        # Update state using mechanics
                        new_status, new_duration = mechanics.update_npc_state(npc_state["status"], npc_state["duration"])
                        npc_state["status"] = new_status
                        npc_state["duration"] = new_duration

                        if new_status == "NORMAL":
                            ui.print_state_effect("NORMAL", 0, "状态恢复")

                        # Save state and continue (skip LLM)
                        memory_data = {
                            "relationship_score": relationship_score,
                            "history": conversation_history,
                            "npc_state": npc_state,
                            "flags": flags
                        }
                        save_memory(memory_data, ui=ui)
                        continue

                    if effect == "auto_success":
                        auto_success = True
                        ui.print_state_effect(current_status, duration, description)

                        # Update state using mechanics
                        new_status, new_duration = mechanics.update_npc_state(npc_state["status"], npc_state["duration"])
                        npc_state["status"] = new_status
                        npc_state["duration"] = new_duration

                        if new_status == "NORMAL":
                            ui.print_state_effect("NORMAL", 0, "状态恢复")
                
                # ==========================================
                # Step 4: NORMAL DIALOGUE FLOW
                # ==========================================
                
                # Step A: DM Analysis
                try:
                    with ui.create_spinner("[dm]🎲 DM is analyzing fate...[/dm]", spinner="dots"):
                        intent_data = analyze_intent(user_input)
                    action_type = intent_data['action_type']
                    dc = intent_data['difficulty_class']
                    # 记录意图判定
                    ui.print_dm_analysis(action_type, dc)
                except Exception as e:
                    # 如果 DM 分析失败，使用默认值并继续
                    ui.print_error(f"⚠️ [DM] 意图分析失败: {e}")
                    intent_data = {
                        'action_type': 'NONE',
                        'difficulty_class': 0,
                        'reason': 'DM analysis failed'
                    }
                    action_type = 'NONE'
                    dc = 0
                
                # Phase 1: Rules Overrule - Calculate DC from NPC stats
                rule_dc = mechanics.calculate_passive_dc(action_type, attributes)
                if rule_dc is not None:
                    dc = rule_dc
                    ui.print_system_info(f"🛡️ DC Auto-Calculated: {dc} (Based on Shadowheart's Stats)")
                
                # Step B: Auto-Roll Logic
                system_info = None
                if action_type != "NONE" and dc > 0:
                    # Check if auto_success is active (VULNERABLE state)
                    if auto_success:
                        # Skip dice roll, force CRITICAL SUCCESS
                        result_type = CheckResult.CRITICAL_SUCCESS
                        system_info = f"Action: {action_type} | Result: CRITICAL SUCCESS (Auto). She is vulnerable."
                        ui.print_auto_success(action_type)
                        
                        # Grant +1 relationship bonus for auto-success
                        relationship_score += 1
                        relationship_score = max(-100, min(100, relationship_score))
                        ui.print_system_info("💕 Relationship +1 (Vulnerable State Bonus)")
                    else:
                        # Normal roll logic
                        # Check if player_data is available
                        if player_data is None:
                            ui.print_error("⚠️ Player profile not loaded. Cannot perform auto-roll.")
                        else:
                            # Get ability score for this action
                            ability_name = mechanics.get_ability_for_action(action_type)
                            player_ability_scores = player_data.get('ability_scores', {})
                            
                            if ability_name not in player_ability_scores:
                                ui.print_error(f"⚠️ Player doesn't have {ability_name} ability score.")
                            else:
                                # Get modifier from player stats
                                ability_score = player_ability_scores[ability_name]
                                modifier = mechanics.calculate_ability_modifier(ability_score)
                                
                                # Calculate situational bonus (check current user input)
                                bonus, reason = mechanics.get_situational_bonus(
                                    conversation_history,
                                    action_type,
                                    situational_bonuses,
                                    flags,
                                    user_input
                                )
                                if bonus != 0:
                                    modifier += bonus
                                    ui.print_situational_bonus(bonus, reason)
                                
                                # Determine roll type (advantage/disadvantage)
                                roll_type = mechanics.determine_roll_type(action_type, relationship_score)
                                
                                # Visual feedback for advantage/disadvantage
                                ui.print_advantage_alert(action_type, roll_type)
                                
                                # Execute roll
                                result = roll_d20(dc, modifier, roll_type=roll_type)
                                
                                # Print result
                                ui.print_roll_result(result)
                                
                                # Trigger state changes based on critical rolls
                                if result['result_type'] == CheckResult.CRITICAL_SUCCESS:
                                    # Natural 20: Set VULNERABLE state
                                    npc_state = {"status": "VULNERABLE", "duration": 3}
                                    ui.print_critical_state_change(CheckResult.CRITICAL_SUCCESS, "VULNERABLE", 3)
                                elif result['result_type'] == CheckResult.CRITICAL_FAILURE:
                                    # Natural 1: Set SILENT state
                                    npc_state = {"status": "SILENT", "duration": 2}
                                    ui.print_critical_state_change(CheckResult.CRITICAL_FAILURE, "SILENT", 2)
                                
                                # Create system info string for injection
                                system_info = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."
                
                # Process dialogue triggers (generic trigger system)
                trigger_messages = mechanics.process_dialogue_triggers(
                    user_input, 
                    dialogue_triggers, 
                    flags, 
                    ui=ui, 
                    player_inv=player_inventory, 
                    npc_inv=character.inventory
                )
                for msg in trigger_messages:
                    ui.print_system_info(msg)

                # Step C: Generation
                # Update system prompt to reflect current relationship score, flags, and summary
                system_prompt = character.render_prompt(relationship_score, flags=flags, summary=summary)
                
                # Create temporary messages list (for sending to LLM, with injected system info)
                messages_to_send = conversation_history.copy()
                
                # Prepare user input (inject system info if exists)
                if system_info is not None:
                    user_content_for_llm = f"[SYSTEM INFO: {system_info}]\n\n{user_input}"
                else:
                    user_content_for_llm = user_input
                
                # Add user message to temporary list
                messages_to_send.append({"role": "user", "content": user_content_for_llm})
                
                # Generate reply with spinner
                with ui.create_spinner("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
                    response = generate_dialogue(system_prompt, conversation_history=messages_to_send)
                
                # 6. 解析 approval change
                approval_change, cleaned_response = parse_approval_change(response)
                
                # 7. 更新关系值
                if approval_change != 0:
                    old_score = relationship_score
                    relationship_score += approval_change
                    # 限制关系值在 -100 到 100 之间
                    relationship_score = max(-100, min(100, relationship_score))
                    
                    # 打印系统调试信息
                    ui.print_relationship_change(approval_change, relationship_score)
                
                # 8. 处理一下回复格式
                if cleaned_response:
                    cleaned_response = cleaned_response.strip('"').strip("'")
                    # Display NPC dialogue in a panel
                    ui.print_npc_response("Shadowheart", cleaned_response)
                else:
                    ui.print_npc_response("Shadowheart", "（没有回应）")
                
                # 9. 【Memory Hygiene】保存干净的对话历史（不包含系统注入标签）
                # 只保存原始用户输入，不包含 [SYSTEM INFO: ...]
                conversation_history.append({"role": "user", "content": user_input})
                # 保存清理后的 AI 回复（不包含 approval tag）
                conversation_history.append({"role": "assistant", "content": cleaned_response})
                
                # 10. 【Rolling Memory Summarization】防止 Token 爆炸
                if len(conversation_history) > settings.MAX_HISTORY:
                    # Take the oldest 4 messages to summarize
                    messages_to_summarize = conversation_history[:4]
                    
                    # Generate or update summary
                    with ui.create_spinner("📝 Consolidating memories...", spinner="dots"):
                        new_summary_text = update_summary(summary, messages_to_summarize)
                        summary = new_summary_text
                    
                    # Remove those 4 messages from conversation_history
                    conversation_history = conversation_history[4:]
                    
                    # Log the consolidation
                    ui.print_system_info(f"🧠 Memory Consolidated: {summary[:100]}..." if len(summary) > 100 else f"🧠 Memory Consolidated: {summary}")
                
                # Save npc_state to memory after each turn
                memory_data = {
                    "relationship_score": relationship_score,
                    "history": conversation_history,
                    "npc_state": npc_state,
                    "flags": flags,
                    "summary": summary
                }
                save_memory(memory_data, ui=ui)
                    
            except KeyboardInterrupt:
                # 强制中断也要存档
                memory_data = {
                    "relationship_score": relationship_score,
                    "history": conversation_history,
                    "npc_state": npc_state,
                    "flags": flags
                }
                save_memory(memory_data, ui=ui)
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

