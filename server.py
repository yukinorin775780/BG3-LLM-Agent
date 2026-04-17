"""
BG3 LLM Agent — FastAPI 后端，供 Web UI 调用。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import inventory
from core.application.game_service import (
    GameService,
    GameServiceError,
    InvalidChatRequestError,
)

BASE_DIR = Path(__file__).resolve().parent
WEB_UI_DIR = BASE_DIR / "web_ui"

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

if WEB_UI_DIR.exists():
    app.mount("/web_ui", StaticFiles(directory=str(WEB_UI_DIR), html=True), name="web_ui")


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
    player_inventory: Dict[str, Any]  # 玩家背包
    combat_state: Optional[Dict[str, Any]] = None  # 回合制战斗状态


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    if WEB_UI_DIR.exists():
        return RedirectResponse(url="/web_ui/")
    return RedirectResponse(url="/docs")


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    result = await game_service.process_chat_turn(
        user_input=req.user_input,
        intent=req.intent,
        session_id=req.session_id,
        character=req.character,
    )
    return ChatResponse(**result)


@app.get("/api/state", response_model=ChatResponse)
async def state_endpoint(session_id: str = "test_consume_003") -> ChatResponse:
    result = await game_service.get_state_snapshot(session_id=session_id)
    return ChatResponse(**result)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
