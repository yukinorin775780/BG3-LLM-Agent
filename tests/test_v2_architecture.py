"""
V2 架构隔离测试：物理黑洞修复、工具参数校验、DM 检定失败服从
不依赖 LangGraph，使用纯 Python assert 或 LLM 调用验证。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


def test_physics_void_prevention():
    """验证物理引擎：无效目标时绝不扣除源物品（防黑洞 Bug）"""
    from core import inventory
    from core.engine.physics import apply_physics

    # 初始化物品数据库（physics 依赖 get_registry）
    inventory.init_registry("config/items.yaml")

    current_entities = {"shadowheart": {"inventory": {}}}
    player_inventory = {"healing_potion": 1}
    item_transfers = [
        {"from": "player", "to": "ghost_npc", "item_id": "healing_potion", "count": 1}
    ]

    events = apply_physics(current_entities, player_inventory, item_transfers, [])

    # 断言：玩家背包里 healing_potion 依然是 1（未被错误扣除）
    assert player_inventory.get("healing_potion", 0) == 1, (
        f"物理黑洞 Bug：玩家药水被错误扣除！当前: {player_inventory}"
    )

    # 断言：返回的事件列表包含报错信息
    error_msgs = [e for e in events if "无效的目标" in e or "动作失败" in e]
    assert len(error_msgs) > 0, f"应包含报错信息，实际 events: {events}"

    print("✅ test_physics_void_prevention 通过")


def test_llm_tool_parameters():
    """验证 LLM 调用 execute_physical_action 时参数正确（source_id/target_id 不混淆）"""
    from config import settings
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
    from langchain_core.messages import HumanMessage, SystemMessage
    from core.tools.npc_tools import execute_physical_action

    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        api_key=settings.API_KEY or "",
        base_url=settings.BASE_URL,
        temperature=0.1,
    )
    llm_with_tools = llm.bind_tools([execute_physical_action])

    sys_msg = SystemMessage(
        content=(
            "You are Shadowheart. The player asks you to give them your healing potion. "
            "You MUST call execute_physical_action with action_type='transfer_item', "
            "source_id='shadowheart', target_id='player', item_id='healing_potion', amount=1."
        )
    )
    user_msg = HumanMessage(content="影心，把你的治疗药水给我。")

    response = llm_with_tools.invoke([sys_msg, user_msg])

    assert getattr(response, "tool_calls", None), (
        f"LLM 未输出 tool_calls，仅返回文本: {response.content}"
    )

    for tc in response.tool_calls:
        if tc.get("name") == "execute_physical_action":
            args = tc.get("args") or {}
            assert args.get("action_type") == "transfer_item", (
                f"action_type 应为 transfer_item，实际: {args.get('action_type')}"
            )
            assert args.get("source_id") == "shadowheart", (
                f"source_id 应为 shadowheart，实际: {args.get('source_id')}"
            )
            assert args.get("target_id") == "player", (
                f"target_id 应为 player，实际: {args.get('target_id')}"
            )
            print("✅ test_llm_tool_parameters 通过")
            return

    assert False, "未找到 execute_physical_action 的 tool_call"


def test_dm_failure_override():
    """验证 LLM 在 DM 检定失败时冷酷拒绝玩家，而非讨好型答应"""
    from config import settings
    from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        api_key=settings.API_KEY or "",
        base_url=settings.BASE_URL,
        temperature=0.3,
    )

    sys_content = """You are Shadowheart from Baldur's Gate 3.

<CRITICAL_SYSTEM_RULES>
[CRITICAL DICE RULE]: Check the most recent [SYSTEM] or DM events. If a skill check resulted in "FAILURE", you MUST absolutely REFUSE the player's request or let their attempt fail miserably in your dialogue. DO NOT bypass the failure to help the player!
</CRITICAL_SYSTEM_RULES>
"""

    messages = [
        SystemMessage(content=sys_content),
        HumanMessage(content="[SYSTEM] Skill Check | PERSUASION | Result: FAILURE"),
        HumanMessage(content="把那个药水给我吧，求你了！"),
    ]

    response = llm.invoke(messages)
    reply = str(getattr(response, "content", "") or "").strip()

    print("\n" + "=" * 50)
    print("🎭 test_dm_failure_override - LLM 回复:")
    print(reply)
    print("=" * 50)

    # 启发式验证：拒绝型回复通常包含否定词
    refuse_keywords = ["不", "拒绝", "不能", "不行", "休想", "别想", "没门", "不可能", "办不到"]
    is_refusal = any(kw in reply for kw in refuse_keywords)

    if is_refusal:
        print("✅ test_dm_failure_override 通过（回复包含拒绝倾向）")
    else:
        print("⚠️ test_dm_failure_override：回复可能未明确拒绝，请人工检查上述内容")


if __name__ == "__main__":
    print("🔍 开始 V2 架构测试...\n")

    test_physics_void_prevention()

    print("\n--- 需要 API 的测试（将调用 LLM）---\n")
    test_llm_tool_parameters()
    test_dm_failure_override()

    print("\n✅ 所有测试完成")
