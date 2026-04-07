"""
应用服务层：封装聊天回合的状态恢复、Genesis、图编排与响应整形。
"""

import copy
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import START

from core.engine.physics import execute_loot
from core.graph.graph_builder import build_graph
from core.systems.world_init import get_initial_world_state

logger = logging.getLogger(__name__)
StreamHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class ChatTurnResult(TypedDict):
    responses: List[Dict[str, str]]
    journal_events: List[str]
    current_location: str
    environment_objects: Dict[str, Any]
    party_status: Dict[str, Any]
    player_inventory: Dict[str, Any]


class GraphProtocol(Protocol):
    async def aget_state(self, config: Dict[str, Any]) -> Any:
        ...

    async def aupdate_state(
        self,
        config: Dict[str, Any],
        payload: Dict[str, Any],
        as_node: str,
    ) -> Any:
        ...

    async def ainvoke(self, payload: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def astream(self, payload: Dict[str, Any], config: Dict[str, Any], stream_mode: str) -> Any:
        ...


class GameServiceError(Exception):
    """Base exception for application-service failures."""


class InvalidChatRequestError(GameServiceError):
    """Raised when API input is invalid for the requested operation."""


class StateAccessError(GameServiceError):
    """Raised when checkpoint state cannot be loaded or updated safely."""


class GraphExecutionError(GameServiceError):
    """Raised when the compiled graph fails to process a turn."""


class GameService:
    """Application service that orchestrates one chat turn end-to-end."""

    def __init__(
        self,
        db_path: str = "memory.db",
        saver_factory: Callable[[str], Any] = AsyncSqliteSaver.from_conn_string,
        graph_builder: Callable[..., GraphProtocol] = build_graph,
        initial_state_factory: Callable[[], Dict[str, Any]] = get_initial_world_state,
        loot_executor: Callable[[Dict[str, Any], Dict[str, Any], str, str], str] = execute_loot,
    ) -> None:
        self._db_path = db_path
        self._saver_factory = saver_factory
        self._graph_builder = graph_builder
        self._initial_state_factory = initial_state_factory
        self._loot_executor = loot_executor

    async def process_chat_turn(
        self,
        *,
        user_input: str = "",
        intent: Optional[str] = None,
        session_id: str,
        character: Optional[str] = None,
        stream_handler: Optional[StreamHandler] = None,
    ) -> ChatTurnResult:
        normalized_input = (user_input or "").strip()
        normalized_intent = (intent or "").strip()
        if not normalized_input and not normalized_intent:
            raise InvalidChatRequestError(
                "At least one of user_input or intent must be non-empty."
            )

        config = {"configurable": {"thread_id": session_id}}

        async with self._saver_factory(self._db_path) as saver:
            graph = self._graph_builder(checkpointer=saver)
            previous_state = await self._load_checkpoint_state(graph, config)
            previous_journal_len = len(previous_state.get("journal_events") or [])

            if not previous_state.get("entities"):
                previous_state = await self._initialize_world_state(graph, config)
                previous_journal_len = len(previous_state.get("journal_events") or [])

            if normalized_intent == "init_sync":
                return self._build_chat_result(
                    previous_state,
                    previous_journal_len=previous_journal_len,
                )

            if normalized_intent == "ui_action_loot":
                result_state = await self._process_loot_action(
                    graph=graph,
                    config=config,
                    previous_state=previous_state,
                    previous_journal_len=previous_journal_len,
                    character=character,
                )
                return self._build_chat_result(
                    result_state,
                    previous_journal_len=previous_journal_len,
                )

            payload: Dict[str, Any] = {"user_input": normalized_input}
            if normalized_intent:
                payload["intent"] = normalized_intent

            logger.info(
                "收到聊天请求: user_input=%r intent=%r session_id=%s",
                normalized_input,
                normalized_intent,
                session_id,
            )
            try:
                if stream_handler is None:
                    result_state = await graph.ainvoke(payload, config=config)
                else:
                    async for update in graph.astream(
                        payload,
                        config=config,
                        stream_mode="updates",
                    ):
                        if isinstance(update, dict):
                            for node_name, node_state in update.items():
                                await stream_handler(
                                    str(node_name),
                                    self._normalize_state(node_state),
                                )
                    result_state = await self._load_checkpoint_state(graph, config)
            except Exception as exc:
                raise GraphExecutionError("Failed to process chat turn.") from exc

            return self._build_chat_result(
                self._normalize_state(result_state),
                previous_journal_len=previous_journal_len,
            )

    async def get_session_state(
        self,
        *,
        session_id: str,
        initialize_if_missing: bool = True,
    ) -> Dict[str, Any]:
        """Load the current session state and optionally run Genesis on empty checkpoints."""
        config = {"configurable": {"thread_id": session_id}}
        async with self._saver_factory(self._db_path) as saver:
            graph = self._graph_builder(checkpointer=saver)
            state = await self._load_checkpoint_state(graph, config)
            if initialize_if_missing and not state.get("entities"):
                state = await self._initialize_world_state(graph, config)
            return state

    async def _load_checkpoint_state(
        self,
        graph: GraphProtocol,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            snapshot = await graph.aget_state(config)  # type: ignore[arg-type]
        except Exception as exc:
            raise StateAccessError("Failed to load session state.") from exc
        return self._normalize_state(getattr(snapshot, "values", {}))

    async def _initialize_world_state(
        self,
        graph: GraphProtocol,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        initial_state = self._initial_state_factory()
        try:
            await graph.aupdate_state(config, initial_state, as_node=START)  # type: ignore[arg-type]
        except Exception as exc:
            raise StateAccessError("Failed to initialize world state.") from exc
        return await self._load_checkpoint_state(graph, config)

    async def _process_loot_action(
        self,
        *,
        graph: GraphProtocol,
        config: Dict[str, Any],
        previous_state: Dict[str, Any],
        previous_journal_len: int,
        character: Optional[str],
    ) -> Dict[str, Any]:
        entities = copy.deepcopy(previous_state.get("entities") or {})
        environment_objects = copy.deepcopy(previous_state.get("environment_objects") or {})
        if not entities:
            raise InvalidChatRequestError("No entities in state; cannot loot.")

        character_id = (character or "").strip().lower()
        if not character_id:
            raise InvalidChatRequestError(
                "character is required for ui_action_loot (e.g. shadowheart)."
            )
        if character_id not in entities:
            raise InvalidChatRequestError(f"Unknown character: {character_id}")

        loot_log = self._loot_executor(
            entities,
            environment_objects,
            character_id,
            "iron_chest",
        )

        try:
            await graph.aupdate_state(
                config,
                {
                    "entities": entities,
                    "environment_objects": environment_objects,
                    "journal_events": [loot_log],
                },
                as_node=START,
            )
        except Exception as exc:
            raise StateAccessError("Failed to persist loot action.") from exc

        result_state = await self._load_checkpoint_state(graph, config)
        # 保留原接口结构：loot 分支无对话 responses，仅返回本回合日志与最新状态。
        return result_state

    def _build_chat_result(
        self,
        state: Dict[str, Any],
        *,
        previous_journal_len: int,
    ) -> ChatTurnResult:
        raw_responses = state.get("speaker_responses") or []
        formatted_responses = [
            {"speaker": speaker, "text": text}
            for speaker, text in raw_responses
        ]
        current_journal = state.get("journal_events") or []
        new_journal = (
            current_journal[previous_journal_len:]
            if len(current_journal) > previous_journal_len
            else []
        )
        player_inventory = state.get("player_inventory")
        return {
            "responses": formatted_responses,
            "journal_events": new_journal,
            "current_location": state.get("current_location", "Unknown"),
            "environment_objects": state.get("environment_objects") or {},
            "party_status": state.get("entities") or {},
            "player_inventory": player_inventory if isinstance(player_inventory, dict) else {},
        }

    @staticmethod
    def _normalize_state(state: Any) -> Dict[str, Any]:
        return state if isinstance(state, dict) else {}


async def process_chat_turn(
    *,
    user_input: str = "",
    intent: Optional[str] = None,
    session_id: str,
    character: Optional[str] = None,
    stream_handler: Optional[StreamHandler] = None,
    saver_factory: Callable[[str], Any] = AsyncSqliteSaver.from_conn_string,
    graph_builder: Callable[..., GraphProtocol] = build_graph,
    initial_state_factory: Callable[[], Dict[str, Any]] = get_initial_world_state,
    loot_executor: Callable[[Dict[str, Any], Dict[str, Any], str, str], str] = execute_loot,
) -> ChatTurnResult:
    """测试友好的函数式入口。"""
    service = GameService(
        saver_factory=saver_factory,
        graph_builder=graph_builder,
        initial_state_factory=initial_state_factory,
        loot_executor=loot_executor,
    )
    return await service.process_chat_turn(
        user_input=user_input,
        intent=intent,
        session_id=session_id,
        character=character,
        stream_handler=stream_handler,
    )
