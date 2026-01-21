"""
Redis Streams Manager

Implements Redis Streams for reliable point-to-point messaging between agents.

Task: 1.5.4 Implement Redis Streams for point-to-point messaging
References:
- Requirements 17: Inter-Agent Communication
- Design Section 15.1: Message Bus Architecture
- Design Section 15.3: Communication Patterns
"""

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import redis

from .message import Message, MessageType
from .redis_manager import get_redis_manager

logger = logging.getLogger(__name__)


class StreamsManager:
    """
    Manages Redis Streams for point-to-point messaging.

    Features:
    - Send messages to specific agents
    - Consume messages from agent streams
    - Consumer groups for load balancing
    - Message acknowledgment
    - Automatic retry on failure
    """

    def __init__(self):
        """Initialize Streams manager."""
        self._redis_manager = get_redis_manager()
        self._client = self._redis_manager.get_client()
        self._consumers: Dict[str, threading.Thread] = {}
        self._running = False
        self._callbacks: Dict[str, Callable[[Message], None]] = {}

    def send_message(self, message: Message) -> str:
        """
        Send a message to a specific agent via Redis Stream.

        Args:
            message: Message to send

        Returns:
            str: Message ID in the stream

        Raises:
            ValueError: If message is broadcast type or missing to_agent_id
        """
        if message.is_broadcast():
            raise ValueError("Broadcast messages should use Pub/Sub, not Streams")

        if not message.to_agent_id:
            raise ValueError("to_agent_id is required for point-to-point messages")

        # Get stream name for target agent
        stream_name = self._get_agent_stream(message.to_agent_id)

        # Serialize message
        message_data = {"message": message.to_json()}

        try:
            # Add message to stream
            message_id = self._client.xadd(
                stream_name, message_data, maxlen=10000, approximate=True  # Keep last 10k messages
            )

            logger.debug(
                f"Sent message {message.message_id} to agent {message.to_agent_id}, "
                f"stream_id={message_id}"
            )
            return message_id

        except Exception as e:
            logger.error(f"Failed to send message via stream: {e}")
            raise

    def start_consumer(
        self,
        agent_id: str,
        callback: Callable[[Message], None],
        consumer_group: str = "default",
        consumer_name: Optional[str] = None,
    ) -> None:
        """
        Start consuming messages for an agent.

        Args:
            agent_id: Agent ID to consume messages for
            callback: Function to call when message received
            consumer_group: Consumer group name
            consumer_name: Consumer name (defaults to agent_id)
        """
        stream_name = self._get_agent_stream(agent_id)
        consumer_name = consumer_name or agent_id

        # Create consumer group if it doesn't exist
        try:
            self._client.xgroup_create(stream_name, consumer_group, id="0", mkstream=True)
            logger.info(f"Created consumer group '{consumer_group}' for stream {stream_name}")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Failed to create consumer group: {e}")
                raise
            # Group already exists, continue

        # Store callback
        callback_key = f"{agent_id}:{consumer_group}:{consumer_name}"
        self._callbacks[callback_key] = callback

        # Start consumer thread
        if callback_key not in self._consumers:
            self._running = True
            thread = threading.Thread(
                target=self._consume_loop,
                args=(stream_name, consumer_group, consumer_name, callback_key),
                daemon=True,
                name=f"StreamConsumer-{agent_id}",
            )
            thread.start()
            self._consumers[callback_key] = thread
            logger.info(
                f"Started consumer for agent {agent_id} "
                f"(group={consumer_group}, name={consumer_name})"
            )

    def stop_consumer(
        self, agent_id: str, consumer_group: str = "default", consumer_name: Optional[str] = None
    ) -> None:
        """
        Stop consuming messages for an agent.

        Args:
            agent_id: Agent ID
            consumer_group: Consumer group name
            consumer_name: Consumer name
        """
        consumer_name = consumer_name or agent_id
        callback_key = f"{agent_id}:{consumer_group}:{consumer_name}"

        if callback_key in self._callbacks:
            del self._callbacks[callback_key]

        if callback_key in self._consumers:
            # Thread will stop when callback is removed
            thread = self._consumers[callback_key]
            thread.join(timeout=5.0)
            del self._consumers[callback_key]
            logger.info(f"Stopped consumer for agent {agent_id}")

    def _consume_loop(
        self, stream_name: str, consumer_group: str, consumer_name: str, callback_key: str
    ) -> None:
        """
        Background loop to consume messages from stream.

        Args:
            stream_name: Redis stream name
            consumer_group: Consumer group name
            consumer_name: Consumer name
            callback_key: Key to lookup callback
        """
        logger.info(f"Consumer loop started for {stream_name}")

        try:
            while self._running and callback_key in self._callbacks:
                try:
                    # Read messages from stream
                    messages = self._client.xreadgroup(
                        consumer_group,
                        consumer_name,
                        {stream_name: ">"},
                        count=10,
                        block=1000,  # Block for 1 second
                    )

                    if messages:
                        for stream, message_list in messages:
                            for message_id, message_data in message_list:
                                self._handle_stream_message(
                                    stream_name,
                                    message_id,
                                    message_data,
                                    consumer_group,
                                    callback_key,
                                )

                except redis.RedisError as e:
                    logger.error(f"Redis error in consumer loop: {e}")
                    time.sleep(1)  # Back off on error

        except Exception as e:
            logger.error(f"Error in consumer loop: {e}")
        finally:
            logger.info(f"Consumer loop stopped for {stream_name}")

    def _handle_stream_message(
        self,
        stream_name: str,
        message_id: str,
        message_data: dict,
        consumer_group: str,
        callback_key: str,
    ) -> None:
        """
        Handle a message from the stream.

        Args:
            stream_name: Stream name
            message_id: Message ID in stream
            message_data: Raw message data
            consumer_group: Consumer group name
            callback_key: Key to lookup callback
        """
        try:
            # Deserialize message
            message_json = message_data.get("message")
            if not message_json:
                logger.warning(f"Message {message_id} missing 'message' field")
                return

            message = Message.from_json(message_json)

            # Call callback
            callback = self._callbacks.get(callback_key)
            if callback:
                try:
                    callback(message)

                    # Acknowledge message
                    self._client.xack(stream_name, consumer_group, message_id)
                    logger.debug(f"Acknowledged message {message_id}")

                except Exception as e:
                    logger.error(f"Error in message callback: {e}")
                    # Don't acknowledge - message will be retried
            else:
                logger.warning(f"No callback found for {callback_key}")

        except Exception as e:
            logger.error(f"Error handling stream message: {e}")

    def get_pending_messages(
        self, agent_id: str, consumer_group: str = "default"
    ) -> List[Tuple[str, dict]]:
        """
        Get pending (unacknowledged) messages for an agent.

        Args:
            agent_id: Agent ID
            consumer_group: Consumer group name

        Returns:
            list: List of (message_id, message_data) tuples
        """
        stream_name = self._get_agent_stream(agent_id)

        try:
            # Get pending messages
            pending = self._client.xpending_range(
                stream_name, consumer_group, min="-", max="+", count=100
            )

            if not pending:
                return []

            # Get message IDs
            message_ids = [p["message_id"] for p in pending]

            # Fetch message data
            messages = self._client.xrange(stream_name, min=message_ids[0], max=message_ids[-1])

            return messages

        except redis.RedisError as e:
            logger.error(f"Failed to get pending messages: {e}")
            return []

    def get_stream_info(self, agent_id: str) -> dict:
        """
        Get information about an agent's stream.

        Args:
            agent_id: Agent ID

        Returns:
            dict: Stream information
        """
        stream_name = self._get_agent_stream(agent_id)

        try:
            info = self._client.xinfo_stream(stream_name)
            return {
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "groups": info.get("groups", 0),
            }
        except redis.RedisError as e:
            logger.error(f"Failed to get stream info: {e}")
            return {}

    def _get_agent_stream(self, agent_id: str) -> str:
        """
        Get Redis stream name for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            str: Stream name
        """
        return f"agent:{agent_id}:messages"

    def stop(self) -> None:
        """Stop all consumers."""
        self._running = False

        # Wait for all consumer threads to stop
        for thread in self._consumers.values():
            thread.join(timeout=5.0)

        self._consumers.clear()
        self._callbacks.clear()
        logger.info("Streams manager stopped")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
