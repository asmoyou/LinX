"""
Pub/Sub Message Manager

Implements Redis Pub/Sub for broadcast messaging between agents.

Tasks:
- 1.5.2 Implement Pub/Sub message publishing
- 1.5.3 Implement Pub/Sub message subscription

References:
- Requirements 17: Inter-Agent Communication
- Design Section 15.1: Message Bus Architecture
- Design Section 15.3: Communication Patterns
"""

import logging
import threading
from typing import Callable, Dict, List, Optional

import redis

from .message import Message, MessageType
from .redis_manager import get_redis_manager

logger = logging.getLogger(__name__)


class PubSubManager:
    """
    Manages Redis Pub/Sub for broadcast messaging.

    Features:
    - Publish messages to channels
    - Subscribe to channels with callbacks
    - Task-based channel routing
    - Automatic message serialization
    """

    def __init__(self):
        """Initialize Pub/Sub manager."""
        self._redis_manager = get_redis_manager()
        self._client = self._redis_manager.get_client()
        self._pubsub: Optional[redis.client.PubSub] = None
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False

    def publish(self, message: Message) -> int:
        """
        Publish a message to a channel.

        Args:
            message: Message to publish

        Returns:
            int: Number of subscribers that received the message

        Raises:
            ValueError: If message is not a broadcast type
        """
        if not message.is_broadcast():
            raise ValueError(
                f"Only broadcast messages can be published. " f"Got: {message.message_type}"
            )

        # Determine channel based on task_id
        channel = self._get_task_channel(message.task_id)

        # Serialize message
        message_json = message.to_json()

        # Publish to Redis
        try:
            num_subscribers = self._client.publish(channel, message_json)
            logger.debug(
                f"Published message {message.message_id} to channel {channel}, "
                f"received by {num_subscribers} subscribers"
            )
            return num_subscribers
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            raise

    def subscribe(self, task_id: str, callback: Callable[[Message], None]) -> None:
        """
        Subscribe to messages for a specific task.

        Args:
            task_id: Task ID to subscribe to
            callback: Function to call when message received
        """
        channel = self._get_task_channel(task_id)

        # Initialize pubsub if needed
        if self._pubsub is None:
            self._pubsub = self._client.pubsub()

        # Add callback to subscriptions
        if channel not in self._subscriptions:
            self._subscriptions[channel] = []
            # Subscribe to channel
            self._pubsub.subscribe(channel)
            logger.info(f"Subscribed to channel: {channel}")

        self._subscriptions[channel].append(callback)

        # Start listener thread if not running
        if not self._running:
            self._start_listener()

    def unsubscribe(self, task_id: str) -> None:
        """
        Unsubscribe from messages for a specific task.

        Args:
            task_id: Task ID to unsubscribe from
        """
        channel = self._get_task_channel(task_id)

        if channel in self._subscriptions:
            del self._subscriptions[channel]

            if self._pubsub:
                self._pubsub.unsubscribe(channel)
                logger.info(f"Unsubscribed from channel: {channel}")

    def _start_listener(self) -> None:
        """Start background thread to listen for messages."""
        if self._listener_thread and self._listener_thread.is_alive():
            return

        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="PubSubListener"
        )
        self._listener_thread.start()
        logger.info("Started Pub/Sub listener thread")

    def _listen_loop(self) -> None:
        """Background loop to process incoming messages."""
        logger.info("Pub/Sub listener loop started")

        try:
            while self._running and self._pubsub:
                # Get message with timeout
                message_data = self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if message_data and message_data["type"] == "message":
                    self._handle_message(message_data)

        except Exception as e:
            logger.error(f"Error in Pub/Sub listener loop: {e}")
        finally:
            logger.info("Pub/Sub listener loop stopped")

    def _handle_message(self, message_data: dict) -> None:
        """
        Handle incoming message from Redis.

        Args:
            message_data: Raw message data from Redis
        """
        try:
            channel = message_data["channel"]
            data = message_data["data"]

            # Deserialize message
            message = Message.from_json(data)

            # Call all callbacks for this channel
            callbacks = self._subscriptions.get(channel, [])
            for callback in callbacks:
                try:
                    callback(message)
                except Exception as e:
                    logger.error(f"Error in message callback for channel {channel}: {e}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _get_task_channel(self, task_id: str) -> str:
        """
        Get Redis channel name for a task.

        Args:
            task_id: Task ID

        Returns:
            str: Channel name
        """
        return f"task:{task_id}:broadcast"

    def stop(self) -> None:
        """Stop the Pub/Sub listener."""
        self._running = False

        if self._listener_thread:
            self._listener_thread.join(timeout=5.0)

        if self._pubsub:
            self._pubsub.close()
            self._pubsub = None

        self._subscriptions.clear()
        logger.info("Pub/Sub manager stopped")

    def get_active_channels(self) -> List[str]:
        """
        Get list of active subscribed channels.

        Returns:
            list: List of channel names
        """
        return list(self._subscriptions.keys())

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
