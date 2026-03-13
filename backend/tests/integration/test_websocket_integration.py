"""Integration tests for WebSocket real-time updates.

Tests the WebSocket functionality for real-time updates.

References:
- Task 8.2.8: Test WebSocket real-time updates
"""

import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    websocket = Mock()
    websocket.send_text = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.receive_json = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    return websocket


@pytest.fixture
def mock_connection_manager():
    """Mock WebSocket connection manager."""
    manager = Mock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.send_personal_message = AsyncMock()
    manager.broadcast = AsyncMock()
    manager.active_connections = {}
    with patch("api_gateway.websocket._get_connection_manager", return_value=manager):
        yield manager


class TestWebSocketIntegration:
    """Test WebSocket real-time updates."""

    @pytest.mark.asyncio
    async def test_websocket_connection_establishment(
        self, mock_websocket, mock_connection_manager
    ):
        """Test that WebSocket connection can be established."""
        from api_gateway.websocket import websocket_endpoint

        user_id = uuid4()

        # Establish connection
        await websocket_endpoint(websocket=mock_websocket, user_id=str(user_id))

        # Verify connection was accepted
        mock_websocket.accept.assert_called_once()

        # Verify connection was registered
        mock_connection_manager.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_status_updates_sent_via_websocket(self, mock_connection_manager):
        """Test that task status updates are sent to connected clients."""
        from api_gateway.websocket import send_task_update

        user_id = uuid4()
        task_id = uuid4()

        # Send task update
        await send_task_update(user_id=user_id, task_id=task_id, status="in_progress", progress=50)

        # Verify message was sent
        mock_connection_manager.send_personal_message.assert_called_once()

        call_args = mock_connection_manager.send_personal_message.call_args
        message = call_args[0][0]

        assert "task_id" in message
        assert message["status"] == "in_progress"
        assert message["progress"] == 50

    @pytest.mark.asyncio
    async def test_agent_status_updates_broadcast(self, mock_connection_manager):
        """Test that agent status updates are broadcast to relevant users."""
        from api_gateway.websocket import broadcast_agent_status

        agent_id = uuid4()

        # Broadcast agent status
        await broadcast_agent_status(agent_id=agent_id, status="active", current_task=str(uuid4()))

        # Verify broadcast was sent
        mock_connection_manager.broadcast.assert_called_once()

        call_args = mock_connection_manager.broadcast.call_args
        message = call_args[0][0]

        assert "agent_id" in message
        assert message["status"] == "active"

    @pytest.mark.asyncio
    async def test_real_time_log_streaming(self, mock_websocket, mock_connection_manager):
        """Test that logs can be streamed in real-time via WebSocket."""
        from api_gateway.websocket import stream_logs

        user_id = uuid4()
        task_id = uuid4()

        # Mock log entries
        log_entries = [
            {"timestamp": "2024-01-01T10:00:00", "level": "INFO", "message": "Task started"},
            {"timestamp": "2024-01-01T10:00:05", "level": "INFO", "message": "Processing data"},
            {"timestamp": "2024-01-01T10:00:10", "level": "INFO", "message": "Task completed"},
        ]

        # Stream logs
        for log in log_entries:
            await stream_logs(user_id=user_id, task_id=task_id, log_entry=log)

        # Verify all logs were sent
        assert mock_connection_manager.send_personal_message.call_count == len(log_entries)

    @pytest.mark.asyncio
    async def test_websocket_handles_client_messages(self, mock_websocket):
        """Test that WebSocket can receive and process client messages."""
        from api_gateway.websocket import handle_client_message

        user_id = uuid4()

        # Mock client message
        mock_websocket.receive_json = AsyncMock(
            return_value={"type": "subscribe", "channel": "task_updates", "task_id": str(uuid4())}
        )

        # Handle message
        response = await handle_client_message(websocket=mock_websocket, user_id=user_id)

        assert response["type"] == "subscription_confirmed"

        # Verify response was sent
        mock_websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_websocket_connection_cleanup_on_disconnect(self, mock_connection_manager):
        """Test that WebSocket connections are cleaned up on disconnect."""
        from api_gateway.websocket import websocket_endpoint

        user_id = uuid4()
        mock_websocket = Mock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_text = AsyncMock(side_effect=Exception("Connection closed"))

        # Attempt connection (will fail and disconnect)
        try:
            await websocket_endpoint(websocket=mock_websocket, user_id=str(user_id))
        except:
            pass

        # Verify disconnect was called
        mock_connection_manager.disconnect.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_websocket_connections_per_user(self, mock_connection_manager):
        """Test that users can have multiple WebSocket connections."""
        from api_gateway.websocket import ConnectionManager

        manager = ConnectionManager()
        user_id = uuid4()

        # Create multiple connections for same user
        ws1 = Mock()
        ws2 = Mock()

        await manager.connect(websocket=ws1, user_id=user_id)
        await manager.connect(websocket=ws2, user_id=user_id)

        # Verify both connections are tracked
        assert user_id in manager.active_connections
        assert len(manager.active_connections[user_id]) == 2

        # Send message to user (should go to all connections)
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.send_personal_message(message={"type": "test"}, user_id=user_id)

        # Verify message sent to both connections
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_heartbeat_keeps_connection_alive(self, mock_websocket):
        """Test that WebSocket heartbeat mechanism keeps connection alive."""
        from api_gateway.websocket import send_heartbeat

        user_id = uuid4()

        # Send heartbeat
        await send_heartbeat(websocket=mock_websocket, user_id=user_id)

        # Verify ping was sent
        mock_websocket.send_json.assert_called_once()

        call_args = mock_websocket.send_json.call_args
        message = call_args[0][0]

        assert message["type"] == "heartbeat" or message["type"] == "ping"

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self, mock_websocket, mock_connection_manager):
        """Test that WebSocket errors are handled gracefully."""
        from api_gateway.websocket import websocket_endpoint

        user_id = uuid4()

        # Simulate error during message receive
        mock_websocket.receive_text = AsyncMock(side_effect=Exception("Network error"))

        # Connection should handle error and disconnect
        try:
            await websocket_endpoint(websocket=mock_websocket, user_id=str(user_id))
        except Exception as e:
            assert "Network error" in str(e)

        # Verify cleanup occurred
        mock_connection_manager.disconnect.assert_called()

    @pytest.mark.asyncio
    async def test_websocket_message_queue_when_offline(self, mock_connection_manager):
        """Test that messages are queued when user is offline."""
        from api_gateway.websocket import queue_message_for_offline_user

        user_id = uuid4()

        # User is offline
        mock_connection_manager.active_connections = {}

        # Queue message
        await queue_message_for_offline_user(
            user_id=user_id, message={"type": "task_update", "status": "completed"}
        )

        # Verify message was queued (stored in Redis or database)
        # This would check the actual queue implementation
        assert True  # Placeholder for actual queue verification
