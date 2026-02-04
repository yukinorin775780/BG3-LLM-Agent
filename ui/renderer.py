"""
UI Renderer Module (View Layer)
Handles all Rich/UI rendering - no game logic
"""

from typing import Optional
from rich.console import Console, Group
from rich.panel import Panel
from rich.theme import Theme
from rich.text import Text
from rich.rule import Rule
from rich.table import Table
from rich.box import HEAVY
from core.dice import CheckResult
from core.inventory import Inventory


class GameRenderer:
    """Handles all UI rendering using Rich library"""
    
    def __init__(self):
        """Initialize the renderer with custom BG3 theme"""
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
        self.console = Console(theme=bg3_theme)
    
    def clear_screen(self):
        """Clear the console screen"""
        self.console.clear()
    
    def show_title(self, title_text: str):
        """Display a styled title rule"""
        self.console.print(Rule(f"[bold purple]{title_text}[/bold purple]", style="bold purple"))
        self.console.print()
    
    def show_dashboard(self, player_name: str, npc_name: str, relationship: int, npc_state: dict, active_quests: Optional[list] = None, player_inventory: Optional[Inventory] = None, npc_inventory: Optional[Inventory] = None, journal: Optional[list] = None) -> Group:
        """
        Render the dashboard panels showing game status, quest journal, and recent events.
        
        Args:
            player_name: Player's name
            npc_name: NPC's name
            relationship: Current relationship score
            npc_state: NPC state dict with 'status' and 'duration'
            active_quests: List of active quest objects (optional)
            player_inventory: Player's inventory object (optional)
            npc_inventory: NPC's inventory object (optional)
            journal: List of journal entry strings for recent events (optional)
        
        Returns:
            Group: A Group containing the status panel, quest panel, and journal panel
        """
        # Panel 1: Status Panel
        dashboard_table = Table.grid(padding=(0, 2))
        dashboard_table.add_column(style="stat")
        dashboard_table.add_column(style="npc")
        dashboard_table.add_column(style="stat")
        dashboard_table.add_column(style="warning")
        
        state_name = npc_state.get("status", "NORMAL")
        state_duration = npc_state.get("duration", 0)
        state_display = f"{state_name}"
        if state_duration > 0:
            state_display += f" ({state_duration} turns)"
        
        # Player inventory display
        player_inv_text = "🎒 Inventory: Empty"
        if player_inventory:
            player_inv_text = f"🎒 Inventory: {player_inventory.list_items()}"
        
        # NPC inventory display
        npc_inv_text = ""
        if npc_inventory:
            npc_inv_text = f"🎒 Equipped: {npc_inventory.list_items()}"
        
        dashboard_table.add_row(
            f"Player: [player]{player_name}[/player]",
            f"NPC: [npc]{npc_name}[/npc]",
            f"Relationship: [stat]{relationship}/100[/stat]",
            f"State: [warning]{state_display}[/warning]"
        )
        
        # Add inventory rows
        dashboard_table.add_row(
            player_inv_text,
            npc_inv_text,
            "",
            ""
        )
        
        status_panel = Panel(dashboard_table, title="[bold]Game Status[/bold]", border_style="blue")
        
        # Panel 2: Quest Panel
        if active_quests:
            quest_content = []
            for quest in active_quests:
                quest_title = quest.get("title", "Unknown Quest")
                stage_desc = quest.get("stage_description", "")
                quest_status = quest.get("status", "ACTIVE")
                
                if quest_status == "COMPLETED":
                    # Completed quests: Green checkmark, dimmed text
                    quest_line = f"✅ [bold green]{quest_title}[/bold green]: [dim]{stage_desc}[/dim]"
                else:
                    # Active quests: Fire icon, bright gold text
                    quest_line = f"🔥 [bold gold1]{quest_title}[/bold gold1]: [gold1]{stage_desc}[/gold1]"
                
                quest_content.append(quest_line)
            
            quest_text = "\n".join(quest_content)
        else:
            quest_text = "[dim]No active quests.[/dim]"
        
        quest_panel = Panel(
            quest_text,
            title="📓 QUEST JOURNAL",
            title_align="left",
            border_style="gold1",
            box=HEAVY,
            expand=True
        )
        
        # Panel 3: Recent Journal Events (data from journal.get_recent_entries(3))
        if journal and len(journal) > 0:
            recent = list(journal)
            recent.reverse()  # Newest first for display
            journal_text = "\n".join(f"• {e}" for e in recent)
        else:
            journal_text = "[dim]No major events yet.[/dim]"
        
        journal_panel = Panel(
            journal_text,
            title="📜 Recent Journal Events",
            title_align="left",
            border_style="dim",
            expand=True
        )
        
        return Group(status_panel, quest_panel, journal_panel)
    
    def input_prompt(self, prompt_text: str = "[player]You > [/player]") -> str:
        """
        Get user input with styled prompt.
        
        Args:
            prompt_text: The prompt text to display
        
        Returns:
            str: User input string
        """
        return self.console.input(prompt_text).strip()
    
    def create_spinner(self, text: str, spinner: str = "dots"):
        """
        Create a status spinner context manager.
        
        Args:
            text: Text to display in spinner
            spinner: Spinner style (default: "dots")
        
        Returns:
            Context manager for console.status
        """
        return self.console.status(text, spinner=spinner)
    
    def print_npc_response(self, name: str, text: str, subtitle: str = ""):
        """
        Display NPC dialogue in a styled panel.
        
        Args:
            name: NPC name
            text: Dialogue text
            subtitle: Optional subtitle (e.g., "Looking at you warily")
        """
        title = f"[npc]{name}[/npc]"
        if subtitle:
            title += f" ({subtitle})"
        
        self.console.print(Panel(
            text,
            title=title,
            style="npc",
            width=80
        ))
        self.console.print()
    
    def print_dm_analysis(self, action: str, dc: int):
        """
        Display DM intent analysis result.
        
        Args:
            action: Action type (e.g., "PERSUASION")
            dc: Difficulty class
        """
        self.console.print(f"[dm]🎲 判定意图: [item]{action}[/item] (DC [stat]{dc}[/stat])[/dm]")
    
    def print_roll_result(self, result_dict: dict):
        """
        Display dice roll result with appropriate styling.
        
        Args:
            result_dict: Result dictionary from roll_d20
        """
        result_type = result_dict['result_type']
        
        # Determine result style
        if result_type == CheckResult.CRITICAL_SUCCESS:
            res_style = "critical"
        elif result_type == CheckResult.CRITICAL_FAILURE:
            res_style = "critical"
        elif result_type == CheckResult.SUCCESS:
            res_style = "success"
        else:
            res_style = "failure"
        
        # Print result with styled output
        self.console.print(f"   └─ [{res_style}]{result_dict['log_str']}[/{res_style}]")
        self.console.print()
    
    def print_system_info(self, text: str):
        """Display system information message"""
        self.console.print(f"[info]{text}[/info]")
    
    def print_warning(self, text: str):
        """Display warning message"""
        self.console.print(f"[warning]{text}[/warning]")
    
    def print_error(self, text: str):
        """Display error message"""
        self.console.print(f"[error]{text}[/error]")
    
    def print_state_effect(self, status: str, duration: int, effect_desc: str):
        """
        Display NPC state effect message.
        
        Args:
            status: State status (e.g., "SILENT", "VULNERABLE")
            duration: Remaining duration
            effect_desc: Description of the effect
        """
        if status == "SILENT":
            self.console.print(f"[warning]❄️ 状态: 拒绝交流 (剩余 {duration} 回合)[/warning]")
        elif status == "VULNERABLE":
            self.console.print(f"[warning]✨ 状态: 心防失守 (剩余 {duration} 回合) -> 自动成功！[/warning]")
        else:
            self.console.print(f"[info]💫 状态恢复: {status}[/info]")
            self.console.print()
    
    def print_advantage_alert(self, action_type: str, roll_type: str):
        """
        Display advantage/disadvantage alert.
        
        Args:
            action_type: Action type (e.g., "PERSUASION")
            roll_type: Roll type ('advantage' or 'disadvantage')
        """
        if roll_type == 'advantage':
            self.console.print(f"[warning]🌟 High relationship grants ADVANTAGE on [item]{action_type}[/item]![/warning]")
        elif roll_type == 'disadvantage':
            self.console.print("[warning]💀 Low relationship imposes DISADVANTAGE![/warning]")
    
    def print_situational_bonus(self, bonus: int, reason: str):
        """
        Display situational bonus message.
        
        Args:
            bonus: Bonus amount
            reason: Reason for the bonus
        """
        self.console.print(f"[warning]💍 Situational Bonus: +[stat]{bonus}[/stat] ([item]{reason}[/item])[/warning]")
    
    def print_relationship_change(self, change: int, current: int):
        """
        Display relationship score change.
        
        Args:
            change: Change amount (can be negative)
            current: Current relationship score
        """
        change_str = f"+{change}" if change > 0 else str(change)
        self.console.print(f"[info]💕 关系值变化: [stat]{change_str}[/stat] (当前: [stat]{current}/100[/stat])[/info]")
    
    def print_auto_success(self, action_type: str):
        """Display auto-success message (VULNERABLE state)"""
        self.console.print(f"[success]🎯 Auto-Success: [item]{action_type}[/item] -> [critical]CRITICAL SUCCESS[/critical][/success]")
        self.console.print()
    
    def print_action_effect(self, message: str):
        """Display NPC action effect (e.g. using an item)."""
        self.console.print(f"[info]🧪 {message}[/info]")

    def print_critical_state_change(self, result_type: CheckResult, new_status: str, duration: int):
        """
        Display critical roll state change message.
        
        Args:
            result_type: CheckResult enum value
            new_status: New NPC status
            duration: Duration of the new state
        """
        if result_type == CheckResult.CRITICAL_SUCCESS:
            self.console.print(f"[critical]🔥 CRITICAL! She is now VULNERABLE for {duration} turns![/critical]")
        elif result_type == CheckResult.CRITICAL_FAILURE:
            self.console.print(f"[critical]❄️ CRITICAL FAIL! She is now SILENT for {duration} turns![/critical]")
    
    def print_rule(self, text: str, style: str = "info"):
        """Display a horizontal rule"""
        self.console.print(Rule(text, style=style))
        self.console.print()
    
    def print(self, *args, **kwargs):
        """Direct print passthrough to console"""
        self.console.print(*args, **kwargs)
