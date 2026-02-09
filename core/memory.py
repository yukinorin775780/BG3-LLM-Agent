import os
import json
from typing import Dict, Any, Optional
from config import settings


class MemoryManager:
    """
    Manages the persistence of game state (save/load).
    Handles backward compatibility and data integrity.
    """

    def __init__(self, save_dir: str = settings.SAVE_DIR, filename: str = "shadowheart_memory.json"):
        self.filepath = os.path.join(save_dir, filename)
        # Ensure the directory exists
        os.makedirs(save_dir, exist_ok=True)

    def load(self, default_relationship: int = 0) -> Dict[str, Any]:
        """
        Load memory state from disk with safe defaults.

        Args:
            default_relationship: Fallback relationship score if not found in save.

        Returns:
            Dict containing the full game state.
        """
        # Default empty state
        default_state = {
            "relationship_score": default_relationship,
            "history": [],
            "npc_state": {"status": "NORMAL", "duration": 0},
            "flags": {},
            "summary": "",
            "inventory_player": {},
            "inventory_npc": {},
            "journal": []
        }

        if not os.path.exists(self.filepath):
            return default_state

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return default_state

                data = json.loads(content)

                # --- Backward Compatibility ---
                # 1. Old format: List (just history)
                if isinstance(data, list):
                    default_state["history"] = data
                    return default_state

                # 2. New format: Dict
                if isinstance(data, dict):
                    # Merge loaded data into default state to ensure all keys exist
                    # (This fixes missing 'summary' or 'journal' in old saves)
                    for key, default_val in default_state.items():
                        if key not in data:
                            data[key] = default_val

                    # Logic Fix: Priority for relationship score
                    # If save has None, use default. If save has value, keep it.
                    if data.get("relationship_score") is None:
                        data["relationship_score"] = default_relationship

                    return data

                return default_state

        except Exception as e:
            print(f"[Memory Error] Failed to load {self.filepath}: {e}")
            return default_state

    def save(self, data: Dict[str, Any]) -> bool:
        """
        Persist memory state to disk.

        Args:
            data: The complete game state dictionary.

        Returns:
            True if save succeeded, False otherwise.
        """
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[Memory Error] Failed to save to {self.filepath}: {e}")
            return False
