"""
Message Data Structures

Defines message format and types for inter-agent communication.

Task: 1.5.5 Add message serialization/deserialization (JSON)
References:
- Requirements 17: Inter-Agent Communication
- Design Section 15.2: Message Format
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


class MessageType(str, Enum):
    """Message types for inter-agent communication."""
    DIRECT = "direct"  # Agent A → Agent B
    BROADCAST = "broadcast"  # Agent A → All agents in task
    REQUEST = "request"  # Agent A requests info from Agent B
    RESPONSE = "response"  # Agent B responds to Agent A
    EVENT = "event"  # Agent A notifies completion/status


@dataclass
class Message:
    """
    Standard message structure for inter-agent communication.
    
    Attributes:
        message_id: Unique message identifier
        from_agent_id: Sender agent ID
        to_agent_id: Recipient agent ID (None for broadcast)
        task_id: Associated task ID
        message_type: Type of message
        payload: Message content and data
        timestamp: Message creation timestamp
        correlation_id: For request-response pairing
    """
    message_id: str
    from_agent_id: str
    to_agent_id: Optional[str]
    task_id: str
    message_type: MessageType
    payload: Dict[str, Any]
    timestamp: str
    correlation_id: Optional[str] = None
    
    @classmethod
    def create(
        cls,
        from_agent_id: str,
        task_id: str,
        message_type: MessageType,
        payload: Dict[str, Any],
        to_agent_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> "Message":
        """
        Create a new message.
        
        Args:
            from_agent_id: Sender agent ID
            task_id: Associated task ID
            message_type: Type of message
            payload: Message content and data
            to_agent_id: Recipient agent ID (None for broadcast)
            correlation_id: For request-response pairing
            
        Returns:
            Message: New message instance
        """
        return cls(
            message_id=str(uuid.uuid4()),
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            task_id=task_id,
            message_type=message_type,
            payload=payload,
            timestamp=datetime.utcnow().isoformat() + "Z",
            correlation_id=correlation_id,
        )
    
    def to_json(self) -> str:
        """
        Serialize message to JSON string.
        
        Returns:
            str: JSON representation of message
        """
        data = asdict(self)
        # Convert enum to string
        data["message_type"] = self.message_type.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """
        Deserialize message from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Message: Deserialized message instance
            
        Raises:
            ValueError: If JSON is invalid or missing required fields
        """
        try:
            data = json.loads(json_str)
            
            # Convert message_type string to enum
            if isinstance(data.get("message_type"), str):
                data["message_type"] = MessageType(data["message_type"])
            
            return cls(**data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            raise ValueError(f"Invalid message JSON: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert message to dictionary.
        
        Returns:
            dict: Dictionary representation of message
        """
        data = asdict(self)
        data["message_type"] = self.message_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """
        Create message from dictionary.
        
        Args:
            data: Dictionary with message data
            
        Returns:
            Message: Message instance
        """
        # Convert message_type string to enum if needed
        if isinstance(data.get("message_type"), str):
            data["message_type"] = MessageType(data["message_type"])
        
        return cls(**data)
    
    def is_broadcast(self) -> bool:
        """Check if message is a broadcast message."""
        return self.message_type == MessageType.BROADCAST or self.to_agent_id is None
    
    def is_request(self) -> bool:
        """Check if message is a request."""
        return self.message_type == MessageType.REQUEST
    
    def is_response(self) -> bool:
        """Check if message is a response."""
        return self.message_type == MessageType.RESPONSE
    
    def create_response(
        self,
        from_agent_id: str,
        payload: Dict[str, Any]
    ) -> "Message":
        """
        Create a response message to this message.
        
        Args:
            from_agent_id: Responder agent ID
            payload: Response payload
            
        Returns:
            Message: Response message with same correlation_id
        """
        return Message.create(
            from_agent_id=from_agent_id,
            to_agent_id=self.from_agent_id,
            task_id=self.task_id,
            message_type=MessageType.RESPONSE,
            payload=payload,
            correlation_id=self.correlation_id or self.message_id,
        )
    
    def __repr__(self) -> str:
        """String representation of message."""
        return (
            f"Message(id={self.message_id[:8]}..., "
            f"type={self.message_type.value}, "
            f"from={self.from_agent_id[:8]}..., "
            f"to={self.to_agent_id[:8] if self.to_agent_id else 'broadcast'}..., "
            f"task={self.task_id[:8]}...)"
        )
