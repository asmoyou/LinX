"""Audit Logging for Classified Data Access.

Implements comprehensive audit logging for classified data operations.

References:
- Requirements 7: Data Security and Privacy
- Design Section 8.4: Data Protection
- Task 5.2.5: Audit logging for classified data access
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import AuditLog
from shared.data_classification import ClassificationLevel

logger = logging.getLogger(__name__)


class ClassificationAuditLogger:
    """Audit logger for classified data operations."""

    def __init__(self):
        """Initialize classification audit logger."""
        logger.info("ClassificationAuditLogger initialized")

    def log_data_access(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        classification: ClassificationLevel,
        action: str,
        agent_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log access to classified data.

        Args:
            user_id: User accessing the data
            resource_type: Type of resource (document, memory, knowledge, etc.)
            resource_id: Resource ID
            classification: Classification level of data
            action: Action performed (read, write, delete, share, etc.)
            agent_id: Optional agent ID if accessed by agent
            details: Additional details
        """
        audit_details = {
            "classification": classification.value,
            "action": action,
        }

        if details:
            audit_details.update(details)

        with get_db_session() as session:
            audit_log = AuditLog(
                user_id=user_id,
                agent_id=agent_id,
                action=f"classified_data_{action}",
                resource_type=resource_type,
                resource_id=resource_id,
                details=audit_details,
            )

            session.add(audit_log)
            session.commit()

        logger.info(
            "Classified data access logged",
            extra={
                "user_id": str(user_id),
                "resource_type": resource_type,
                "resource_id": str(resource_id),
                "classification": classification.value,
                "action": action,
            },
        )

    def log_classification_change(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        old_classification: ClassificationLevel,
        new_classification: ClassificationLevel,
        reason: Optional[str] = None,
    ) -> None:
        """Log classification level change.

        Args:
            user_id: User making the change
            resource_type: Type of resource
            resource_id: Resource ID
            old_classification: Previous classification
            new_classification: New classification
            reason: Optional reason for change
        """
        details = {
            "old_classification": old_classification.value,
            "new_classification": new_classification.value,
        }

        if reason:
            details["reason"] = reason

        with get_db_session() as session:
            audit_log = AuditLog(
                user_id=user_id,
                action="classification_changed",
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )

            session.add(audit_log)
            session.commit()

        logger.warning(
            "Classification level changed",
            extra={
                "user_id": str(user_id),
                "resource_type": resource_type,
                "resource_id": str(resource_id),
                "old_classification": old_classification.value,
                "new_classification": new_classification.value,
            },
        )

    def log_unauthorized_access_attempt(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        classification: ClassificationLevel,
        reason: str,
    ) -> None:
        """Log unauthorized access attempt to classified data.

        Args:
            user_id: User attempting access
            resource_type: Type of resource
            resource_id: Resource ID
            classification: Classification level
            reason: Reason for denial
        """
        details = {
            "classification": classification.value,
            "denial_reason": reason,
        }

        with get_db_session() as session:
            audit_log = AuditLog(
                user_id=user_id,
                action="unauthorized_access_attempt",
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )

            session.add(audit_log)
            session.commit()

        logger.warning(
            "Unauthorized access attempt to classified data",
            extra={
                "user_id": str(user_id),
                "resource_type": resource_type,
                "resource_id": str(resource_id),
                "classification": classification.value,
                "reason": reason,
            },
        )

    def log_data_sharing(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        classification: ClassificationLevel,
        shared_with: UUID,
        permissions: Dict[str, bool],
    ) -> None:
        """Log sharing of classified data.

        Args:
            user_id: User sharing the data
            resource_type: Type of resource
            resource_id: Resource ID
            classification: Classification level
            shared_with: User ID data is shared with
            permissions: Permissions granted
        """
        details = {
            "classification": classification.value,
            "shared_with": str(shared_with),
            "permissions": permissions,
        }

        with get_db_session() as session:
            audit_log = AuditLog(
                user_id=user_id,
                action="classified_data_shared",
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )

            session.add(audit_log)
            session.commit()

        logger.info(
            "Classified data shared",
            extra={
                "user_id": str(user_id),
                "resource_type": resource_type,
                "resource_id": str(resource_id),
                "classification": classification.value,
                "shared_with": str(shared_with),
            },
        )

    def log_export(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        classification: ClassificationLevel,
        export_format: str,
        destination: str,
    ) -> None:
        """Log export of classified data.

        Args:
            user_id: User exporting data
            resource_type: Type of resource
            resource_id: Resource ID
            classification: Classification level
            export_format: Format of export
            destination: Export destination
        """
        details = {
            "classification": classification.value,
            "export_format": export_format,
            "destination": destination,
        }

        with get_db_session() as session:
            audit_log = AuditLog(
                user_id=user_id,
                action="classified_data_exported",
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )

            session.add(audit_log)
            session.commit()

        logger.info(
            "Classified data exported",
            extra={
                "user_id": str(user_id),
                "resource_type": resource_type,
                "resource_id": str(resource_id),
                "classification": classification.value,
                "export_format": export_format,
            },
        )


# Global audit logger instance
_audit_logger_instance: Optional[ClassificationAuditLogger] = None


def get_classification_audit_logger() -> ClassificationAuditLogger:
    """Get global classification audit logger instance.

    Returns:
        ClassificationAuditLogger instance
    """
    global _audit_logger_instance

    if _audit_logger_instance is None:
        _audit_logger_instance = ClassificationAuditLogger()

    return _audit_logger_instance
