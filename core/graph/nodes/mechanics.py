"""
Mechanics 节点：技能检定与掷骰。
"""

from core.graph.graph_state import GameState
from core.systems import mechanics


def mechanics_node(state: GameState) -> dict:
    """
    根据意图执行技能检定（PERSUASION/DECEPTION/STEALTH/INSIGHT 等）。

    调用 mechanics.execute_skill_check：仅合并 journal_events 与 latest_roll；
    不修改 entities / affection（情感由 DM 与 LLM 决定）。
    """
    intent = state.get("intent", "chat")
    is_probing_secret = state.get("is_probing_secret", False)
    if intent in ["chat", "CHAT", "command_done", "pending", "gift_given", "item_used"] and not is_probing_secret:
        return {}

    print(f"⚙️ Mechanics Node: Processing {intent} (is_probing_secret={is_probing_secret})...")
    result = mechanics.execute_skill_check(state)

    out: dict = {"journal_events": result.get("journal_events", [])}
    if "raw_roll_data" in result:
        out["latest_roll"] = result["raw_roll_data"]
    return out
