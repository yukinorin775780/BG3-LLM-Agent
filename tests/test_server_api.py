"""
FastAPI 路由保护性测试。
锁定 /api/chat 的轻量委托与错误映射。
"""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import server
from core.application.game_service import InvalidChatRequestError


def test_chat_endpoint_delegates_to_service_and_preserves_response_schema():
    expected_payload = {
        "responses": [{"speaker": "shadowheart", "text": "别碰那个圣徽。"}],
        "journal_events": ["Story advanced"],
        "current_location": "camp_center",
        "environment_objects": {"iron_chest": {"status": "locked"}},
        "party_status": {"shadowheart": {"hp": 10}},
        "player_inventory": {"healing_potion": 2},
        "combat_state": {
            "combat_active": True,
            "initiative_order": ["player", "goblin_1"],
            "current_turn_index": 0,
            "turn_resources": {"player": {"action": 1, "bonus_action": 1, "movement": 6}},
        },
    }
    original_service = server.game_service
    mock_service = AsyncMock()
    mock_service.process_chat_turn.return_value = expected_payload
    server.game_service = mock_service

    try:
        client = TestClient(server.app)
        response = client.post(
            "/api/chat",
            json={
                "user_input": "你好",
                "intent": "chat",
                "session_id": "session-1",
                "character": "shadowheart",
                "map_id": "necromancer_lab",
            },
        )
    finally:
        server.game_service = original_service

    assert response.status_code == 200
    assert response.json() == expected_payload
    mock_service.process_chat_turn.assert_awaited_once_with(
        user_input="你好",
        intent="chat",
        session_id="session-1",
        character="shadowheart",
        map_id="necromancer_lab",
    )


def test_chat_endpoint_maps_service_validation_error_to_http_400():
    original_service = server.game_service
    server.game_service = AsyncMock()
    server.game_service.process_chat_turn.side_effect = InvalidChatRequestError(
        "Unknown character: shadowheart"
    )

    try:
        client = TestClient(server.app)
        response = client.post(
            "/api/chat",
            json={"user_input": "loot", "intent": "ui_action_loot", "session_id": "s-1"},
        )
    finally:
        server.game_service = original_service

    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown character: shadowheart"}


def test_state_endpoint_forwards_optional_map_id_to_game_service():
    original_service = server.game_service
    expected = {"game_state": {"current_location": "死灵法师的废弃实验室"}}
    mock_service = AsyncMock()
    mock_service.get_state_snapshot.return_value = expected
    server.game_service = mock_service

    try:
        client = TestClient(server.app)
        response = client.get(
            "/api/state",
            params={"session_id": "session-map", "map_id": "necromancer_lab"},
        )
    finally:
        server.game_service = original_service

    assert response.status_code == 200
    assert response.json() == expected
    mock_service.get_state_snapshot.assert_awaited_once_with(
        session_id="session-map",
        map_id="necromancer_lab",
    )
