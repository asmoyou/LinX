"""
Message Bus Tests

Tests for Redis-based inter-agent communication.

Run with: pytest backend/message_bus/test_message_bus.py -v
"""

import time
import uuid
from typing import List

import pytest

from .audit import MessageAuditor
from .authorization import AgentPermissions, MessageAuthorizer
from .message import Message, MessageType
from .pubsub import PubSubManager
from .redis_manager import RedisConnectionManager, get_redis_manager
from .streams import StreamsManager


class TestRedisConnectionManager:
    """Test Redis connection manager."""

    def test_initialize_connection(self):
        """Test Redis connection initialization."""
        manager = RedisConnectionManager()
        manager.initialize()

        assert manager.get_client() is not None
        assert manager.health_check() is True

        manager.close()

    def test_connection_pool_stats(self):
        """Test connection pool statistics."""
        manager = RedisConnectionManager()
        manager.initialize()

        stats = manager.get_pool_stats()
        assert stats["initialized"] is True
        assert stats["max_connections"] > 0

        manager.close()

    def test_context_manager(self):
        """Test context manager usage."""
        with RedisConnectionManager() as manager:
            assert manager.health_check() is True


class TestMessage:
    """Test message data structures."""

    def test_create_message(self):
        """Test message creation."""
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Hello"},
        )

        assert message.message_id is not None
        assert message.from_agent_id == "agent-1"
        assert message.to_agent_id == "agent-2"
        assert message.task_id == "task-1"
        assert message.message_type == MessageType.DIRECT
        assert message.payload["content"] == "Hello"
        assert message.timestamp is not None

    def test_message_serialization(self):
        """Test message JSON serialization."""
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.REQUEST,
            payload={"query": "status"},
        )

        # Serialize
        json_str = message.to_json()
        assert isinstance(json_str, str)
        assert "agent-1" in json_str

        # Deserialize
        restored = Message.from_json(json_str)
        assert restored.message_id == message.message_id
        assert restored.from_agent_id == message.from_agent_id
        assert restored.message_type == message.message_type

    def test_broadcast_message(self):
        """Test broadcast message creation."""
        message = Message.create(
            from_agent_id="agent-1",
            task_id="task-1",
            message_type=MessageType.BROADCAST,
            payload={"announcement": "Task completed"},
        )

        assert message.is_broadcast() is True
        assert message.to_agent_id is None

    def test_create_response(self):
        """Test response message creation."""
        request = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.REQUEST,
            payload={"query": "status"},
            correlation_id="corr-123",
        )

        response = request.create_response(from_agent_id="agent-2", payload={"status": "running"})

        assert response.message_type == MessageType.RESPONSE
        assert response.from_agent_id == "agent-2"
        assert response.to_agent_id == "agent-1"
        assert response.correlation_id == "corr-123"


class TestPubSubManager:
    """Test Pub/Sub manager."""

    @pytest.fixture
    def pubsub_manager(self):
        """Create Pub/Sub manager."""
        manager = PubSubManager()
        yield manager
        manager.stop()

    def test_publish_broadcast(self, pubsub_manager):
        """Test publishing broadcast message."""
        message = Message.create(
            from_agent_id="agent-1",
            task_id="task-1",
            message_type=MessageType.BROADCAST,
            payload={"content": "Hello all"},
        )

        # Publish (no subscribers yet)
        num_subscribers = pubsub_manager.publish(message)
        assert num_subscribers >= 0

    def test_subscribe_and_receive(self, pubsub_manager):
        """Test subscribing and receiving messages."""
        received_messages: List[Message] = []

        def callback(message: Message):
            received_messages.append(message)

        # Subscribe
        task_id = "task-1"
        pubsub_manager.subscribe(task_id, callback)

        # Give subscription time to register
        time.sleep(0.5)

        # Publish message
        message = Message.create(
            from_agent_id="agent-1",
            task_id=task_id,
            message_type=MessageType.BROADCAST,
            payload={"content": "Test message"},
        )
        pubsub_manager.publish(message)

        # Wait for message
        time.sleep(0.5)

        # Verify received
        assert len(received_messages) == 1
        assert received_messages[0].message_id == message.message_id
        assert received_messages[0].payload["content"] == "Test message"

    def test_unsubscribe(self, pubsub_manager):
        """Test unsubscribing from messages."""
        received_messages: List[Message] = []

        def callback(message: Message):
            received_messages.append(message)

        task_id = "task-1"
        pubsub_manager.subscribe(task_id, callback)
        time.sleep(0.5)

        # Unsubscribe
        pubsub_manager.unsubscribe(task_id)
        time.sleep(0.5)

        # Publish message (should not be received)
        message = Message.create(
            from_agent_id="agent-1",
            task_id=task_id,
            message_type=MessageType.BROADCAST,
            payload={"content": "Should not receive"},
        )
        pubsub_manager.publish(message)
        time.sleep(0.5)

        # Verify not received
        assert len(received_messages) == 0


