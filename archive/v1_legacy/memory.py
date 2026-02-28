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
        os.makedirs(save_dir, exist_ok=True)

    def load(self, default_relationship: int = 0) -> Dict[str, Any]:
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

                if isinstance(data, list):
                    default_state["history"] = data
                    return default_state

                if isinstance(data, dict):
                    for key, default_val in default_state.items():
                        if key not in data:
                            data[key] = default_val

                    if data.get("relationship_score") is None:
                        data["relationship_score"] = default_relationship

                    return data

                return default_state

        except Exception as e:
            print(f"[Memory Error] Failed to load {self.filepath}: {e}")
            return default_state

    def save(self, data: Dict[str, Any]) -> bool:
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[Memory Error] Failed to save to {self.filepath}: {e}")
            return False
