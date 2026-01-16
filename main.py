"""
BG3 LLM Agent - Main Entry Point
Reads character attributes and generates dialogue using LLM API (阿里云百炼)
"""

import os
import sys
import json
from typing import Optional
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
from rich.text import Text
from rich.rule import Rule
from rich.table import Table
from characters.loader import load_character
from core.engine import generate_dialogue, parse_approval_change
from core.dice import roll_d20, CheckResult
from core.dm import analyze_intent

# Create custom theme for BG3 UI
bg3_theme = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "failure": "bold red",
    "critical": "bold yellow reverse blink",
    "npc": "bold purple",
    "player": "bold white",
    "dm": "italic grey50",
    "stat": "bold blue",
    "item": "bold magenta",
})

# Initialize console with custom theme
console = Console(theme=bg3_theme)

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
        console.print("[error]❌ 命令格式错误。用法: /roll <ability> <dc>[/error]")
        console.print("[info]   例如: /roll wis 12 或 /roll cha 15[/info]")
        return None
    
    command = parts[0].lower()
    
    if command == '/roll':
        if len(parts) < 3:
            console.print("[error]❌ /roll 命令需要两个参数: <ability> <dc>[/error]")
            console.print("[info]   例如: /roll wis 12 或 /roll cha 15[/info]")
            return None
        
        ability_name = parts[1]
        try:
            dc = int(parts[2])
        except ValueError:
            console.print(f"[error]❌ DC 必须是数字，收到: [stat]{parts[2]}[/stat][/error]")
            return None
        
        # Normalize ability name
        normalized_ability = normalize_ability_name(ability_name)
        if not normalized_ability:
            console.print(f"[error]❌ 未知的能力值: [item]{ability_name}[/item][/error]")
            console.print("[info]   支持的能力值: STR, DEX, CON, INT, WIS, CHA[/info]")
            return None
        
        # Get ability score and calculate modifier
        ability_scores = attributes.get('ability_scores', {})
        if normalized_ability not in ability_scores:
            console.print(f"[error]❌ 角色没有 [stat]{normalized_ability}[/stat] 能力值[/error]")
            return None
        
        ability_score = ability_scores[normalized_ability]
        modifier = calculate_ability_modifier(ability_score)
        
        # Determine roll type based on relationship and action
        roll_type = determine_roll_type(action_type, relationship_score)
        
        # Visual feedback for advantage/disadvantage
        if roll_type == 'advantage':
            console.print(f"[warning]🌟 High relationship grants ADVANTAGE on [item]{action_type}[/item]![/warning]")
        elif roll_type == 'disadvantage':
            console.print("[warning]💀 Low relationship imposes DISADVANTAGE![/warning]")
        
        # Roll the dice
        result = roll_d20(dc, modifier, roll_type=roll_type)
        
        # Determine result style
        if result['result_type'] == CheckResult.CRITICAL_SUCCESS:
            res_style = "critical"
        elif result['result_type'] == CheckResult.CRITICAL_FAILURE:
            res_style = "critical"
        elif result['result_type'] == CheckResult.SUCCESS:
            res_style = "success"
        else:
            res_style = "failure"
        
        # Print the result with styled output
        console.print(f"   └─ [{res_style}]{result['log_str']}[/{res_style}]")
        console.print()
        
        # Generate narrative result string for LLM injection
        roll_summary = f"Skill Check Result: {result['result_type'].value} (Rolled {result['total']} vs DC {dc})."
        return roll_summary
    
    else:
        console.print(f"[error]❌ 未知命令: [item]{command}[/item][/error]")
        console.print("[info]   支持的命令: /roll[/info]")
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
                    console.print(f"[info]🧠 记忆文件为空，使用 YAML 配置的关系值: [stat]{default_relationship_score}[/stat][/info]")
                    return {
                        "relationship_score": default_relationship_score,
                        "history": [],
                        "npc_state": {"status": "NORMAL", "duration": 0}
                    }
                
                data = json.loads(content)
                
                # 向后兼容：如果文件是列表格式（旧格式），转换为新格式
                if isinstance(data, list):
                    console.print(f"[info]🧠 检测到旧格式记忆文件，正在转换...[/info]")
                    console.print(f"[info]💕 使用 YAML 配置的关系值: [stat]{default_relationship_score}[/stat][/info]")
                    return {
                        "relationship_score": default_relationship_score,
                        "history": data,
                        "npc_state": {"status": "NORMAL", "duration": 0}
                    }
                
                # 新格式：包含 relationship_score 和 history
                if isinstance(data, dict):
                    # 优先使用记忆文件中的关系值，如果没有则使用默认值
                    relationship_score = data.get("relationship_score")
                    if relationship_score is None:
                        # 记忆文件中没有关系值，使用 YAML 配置的值
                        relationship_score = default_relationship_score
                        console.print(f"[info]🧠 记忆文件中没有关系值，使用 YAML 配置: [stat]{relationship_score}[/stat][/info]")
                    else:
                        # 使用记忆文件中的关系值（最高优先级）
                        console.print(f"[info]🧠 成功唤醒记忆，共读取 [stat]{len(data.get('history', []))}[/stat] 条往事...[/info]")
                        console.print(f"[info]💕 当前关系值（来自记忆）: [stat]{relationship_score}/100[/stat][/info]")
                    
                    history = data.get("history", [])
                    # Get npc_state or use default
                    npc_state = data.get("npc_state", {"status": "NORMAL", "duration": 0})
                    return {
                        "relationship_score": relationship_score,
                        "history": history,
                        "npc_state": npc_state
                    }
                
                # 如果格式不对，使用默认值
                console.print(f"[warning]⚠️ 记忆文件格式错误，使用 YAML 配置的关系值: [stat]{default_relationship_score}[/stat][/warning]")
                return {
                    "relationship_score": default_relationship_score,
                    "history": [],
                    "npc_state": {"status": "NORMAL", "duration": 0}
                }
                
        except Exception as e:
            # 记忆文件读取失败，使用 YAML 配置的值
            console.print(f"[warning]⚠️ 记忆文件读取失败，使用 YAML 配置的关系值: [stat]{default_relationship_score}[/stat] ({e})[/warning]")
            return {
                "relationship_score": default_relationship_score,
                "history": [],
                "npc_state": {"status": "NORMAL", "duration": 0}
            }
    
    # 记忆文件不存在，使用 YAML 配置的值
    console.print(f"[info]🧠 未找到记忆文件，使用 YAML 配置的关系值: [stat]{default_relationship_score}[/stat][/info]")
    return {
        "relationship_score": default_relationship_score,
        "history": [],
        "npc_state": {"status": "NORMAL", "duration": 0}
    }


