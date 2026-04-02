"""
BG3 LLM Agent — FastAPI 后端，供 Web UI 调用。
"""

import copy
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import START
from pydantic import BaseModel

from core import inventory
from core.engine.physics import execute_loot
from core.graph.graph_builder import build_graph
from core.graph.nodes.utils import first_entity_id
from core.systems.world_init import get_initial_world_state

# 初始化物品数据库
inventory.init_registry("config/items.yaml")

app = FastAPI(title="BG3 LLM Agent API", version="2.0")

# 允许跨域请求 (为了下周的前端网页做准备)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Data Models ---
class ChatRequest(BaseModel):
    user_input: str = ""
    intent: str | None = None  # 可选：系统级指令 / 挂机模式等预留意图通道
    session_id: str = "test_run_001"  # 默认新会话，避开旧 SQLite 存档
    character: str | None = None  # 可选：UI 拾取等指定角色 id（如 shadowheart）


class ChatResponse(BaseModel):
    responses: List[Dict[str, str]]  # 例如: [{"speaker": "astarion", "text": "亲爱的..."}]
    journal_events: List[str]  # 本回合发生的新事件
    current_location: str  # 当前位置
    environment_objects: Dict[str, Any]  # 场景里的可交互物品 (如箱子、门)
    party_status: Dict[str, Any]  # 队友的血量、好感度等状态


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    uin = (req.user_input or "").strip()
    intent_s = (req.intent or "").strip()
    if not uin and not intent_s:
        raise HTTPException(
            status_code=400,
            detail="At least one of user_input or intent must be non-empty.",
        )

    config = {"configurable": {"thread_id": req.session_id}}

    # 连接 LangGraph 记忆库
    async with AsyncSqliteSaver.from_conn_string("memory.db") as saver:
        graph = build_graph(checkpointer=saver)

        # 1. 检查是否为空存档 (创世逻辑，与 main.py 对齐)
        try:
            snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
            prev_values = snapshot.values if hasattr(snapshot, "values") else {}
        except Exception:
            prev_values = {}
        if not isinstance(prev_values, dict):
            prev_values = {}

        # 记录本轮之前的日志长度，用于提取增量日志
        prev_journal_len = len((prev_values or {}).get("journal_events") or [])

        if not (prev_values or {}).get("entities"):
            initial_state = get_initial_world_state()
            await graph.aupdate_state(config, initial_state, as_node=START)  # type: ignore[arg-type]

            snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
            prev_values = snapshot.values if hasattr(snapshot, "values") else {}
            if not isinstance(prev_values, dict):
                prev_values = {}
            prev_journal_len = len((prev_values or {}).get("journal_events") or [])

        # 2a. UI 直连拾取：跳过 LLM，仅执行物理并写回 checkpoint
        if intent_s == "ui_action_loot":
            entities = copy.deepcopy((prev_values or {}).get("entities") or {})
            env_objs = copy.deepcopy((prev_values or {}).get("environment_objects") or {})
            if not entities:
                raise HTTPException(status_code=400, detail="No entities in state; cannot loot.")
            char_id = (req.character or "").strip().lower()
            if not char_id:
                raise HTTPException(
                    status_code=400,
                    detail="character is required for ui_action_loot (e.g. shadowheart).",
                )
            if char_id not in entities:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown character: {char_id}",
                )
            target_obj = "iron_chest"
            loot_log = execute_loot(entities, env_objs, char_id, target_obj)
            await graph.aupdate_state(  
                config, # type: ignore[arg-type]
                {
                    "entities": entities,
                    "environment_objects": env_objs,
                    "journal_events": [loot_log],
                },
                as_node=START,
            )
            snap2 = await graph.aget_state(config)  # type: ignore[arg-type]
            result_state = snap2.values if hasattr(snap2, "values") else {}
            if not isinstance(result_state, dict):
                result_state = {}
            curr_journal = result_state.get("journal_events") or []
            new_journal = curr_journal[prev_journal_len:] if len(curr_journal) > prev_journal_len else []
            return ChatResponse(
                responses=[],
                journal_events=new_journal,
                current_location=result_state.get("current_location", "Unknown"),
                environment_objects=result_state.get("environment_objects") or {},
                party_status=result_state.get("entities") or {},
            )

        # 2b. 驱动大图运转 (执行动作与对话)
        # 使用 ainvoke 会直接返回执行完毕后的最终状态
        payload: Dict[str, Any] = {"user_input": uin}
        if intent_s:
            payload["intent"] = intent_s
        print("🗣️ 收到请求:", "user_input=", repr(uin), "intent=", repr(intent_s))
        result_state = await graph.ainvoke(payload, config=config)  # type: ignore[arg-type]

        # 3. 提取需要返回给前端的“干净数据”
        # 获取 NPC 回复
        raw_responses = result_state.get("speaker_responses", [])
        formatted_responses = [{"speaker": spk, "text": text} for spk, text in raw_responses]

        # 提取增量日志 (只把这回合发生的事发给前端)
        curr_journal = result_state.get("journal_events", [])
        new_journal = curr_journal[prev_journal_len:] if len(curr_journal) > prev_journal_len else []

        # 提取环境与状态
        loc = result_state.get("current_location", "Unknown")
        env_objs = result_state.get("environment_objects", {})
        entities = result_state.get("entities", {})

        return ChatResponse(
            responses=formatted_responses,
            journal_events=new_journal,
            current_location=loc,
            environment_objects=env_objs,
            party_status=entities,
        )


if __name__ == "__main__":
    import uvicorn

    # 启动命令: python server.py
    print("🚀 BG3 Engine API is starting...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
