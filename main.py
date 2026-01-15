"""
BG3 LLM Agent - Main Entry Point
Reads character attributes and generates dialogue using LLM API (阿里云百炼)
"""

import os
import sys
import json
from typing import Optional
from dotenv import load_dotenv
from characters.loader import load_character
from core.engine import generate_dialogue, parse_approval_change
from core.dice import roll_d20
from core.dm import analyze_intent

# Load environment variables from .env file
load_dotenv()

# 定义记忆文件保存的位置
MEMORY_FILE = "data/shadowheart_memory.json"

# 角色名称
CHARACTER_NAME = "shadowheart"


def calculate_ability_modifier(ability_score):
    """
    Calculate D&D 5e ability modifier from ability score.
    
    Formula: (ability_score - 10) // 2
    
    Args:
        ability_score: The ability score (typically 1-20)
    
    Returns:
        int: The ability modifier
    """
    return (ability_score - 10) // 2


def get_ability_modifiers(ability_scores):
    """
    Calculate all ability modifiers from ability scores.
    
    Args:
        ability_scores: Dictionary of ability scores (e.g., {"STR": 13, "DEX": 14, ...})
    
    Returns:
        dict: Dictionary of ability modifiers with same keys
    """
    return {ability: calculate_ability_modifier(score) for ability, score in ability_scores.items()}


def normalize_ability_name(ability_name: str) -> Optional[str]:
    """
    Normalize ability name to standard format (STR, DEX, CON, INT, WIS, CHA).
    Handles common abbreviations and case variations.
    
    Args:
        ability_name: User input ability name (e.g., "wis", "CHA", "charisma")
    
    Returns:
        Optional[str]: Standardized ability name (STR, DEX, CON, INT, WIS, CHA) or None if not found
    """
    ability_name = ability_name.upper().strip()
    
    # Mapping of common abbreviations to standard names
    ability_map = {
        "STR": "STR", "STRENGTH": "STR",
        "DEX": "DEX", "DEXTERITY": "DEX",
        "CON": "CON", "CONSTITUTION": "CON",
        "INT": "INT", "INTELLIGENCE": "INT",
        "WIS": "WIS", "WISDOM": "WIS",
        "CHA": "CHA", "CHARISMA": "CHA"
    }
    
    return ability_map.get(ability_name)


def handle_command(user_input: str, attributes: dict, relationship_score: int = 0, action_type: str = 'NONE') -> Optional[str]:
    """
    Handle user commands (commands starting with '/').
    
    Supported commands:
    - /roll <ability> <dc>: Roll a D20 check with the specified ability modifier
    
    Args:
        user_input: The user's input string
        attributes: Character attributes dictionary containing ability_scores
        relationship_score: Current relationship score (for determining advantage/disadvantage)
        action_type: Current action type from DM analysis (for determining advantage/disadvantage)
    
    Returns:
        Optional[str]: Roll result narrative string if a roll occurred, None otherwise
    """
    if not user_input.startswith('/'):
        return None
    
    parts = user_input.split()
    if len(parts) < 2:
        print("❌ [System] 命令格式错误。用法: /roll <ability> <dc>")
        print("   例如: /roll wis 12 或 /roll cha 15")
        return None
    
    command = parts[0].lower()
    
    if command == '/roll':
        if len(parts) < 3:
            print("❌ [System] /roll 命令需要两个参数: <ability> <dc>")
            print("   例如: /roll wis 12 或 /roll cha 15")
            return None
        
        ability_name = parts[1]
        try:
            dc = int(parts[2])
        except ValueError:
            print(f"❌ [System] DC 必须是数字，收到: {parts[2]}")
            return None
        
        # Normalize ability name
        normalized_ability = normalize_ability_name(ability_name)
        if not normalized_ability:
            print(f"❌ [System] 未知的能力值: {ability_name}")
            print("   支持的能力值: STR, DEX, CON, INT, WIS, CHA")
            return None
        
        # Get ability score and calculate modifier
        ability_scores = attributes.get('ability_scores', {})
        if normalized_ability not in ability_scores:
            print(f"❌ [System] 角色没有 {normalized_ability} 能力值")
            return None
        
        ability_score = ability_scores[normalized_ability]
        modifier = calculate_ability_modifier(ability_score)
        
        # Determine roll type based on relationship and action
        roll_type = determine_roll_type(action_type, relationship_score)
        
        # Visual feedback for advantage/disadvantage
        if roll_type == 'advantage':
            print(f"🌟 [System] High relationship grants ADVANTAGE on {action_type}!")
        elif roll_type == 'disadvantage':
            print("💀 [System] Low relationship imposes DISADVANTAGE!")
        
        # Roll the dice
        result = roll_d20(dc, modifier, roll_type=roll_type)
        
        # Print the result
        print(f"\n{result['log_str']}\n")
        
        # Generate narrative result string for LLM injection
        roll_summary = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."
        return roll_summary
    
    else:
        print(f"❌ [System] 未知命令: {command}")
        print("   支持的命令: /roll")
        return None




