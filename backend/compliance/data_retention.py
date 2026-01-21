"""Data retention policies.

References:
- Requirements 7: Data Privacy and Security
- Design Section 8: Security Architecture
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DataCategory(Enum):
    """Data categories for retention."""

    USER_DATA = "user_data"
    AGENT_DATA = "agent_data"
    TASK_DATA = "task_data"
    KNOWLEDGE_DATA = "knowledge_data"
    MEMORY_DATA = "memory_data"
    AUDIT_LOGS = "audit_logs"
    BACKUP_DATA = "backup_data"


@dataclass
class RetentionPolicy:
    """Data retention policy."""

    category: DataCategory
    retention_days: int
    description: str
    auto_delete: bool = True


@dataclass
class RetentionJob:
    """Retention cleanup job."""

    job_id: str
    category: DataCategory
    started_at: datetime
    completed_at: Optional[datetime] = None
    items_deleted: int = 0
    status: str = "running"  # running, completed, failed


class DataRetentionManager:
    """Data retention manager.

    Manages data retention policies:
    - Define retention periods per data category
    - Automatic cleanup of expired data
    - Retention job tracking
    - Compliance reporting
    """

    def __init__(self):
        """Initialize data retention manager."""
        self.policies: Dict[DataCategory, RetentionPolicy] = {}
        self.jobs: List[RetentionJob] = []

        # Initialize default policies
        self._initialize_default_policies()

        logger.info("DataRetentionManager initialized")

    def _initialize_default_policies(self):
        """Initialize default retention policies."""
        # User data: Keep for 7 years (legal requirement)
        self.policies[DataCategory.USER_DATA] = RetentionPolicy(
            category=DataCategory.USER_DATA,
            retention_days=365 * 7,
            description="User account and personal data",
            auto_delete=False,  # Manual deletion only
        )

        # Agent data: Keep for 2 years
        self.policies[DataCategory.AGENT_DATA] = RetentionPolicy(
            category=DataCategory.AGENT_DATA,
            retention_days=365 * 2,
            description="Agent configurations and history",
            auto_delete=True,
        )

        # Task data: Keep for 1 year
        self.policies[DataCategory.TASK_DATA] = RetentionPolicy(
            category=DataCategory.TASK_DATA,
            retention_days=365,
            description="Task execution history",
            auto_delete=True,
        )

        # Knowledge data: Keep for 3 years
        self.policies[DataCategory.KNOWLEDGE_DATA] = RetentionPolicy(
            category=DataCategory.KNOWLEDGE_DATA,
            retention_days=365 * 3,
            description="Knowledge base documents",
            auto_delete=False,  # Manual deletion only
        )

        # Memory data: Keep for 1 year
        self.policies[DataCategory.MEMORY_DATA] = RetentionPolicy(
            category=DataCategory.MEMORY_DATA,
            retention_days=365,
            description="Agent and company memories",
            auto_delete=True,
        )

        # Audit logs: Keep for 7 years (compliance requirement)
        self.policies[DataCategory.AUDIT_LOGS] = RetentionPolicy(
            category=DataCategory.AUDIT_LOGS,
            retention_days=365 * 7,
            description="Security and compliance audit logs",
            auto_delete=False,  # Never auto-delete
        )

        # Backup data: Keep for 90 days
        self.policies[DataCategory.BACKUP_DATA] = RetentionPolicy(
            category=DataCategory.BACKUP_DATA,
            retention_days=90,
            description="Database and file backups",
            auto_delete=True,
        )

    def get_policy(self, category: DataCategory) -> Optional[RetentionPolicy]:
        """Get retention policy for category.

        Args:
            category: Data category

        Returns:
            Retention policy or None
        """
        return self.policies.get(category)

    def set_policy(self, policy: RetentionPolicy):
        """Set retention policy for category.

        Args:
            policy: Retention policy
        """
        self.policies[policy.category] = policy

        logger.info(
            f"Retention policy set: {policy.category.value}",
            extra={
                "retention_days": policy.retention_days,
                "auto_delete": policy.auto_delete,
            },
        )

    def list_policies(self) -> List[RetentionPolicy]:
        """List all retention policies.

        Returns:
            List of retention policies
        """
        return list(self.policies.values())

    def calculate_expiry_date(
        self,
        category: DataCategory,
        created_at: datetime,
    ) -> datetime:
        """Calculate expiry date for data.

        Args:
            category: Data category
            created_at: Creation date

        Returns:
            Expiry date
        """
        policy = self.get_policy(category)
        if not policy:
            raise ValueError(f"No policy found for category: {category}")

        return created_at + timedelta(days=policy.retention_days)

    def is_expired(
        self,
        category: DataCategory,
        created_at: datetime,
    ) -> bool:
        """Check if data is expired.

        Args:
            category: Data category
            created_at: Creation date

        Returns:
            True if expired
        """
        expiry_date = self.calculate_expiry_date(category, created_at)
        return datetime.now() > expiry_date

    def run_cleanup(self, category: DataCategory) -> RetentionJob:
        """Run retention cleanup for category.

        Args:
            category: Data category

        Returns:
            Retention job
        """
        policy = self.get_policy(category)
        if not policy:
            raise ValueError(f"No policy found for category: {category}")

        if not policy.auto_delete:
            raise ValueError(f"Auto-delete not enabled for category: {category}")

        job_id = f"cleanup_{category.value}_{int(datetime.now().timestamp())}"

        job = RetentionJob(
            job_id=job_id,
            category=category,
            started_at=datetime.now(),
            status="running",
        )

        self.jobs.append(job)

        logger.info(
            f"Starting retention cleanup: {category.value}",
            extra={"job_id": job_id},
        )

        try:
            # Delete expired data
            items_deleted = self._delete_expired_data(category, policy.retention_days)

            # Update job
            job.items_deleted = items_deleted
            job.completed_at = datetime.now()
            job.status = "completed"

            logger.info(
                f"Retention cleanup completed: {category.value}",
                extra={
                    "job_id": job_id,
                    "items_deleted": items_deleted,
                },
            )

        except Exception as e:
            logger.error(f"Retention cleanup failed: {category.value} - {e}")
            job.status = "failed"

        return job

    def run_all_cleanups(self) -> List[RetentionJob]:
        """Run retention cleanup for all categories with auto-delete enabled.

        Returns:
            List of retention jobs
        """
        jobs = []

        for policy in self.policies.values():
            if policy.auto_delete:
                try:
                    job = self.run_cleanup(policy.category)
                    jobs.append(job)
                except Exception as e:
                    logger.error(f"Failed to run cleanup for {policy.category.value}: {e}")

        return jobs

    def get_job_status(self, job_id: str) -> Optional[RetentionJob]:
        """Get retention job status.

        Args:
            job_id: Job ID

        Returns:
            Retention job or None
        """
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def get_retention_stats(self) -> Dict[str, any]:
        """Get retention statistics.

        Returns:
            Statistics dictionary
        """
        total_jobs = len(self.jobs)
        completed_jobs = sum(1 for j in self.jobs if j.status == "completed")
        failed_jobs = sum(1 for j in self.jobs if j.status == "failed")
        total_deleted = sum(j.items_deleted for j in self.jobs if j.status == "completed")

        return {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "total_items_deleted": total_deleted,
            "policies": {
                policy.category.value: {
                    "retention_days": policy.retention_days,
                    "auto_delete": policy.auto_delete,
                }
                for policy in self.policies.values()
            },
        }

    def _delete_expired_data(self, category: DataCategory, retention_days: int) -> int:
        """Delete expired data for category.

        Args:
            category: Data category
            retention_days: Retention period in days

        Returns:
            Number of items deleted
        """
        # Mock: In production, query and delete from database
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        logger.info(
            f"Deleting {category.value} older than {cutoff_date}",
            extra={"category": category.value, "cutoff_date": cutoff_date.isoformat()},
        )

        # Mock deletion count
        items_deleted = 10  # In production, this would be actual count

        return items_deleted
