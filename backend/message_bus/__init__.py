"""
Message Bus Module

This module provides inter-agent communication infrastructure using Redis.
Supports Pub/Sub for broadcasting and Redis Streams for point-to-point messaging.

References:
- Requirements 17: Inter-Agent Communication
- Design Section 15: Inter-Agent Communication
"""

from .redis_manager import RedisConnectionManager
from .pubsub import PubSubManager
from .streams import StreamsManager
from .message import Message, MessageType
from .authorization import MessageAuthorizer
from .audit import MessageAuditor

__all__ = [
    "RedisConnectionManager",
    "PubSubManager",
    "StreamsManager",
    "Message",
    "MessageType",
    "MessageAuthorizer",
    "MessageAuditor",
]
