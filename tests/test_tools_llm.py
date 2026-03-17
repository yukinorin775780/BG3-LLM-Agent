"""
隔离测试：验证大模型是否能连续、多次调用 Tools（Agent 核心循环）
完全绕过 LangGraph，手写一个最基础的 Agent Loop。
"""

import sys
import json
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

load_dotenv()

# ==========================================
# 1. 模拟物理世界 (Mock 数据库)
# ==========================================
PLAYER_INVENTORY = {"治疗药水": 0, "金币": 100}
SHADOWHEART_INVENTORY = {"莎尔的圣徽": 1}

# ==========================================
# 2. 定义赛博义体 (Tools)
# 使用 @tool 装饰器，LangChain 会自动提取函数签名和 docstring 给大模型
# ==========================================
@tool
def check_target_inventory(item_keyword: str, target_id: str) -> str:
    """
    检查目标角色的背包中是否包含特定物品。
    :param item_keyword: 物品名称，例如 '治疗药水'
    :param target_id: 目标ID，例如 'player' 或 'shadowheart'
    """
    inventory = PLAYER_INVENTORY if target_id == "player" else SHADOWHEART_INVENTORY
    has_item = item_keyword in inventory and inventory[item_keyword] > 0
    return json.dumps({"has_item": has_item, "target_id": target_id, "item": item_keyword})


@tool
def transfer_item(item_keyword: str, source_id: str, target_id: str) -> str:
    """
    在两个角色之间转移物品。必须在确认源角色有该物品后才能调用！

    CRITICAL PERSPECTIVE RULES:
    - If the player gives YOU (the NPC) an item: source_id MUST be 'player' and target_id MUST be your character ID (e.g., 'shadowheart').
    - If YOU (the NPC) give the player an item: source_id MUST be your character ID and target_id MUST be 'player'.
    DO NOT mix up the source and target!

    :param item_keyword: 物品名称
    :param source_id: 失去物品的角色ID (the one who LOSES the item)
    :param target_id: 获得物品的角色ID (the one who RECEIVES the item)
    """
    source_inv = PLAYER_INVENTORY if source_id == "player" else SHADOWHEART_INVENTORY
    target_inv = PLAYER_INVENTORY if target_id == "player" else SHADOWHEART_INVENTORY

    if item_keyword in source_inv and source_inv[item_keyword] > 0:
        source_inv[item_keyword] -= 1
        target_inv[item_keyword] = target_inv.get(item_keyword, 0) + 1
        return json.dumps({"status": "success", "message": f"成功将 {item_keyword} 从 {source_id} 转移给 {target_id}"})
    else:
        return json.dumps({"status": "failed", "message": f"{source_id} 没有 {item_keyword}"})


# ==========================================
# 3. 核心测试逻辑
# ==========================================
def test_npc_agent_loop():
    print("🔍 开始测试 LLM Agent 连续工具调用能力...\n")

    print(f"🎒 [初始状态] 玩家背包: {PLAYER_INVENTORY}")
    print(f"🎒 [初始状态] 影心背包: {SHADOWHEART_INVENTORY}\n")

    from config import settings

    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        api_key=settings.API_KEY or "",  # type: ignore[arg-type]
        base_url=settings.BASE_URL,
        temperature=0.7,
    )

    tools = [check_target_inventory, transfer_item]
    llm_with_tools = llm.bind_tools(tools)

    # System Prompt 明确给出"操作流"指导
    sys_msg = SystemMessage(
        content=(
            "You are Shadowheart from Baldur's Gate 3. "
            "If the player offers you an item, you must follow these steps strictly:\n"
            "1. Call `check_target_inventory` to verify they have it.\n"
            "2. IF they have it, call `transfer_item` to take it from 'player' to 'shadowheart', THEN thank them with your typical guarded/sassy personality.\n"
            "3. IF they don't have it, DO NOT call `transfer_item`. Just mock them for lying."
        )
    )
    user_msg = HumanMessage(content="影心，我把刚才那瓶治疗药水递给你。")
    messages = [sys_msg, user_msg]

    print("🗣️ 玩家: 影心，我把刚才那瓶治疗药水递给你。")
    print("🧠 触发 Agent 思考循环...\n")

    # ==========================================
    # 💥 Agent 核心逻辑：While 循环
    # ==========================================
    loop_count = 1
    while True:
        print(f"--- 第 {loop_count} 轮思考 ---")
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # 如果没有工具调用，说明大模型决定说话了，跳出循环
        if not response.tool_calls:
            print("✅ 大模型判断所有操作已完成，准备输出文本。")
            break

        # 如果有工具调用，就挨个执行
        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            print(f"   ⚙️ [决定调用] {tool_name} (参数: {tool_args})")

            # 路由到对应的本地函数
            if tool_name == "check_target_inventory":
                result_str = check_target_inventory.invoke(tool_args)
            elif tool_name == "transfer_item":
                result_str = transfer_item.invoke(tool_args)
            else:
                result_str = '{"error": "tool not found"}'

            print(f"   📥 [工具返回] {result_str}")

            # 将结果封装备忘，塞回消息队列
            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

        loop_count += 1
        print("-" * 30)

    # 循环结束后，打印最终文本和世界状态
    print("\n" + "=" * 40)
    print("🎭 影心:")
    print(response.content)
    print("=" * 40 + "\n")

    print(f"🎒 [最终状态] 玩家背包: {PLAYER_INVENTORY}")
    print(f"🎒 [最终状态] 影心背包: {SHADOWHEART_INVENTORY}")


if __name__ == "__main__":
    test_npc_agent_loop()
