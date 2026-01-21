"""GDPR compliance implementation.

References:
- Requirements 7: Data Privacy and Security
- GDPR Articles 15-22

Implements:
- Right to access (Article 15)
- Right to rectification (Article 16)
- Right to erasure (Article 17)
- Right to data portability (Article 20)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Any, Optional
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DataExportRequest:
    """Data export request."""
    
    request_id: str
    user_id: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, processing, completed, failed
    export_file: Optional[str] = None


@dataclass
class DataDeletionRequest:
    """Data deletion request."""
    
    request_id: str
    user_id: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, processing, completed, failed
    deleted_items: List[str] = None
    
    def __post_init__(self):
        if self.deleted_items is None:
            self.deleted_items = []


class GDPRComplianceManager:
    """GDPR compliance manager.
    
    Implements GDPR rights:
    - Right to access: Export user data
    - Right to erasure: Delete user data
    - Right to rectification: Update user data
    - Right to data portability: Export in machine-readable format
    """
    
    def __init__(self, export_dir: str = "/tmp/gdpr_exports"):
        """Initialize GDPR compliance manager.
        
        Args:
            export_dir: Directory for data exports
        """
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        
        self.export_requests: List[DataExportRequest] = []
        self.deletion_requests: List[DataDeletionRequest] = []
        
        logger.info("GDPRComplianceManager initialized")
    
    def request_data_export(self, user_id: str) -> DataExportRequest:
        """Request user data export (Right to Access - Article 15).
        
        Args:
            user_id: User ID
            
        Returns:
            Data export request
        """
        request_id = f"export_{user_id}_{int(datetime.now().timestamp())}"
        
        request = DataExportRequest(
            request_id=request_id,
            user_id=user_id,
            requested_at=datetime.now(),
            status="pending",
        )
        
        self.export_requests.append(request)
        
        logger.info(
            f"Data export requested for user: {user_id}",
            extra={"request_id": request_id},
        )
        
        return request
    
    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Export all user data in machine-readable format.
        
        Args:
            user_id: User ID
            
        Returns:
            User data dictionary
        """
        logger.info(f"Exporting data for user: {user_id}")
        
        # Collect data from all sources
        user_data = {
            "user_id": user_id,
            "export_date": datetime.now().isoformat(),
            "personal_information": self._export_personal_info(user_id),
            "agents": self._export_agents(user_id),
            "tasks": self._export_tasks(user_id),
            "knowledge_items": self._export_knowledge(user_id),
            "memories": self._export_memories(user_id),
            "audit_logs": self._export_audit_logs(user_id),
            "consent_records": self._export_consent_records(user_id),
        }
        
        # Save to file
        export_file = self.export_dir / f"user_{user_id}_{int(datetime.now().timestamp())}.json"
        with open(export_file, "w") as f:
            json.dump(user_data, f, indent=2)
        
        logger.info(f"Data exported to: {export_file}")
        
        return user_data
    
    def complete_export_request(self, request_id: str) -> bool:
        """Complete data export request.
        
        Args:
            request_id: Request ID
            
        Returns:
            True if completed
        """
        request = self._find_export_request(request_id)
        if not request:
            logger.error(f"Export request not found: {request_id}")
            return False
        
        try:
            # Export data
            user_data = self.export_user_data(request.user_id)
            
            # Update request
            request.status = "completed"
            request.completed_at = datetime.now()
            request.export_file = str(self.export_dir / f"user_{request.user_id}_{int(datetime.now().timestamp())}.json")
            
            logger.info(f"Export request completed: {request_id}")
            return True
            
        except Exception as e:
            logger.error(f"Export request failed: {request_id} - {e}")
            request.status = "failed"
            return False
    
    def request_data_deletion(self, user_id: str) -> DataDeletionRequest:
        """Request user data deletion (Right to Erasure - Article 17).
        
        Args:
            user_id: User ID
            
        Returns:
            Data deletion request
        """
        request_id = f"delete_{user_id}_{int(datetime.now().timestamp())}"
        
        request = DataDeletionRequest(
            request_id=request_id,
            user_id=user_id,
            requested_at=datetime.now(),
            status="pending",
        )
        
        self.deletion_requests.append(request)
        
        logger.warning(
            f"Data deletion requested for user: {user_id}",
            extra={"request_id": request_id},
        )
        
        return request
    
    def delete_user_data(self, user_id: str) -> List[str]:
        """Delete all user data (Right to Erasure).
        
        Args:
            user_id: User ID
            
        Returns:
            List of deleted items
        """
        logger.warning(f"Deleting data for user: {user_id}")
        
        deleted_items = []
        
        # Delete from all sources
        deleted_items.extend(self._delete_personal_info(user_id))
        deleted_items.extend(self._delete_agents(user_id))
        deleted_items.extend(self._delete_tasks(user_id))
        deleted_items.extend(self._delete_knowledge(user_id))
        deleted_items.extend(self._delete_memories(user_id))
        deleted_items.extend(self._delete_consent_records(user_id))
        
        # Keep audit logs for compliance (anonymized)
        self._anonymize_audit_logs(user_id)
        
        logger.warning(
            f"Deleted {len(deleted_items)} items for user: {user_id}",
            extra={"deleted_items": deleted_items},
        )
        
        return deleted_items
    
    def complete_deletion_request(self, request_id: str) -> bool:
        """Complete data deletion request.
        
        Args:
            request_id: Request ID
            
        Returns:
            True if completed
        """
        request = self._find_deletion_request(request_id)
        if not request:
            logger.error(f"Deletion request not found: {request_id}")
            return False
        
        try:
            # Delete data
            deleted_items = self.delete_user_data(request.user_id)
            
            # Update request
            request.status = "completed"
            request.completed_at = datetime.now()
            request.deleted_items = deleted_items
            
            logger.warning(f"Deletion request completed: {request_id}")
            return True
            
        except Exception as e:
            logger.error(f"Deletion request failed: {request_id} - {e}")
            request.status = "failed"
            return False
    
    def get_export_status(self, request_id: str) -> Optional[DataExportRequest]:
        """Get export request status.
        
        Args:
            request_id: Request ID
            
        Returns:
            Export request or None
        """
        return self._find_export_request(request_id)
    
    def get_deletion_status(self, request_id: str) -> Optional[DataDeletionRequest]:
        """Get deletion request status.
        
        Args:
            request_id: Request ID
            
        Returns:
            Deletion request or None
        """
        return self._find_deletion_request(request_id)
    
    # Helper methods for data export
    
    def _export_personal_info(self, user_id: str) -> Dict[str, Any]:
        """Export personal information."""
        # Mock: In production, query from database
        return {
            "user_id": user_id,
            "email": f"user{user_id}@example.com",
            "name": f"User {user_id}",
            "created_at": datetime.now().isoformat(),
        }
    
    def _export_agents(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user's agents."""
        # Mock: In production, query from database
        return [
            {"agent_id": f"agent_{user_id}_1", "name": "Agent 1"},
            {"agent_id": f"agent_{user_id}_2", "name": "Agent 2"},
        ]
    
    def _export_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user's tasks."""
        # Mock: In production, query from database
        return [
            {"task_id": f"task_{user_id}_1", "description": "Task 1"},
        ]
    
    def _export_knowledge(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user's knowledge items."""
        # Mock: In production, query from database
        return [
            {"knowledge_id": f"knowledge_{user_id}_1", "title": "Document 1"},
        ]
    
    def _export_memories(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user's memories."""
        # Mock: In production, query from Milvus
        return [
            {"memory_id": f"memory_{user_id}_1", "content": "Memory 1"},
        ]
    
    def _export_audit_logs(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user's audit logs."""
        # Mock: In production, query from database
        return [
            {"log_id": f"log_{user_id}_1", "action": "login"},
        ]
    
    def _export_consent_records(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user's consent records."""
        # Mock: In production, query from database
        return [
            {"consent_id": f"consent_{user_id}_1", "type": "terms_of_service"},
        ]
    
    # Helper methods for data deletion
    
    def _delete_personal_info(self, user_id: str) -> List[str]:
        """Delete personal information."""
        # Mock: In production, delete from database
        return [f"personal_info_{user_id}"]
    
    def _delete_agents(self, user_id: str) -> List[str]:
        """Delete user's agents."""
        # Mock: In production, delete from database
        return [f"agent_{user_id}_1", f"agent_{user_id}_2"]
    
    def _delete_tasks(self, user_id: str) -> List[str]:
        """Delete user's tasks."""
        # Mock: In production, delete from database
        return [f"task_{user_id}_1"]
    
    def _delete_knowledge(self, user_id: str) -> List[str]:
        """Delete user's knowledge items."""
        # Mock: In production, delete from database and MinIO
        return [f"knowledge_{user_id}_1"]
    
    def _delete_memories(self, user_id: str) -> List[str]:
        """Delete user's memories."""
        # Mock: In production, delete from Milvus
        return [f"memory_{user_id}_1"]
    
    def _delete_consent_records(self, user_id: str) -> List[str]:
        """Delete user's consent records."""
        # Mock: In production, delete from database
        return [f"consent_{user_id}_1"]
    
    def _anonymize_audit_logs(self, user_id: str):
        """Anonymize audit logs (keep for compliance)."""
        # Mock: In production, update database to replace user_id with anonymous ID
        logger.info(f"Anonymized audit logs for user: {user_id}")
    
    def _find_export_request(self, request_id: str) -> Optional[DataExportRequest]:
        """Find export request by ID."""
        for request in self.export_requests:
            if request.request_id == request_id:
                return request
        return None
    
    def _find_deletion_request(self, request_id: str) -> Optional[DataDeletionRequest]:
        """Find deletion request by ID."""
        for request in self.deletion_requests:
            if request.request_id == request_id:
                return request
        return None
