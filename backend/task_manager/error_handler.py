"""Error Handling and Recovery for Task Execution.

Implements failure detection, retry logic, and recovery strategies.

References:
- Requirements 18: Error Handling
- Design Section 7.4: Error Handling and Recovery
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from uuid import UUID
from enum import Enum

from database.connection import get_db_session
from database.models import Task as TaskModel, AuditLog

logger = logging.getLogger(__name__)


class FailureType(Enum):
    """Types of task failures."""
    
    TIMEOUT = "timeout"
    AGENT_ERROR = "agent_error"
    CONTAINER_CRASH = "container_crash"
    VALIDATION_ERROR = "validation_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Recovery strategies for failures."""
    
    RETRY = "retry"
    REASSIGN = "reassign"
    ESCALATE = "escalate"
    PARTIAL_SUCCESS = "partial_success"
    FAIL = "fail"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""
    
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class FailureRecord:
    """Record of a task failure."""
    
    task_id: UUID
    failure_type: FailureType
    error_message: str
    timestamp: datetime
    agent_id: Optional[UUID] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerState:
    """State of a circuit breaker."""
    
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "closed"  # closed, open, half_open
    threshold: int = 5
    timeout_seconds: int = 60


class FailureDetector:
    """Detects various types of task failures."""
    
    def __init__(self):
        """Initialize failure detector."""
        self._timeout_thresholds: Dict[str, int] = {
            "default": 300,  # 5 minutes
            "data_analysis": 600,  # 10 minutes
            "code_generation": 300,
            "content_writing": 180,
        }
        
        logger.info("FailureDetector initialized")
    
    def detect_failure(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> Optional[FailureRecord]:
        """Detect if a task has failed.
        
        Args:
            task_id: Task ID
            user_id: User ID
        
        Returns:
            FailureRecord if failure detected, None otherwise
        """
        with get_db_session() as session:
            task = session.query(TaskModel).filter(
                TaskModel.task_id == task_id,
                TaskModel.created_by_user_id == user_id,
            ).first()
            
            if not task:
                return None
            
            # Check for timeout
            if task.status == "in_progress":
                timeout = self._get_timeout_threshold(task)
                elapsed = (datetime.utcnow() - task.created_at).total_seconds()
                
                if elapsed > timeout:
                    return FailureRecord(
                        task_id=task_id,
                        failure_type=FailureType.TIMEOUT,
                        error_message=f"Task timeout after {elapsed:.0f} seconds",
                        timestamp=datetime.utcnow(),
                        agent_id=task.assigned_agent_id,
                    )
            
            # Check for explicit failure
            if task.status == "failed":
                error_msg = "Unknown error"
                if task.result and "error" in task.result:
                    error_msg = task.result["error"]
                
                return FailureRecord(
                    task_id=task_id,
                    failure_type=FailureType.AGENT_ERROR,
                    error_message=error_msg,
                    timestamp=datetime.utcnow(),
                    agent_id=task.assigned_agent_id,
                )
        
        return None
    
    def _get_timeout_threshold(self, task: TaskModel) -> int:
        """Get timeout threshold for a task.
        
        Args:
            task: Task model
        
        Returns:
            Timeout in seconds
        """
        # Try to determine task type from goal text
        goal_lower = task.goal_text.lower()
        
        for task_type, threshold in self._timeout_thresholds.items():
            if task_type in goal_lower:
                return threshold
        
        return self._timeout_thresholds["default"]


class RetryManager:
    """Manages retry logic for failed tasks."""
    
    def __init__(self, default_policy: Optional[RetryPolicy] = None):
        """Initialize retry manager.
        
        Args:
            default_policy: Default retry policy
        """
        self.default_policy = default_policy or RetryPolicy()
        self._retry_history: Dict[UUID, List[datetime]] = {}
        
        logger.info("RetryManager initialized")
    
    def should_retry(
        self,
        task_id: UUID,
        failure_record: FailureRecord,
        policy: Optional[RetryPolicy] = None,
    ) -> bool:
        """Determine if a task should be retried.
        
        Args:
            task_id: Task ID
            failure_record: Failure record
            policy: Retry policy (uses default if None)
        
        Returns:
            True if task should be retried
        """
        policy = policy or self.default_policy
        
        # Check retry count
        if failure_record.retry_count >= policy.max_retries:
            logger.info(
                "Max retries reached",
                extra={
                    "task_id": str(task_id),
                    "retry_count": failure_record.retry_count,
                },
            )
            return False
        
        # Some failures should not be retried
        non_retryable = [
            FailureType.VALIDATION_ERROR,
        ]
        
        if failure_record.failure_type in non_retryable:
            logger.info(
                "Failure type not retryable",
                extra={
                    "task_id": str(task_id),
                    "failure_type": failure_record.failure_type.value,
                },
            )
            return False
        
        return True
    
    def calculate_retry_delay(
        self,
        retry_count: int,
        policy: Optional[RetryPolicy] = None,
    ) -> float:
        """Calculate delay before next retry.
        
        Args:
            retry_count: Current retry count
            policy: Retry policy
        
        Returns:
            Delay in seconds
        """
        policy = policy or self.default_policy
        
        # Exponential backoff
        delay = policy.initial_delay_seconds * (policy.exponential_base ** retry_count)
        delay = min(delay, policy.max_delay_seconds)
        
        # Add jitter
        if policy.jitter:
            import random
            jitter = random.uniform(0, delay * 0.1)
            delay += jitter
        
        return delay
    
    def record_retry(self, task_id: UUID) -> None:
        """Record a retry attempt.
        
        Args:
            task_id: Task ID
        """
        if task_id not in self._retry_history:
            self._retry_history[task_id] = []
        
        self._retry_history[task_id].append(datetime.utcnow())
        
        logger.debug(
            "Retry recorded",
            extra={
                "task_id": str(task_id),
                "total_retries": len(self._retry_history[task_id]),
            },
        )


class TaskReassigner:
    """Handles task reassignment to different agents."""
    
    def __init__(self):
        """Initialize task reassigner."""
        logger.info("TaskReassigner initialized")
    
    async def reassign_task(
        self,
        task_id: UUID,
        user_id: UUID,
        exclude_agent_ids: Optional[List[UUID]] = None,
    ) -> bool:
        """Reassign a task to a different agent.
        
        Args:
            task_id: Task ID
            user_id: User ID
            exclude_agent_ids: Agent IDs to exclude
        
        Returns:
            True if reassignment successful
        """
        from task_manager.agent_assigner import AgentAssigner
        
        exclude_agent_ids = exclude_agent_ids or []
        
        with get_db_session() as session:
            task = session.query(TaskModel).filter(
                TaskModel.task_id == task_id,
                TaskModel.created_by_user_id == user_id,
            ).first()
            
            if not task:
                logger.error(
                    "Task not found for reassignment",
                    extra={"task_id": str(task_id)},
                )
                return False
            
            # Add current agent to exclusion list
            if task.assigned_agent_id:
                exclude_agent_ids.append(task.assigned_agent_id)
            
            # Get required capabilities
            required_capabilities = []
            if task.result and "required_capabilities" in task.result:
                required_capabilities = task.result["required_capabilities"]
        
        # Find new agent
        assigner = AgentAssigner()
        assignment = assigner.assign_agent_to_task(
            task_id=task_id,
            required_capabilities=required_capabilities,
            user_id=user_id,
            exclude_agent_ids=exclude_agent_ids,
        )
        
        if not assignment.agent_id:
            logger.warning(
                "No agent available for reassignment",
                extra={"task_id": str(task_id)},
            )
            return False
        
        # Update task with new agent
        with get_db_session() as session:
            task = session.query(TaskModel).filter(
                TaskModel.task_id == task_id,
            ).first()
            
            if task:
                old_agent_id = task.assigned_agent_id
                task.assigned_agent_id = assignment.agent_id
                task.status = "pending"
                session.commit()
                
                logger.info(
                    "Task reassigned",
                    extra={
                        "task_id": str(task_id),
                        "old_agent": str(old_agent_id),
                        "new_agent": str(assignment.agent_id),
                    },
                )
        
        return True


class EscalationManager:
    """Manages escalation of failures to users."""
    
    def __init__(self):
        """Initialize escalation manager."""
        self._escalation_callbacks: List[Callable] = []
        
        logger.info("EscalationManager initialized")
    
    def register_escalation_callback(
        self,
        callback: Callable[[UUID, FailureRecord], None],
    ) -> None:
        """Register a callback for escalations.
        
        Args:
            callback: Callback function
        """
        self._escalation_callbacks.append(callback)
    
    async def escalate_to_user(
        self,
        task_id: UUID,
        user_id: UUID,
        failure_record: FailureRecord,
        message: str,
    ) -> bool:
        """Escalate a failure to the user.
        
        Args:
            task_id: Task ID
            user_id: User ID
            failure_record: Failure record
            message: Escalation message
        
        Returns:
            True if escalation successful
        """
        logger.info(
            "Escalating to user",
            extra={
                "task_id": str(task_id),
                "user_id": str(user_id),
                "failure_type": failure_record.failure_type.value,
            },
        )
        
        # Store escalation in task result
        with get_db_session() as session:
            task = session.query(TaskModel).filter(
                TaskModel.task_id == task_id,
            ).first()
            
            if task:
                if not task.result:
                    task.result = {}
                
                task.result["escalated"] = True
                task.result["escalation_message"] = message
                task.result["escalation_time"] = datetime.utcnow().isoformat()
                task.status = "escalated"
                
                session.commit()
        
        # Notify via callbacks
        for callback in self._escalation_callbacks:
            try:
                callback(task_id, failure_record)
            except Exception as e:
                logger.error(
                    "Escalation callback failed",
                    extra={"error": str(e)},
                )
        
        return True


class CircuitBreaker:
    """Implements circuit breaker pattern for failing components."""
    
    def __init__(self):
        """Initialize circuit breaker."""
        self._breakers: Dict[str, CircuitBreakerState] = {}
        
        logger.info("CircuitBreaker initialized")
    
    def record_success(self, component_id: str) -> None:
        """Record a successful operation.
        
        Args:
            component_id: Component identifier
        """
        if component_id in self._breakers:
            breaker = self._breakers[component_id]
            breaker.failure_count = 0
            
            if breaker.state == "half_open":
                breaker.state = "closed"
                logger.info(
                    "Circuit breaker closed",
                    extra={"component_id": component_id},
                )
    
    def record_failure(self, component_id: str) -> None:
        """Record a failed operation.
        
        Args:
            component_id: Component identifier
        """
        if component_id not in self._breakers:
            self._breakers[component_id] = CircuitBreakerState()
        
        breaker = self._breakers[component_id]
        breaker.failure_count += 1
        breaker.last_failure_time = datetime.utcnow()
        
        if breaker.failure_count >= breaker.threshold:
            breaker.state = "open"
            logger.warning(
                "Circuit breaker opened",
                extra={
                    "component_id": component_id,
                    "failure_count": breaker.failure_count,
                },
            )
    
    def is_open(self, component_id: str) -> bool:
        """Check if circuit breaker is open.
        
        Args:
            component_id: Component identifier
        
        Returns:
            True if circuit is open
        """
        if component_id not in self._breakers:
            return False
        
        breaker = self._breakers[component_id]
        
        if breaker.state == "closed":
            return False
        
        if breaker.state == "open":
            # Check if timeout has passed
            if breaker.last_failure_time:
                elapsed = (datetime.utcnow() - breaker.last_failure_time).total_seconds()
                if elapsed > breaker.timeout_seconds:
                    breaker.state = "half_open"
                    logger.info(
                        "Circuit breaker half-open",
                        extra={"component_id": component_id},
                    )
                    return False
            
            return True
        
        # half_open state - allow one request through
        return False


class FailureLogger:
    """Logs failures to audit logs."""
    
    def __init__(self):
        """Initialize failure logger."""
        logger.info("FailureLogger initialized")
    
    def log_failure(
        self,
        failure_record: FailureRecord,
        user_id: UUID,
        additional_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a failure to audit logs.
        
        Args:
            failure_record: Failure record
            user_id: User ID
            additional_details: Additional details to log
        """
        details = {
            "failure_type": failure_record.failure_type.value,
            "error_message": failure_record.error_message,
            "retry_count": failure_record.retry_count,
            "timestamp": failure_record.timestamp.isoformat(),
        }
        
        if additional_details:
            details.update(additional_details)
        
        with get_db_session() as session:
            audit_log = AuditLog(
                user_id=user_id,
                agent_id=failure_record.agent_id,
                action="task_failure",
                resource_type="task",
                resource_id=failure_record.task_id,
                details=details,
            )
            
            session.add(audit_log)
            session.commit()
        
        logger.info(
            "Failure logged to audit",
            extra={
                "task_id": str(failure_record.task_id),
                "failure_type": failure_record.failure_type.value,
            },
        )


class AlertManager:
    """Manages alerts for critical failures."""
    
    def __init__(self):
        """Initialize alert manager."""
        self._alert_callbacks: List[Callable] = []
        
        logger.info("AlertManager initialized")
    
    def register_alert_callback(
        self,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """Register a callback for alerts.
        
        Args:
            callback: Callback function
        """
        self._alert_callbacks.append(callback)
    
    def send_alert(
        self,
        severity: str,
        message: str,
        details: Dict[str, Any],
    ) -> None:
        """Send an alert to administrators.
        
        Args:
            severity: Alert severity (info, warning, critical)
            message: Alert message
            details: Alert details
        """
        logger.warning(
            f"Alert: {message}",
            extra={
                "severity": severity,
                "details": details,
            },
        )
        
        # Notify via callbacks
        for callback in self._alert_callbacks:
            try:
                callback(message, details)
            except Exception as e:
                logger.error(
                    "Alert callback failed",
                    extra={"error": str(e)},
                )
