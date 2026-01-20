"""
Message Audit Logging

Implements audit logging for all inter-agent messages.

Task: 1.5.7 Add message audit logging
References:
- Requirements 17: Inter-Agent Communication
- Design Section 15.4: Access Control
"""

import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
import json

from .message import Message

logger = logging.getLogger(__name__)


@dataclass
class MessageAuditLog:
    """
    Audit log entry for a message.
    
    Attributes:
        log_id: Unique log entry ID
        message_id: Message ID
        from_agent_id: Sender agent ID
        to_agent_id: Recipient agent ID (None for broadcast)
        task_id: Associated task ID
        message_type: Type of message
        timestamp: When message was sent
        authorized: Whether message was authorized
        delivered: Whether message was delivered successfully
        error: Error message if delivery failed
        audit_timestamp: When audit log was created
    """
    log_id: str
    message_id: str
    from_agent_id: str
    to_agent_id: Optional[str]
    task_id: str
    message_type: str
    timestamp: str
    authorized: bool
    delivered: bool
    error: Optional[str] = None
    audit_timestamp: Optional[str] = None
    
    def __post_init__(self):
        """Set audit timestamp if not provided."""
        if self.audit_timestamp is None:
            self.audit_timestamp = datetime.utcnow().isoformat() + "Z"


class MessageAuditor:
    """
    Audits inter-agent messages.
    
    Features:
    - Log all message attempts
    - Track authorization decisions
    - Track delivery status
    - Support for database persistence
    - In-memory buffer for recent logs
    """
    
    def __init__(self, buffer_size: int = 1000):
        """
        Initialize message auditor.
        
        Args:
            buffer_size: Maximum number of logs to keep in memory
        """
        self._buffer_size = buffer_size
        self._logs: list[MessageAuditLog] = []
        self._log_count = 0
    
    def log_message_attempt(
        self,
        message: Message,
        authorized: bool,
        authorization_reason: Optional[str] = None
    ) -> MessageAuditLog:
        """
        Log a message send attempt.
        
        Args:
            message: Message being sent
            authorized: Whether message was authorized
            authorization_reason: Reason if not authorized
            
        Returns:
            MessageAuditLog: Created audit log entry
        """
        log_entry = MessageAuditLog(
            log_id=f"audit-{self._log_count}",
            message_id=message.message_id,
            from_agent_id=message.from_agent_id,
            to_agent_id=message.to_agent_id,
            task_id=message.task_id,
            message_type=message.message_type.value,
            timestamp=message.timestamp,
            authorized=authorized,
            delivered=False,  # Will be updated on delivery
            error=authorization_reason if not authorized else None,
        )
        
        self._add_log(log_entry)
        self._log_count += 1
        
        # Log to standard logger
        if authorized:
            logger.info(
                f"Message authorized: {message.message_id} "
                f"from {message.from_agent_id} to "
                f"{message.to_agent_id or 'broadcast'}"
            )
        else:
            logger.warning(
                f"Message denied: {message.message_id} "
                f"from {message.from_agent_id} - {authorization_reason}"
            )
        
        return log_entry
    
    def log_message_delivery(
        self,
        message_id: str,
        delivered: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Log message delivery status.
        
        Args:
            message_id: Message ID
            delivered: Whether message was delivered
            error: Error message if delivery failed
        """
        # Find log entry
        log_entry = self._find_log(message_id)
        if log_entry:
            log_entry.delivered = delivered
            if error:
                log_entry.error = error
            
            # Log to standard logger
            if delivered:
                logger.info(f"Message delivered: {message_id}")
            else:
                logger.error(f"Message delivery failed: {message_id} - {error}")
        else:
            logger.warning(f"No audit log found for message {message_id}")
    
    def get_logs(
        self,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 100
    ) -> list[MessageAuditLog]:
        """
        Get audit logs with optional filtering.
        
        Args:
            agent_id: Filter by sender or recipient agent ID
            task_id: Filter by task ID
            limit: Maximum number of logs to return
            
        Returns:
            list: List of audit log entries
        """
        logs = self._logs
        
        # Filter by agent_id
        if agent_id:
            logs = [
                log for log in logs
                if log.from_agent_id == agent_id or log.to_agent_id == agent_id
            ]
        
        # Filter by task_id
        if task_id:
            logs = [log for log in logs if log.task_id == task_id]
        
        # Return most recent logs up to limit
        return logs[-limit:]
    
    def get_log(self, message_id: str) -> Optional[MessageAuditLog]:
        """
        Get audit log for a specific message.
        
        Args:
            message_id: Message ID
            
        Returns:
            MessageAuditLog or None if not found
        """
        return self._find_log(message_id)
    
    def get_statistics(self) -> dict:
        """
        Get audit statistics.
        
        Returns:
            dict: Statistics about logged messages
        """
        total = len(self._logs)
        authorized = sum(1 for log in self._logs if log.authorized)
        delivered = sum(1 for log in self._logs if log.delivered)
        failed = sum(1 for log in self._logs if not log.delivered and log.authorized)
        
        return {
            "total_messages": total,
            "authorized": authorized,
            "unauthorized": total - authorized,
            "delivered": delivered,
            "failed": failed,
            "authorization_rate": authorized / total if total > 0 else 0,
            "delivery_rate": delivered / authorized if authorized > 0 else 0,
        }
    
    def export_logs(self, filepath: str) -> None:
        """
        Export audit logs to JSON file.
        
        Args:
            filepath: Path to output file
        """
        try:
            logs_data = [asdict(log) for log in self._logs]
            with open(filepath, 'w') as f:
                json.dump(logs_data, f, indent=2)
            logger.info(f"Exported {len(logs_data)} audit logs to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export audit logs: {e}")
            raise
    
    def clear_logs(self) -> None:
        """Clear all audit logs from memory."""
        self._logs.clear()
        logger.info("Cleared all audit logs")
    
    def _add_log(self, log_entry: MessageAuditLog) -> None:
        """
        Add log entry to buffer.
        
        Args:
            log_entry: Log entry to add
        """
        self._logs.append(log_entry)
        
        # Trim buffer if needed
        if len(self._logs) > self._buffer_size:
            self._logs = self._logs[-self._buffer_size:]
    
    def _find_log(self, message_id: str) -> Optional[MessageAuditLog]:
        """
        Find log entry by message ID.
        
        Args:
            message_id: Message ID to find
            
        Returns:
            MessageAuditLog or None if not found
        """
        for log in reversed(self._logs):  # Search from most recent
            if log.message_id == message_id:
                return log
        return None


# Global instance
_auditor: Optional[MessageAuditor] = None


def get_message_auditor() -> MessageAuditor:
    """
    Get global message auditor instance.
    
    Returns:
        MessageAuditor: Global auditor instance
    """
    global _auditor
    if _auditor is None:
        _auditor = MessageAuditor()
    return _auditor