def save_memory(memory_data):
    """把记忆写入本地文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        console.print("[info]💾 记忆已固化至莎尔的卷轴中。[/info]")
    except Exception as e:
        console.print(f"[error]❌ 存档失败: {e}[/error]")


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
    # Clear screen and show title
    console.clear()
    console.print(Rule("[bold purple]BG3 LLM Agent - Shadowheart Dialogue Generator[/bold purple]", style="bold purple"))
    console.print()
    
    # Load player profile
    with console.status("[info]Loading player profile...[/info]", spinner="dots"):
        try:
            player_data = load_player_profile()
            console.print(f"[info]✓[/info] Loaded player profile: [player]{player_data['name']}[/player]")
            console.print(f"  - [stat]{player_data['race']} {player_data['class']}[/stat] (Level [stat]{player_data['level']}[/stat])")
            console.print()
        except Exception as e:
            console.print(f"[error]⚠️ Failed to load player profile: {e}[/error]")
            console.print("[info]  Continuing without player profile...[/info]")
            player_data = None
            console.print()
    
    # Load character
    with console.status("[info]Loading Shadowheart's attributes...[/info]", spinner="dots"):
        character = load_character(CHARACTER_NAME)
        attributes = character.data  # 保留对原始数据的引用，用于显示
    console.print(f"[info]✓[/info] Loaded attributes for [npc]{attributes['name']}[/npc]")
    console.print(f"  - [stat]{attributes['race']} {attributes['class']}[/stat] (Level [stat]{attributes['level']}[/stat])")
    console.print(f"  - Deity: [item]{attributes['deity']}[/item]")
    console.print()
    
    # Display key attributes
    console.print("[info]Key Attributes:[/info]")
    ability_modifiers = get_ability_modifiers(attributes['ability_scores'])
    for ability, score in attributes['ability_scores'].items():
        modifier = ability_modifiers[ability]
        console.print(f"  [stat]{ability}: {score}[/stat] ([stat]+{modifier:+d}[/stat])")
    console.print()     
    
    # Generate initial greeting
    try:
        # 1. 【关键修改】启动时尝试加载旧记忆
        # 优先级：记忆文件 > YAML 配置 > 默认值 0
        # 从 YAML 配置中获取初始关系值作为默认值
        default_relationship = attributes.get('relationship', 0)
        memory_data = load_memory(default_relationship_score=default_relationship)
        relationship_score = memory_data["relationship_score"]
        conversation_history = memory_data["history"]
        npc_state = memory_data.get("npc_state", {"status": "NORMAL", "duration": 0})
        
        # 2. 生成 System Prompt（使用 Character 对象的 render_prompt 方法）
        system_prompt = character.render_prompt(relationship_score)
        
        # Create dashboard panel
        def render_dashboard():
            """Render the top dashboard panel"""
            dashboard_table = Table.grid(padding=(0, 2))
            dashboard_table.add_column(style="stat")
            dashboard_table.add_column(style="npc")
            dashboard_table.add_column(style="stat")
            dashboard_table.add_column(style="warning")
            
            player_name = player_data['name'] if player_data else "Unknown"
            state_name = npc_state.get("status", "NORMAL")
            state_duration = npc_state.get("duration", 0)
            state_display = f"{state_name}"
            if state_duration > 0:
                state_display += f" ({state_duration} turns)"
            
            dashboard_table.add_row(
                f"Player: [player]{player_name}[/player]",
                f"NPC: [npc]{attributes['name']}[/npc]",
                f"Relationship: [stat]{relationship_score}/100[/stat]",
                f"State: [warning]{state_display}[/warning]"
            )
            return Panel(dashboard_table, title="[bold]Game Status[/bold]", border_style="blue")
        
        console.print(render_dashboard())
        console.print()
        
        # 如果是新对话（没记忆），生成并打印开场白
        if not conversation_history:
            with console.status("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
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
            console.print(Panel(
                cleaned_dialogue,
                title="[npc]Shadowheart[/npc] (Looking at you warily)",
                style="npc",
                width=80
            ))
            console.print()
            
            # 把初始问候加入对话历史（存储清理后的文本）
            conversation_history.append({"role": "assistant", "content": cleaned_dialogue})
        else:
            # 如果有记忆，显示不同的开场白
            console.print(Panel(
                "*Nods slightly acknowledging your return*",
                title="[npc]Shadowheart[/npc] (Remembers you)",
                style="npc",
                width=80
            ))
            console.print()
        
        # Start interactive conversation
        console.print(Rule("[info]💬 开始与影心对话（输入 'quit' 或 'exit' 退出并存档）[/info]", style="info"))
        console.print()
        
        while True:
            try:
                # Update dashboard
                console.print(render_dashboard())
                console.print()
                
                # ==========================================
                # Step 1: Get User Input
                # ==========================================
                user_input = console.input("[player]You > [/player]").strip()
                
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
                        "npc_state": npc_state
                    }
                    save_memory(memory_data)
                    console.print("\n[info]再见！[/info]")
                    break
                
                if user_input.startswith('/'):
                    # Handle commands (e.g., /roll)
                    current_action = 'NONE'  # Commands don't use DM analysis
                    roll_result = handle_command(user_input, attributes, relationship_score, current_action)
                    if roll_result is not None:
                        # Store the roll result for injection into next dialogue
                        console.print(f"[info]💡 Roll result stored. Type your dialogue to use it.[/info]")
                    continue  # Skip the rest of the loop for commands
                
                # ==========================================
                # Step 3: STATE CHECK (Before Normal Dialogue)
                # ==========================================
                auto_success = False
                
                # Rule - SILENT: Skip LLM, print message, decrement duration
                if npc_state.get("status") == "SILENT" and npc_state.get("duration", 0) > 0:
                    duration = npc_state["duration"]
                    console.print(f"[warning]❄️ 状态: 拒绝交流 (剩余 {duration} 回合)[/warning]")
                    console.print(Panel(
                        "(她转过身去，完全无视了你的存在。)",
                        title="[npc]Shadowheart[/npc]",
                        style="npc",
                        width=80
                    ))
                    console.print()
                    
                    # Decrement duration
                    npc_state["duration"] -= 1
                    if npc_state["duration"] <= 0:
                        npc_state["status"] = "NORMAL"
                        npc_state["duration"] = 0
                        console.print("[info]💫 状态恢复: NORMAL[/info]")
                        console.print()
                    
                    # Save state and continue (skip LLM)
                    memory_data = {
                        "relationship_score": relationship_score,
                        "history": conversation_history,
                        "npc_state": npc_state
                    }
                    save_memory(memory_data)
                    continue
                
                # Rule - VULNERABLE: Auto-success, decrement duration
                if npc_state.get("status") == "VULNERABLE" and npc_state.get("duration", 0) > 0:
                    duration = npc_state["duration"]
                    auto_success = True
                    console.print(f"[warning]✨ 状态: 心防失守 (剩余 {duration} 回合) -> 自动成功！[/warning]")
                    
                    # Decrement duration
                    npc_state["duration"] -= 1
                    if npc_state["duration"] <= 0:
                        npc_state["status"] = "NORMAL"
                        npc_state["duration"] = 0
                        console.print("[info]💫 状态恢复: NORMAL[/info]")
                
                # ==========================================
                # Step 4: NORMAL DIALOGUE FLOW
                # ==========================================
                
                # Step A: DM Analysis
                try:
                    with console.status("[dm]🎲 DM is analyzing fate...[/dm]", spinner="dots"):
                        intent_data = analyze_intent(user_input)
                    action_type = intent_data['action_type']
                    dc = intent_data['difficulty_class']
                    # 记录意图判定
                    console.print(f"[dm]🎲 判定意图: [item]{action_type}[/item] (DC [stat]{dc}[/stat])[/dm]")
                except Exception as e:
                    # 如果 DM 分析失败，使用默认值并继续
                    console.print(f"[error]⚠️ [DM] 意图分析失败: {e}[/error]")
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
                    console.print(f"[info]🛡️ DC Auto-Calculated: [stat]{dc}[/stat] (Based on Shadowheart's Stats)[/info]")
                
                # Step B: Auto-Roll Logic
                system_info = None
                if action_type != "NONE" and dc > 0:
                    # Check if auto_success is active (VULNERABLE state)
                    if auto_success:
                        # Skip dice roll, force CRITICAL SUCCESS
                        result_type = CheckResult.CRITICAL_SUCCESS
                        system_info = f"Action: {action_type} | Result: CRITICAL SUCCESS (Auto). She is vulnerable."
                        console.print(f"[success]🎯 Auto-Success: [item]{action_type}[/item] -> [critical]CRITICAL SUCCESS[/critical][/success]")
                        console.print()
                        
                        # Grant +1 relationship bonus for auto-success
                        relationship_score += 1
                        relationship_score = max(-100, min(100, relationship_score))
                        console.print(f"[info]💕 Relationship +1 (Vulnerable State Bonus)[/info]")
                    else:
                        # Normal roll logic
                        # Check if player_data is available
                        if player_data is None:
                            console.print("[error]⚠️ Player profile not loaded. Cannot perform auto-roll.[/error]")
                        else:
                            # Get ability score for this action
                            ability_name = get_ability_for_action(action_type)
                            player_ability_scores = player_data.get('ability_scores', {})
                            
                            if ability_name not in player_ability_scores:
                                console.print(f"[error]⚠️ Player doesn't have [stat]{ability_name}[/stat] ability score.[/error]")
                            else:
                                # Get modifier from player stats
                                ability_score = player_ability_scores[ability_name]
                                modifier = calculate_ability_modifier(ability_score)
                                
                                # Calculate situational bonus (check current user input)
                                bonus, reason = get_situational_bonus(conversation_history, action_type, user_input)
                                if bonus != 0:
                                    modifier += bonus
                                    console.print(f"[warning]💍 Situational Bonus: +[stat]{bonus}[/stat] ([item]{reason}[/item])[/warning]")
                                
                                # Determine roll type (advantage/disadvantage)
                                roll_type = determine_roll_type(action_type, relationship_score)
                                
                                # Visual feedback for advantage/disadvantage
                                if roll_type == 'advantage':
                                    console.print(f"[warning]🌟 High relationship grants ADVANTAGE on [item]{action_type}[/item]![/warning]")
                                elif roll_type == 'disadvantage':
                                    console.print("[warning]💀 Low relationship imposes DISADVANTAGE![/warning]")
                                
                                # Execute roll
                                result = roll_d20(dc, modifier, roll_type=roll_type)
                                
                                # Determine result style
                                if result['result_type'] == CheckResult.CRITICAL_SUCCESS:
                                    res_style = "critical"
                                elif result['result_type'] == CheckResult.CRITICAL_FAILURE:
                                    res_style = "critical"
                                elif result['result_type'] == CheckResult.SUCCESS:
                                    res_style = "success"
                                else:
                                    res_style = "failure"
                                
                                # Print result with styled output
                                console.print(f"   └─ [{res_style}]{result['log_str']}[/{res_style}]")
                                console.print()
                                
                                # Trigger state changes based on critical rolls
                                if result['result_type'] == CheckResult.CRITICAL_SUCCESS:
                                    # Natural 20: Set VULNERABLE state
                                    npc_state = {"status": "VULNERABLE", "duration": 3}
                                    console.print(f"[critical]🔥 CRITICAL! She is now VULNERABLE for 3 turns![/critical]")
                                elif result['result_type'] == CheckResult.CRITICAL_FAILURE:
                                    # Natural 1: Set SILENT state
                                    npc_state = {"status": "SILENT", "duration": 2}
                                    console.print(f"[critical]❄️ CRITICAL FAIL! She is now SILENT for 2 turns![/critical]")
                                
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
                
                # Generate reply with spinner
                with console.status("[npc]Shadowheart is thinking...[/npc]", spinner="dots"):
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
                    console.print(f"[info]💕 关系值变化: [stat]{change_str}[/stat] (当前: [stat]{relationship_score}/100[/stat])[/info]")
                
                # 8. 处理一下回复格式
                if cleaned_response:
                    cleaned_response = cleaned_response.strip('"').strip("'")
                    # Display NPC dialogue in a panel
                    console.print(Panel(
                        cleaned_response,
                        title="[npc]Shadowheart[/npc]",
                        style="npc",
                        width=80
                    ))
                else:
                    console.print(Panel(
                        "（没有回应）",
                        title="[npc]Shadowheart[/npc]",
                        style="npc",
                        width=80
                    ))
                console.print()
                
                # 9. 【Memory Hygiene】保存干净的对话历史（不包含系统注入标签）
                # 只保存原始用户输入，不包含 [SYSTEM INFO: ...]
                conversation_history.append({"role": "user", "content": user_input})
                # 保存清理后的 AI 回复（不包含 approval tag）
                conversation_history.append({"role": "assistant", "content": cleaned_response})
                
                # Save npc_state to memory after each turn
                memory_data = {
                    "relationship_score": relationship_score,
                    "history": conversation_history,
                    "npc_state": npc_state
                }
                save_memory(memory_data)
                
                # 10. 滚动窗口：防止 Token 爆炸（保留最近 20 轮）
                # 注意：这里我们只是截断"发给 AI"的列表，还是截断"存储"的列表？
                # 为了简单，我们暂时让记忆文件也保持在 20 轮以内，避免文件无限膨胀
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]
                    
            except KeyboardInterrupt:
                # 强制中断也要存档
                memory_data = {
                    "relationship_score": relationship_score,
                    "history": conversation_history,
                    "npc_state": npc_state
                }
                save_memory(memory_data)
                console.print("\n\n[info]再见！[/info]")
                break
            except Exception as e:
                console.print(f"\n[error]❌ 错误: {e}[/error]")
                console.print("[info]请重试...[/info]\n")
        
    except ImportError as e:
        console.print(f"[error]❌ 导入错误: {e}[/error]")
        console.print("\n[info]请安装必要的依赖包:[/info]")
        console.print("[stat]  pip install dashscope python-dotenv rich[/stat]")
        
        console.print("\n[info]要使用百炼 API，你需要:[/info]")
        console.print("[stat]1. 安装 dashscope 包: pip install dashscope[/stat]")
        console.print("[stat]2. 在项目根目录创建 .env 文件[/stat]")
        console.print("[stat]3. 添加你的 API key: BAILIAN_API_KEY=your-api-key[/stat]")
        console.print("\n[info]或者使用模拟响应进行测试:[/info]")
        
        # Fallback mock dialogue
        console.print()
        console.print(Rule("[info]Mock Dialogue (API not configured)[/info]", style="info"))
        console.print(Panel(
            'Shar\'s will be done. I sense there\'s more to you than meets the eye, '
            'just as there is more to me. Trust is earned, not given freely.',
            title="[npc]Shadowheart[/npc]",
            style="npc",
            width=80
        ))
        console.print(Rule(style="info"))
        
    except Exception as e:
        console.print(f"[error]❌ 意外错误: {e}[/error]")
        console.print(f"[error]错误类型: {type(e).__name__}[/error]")
        import traceback
        console.print("\n[error]详细错误信息:[/error]")
        console.print(traceback.format_exc())


if __name__ == "__main__":
    main()