def load_memory(default_relationship_score=0):
    """
    从本地文件读取记忆，支持优先级系统。
    
    优先级（从高到低）：
    1. 记忆文件中的 relationship_score（如果存在）
    2. 传入的 default_relationship_score（通常来自 YAML 配置）
    3. 默认值 0
    
    Args:
        default_relationship_score: 默认关系值，通常从 YAML 配置文件中读取
    
    Returns:
        dict: 包含 relationship_score 和 history 的字典
    """
    # 尝试从记忆文件读取
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # 如果是空文件，使用默认值
                    print(f"🧠 [System] 记忆文件为空，使用 YAML 配置的关系值: {default_relationship_score}")
                    return {"relationship_score": default_relationship_score, "history": []}
                
                data = json.loads(content)
                
                # 向后兼容：如果文件是列表格式（旧格式），转换为新格式
                if isinstance(data, list):
                    print(f"🧠 [System] 检测到旧格式记忆文件，正在转换...")
                    print(f"💕 [System] 使用 YAML 配置的关系值: {default_relationship_score}")
                    return {"relationship_score": default_relationship_score, "history": data}
                
                # 新格式：包含 relationship_score 和 history
                if isinstance(data, dict):
                    # 优先使用记忆文件中的关系值，如果没有则使用默认值
                    relationship_score = data.get("relationship_score")
                    if relationship_score is None:
                        # 记忆文件中没有关系值，使用 YAML 配置的值
                        relationship_score = default_relationship_score
                        print(f"🧠 [System] 记忆文件中没有关系值，使用 YAML 配置: {relationship_score}")
                    else:
                        # 使用记忆文件中的关系值（最高优先级）
                        print(f"🧠 [System] 成功唤醒记忆，共读取 {len(data.get('history', []))} 条往事...")
                        print(f"💕 [System] 当前关系值（来自记忆）: {relationship_score}/100")
                    
                    history = data.get("history", [])
                    return {"relationship_score": relationship_score, "history": history}
                
                # 如果格式不对，使用默认值
                print(f"⚠️ [System] 记忆文件格式错误，使用 YAML 配置的关系值: {default_relationship_score}")
                return {"relationship_score": default_relationship_score, "history": []}
                
        except Exception as e:
            # 记忆文件读取失败，使用 YAML 配置的值
            print(f"⚠️ [System] 记忆文件读取失败，使用 YAML 配置的关系值: {default_relationship_score} ({e})")
            return {"relationship_score": default_relationship_score, "history": []}
    
    # 记忆文件不存在，使用 YAML 配置的值
    print(f"🧠 [System] 未找到记忆文件，使用 YAML 配置的关系值: {default_relationship_score}")
    return {"relationship_score": default_relationship_score, "history": []}


