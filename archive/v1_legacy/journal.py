"""
Narrative Journal - Tracks key game events for grounding and UI.
"""

from typing import List, Optional, Any

MAX_ENTRIES = 50


class Journal:
    """
    Manages a list of past events (e.g. critical rolls, story triggers).
    Supports save/load via to_dict/from_dict for backward compatibility.
    """

    def __init__(self) -> None:
        self._entries: List[str] = []

    def add_entry(self, text: str, turn_count: Optional[int] = None) -> None:
        """
        Add a timestamped/turn-based entry. Keeps only the last MAX_ENTRIES.
        """
        if turn_count is not None:
            entry = f"[Turn {turn_count}] {text}"
        else:
            entry = f"[Event] {text}"
        self._entries.append(entry)
        if len(self._entries) > MAX_ENTRIES:
            del self._entries[: len(self._entries) - MAX_ENTRIES]

    def get_recent_entries(self, limit: int = 3) -> List[str]:
        """
        Return the last N entries (newest last). For UI/AI display.
        """
        if not self._entries:
            return []
        return self._entries[-limit:]

    def to_dict(self) -> List[str]:
        """
        Serialize for JSON save. Returns a list for backward compatibility.
        """
        return list(self._entries)

    @classmethod
    def from_dict(cls, data: Any) -> "Journal":
        """
        Deserialize from JSON. Handles missing or old formats gracefully.
        - None / missing -> empty Journal
        - list (legacy) -> entries
        - dict with "entries" -> entries
        """
        inst = cls()
        if data is None:
            return inst
        if isinstance(data, list):
            inst._entries = list(data)
            return inst
        if isinstance(data, dict):
            inst._entries = list(data.get("entries", data.get("journal", [])))
            return inst
        return inst
