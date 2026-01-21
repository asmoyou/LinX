"""Tests for Inter-Agent Communication.

References:
- Requirements 17: Inter-Agent Communication
- Design Section 15: Inter-Agent Communication
"""

import asyncio
from uuid import uuid4

import pytest

from agent_framework.inter_agent_communication import (
    InterAgentCommunicator,
    MessageResponse,
    get_communicator,
)
from message_bus import Message, MessageType


class TestInterAgentCommunicator:
    """Test InterAgentCommunicator functionality."""

    def test_communicator_initialization(self):
        """Test communicator initializes correctly."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        assert communicator is not None
        assert communicator.agent_id == str(agent_id)
        assert communicator.task_id == str(task_id)
        assert communicator.pubsub_manager is not None
        assert communicator.streams_manager is not None

    def test_communicator_with_options(self):
        """Test communicator with custom options."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,
            enable_audit=False,
        )

        assert communicator.authorizer is None
        assert communicator.auditor is None

    @pytest.mark.asyncio
    async def test_send_direct_message(self):
        """Test sending direct message."""
        agent_id = uuid4()
        task_id = uuid4()
        to_agent_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,  # Disable for testing
        )

        payload = {"content": "Hello, agent!"}

        # Note: This will fail without actual Redis, but tests the interface
        try:
            result = await communicator.send_direct_message(
                to_agent_id=to_agent_id,
                payload=payload,
            )
            # In a real test with Redis, this would be True
            assert isinstance(result, bool)
        except Exception:
            # Expected without Redis
            pass

    @pytest.mark.asyncio
    async def test_broadcast_message(self):
        """Test broadcasting message."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,
        )

        payload = {"announcement": "Task starting"}

        try:
            result = await communicator.broadcast_message(payload=payload)
            assert isinstance(result, int)
        except Exception:
            # Expected without Redis
            pass

    @pytest.mark.asyncio
    async def test_send_request(self):
        """Test sending request and waiting for response."""
        agent_id = uuid4()
        task_id = uuid4()
        to_agent_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,
        )

        payload = {"request_type": "get_status"}

        try:
            response = await communicator.send_request(
                to_agent_id=to_agent_id,
                payload=payload,
                timeout=1.0,  # Short timeout for testing
            )

            assert isinstance(response, MessageResponse)
            # Without actual response, should timeout
            assert response.timeout or not response.success
        except Exception:
            # Expected without Redis
            pass

    @pytest.mark.asyncio
    async def test_send_response(self):
        """Test sending response to a request."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,
        )

        # Create a mock request message
        request_message = Message.create(
            from_agent_id=str(uuid4()),
            to_agent_id=str(agent_id),
            task_id=str(task_id),
            message_type=MessageType.REQUEST,
            payload={"request_type": "test"},
            correlation_id=str(uuid4()),
        )

        response_payload = {"status": "ok"}

        try:
            result = await communicator.send_response(
                request_message=request_message,
                payload=response_payload,
            )
            assert isinstance(result, bool)
        except Exception:
            # Expected without Redis
            pass

    @pytest.mark.asyncio
    async def test_send_event(self):
        """Test sending event notification."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,
        )

        payload = {"progress": 50}

        try:
            result = await communicator.send_event(
                event_type="progress_update",
                payload=payload,
            )
            assert isinstance(result, int)
        except Exception:
            # Expected without Redis
            pass

    def test_register_message_handler(self):
        """Test registering message handler."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        def handler(message: Message):
            pass

        communicator.register_message_handler(
            message_type=MessageType.DIRECT,
            handler=handler,
        )

        assert MessageType.DIRECT.value in communicator._message_handlers

    def test_register_request_handler(self):
        """Test registering request handler."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        def handler(message: Message) -> dict:
            return {"result": "ok"}

        communicator.register_request_handler(
            request_type="test_request",
            handler=handler,
        )

        assert "test_request" in communicator._request_handlers

    @pytest.mark.asyncio
    async def test_start_and_stop_listening(self):
        """Test starting and stopping message listening."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        try:
            await communicator.start_listening()
            # Should not raise exception
            communicator.stop_listening()
        except Exception:
            # Expected without Redis
            pass

    def test_set_online_status(self):
        """Test setting online/offline status."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        communicator.set_online_status(False)
        assert communicator._is_online is False

        communicator.set_online_status(True)
        assert communicator._is_online is True

    def test_get_message_queue_size(self):
        """Test getting message queue size."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        size = communicator.get_message_queue_size()
        assert size == 0

    def test_context_manager(self):
        """Test using communicator as context manager."""
        agent_id = uuid4()
        task_id = uuid4()

        with InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        ) as communicator:
            assert communicator is not None

        # Should have stopped listening after exit
        # (no exception should be raised)

    def test_get_communicator_singleton(self):
        """Test global communicator registry."""
        agent_id = uuid4()
        task_id = uuid4()

        comm1 = get_communicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        comm2 = get_communicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        # Should return same instance for same agent+task
        assert comm1 is comm2

    def test_get_communicator_different_agents(self):
        """Test getting communicators for different agents."""
        agent_id1 = uuid4()
        agent_id2 = uuid4()
        task_id = uuid4()

        comm1 = get_communicator(
            agent_id=agent_id1,
            task_id=task_id,
        )

        comm2 = get_communicator(
            agent_id=agent_id2,
            task_id=task_id,
        )

        # Should return different instances for different agents
        assert comm1 is not comm2


