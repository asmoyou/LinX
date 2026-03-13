"""Recovery Coordinator for Task Failures.

Coordinates error detection, recovery strategies, and failure handling.

References:
- Requirements 18: Error Handling
- Design Section 7.4: Error Handling and Recovery
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from task_manager.error_handler import (
    AlertManager,
    CircuitBreaker,
    EscalationManager,
    FailureDetector,
    FailureLogger,
    FailureRecord,
    FailureType,
    RecoveryStrategy,
    RetryManager,
    RetryPolicy,
    TaskReassigner,
)

logger = logging.getLogger(__name__)


class RecoveryCoordinator:
    """Coordinates error recovery for failed tasks."""

    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        """Initialize recovery coordinator.

        Args:
            retry_policy: Default retry policy
        """
        self.failure_detector = FailureDetector()
        self.retry_manager = RetryManager(retry_policy)
        self.task_reassigner = TaskReassigner()
        self.escalation_manager = EscalationManager()
        self.circuit_breaker = CircuitBreaker()
        self.failure_logger = FailureLogger()
        self.alert_manager = AlertManager()

        logger.info("RecoveryCoordinator initialized")

    async def create_recovery_plan(
        self,
        task_id: UUID,
        failure_reason: str,
        attempt: int,
    ) -> Dict[str, Any]:
        """Backward-compatible planning helper used by older tests."""
        failure_type = (
            FailureType.TIMEOUT if "timeout" in failure_reason.lower() else FailureType.AGENT_ERROR
        )
        failure_record = FailureRecord(
            task_id=task_id,
            failure_type=failure_type,
            error_message=failure_reason,
            timestamp=datetime.utcnow(),
        )
        failure_record.retry_count = attempt
        strategy = self._select_recovery_strategy(failure_record)
        plan: Dict[str, Any] = {"action": strategy.value}
        if strategy == RecoveryStrategy.RETRY:
            plan["retry_delay"] = self.retry_manager.calculate_retry_delay(attempt)
        elif strategy == RecoveryStrategy.REASSIGN:
            plan["new_agent_criteria"] = {"exclude_failed_agent": True}
        return plan

    async def handle_task_failure(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: Optional[FailureRecord] = None,
    ) -> RecoveryStrategy:
        """Handle a task failure and determine recovery strategy.

        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record (will detect if None)

        Returns:
            Recovery strategy applied
        """
        # Detect failure if not provided
        if not failure_record:
            failure_record = self.failure_detector.detect_failure(task_id, user_id)

            if not failure_record:
                logger.warning(
                    "No failure detected",
                    extra={"task_id": str(task_id)},
                )
                return RecoveryStrategy.FAIL

        logger.info(
            "Handling task failure",
            extra={
                "task_id": str(task_id),
                "failure_type": failure_record.failure_type.value,
                "retry_count": failure_record.retry_count,
            },
        )

        # Log failure
        self.failure_logger.log_failure(failure_record, user_id)

        # Check circuit breaker
        if failure_record.agent_id:
            component_id = f"agent:{failure_record.agent_id}"
            self.circuit_breaker.record_failure(component_id)

            if self.circuit_breaker.is_open(component_id):
                logger.warning(
                    "Circuit breaker open for agent",
                    extra={"agent_id": str(failure_record.agent_id)},
                )

                # Try reassignment
                return await self._apply_reassignment(task_id, user_id, failure_record)

        # Determine recovery strategy
        strategy = self._select_recovery_strategy(failure_record)

        # Apply recovery strategy
        if strategy == RecoveryStrategy.RETRY:
            return await self._apply_retry(task_id, user_id, failure_record)

        elif strategy == RecoveryStrategy.REASSIGN:
            return await self._apply_reassignment(task_id, user_id, failure_record)

        elif strategy == RecoveryStrategy.ESCALATE:
            return await self._apply_escalation(task_id, user_id, failure_record)

        elif strategy == RecoveryStrategy.PARTIAL_SUCCESS:
            return await self._apply_partial_success(task_id, user_id, failure_record)

        else:
            return await self._apply_failure(task_id, user_id, failure_record)

    def _select_recovery_strategy(
        self,
        failure_record: FailureRecord,
    ) -> RecoveryStrategy:
        """Select appropriate recovery strategy.

        Args:
            failure_record: Failure record

        Returns:
            Selected recovery strategy
        """
        # Check if retry is appropriate
        if self.retry_manager.should_retry(
            failure_record.task_id,
            failure_record,
        ):
            return RecoveryStrategy.RETRY

        # For timeouts and agent errors, try reassignment
        if failure_record.failure_type in [
            FailureType.TIMEOUT,
            FailureType.AGENT_ERROR,
            FailureType.CONTAINER_CRASH,
        ]:
            return RecoveryStrategy.REASSIGN

        # For validation errors, escalate
        if failure_record.failure_type == FailureType.VALIDATION_ERROR:
            return RecoveryStrategy.ESCALATE

        # Default to escalation
        return RecoveryStrategy.ESCALATE

    async def _apply_retry(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: FailureRecord,
    ) -> RecoveryStrategy:
        """Apply retry recovery strategy.

        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record

        Returns:
            Applied strategy
        """
        # Calculate delay
        delay = self.retry_manager.calculate_retry_delay(
            failure_record.retry_count,
        )

        logger.info(
            "Retrying task",
            extra={
                "task_id": str(task_id),
                "retry_count": failure_record.retry_count + 1,
                "delay_seconds": delay,
            },
        )

        # Wait before retry
        await asyncio.sleep(delay)

        # Record retry
        self.retry_manager.record_retry(task_id)

        # Reset task status for retry
        from database.connection import get_db_session
        from database.models import Task as TaskModel

        with get_db_session() as session:
            task = (
                session.query(TaskModel)
                .filter(
                    TaskModel.task_id == task_id,
                )
                .first()
            )

            if task:
                task.status = "pending"
                if not task.result:
                    task.result = {}
                task.result["retry_count"] = failure_record.retry_count + 1
                session.commit()

        return RecoveryStrategy.RETRY

    async def _apply_reassignment(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: FailureRecord,
    ) -> RecoveryStrategy:
        """Apply reassignment recovery strategy.

        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record

        Returns:
            Applied strategy
        """
        logger.info(
            "Reassigning task",
            extra={"task_id": str(task_id)},
        )

        # Exclude failed agent
        exclude_agents = []
        if failure_record.agent_id:
            exclude_agents.append(failure_record.agent_id)

        # Attempt reassignment
        success = await self.task_reassigner.reassign_task(
            task_id=task_id,
            user_id=user_id,
            exclude_agent_ids=exclude_agents,
        )

        if success:
            return RecoveryStrategy.REASSIGN
        else:
            # No agents available, escalate
            return await self._apply_escalation(task_id, user_id, failure_record)

    async def _apply_escalation(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: FailureRecord,
    ) -> RecoveryStrategy:
        """Apply escalation recovery strategy.

        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record

        Returns:
            Applied strategy
        """
        message = (
            f"Task {task_id} failed with {failure_record.failure_type.value}. "
            f"Error: {failure_record.error_message}. "
            "Please review and provide guidance."
        )

        await self.escalation_manager.escalate_to_user(
            task_id=task_id,
            user_id=user_id,
            failure_record=failure_record,
            message=message,
        )

        # Send alert for critical failures
        if failure_record.retry_count >= 2:
            self.alert_manager.send_alert(
                severity="critical",
                message=f"Task {task_id} escalated after multiple failures",
                details={
                    "task_id": str(task_id),
                    "user_id": str(user_id),
                    "failure_type": failure_record.failure_type.value,
                    "retry_count": failure_record.retry_count,
                },
            )

        return RecoveryStrategy.ESCALATE

    async def _apply_partial_success(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: FailureRecord,
    ) -> RecoveryStrategy:
        """Apply partial success recovery strategy.

        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record

        Returns:
            Applied strategy
        """
        logger.info(
            "Accepting partial success",
            extra={"task_id": str(task_id)},
        )

        from database.connection import get_db_session
        from database.models import Task as TaskModel

        # Check if any subtasks succeeded
        with get_db_session() as session:
            subtasks = (
                session.query(TaskModel)
                .filter(
                    TaskModel.parent_task_id == task_id,
                )
                .all()
            )

            completed_subtasks = [st for st in subtasks if st.status == "completed"]

            if completed_subtasks:
                # Mark parent as partially completed
                parent_task = (
                    session.query(TaskModel)
                    .filter(
                        TaskModel.task_id == task_id,
                    )
                    .first()
                )

                if parent_task:
                    parent_task.status = "partial_success"
                    if not parent_task.result:
                        parent_task.result = {}
                    parent_task.result["partial_success"] = True
                    parent_task.result["completed_subtasks"] = len(completed_subtasks)
                    parent_task.result["total_subtasks"] = len(subtasks)

                    session.commit()

                return RecoveryStrategy.PARTIAL_SUCCESS

        # No subtasks succeeded, escalate
        return await self._apply_escalation(task_id, user_id, failure_record)

    async def _apply_failure(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: FailureRecord,
    ) -> RecoveryStrategy:
        """Apply failure strategy (no recovery).

        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record

        Returns:
            Applied strategy
        """
        logger.error(
            "Task failed with no recovery",
            extra={"task_id": str(task_id)},
        )

        # Send critical alert
        self.alert_manager.send_alert(
            severity="critical",
            message=f"Task {task_id} failed permanently",
            details={
                "task_id": str(task_id),
                "user_id": str(user_id),
                "failure_type": failure_record.failure_type.value,
                "error_message": failure_record.error_message,
            },
        )

        return RecoveryStrategy.FAIL

    def register_escalation_callback(self, callback) -> None:
        """Register callback for escalations.

        Args:
            callback: Callback function
        """
        self.escalation_manager.register_escalation_callback(callback)

    def register_alert_callback(self, callback) -> None:
        """Register callback for alerts.

        Args:
            callback: Callback function
        """
        self.alert_manager.register_alert_callback(callback)
