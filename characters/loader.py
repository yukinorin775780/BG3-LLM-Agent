"""
Character Loader Module
Loads character data from YAML files and Jinja2 templates.
"""

import os
import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from typing import Dict, Any, Optional, List
from core import inventory


class CharacterLoader:
    """
    Loads character attributes from YAML files and renders prompts using Jinja2 templates.
    
    Uses relative paths based on the module's location to find character files.
    """
    
    def __init__(self):
        """Initialize the CharacterLoader with the characters directory path."""
        # Get the directory where this module is located
        self.characters_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Initialize Jinja2 environment with the characters directory as template path
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.characters_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
    
    def load_character(self, name: str) -> Dict[str, Any]:
        """
        Load character data from YAML file and return attributes dictionary.
        
        Args:
            name: Character name (e.g., "shadowheart")
                The method will look for {name}.yaml in the characters directory.
        
        Returns:
            dict: Character attributes loaded from YAML file
        
        Raises:
            FileNotFoundError: If the YAML file doesn't exist
            yaml.YAMLError: If the YAML file is malformed
        """
        # Construct path to YAML file
        yaml_filename = f"{name}.yaml"
        yaml_path = os.path.join(self.characters_dir, yaml_filename)
        
        # Check if file exists
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(
                f"Character file not found: {yaml_path}\n"
                f"Expected file: {yaml_filename} in {self.characters_dir}"
            )
        
        # Load YAML file
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                attributes = yaml.safe_load(f)
            
            if attributes is None:
                raise ValueError(f"YAML file is empty or contains no data: {yaml_path}")
            
            return attributes
            
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML file {yaml_path}: {e}")
    
    def load_template(self, name: str) -> Any:
        """
        Load Jinja2 template for the character.
        
        Args:
            name: Character name (e.g., "shadowheart")
                The method will look for {name}_persona_template.j2 or persona_template.j2 in the characters directory.
        
        Returns:
            jinja2.Template: Loaded Jinja2 template
        
        Raises:
            TemplateNotFound: If the template file doesn't exist
        """
        # Try character-specific template first (e.g., shadowheart_persona_template.j2)
        template_names = [
            f"{name}_persona_template.j2",
            "persona_template.j2"  # Fallback to generic persona_template.j2
        ]
        
        for template_name in template_names:
            try:
                template = self.jinja_env.get_template(template_name)
                return template
            except TemplateNotFound:
                continue
        
        # If no template found, raise error
        raise TemplateNotFound(
            f"Template not found for character '{name}'. "
            f"Tried: {', '.join(template_names)}"
        )
    
    def render_prompt(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Render the prompt template with character attributes.
        
        This method loads the character data, calculates necessary values,
        and renders the Jinja2 template.
        
        Args:
            name: Character name (e.g., "shadowheart")
            attributes: Optional character attributes dictionary.
                If None, will load from YAML file.
            **kwargs: Additional variables to pass to the template
                (e.g., wis_mod, int_mod, cha_mod, relationship_score, etc.)
        
        Returns:
            str: Rendered prompt string
        """
        # Load attributes if not provided
        if attributes is None:
            attributes = self.load_character(name)
        
        # Load template
        template = self.load_template(name)
        
        # Prepare template variables
        template_vars = {
            "attributes": attributes,
            **kwargs
        }
        
        # Render template
        return template.render(**template_vars)
    
    def get_characters_dir(self) -> str:
        """
        Get the characters directory path.
        
        Returns:
            str: Absolute path to the characters directory
        """
        return self.characters_dir
    
    @staticmethod
    def get_relationship_status(relationship_score: int) -> str:
        """
        Get the relationship status name based on the relationship score.
        
        This is a utility function that converts a numeric relationship score
        into a human-readable status string.
        
        Args:
            relationship_score: The relationship score (range: -100 to 100)
        
        Returns:
            str: The relationship status name with Chinese translation
        
        Examples:
            >>> CharacterLoader.get_relationship_status(85)
            'Devoted (恋人/至死不渝)'
            >>> CharacterLoader.get_relationship_status(0)
            'Neutral (中立)'
            >>> CharacterLoader.get_relationship_status(-60)
            'Hostile (敌对)'
        """
        if relationship_score >= 81:
            return "Devoted (恋人/至死不渝)"
        elif relationship_score >= 41:
            return "Trusting (信赖)"
        elif relationship_score >= 11:
            return "Friendly (友好)"
        elif relationship_score >= -9:
            return "Neutral (中立)"
        elif relationship_score >= -49:
            return "Negative (反感)"
        else:  # relationship_score <= -50
            return "Hostile (敌对)"

# =========================================================================
# 新增：封装一个 Character 对象，让 main.py 调用更简单
# =========================================================================

class Character:
    """
    Represents a loaded character instance.
    Holds the data and provides methods to render prompts.
    """
    def __init__(self, name: str, data: Dict[str, Any], loader: CharacterLoader, quests: Optional[List[Any]] = None):
        self.name = name
        self.data = data
        self.loader = loader
        self.quests = quests if quests is not None else []
        self.inventory = inventory.Inventory()
        
    def render_prompt(
        self,
        relationship_score: int,
        flags: Optional[dict] = None,
        summary: str = "",
        journal_entries: Optional[List[str]] = None,
        inventory_items: Optional[List[str]] = None,
        has_healing_potion: bool = False,
    ) -> str:
        """
        Render the system prompt for this character based on current relationship, flags, summary,
        journal entries, and inventory items.
        
        Args:
            relationship_score: Current relationship score with the player
            flags: Dictionary of persistent world-state flags (defaults to empty dict)
            summary: Story summary for context (defaults to empty string)
            journal_entries: Recent journal entries for the AI to remember (defaults to [])
            inventory_items: List of item names the character is holding (defaults to [])
            has_healing_potion: Whether the character has at least one healing_potion (for reality constraints)
        """
        # 我们需要在渲染时，把最新的 relationship_score 注入到 attributes 里
        # 但不要直接修改 self.data，以免污染原始数据，所以 copy 一份
        current_attributes = self.data.copy()
        current_attributes['relationship'] = relationship_score
        
        # Ensure flags is a dict (default to empty)
        if flags is None:
            flags = {}
        if journal_entries is None:
            journal_entries = []
        if inventory_items is None:
            inventory_items = []
        
        return self.loader.render_prompt(
            name=self.name,
            attributes=current_attributes,
            flags=flags,
            summary=summary,
            journal_entries=journal_entries,
            inventory_items=inventory_items,
            has_healing_potion=has_healing_potion,
        )

# =========================================================================
# 新增：对外暴露的快捷函数 (main.py 只需要 import 这个)
# =========================================================================

def load_character(name: str) -> Character:
    """
    Factory function to load a character and return a Character object.
    
    Args:
        name: The name of the character (e.g., "shadowheart")
    
    Returns:
        Character: An initialized character object
    """
    loader = CharacterLoader()
    data = loader.load_character(name)
    quests_data = data.get('quests', [])
    character = Character(name, data, loader, quests=quests_data)
    
    # Load inventory items
    inv_data = data.get('inventory', [])
    for item in inv_data:
        character.inventory.add(item)
    
    return character