def save_memory(memory_data):
    """把记忆写入本地文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        print("💾 [System] 记忆已固化至莎尔的卷轴中。")
    except Exception as e:
        print(f"❌ [System] 存档失败: {e}")


def load_player_profile():
    """
    Load player profile from data/player.json.
    
    Returns:
        dict: Player profile data
    
    Raises:
        FileNotFoundError: If player.json doesn't exist
        json.JSONDecodeError: If JSON is malformed
    """
    player_file = "data/player.json"
    if not os.path.exists(player_file):
        raise FileNotFoundError(f"Player profile not found: {player_file}")
    
    with open(player_file, 'r', encoding='utf-8') as f:
        player_data = json.load(f)
    
    return player_data


def get_ability_for_action(action_type: str) -> str:
    """
    Map action type to the corresponding ability score.
    
    Args:
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
    
    Returns:
        str: Ability score abbreviation (STR, DEX, CON, INT, WIS, CHA)
    """
    action_to_ability = {
        "DECEPTION": "CHA",
        "PERSUASION": "CHA",
        "INTIMIDATION": "CHA",
        "INSIGHT": "WIS",
        "ATTACK": "STR",  # Default to STR, could be weapon-dependent
        "NONE": "CHA"  # Default fallback
    }
    return action_to_ability.get(action_type, "CHA")


def determine_roll_type(action_type: str, relationship_score: int) -> str:
    """
    Determine roll type (normal/advantage/disadvantage) based on action and relationship.
    
    Args:
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
        relationship_score: Current relationship score with the NPC
    
    Returns:
        str: 'normal', 'advantage', or 'disadvantage'
    """
    # Advantage: PERSUASION or DECEPTION with high relationship (>= 30)
    if action_type in ["PERSUASION", "DECEPTION"] and relationship_score >= 30:
        return 'advantage'
    
    # Disadvantage: Low relationship (<= -20)
    if relationship_score <= -20:
        return 'disadvantage'
    
    return 'normal'


def calculate_passive_dc(action_type: str, npc_attributes: dict) -> int | None:
    """
    Calculate passive DC based on NPC's stats (Phase 1: Rules Overrule).
    
    This function calculates the DC that the player must beat based on the NPC's
    actual ability scores, overriding the DM AI's DC estimate.
    
    Args:
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
        npc_attributes: NPC character attributes dictionary containing ability_scores
    
    Returns:
        int | None: Calculated DC if applicable, None to use DM's default DC
    """
    # Get NPC's WIS modifier
    ability_scores = npc_attributes.get('ability_scores', {})
    wis_score = ability_scores.get('WIS', 10)
    wis_mod = (wis_score - 10) // 2
    
    # Calculate passive DC based on action type
    if action_type == "DECEPTION":
        # Passive Insight: 10 + WIS modifier (detecting lies)
        return 10 + wis_mod
    elif action_type == "PERSUASION":
        # Passive Insight/Skepticism: 10 + WIS modifier (judging honesty)
        return 10 + wis_mod
    elif action_type == "INTIMIDATION":
        # Passive Willpower: 10 + WIS modifier (resisting threats)
        return 10 + wis_mod
    else:
        # For other action types, use DM's default DC
        return None


def get_situational_bonus(history: list, action_type: str, current_message: str = "") -> tuple[int, str]:
    """
    Calculate situational bonus based on conversation context (Simple Keyword Matching).
    
    This function checks the current user message (and optionally history) for keywords 
    that indicate shared context or past bonds, which grant bonuses to social skill checks.
    
    Args:
        history: List of conversation history dicts with 'role' and 'content' keys
        action_type: The action type from DM analysis (e.g., "PERSUASION", "DECEPTION")
        current_message: The current user input message (optional, checked first)
    
    Returns:
        tuple[int, str]: (bonus, reason) - bonus amount and explanation
    """
    # Check current message first, then fall back to last message in history
    message_to_check = current_message
    
    if not message_to_check:
        # Get the last user message from history
        for msg in reversed(history):
            if msg.get('role') == 'user':
                message_to_check = msg.get('content', '')
                break
    
    if not message_to_check:
        return (0, "")
    
    # Convert to lowercase for matching
    message_lower = message_to_check.lower()
    
    # Rule 1: Shared Context (Shared Faith/Knowledge)
    # Keywords: ["shar", "莎尔", "lady of loss"]
    # Applies to: PERSUASION or DECEPTION
    if action_type in ["PERSUASION", "DECEPTION"]:
        shared_faith_keywords = ["shar", "莎尔", "lady of loss"]
        if any(keyword in message_lower for keyword in shared_faith_keywords):
            return (2, "Shared Faith/Knowledge")
    
    # Rule 2: Past Bond
    # Keywords: ["ship", "nautiloid", "飞船", "螺壳舰"]
    # Applies to: All action types
    past_bond_keywords = ["ship", "nautiloid", "飞船", "螺壳舰"]
    if any(keyword in message_lower for keyword in past_bond_keywords):
        return (2, "Past Bond")
    
    # Default: No bonus
    return (0, "")


def main():
    """Main function to load attributes and generate dialogue"""
    print("=" * 60)
    print("BG3 LLM Agent - Shadowheart Dialogue Generator")
    print("=" * 60)
    
    # Load player profile
    print("Loading player profile...")
    try:
        player_data = load_player_profile()
        print(f"✓ Loaded player profile: {player_data['name']}")
        print(f"  - {player_data['race']} {player_data['class']} (Level {player_data['level']})")
        print()
    except Exception as e:
        print(f"⚠️ [System] Failed to load player profile: {e}")
        print("  Continuing without player profile...")
        player_data = None
        print()
    
    # Load character
    print("Loading Shadowheart's attributes...")
    character = load_character(CHARACTER_NAME)
    attributes = character.data  # 保留对原始数据的引用，用于显示
    print(f"✓ Loaded attributes for {attributes['name']}")
    print(f"  - {attributes['race']} {attributes['class']} (Level {attributes['level']})")
    print(f"  - Deity: {attributes['deity']}")
    print()
    
    # Display key attributes
    print("Key Attributes:")
    ability_modifiers = get_ability_modifiers(attributes['ability_scores'])
    for ability, score in attributes['ability_scores'].items():
        modifier = ability_modifiers[ability]
        print(f"  {ability}: {score} (+{modifier:+d})")
    print()     
    
    # Generate initial greeting
    print("Generating initial greeting...")
    try:
        # 1. 【关键修改】启动时尝试加载旧记忆
        # 优先级：记忆文件 > YAML 配置 > 默认值 0
        # 从 YAML 配置中获取初始关系值作为默认值
        default_relationship = attributes.get('relationship', 0)
        memory_data = load_memory(default_relationship_score=default_relationship)
        relationship_score = memory_data["relationship_score"]
        conversation_history = memory_data["history"]
        
        # 2. 生成 System Prompt（使用 Character 对象的 render_prompt 方法）
        system_prompt = character.render_prompt(relationship_score)
        
        print("=" * 60)
        # 如果是新对话（没记忆），生成并打印开场白
        if not conversation_history:
            # 生成初始问候（使用空的对话历史）
            dialogue = generate_dialogue(system_prompt, conversation_history=conversation_history)
            
            # 解析 approval change（初始问候通常不会有变化，但为了统一处理）
            approval_change, cleaned_dialogue = parse_approval_change(dialogue)
            
            # 更新关系值
            relationship_score += approval_change
            
            # 清理引号
            if cleaned_dialogue:
                cleaned_dialogue = cleaned_dialogue.strip('"').strip("'")
            
            print(f"{attributes['name']} (Looking at you warily):")
            print(f'"{cleaned_dialogue}"')
            
            # 把初始问候加入对话历史（存储清理后的文本）
            conversation_history.append({"role": "assistant", "content": cleaned_dialogue})
        else:
            # 如果有记忆，显示不同的开场白
            print(f"{attributes['name']} (Remembers you): *Nods slightly acknowledging your return*")
        print("=" * 60)
        print()
        
        # Start interactive conversation
        print("💬 开始与影心对话（输入 'quit' 或 'exit' 退出并存档）")
        print("=" * 60)
        print()
        
        while True:
            try:
                # ==========================================
                # Step 1: Get User Input
                # ==========================================
                user_input = input("你: ").strip()
                
                if not user_input:
                    continue
                
                # ==========================================
                # Step 2: Command Interceptor
                # ==========================================
                if user_input.lower() in ['quit', 'exit', '退出', 'q']:
                    # Exit command
                    memory_data = {
                        "relationship_score": relationship_score,
                        "history": conversation_history
                    }
                    save_memory(memory_data)
                    print("\n再见！")
                    break
                
                if user_input.startswith('/'):
                    # Handle commands (e.g., /roll)
                    current_action = 'NONE'  # Commands don't use DM analysis
                    roll_result = handle_command(user_input, attributes, relationship_score, current_action)
                    if roll_result is not None:
                        # Store the roll result for injection into next dialogue
                        print(f"💡 [System] Roll result stored. Type your dialogue to use it.")
                    continue  # Skip the rest of the loop for commands
                
                # ==========================================
                # Step 3: NORMAL DIALOGUE FLOW
                # ==========================================
                
                # Step A: DM Analysis
                try:
                    intent_data = analyze_intent(user_input)
                    action_type = intent_data['action_type']
                    dc = intent_data['difficulty_class']
                    # 记录意图判定
                    print(f"🎲 [DM] 判定意图: {action_type} (DC {dc})")
                except Exception as e:
                    # 如果 DM 分析失败，使用默认值并继续
                    print(f"⚠️ [DM] 意图分析失败: {e}")
                    intent_data = {
                        'action_type': 'NONE',
                        'difficulty_class': 0,
                        'reason': 'DM analysis failed'
                    }
                    action_type = 'NONE'
                    dc = 0
                
                # Phase 1: Rules Overrule - Calculate DC from NPC stats
                rule_dc = calculate_passive_dc(action_type, attributes)
                if rule_dc is not None:
                    dc = rule_dc
                    print(f"🛡️ [System] DC Auto-Calculated: {dc} (Based on Shadowheart's Stats)")
                
                # Step B: Auto-Roll Logic
                system_info = None
                if action_type != "NONE" and dc > 0:
                    # Check if player_data is available
                    if player_data is None:
                        print("⚠️ [System] Player profile not loaded. Cannot perform auto-roll.")
                    else:
                        # Get ability score for this action
                        ability_name = get_ability_for_action(action_type)
                        player_ability_scores = player_data.get('ability_scores', {})
                        
                        if ability_name not in player_ability_scores:
                            print(f"⚠️ [System] Player doesn't have {ability_name} ability score.")
                        else:
                            # Get modifier from player stats
                            ability_score = player_ability_scores[ability_name]
                            modifier = calculate_ability_modifier(ability_score)
                            
                            # Calculate situational bonus (check current user input)
                            bonus, reason = get_situational_bonus(conversation_history, action_type, user_input)
                            if bonus != 0:
                                modifier += bonus
                                print(f"💍 [System] Situational Bonus: +{bonus} ({reason})")
                            
                            # Determine roll type (advantage/disadvantage)
                            roll_type = determine_roll_type(action_type, relationship_score)
                            
                            # Visual feedback for advantage/disadvantage
                            if roll_type == 'advantage':
                                print(f"🌟 [System] High relationship grants ADVANTAGE on {action_type}!")
                            elif roll_type == 'disadvantage':
                                print("💀 [System] Low relationship imposes DISADVANTAGE!")
                            
                            # Execute roll
                            result = roll_d20(dc, modifier, roll_type=roll_type)
                            
                            # Print result
                            print(f"\n{result['log_str']}\n")
                            
                            # Create system info string for injection
                            system_info = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."
                
                # Step C: Generation
                # Update system prompt to reflect current relationship score
                system_prompt = character.render_prompt(relationship_score)
                
                # Create temporary messages list (for sending to LLM, with injected system info)
                messages_to_send = conversation_history.copy()
                
                # Prepare user input (inject system info if exists)
                if system_info is not None:
                    user_content_for_llm = f"[SYSTEM INFO: {system_info}]\n\n{user_input}"
                else:
                    user_content_for_llm = user_input
                
                # Add user message to temporary list
                messages_to_send.append({"role": "user", "content": user_content_for_llm})
                
                # Generate reply
                print(f"\n{attributes['name']}: ", end="", flush=True)
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
                    change_str = f"+{approval_change}" if approval_change > 0 else str(approval_change)
                    print(f"\n💕 [System] 关系值变化: {change_str} (当前: {relationship_score}/100)")
                    print(f"{attributes['name']}: ", end="", flush=True)
                
                # 8. 处理一下回复格式
                if cleaned_response:
                    cleaned_response = cleaned_response.strip('"').strip("'")
                    print(f'"{cleaned_response}"')
                else:
                    print("（没有回应）")
                print()
                
                # 9. 【Memory Hygiene】保存干净的对话历史（不包含系统注入标签）
                # 只保存原始用户输入，不包含 [SYSTEM INFO: ...]
                conversation_history.append({"role": "user", "content": user_input})
                # 保存清理后的 AI 回复（不包含 approval tag）
                conversation_history.append({"role": "assistant", "content": cleaned_response})
                
                # 8. 【可选】每轮对话都自动存档（防止程序崩了丢失记忆）
                # memory_data = {
                #     "relationship_score": relationship_score,
                #     "history": conversation_history
                # }
                # save_memory(memory_data)
                
                # 9. 滚动窗口：防止 Token 爆炸（保留最近 20 轮）
                # 注意：这里我们只是截断"发给 AI"的列表，还是截断"存储"的列表？
                # 为了简单，我们暂时让记忆文件也保持在 20 轮以内，避免文件无限膨胀
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]
                    
            except KeyboardInterrupt:
                # 强制中断也要存档
                memory_data = {
                    "relationship_score": relationship_score,
                    "history": conversation_history
                }
                save_memory(memory_data)
                print("\n\n再见！")
                break
            except Exception as e:
                print(f"\n❌ 错误: {e}")
                print("请重试...\n")
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("\n请安装必要的依赖包:")
        print("  pip install dashscope python-dotenv")
        
        print("\n要使用百炼 API，你需要:")
        print("1. 安装 dashscope 包: pip install dashscope")
        print("2. 在项目根目录创建 .env 文件")
        print("3. 添加你的 API key: BAILIAN_API_KEY=your-api-key")
        print("\n或者使用模拟响应进行测试:")
        
        # Fallback mock dialogue
        print("\n" + "=" * 60)
        print("Mock Dialogue (API not configured):")
        print("=" * 60)
        print('"Shar\'s will be done. I sense there\'s more to you than meets the eye, '
              'just as there is more to me. Trust is earned, not given freely."')
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()


if __name__ == "__main__":
    main()

