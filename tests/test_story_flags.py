"""
剧情标识 (story_rules) 渲染测试
验证 loader 根据 current_flags 收集 active_story_rules 并注入 persona 模板。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from characters.loader import load_character

BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _render_shadowheart_prompt(current_flags: dict) -> str:
    sh = load_character("shadowheart")
    attrs = sh.data.copy()
    attrs["relationship"] = 50
    return sh.loader.render_prompt(
        name=sh.name,
        attributes=attrs,
        current_flags=current_flags,
        flags={},  # 与 current_flags 分离，避免重复合并
        summary="",
        journal_entries=[],
        inventory_items=["healing_potion"],
        has_healing_potion=True,
        time_of_day="晨曦 (Morning)",
        hp=20,
        active_buffs=[],
        relationship_score=50,
        affection=50,
        shar_faith=70,
        memory_awakening=10,
    )


def run_test():
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  story_rules / current_flags 渲染测试 (Shadowheart){RESET}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    current_flags = {
        "abandoned_shar": True,
        "knows_secret": True,
        "insulted_shar": False,
    }

    prompt = _render_shadowheart_prompt(current_flags)

    print(f"{CYAN}[完整 Prompt 开始]{RESET}\n")
    print(prompt)
    print(f"\n{CYAN}[完整 Prompt 结束]{RESET}\n")

    print(f"{BOLD}{'='*70}{RESET}")
    print(f"{YELLOW}【验证检查】{RESET}")
    print("  - 应同时出现: [FAITH SHIFT: SHAR ABANDONED]、[STORY STATE UPDATE: THE ARTIFACT]")
    print("  - 不应出现: [CRITICAL MEMORY: SHAR INSULTED]（insulted_shar 为 False）")
    print(f"{BOLD}{'='*70}{RESET}\n")

    assert "[CURRENT STORY STATE]" in prompt, "缺少 [CURRENT STORY STATE] 区块"
    assert "[FAITH SHIFT: SHAR ABANDONED]" in prompt, "缺少 [FAITH SHIFT: SHAR ABANDONED]"
    assert "[STORY STATE UPDATE: THE ARTIFACT]" in prompt, "缺少 [STORY STATE UPDATE: THE ARTIFACT]"
    assert "[CRITICAL MEMORY: SHAR INSULTED]" not in prompt, "不应渲染 insulted_shar（False）"

    print(f"{GREEN}✓ 所有断言通过{RESET}")


if __name__ == "__main__":
    run_test()
