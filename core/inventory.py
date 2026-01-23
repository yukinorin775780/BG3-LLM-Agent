"""
Inventory Management Module
Handles item storage and management for characters.
"""

from typing import List


class Inventory:
    """
    Simple inventory system for managing items.
    """
    
    def __init__(self):
        """Initialize an empty inventory."""
        self.items: List[str] = []
    
    def add(self, item_name: str) -> None:
        """
        Add an item to the inventory.
        
        Args:
            item_name: Name of the item to add
        """
        if item_name and item_name not in self.items:
            self.items.append(item_name)
    
    def remove(self, item_name: str) -> bool:
        """
        Remove an item from the inventory if it exists.
        
        Args:
            item_name: Name of the item to remove
        
        Returns:
            bool: True if item was removed, False if it didn't exist
        """
        if item_name in self.items:
            self.items.remove(item_name)
            return True
        return False
    
    def has(self, item_name: str) -> bool:
        """
        Check if an item exists in the inventory.
        
        Args:
            item_name: Name of the item to check
        
        Returns:
            bool: True if item exists, False otherwise
        """
        return item_name in self.items
    
    def list_items(self) -> str:
        """
        Get a comma-separated string of all items.
        
        Returns:
            str: Comma-separated list of items, or "Empty" if inventory is empty
        """
        if not self.items:
            return "Empty"
        return ", ".join(self.items)
