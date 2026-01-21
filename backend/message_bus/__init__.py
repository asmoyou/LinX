"""
Message Bus Module

This module provides inter-agent communication infrastructure using Redis.
Supports Pub/Sub for broadcasting and Redis Streams for point-to-point messaging.

References:
- Requirements 17: Inter-Agent Communication
- Design Section 15: Inter-Agent Communication
"""

from .audit import MessageAuditor
from .authorization import MessageAuthorizer
from .message import Message, MessageType
from .pubsub import PubSubManager
from .redis_manager import RedisConnectionManager
from .streams import StreamsManager

__all__ = [
    "RedisConnectionManager",
    "PubSubManager",
    "StreamsManager",
    "Message",
    "MessageType",
    "MessageAuthorizer",
    "MessageAuditor",
]