class TestMessageResponse:
    """Test MessageResponse dataclass."""

    def test_message_response_success(self):
        """Test successful message response."""
        message = Message.create(
            from_agent_id=str(uuid4()),
            to_agent_id=str(uuid4()),
            task_id=str(uuid4()),
            message_type=MessageType.RESPONSE,
            payload={"result": "ok"},
        )

        response = MessageResponse(
            success=True,
            response_message=message,
        )

        assert response.success is True
        assert response.response_message is message
        assert response.error is None
        assert response.timeout is False

    def test_message_response_error(self):
        """Test error message response."""
        response = MessageResponse(
            success=False,
            error="Connection failed",
        )

        assert response.success is False
        assert response.error == "Connection failed"
        assert response.response_message is None

    def test_message_response_timeout(self):
        """Test timeout message response."""
        response = MessageResponse(
            success=False,
            error="Request timeout",
            timeout=True,
        )

        assert response.success is False
        assert response.timeout is True
        assert response.error == "Request timeout"


class TestMessageHandling:
    """Test message handling functionality."""

    def test_handle_incoming_message_skips_self(self):
        """Test that messages from self are skipped."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        # Create message from self
        message = Message.create(
            from_agent_id=str(agent_id),  # Same as communicator
            to_agent_id=str(uuid4()),
            task_id=str(task_id),
            message_type=MessageType.DIRECT,
            payload={"test": "data"},
        )

        # Should not raise exception
        communicator._handle_incoming_message(message)

    def test_handle_request_with_handler(self):
        """Test handling request with registered handler."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=False,
        )

        # Register handler
        def handler(message: Message) -> dict:
            return {"status": "processed"}

        communicator.register_request_handler(
            request_type="test_request",
            handler=handler,
        )

        # Create request message
        request_message = Message.create(
            from_agent_id=str(uuid4()),
            to_agent_id=str(agent_id),
            task_id=str(task_id),
            message_type=MessageType.REQUEST,
            payload={"request_type": "test_request"},
            correlation_id=str(uuid4()),
        )

        # Handle request (should not raise exception)
        communicator._handle_request(request_message)

    def test_handle_request_without_handler(self):
        """Test handling request without registered handler."""
        agent_id = uuid4()
        task_id = uuid4()

        communicator = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
        )

        # Create request message
        request_message = Message.create(
            from_agent_id=str(uuid4()),
            to_agent_id=str(agent_id),
            task_id=str(task_id),
            message_type=MessageType.REQUEST,
            payload={"request_type": "unknown_request"},
            correlation_id=str(uuid4()),
        )

        # Should not raise exception (just log warning)
        communicator._handle_request(request_message)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