class TestStreamsManager:
    """Test Streams manager."""

    @pytest.fixture
    def streams_manager(self):
        """Create Streams manager."""
        manager = StreamsManager()
        yield manager
        manager.stop()

    def test_send_message(self, streams_manager):
        """Test sending message via stream."""
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Direct message"},
        )

        stream_id = streams_manager.send_message(message)
        assert stream_id is not None

    def test_consume_messages(self, streams_manager):
        """Test consuming messages from stream."""
        received_messages: List[Message] = []

        def callback(message: Message):
            received_messages.append(message)

        agent_id = "agent-2"

        # Start consumer
        streams_manager.start_consumer(agent_id, callback)
        time.sleep(0.5)

        # Send message
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id=agent_id,
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Test stream message"},
        )
        streams_manager.send_message(message)

        # Wait for message
        time.sleep(1.0)

        # Verify received
        assert len(received_messages) == 1
        assert received_messages[0].message_id == message.message_id

        # Stop consumer
        streams_manager.stop_consumer(agent_id)

    def test_get_stream_info(self, streams_manager):
        """Test getting stream information."""
        agent_id = "agent-3"

        # Send a message to create stream
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id=agent_id,
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Test"},
        )
        streams_manager.send_message(message)

        # Get stream info
        info = streams_manager.get_stream_info(agent_id)
        assert info.get("length", 0) > 0


class TestMessageAuthorizer:
    """Test message authorizer."""

    @pytest.fixture
    def authorizer(self):
        """Create message authorizer."""
        auth = MessageAuthorizer()

        # Register test agents
        auth.register_agent(
            AgentPermissions(
                agent_id="agent-1",
                assigned_tasks={"task-1", "task-2"},
                can_broadcast=True,
                can_send_direct=True,
            )
        )

        auth.register_agent(
            AgentPermissions(
                agent_id="agent-2",
                assigned_tasks={"task-1"},
                can_broadcast=False,
                can_send_direct=True,
            )
        )

        yield auth
        auth.clear()

    def test_authorize_valid_message(self, authorizer):
        """Test authorizing valid message."""
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Hello"},
        )

        authorized, reason = authorizer.authorize_message(message)
        assert authorized is True
        assert reason is None

    def test_authorize_broadcast_denied(self, authorizer):
        """Test denying broadcast from agent without permission."""
        message = Message.create(
            from_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.BROADCAST,
            payload={"content": "Broadcast"},
        )

        authorized, reason = authorizer.authorize_message(message)
        assert authorized is False
        assert "cannot send broadcast" in reason

    def test_authorize_wrong_task(self, authorizer):
        """Test denying message for unassigned task."""
        message = Message.create(
            from_agent_id="agent-2",
            to_agent_id="agent-1",
            task_id="task-2",  # agent-2 not assigned to task-2
            message_type=MessageType.DIRECT,
            payload={"content": "Hello"},
        )

        authorized, reason = authorizer.authorize_message(message)
        assert authorized is False
        assert "not assigned to task" in reason

    def test_update_agent_tasks(self, authorizer):
        """Test updating agent task assignments."""
        authorizer.add_agent_task("agent-2", "task-2")

        perms = authorizer.get_agent_permissions("agent-2")
        assert "task-2" in perms.assigned_tasks

        authorizer.remove_agent_task("agent-2", "task-2")
        assert "task-2" not in perms.assigned_tasks


class TestMessageAuditor:
    """Test message auditor."""

    @pytest.fixture
    def auditor(self):
        """Create message auditor."""
        aud = MessageAuditor()
        yield aud
        aud.clear_logs()

    def test_log_message_attempt(self, auditor):
        """Test logging message attempt."""
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Test"},
        )

        log_entry = auditor.log_message_attempt(message, authorized=True)

        assert log_entry.message_id == message.message_id
        assert log_entry.authorized is True
        assert log_entry.delivered is False

    def test_log_message_delivery(self, auditor):
        """Test logging message delivery."""
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Test"},
        )

        log_entry = auditor.log_message_attempt(message, authorized=True)
        auditor.log_message_delivery(message.message_id, delivered=True)

        retrieved_log = auditor.get_log(message.message_id)
        assert retrieved_log.delivered is True

    def test_get_statistics(self, auditor):
        """Test getting audit statistics."""
        # Log some messages
        for i in range(5):
            message = Message.create(
                from_agent_id="agent-1",
                to_agent_id="agent-2",
                task_id="task-1",
                message_type=MessageType.DIRECT,
                payload={"content": f"Message {i}"},
            )
            auditor.log_message_attempt(message, authorized=True)
            auditor.log_message_delivery(message.message_id, delivered=True)

        # Log one unauthorized
        message = Message.create(
            from_agent_id="agent-1",
            to_agent_id="agent-2",
            task_id="task-1",
            message_type=MessageType.DIRECT,
            payload={"content": "Denied"},
        )
        auditor.log_message_attempt(message, authorized=False, authorization_reason="Test denial")

        stats = auditor.get_statistics()
        assert stats["total_messages"] == 6
        assert stats["authorized"] == 5
        assert stats["unauthorized"] == 1
        assert stats["delivered"] == 5

    def test_filter_logs(self, auditor):
        """Test filtering audit logs."""
        # Log messages from different agents
        for agent_id in ["agent-1", "agent-2"]:
            message = Message.create(
                from_agent_id=agent_id,
                to_agent_id="agent-3",
                task_id="task-1",
                message_type=MessageType.DIRECT,
                payload={"content": "Test"},
            )
            auditor.log_message_attempt(message, authorized=True)

        # Filter by agent
        logs = auditor.get_logs(agent_id="agent-1")
        assert len(logs) == 1
        assert logs[0].from_agent_id == "agent-1"

        # Filter by task
        logs = auditor.get_logs(task_id="task-1")
        assert len(logs) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
