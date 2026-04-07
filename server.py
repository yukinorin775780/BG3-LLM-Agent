"""
BG3 LLM Agent — FastAPI 后端，供 Web UI 调用。
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import inventory
from core.application.game_service import (
    GameService,
    GameServiceError,
    InvalidChatRequestError,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载物品注册表，避免请求路径承担初始化职责。"""
    del app
    inventory.init_registry("config/items.yaml")
    yield


app = FastAPI(title="BG3 LLM Agent API", version="2.0", lifespan=lifespan)
game_service = GameService()


# 允许跨域请求 (为了下周的前端网页做准备)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(InvalidChatRequestError)
async def handle_invalid_chat_request(
    request: Request, exc: InvalidChatRequestError
) -> JSONResponse:
    del request
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(GameServiceError)
async def handle_game_service_error(
    request: Request, exc: GameServiceError
) -> JSONResponse:
    del request
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# --- Pydantic Data Models ---
class ChatRequest(BaseModel):
    user_input: str = ""
    intent: Optional[str] = None  # 可选：系统级指令 / 挂机模式等预留意图通道
    session_id: str = "test_consume_003"  # 默认新会话，避开旧 SQLite 存档
    character: Optional[str] = None  # 可选：UI 拾取等指定角色 id（如 shadowheart）


class ChatResponse(BaseModel):
    responses: List[Dict[str, str]]  # 例如: [{"speaker": "astarion", "text": "亲爱的..."}]
    journal_events: List[str]  # 本回合发生的新事件
    current_location: str  # 当前位置
    environment_objects: Dict[str, Any]  # 场景里的可交互物品 (如箱子、门)
    party_status: Dict[str, Any]  # 队友的血量、好感度等状态


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    result = await game_service.process_chat_turn(
        user_input=req.user_input,
        intent=req.intent,
        session_id=req.session_id,
        character=req.character,
    )
    return ChatResponse(**result)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
