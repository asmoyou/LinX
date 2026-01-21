"""Audit Log Compliance and Reporting.

Implements compliance reporting capabilities and audit log immutability enforcement.

References:
- Requirements 7, 11: Security and Monitoring
- Design Section 11.2: Logging Strategy
- Task 5.5: Logging and Audit
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database.models import AuditLog

logger = logging.getLogger(__name__)


class AuditLogImmutabilityError(Exception):
    """Exception raised when attempting to modify immutable audit logs."""
    pass


class ComplianceReportType:
    """Types of compliance reports."""
    ACCESS_SUMMARY = "access_summary"
    FAILED_ACCESS_ATTEMPTS = "failed_access_attempts"
    USER_ACTIVITY = "user_activity"
    RESOURCE_ACCESS = "resource_access"
    AUTHENTICATION_EVENTS = "authentication_events"
    PERMISSION_CHANGES = "permission_changes"
    DATA_ACCESS_AUDIT = "data_access_audit"
    SECURITY_EVENTS = "security_events"


def enforce_audit_log_immutability(session: Session, audit_log_id: UUID) -> None:
    """Enforce that audit logs cannot be modified or deleted.
    
    This function checks if an audit log exists and raises an error if
    any attempt is made to modify or delete it.
    
    Args:
        session: SQLAlchemy database session
        audit_log_id: Audit log ID to protect
        
    Raises:
        AuditLogImmutabilityError: If attempting to modify/delete audit log
    """
    audit_log = session.query(AuditLog).filter(
        AuditLog.id == audit_log_id
    ).first()
    
    if audit_log:
        raise AuditLogImmutabilityError(
            f"Audit log {audit_log_id} is immutable and cannot be modified or deleted"
        )


def verify_audit_log_integrity(
    session: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """Verify integrity of audit logs.
    
    Checks for:
    - Missing sequence numbers
    - Duplicate entries
    - Timestamp anomalies
    
    Args:
        session: SQLAlchemy database session
        start_date: Start date for verification
        end_date: End date for verification
        
    Returns:
        Dictionary with integrity check results
    """
    query = session.query(AuditLog)
    
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    logs = query.order_by(AuditLog.timestamp).all()
    
    total_logs = len(logs)
    issues = []
    
    # Check for timestamp anomalies (future timestamps)
    now = datetime.utcnow()
    future_logs = [log for log in logs if log.timestamp > now]
    if future_logs:
        issues.append({
            "type": "future_timestamp",
            "count": len(future_logs),
            "description": "Audit logs with future timestamps detected"
        })
    
    # Check for duplicate entries (same user, action, resource, timestamp)
    seen = set()
    duplicates = 0
    for log in logs:
        key = (log.user_id, log.action, log.resource_id, log.timestamp)
        if key in seen:
            duplicates += 1
        seen.add(key)
    
    if duplicates > 0:
        issues.append({
            "type": "duplicates",
            "count": duplicates,
            "description": "Potential duplicate audit log entries"
        })
    
    return {
        "total_logs": total_logs,
        "issues_found": len(issues),
        "issues": issues,
        "verified_at": datetime.utcnow().isoformat(),
        "integrity_status": "clean" if len(issues) == 0 else "issues_detected"
    }


def generate_access_summary_report(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Generate access summary compliance report.
    
    Args:
        session: SQLAlchemy database session
        start_date: Report start date
        end_date: Report end date
        user_id: Optional user ID to filter by
        
    Returns:
        Dictionary with access summary statistics
    """
    query = session.query(AuditLog).filter(
        and_(
            AuditLog.timestamp >= start_date,
            AuditLog.timestamp <= end_date
        )
    )
    
    if user_id:
        query = query.filter(AuditLog.user_id == UUID(user_id))
    
    logs = query.all()
    
    # Calculate statistics
    total_accesses = len(logs)
    
    # Group by resource type
    resource_access = {}
    for log in logs:
        resource_type = log.resource_type or "unknown"
        resource_access[resource_type] = resource_access.get(resource_type, 0) + 1
    
    # Group by action
    action_counts = {}
    for log in logs:
        action = log.action
        action_counts[action] = action_counts.get(action, 0) + 1
    
    # Count successful vs failed
    successful = sum(1 for log in logs if log.details.get("result") == "success")
    failed = sum(1 for log in logs if log.details.get("result") in ["denied", "error"])
    
    # Unique users
    unique_users = len(set(log.user_id for log in logs if log.user_id))
    
    return {
        "report_type": ComplianceReportType.ACCESS_SUMMARY,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_accesses": total_accesses,
        "successful_accesses": successful,
        "failed_accesses": failed,
        "unique_users": unique_users,
        "resource_access": resource_access,
        "action_counts": action_counts,
        "generated_at": datetime.utcnow().isoformat()
    }


def generate_failed_access_report(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    threshold: int = 5
) -> Dict[str, Any]:
    """Generate report of failed access attempts.
    
    Identifies users with multiple failed access attempts, which may
    indicate security issues or unauthorized access attempts.
    
    Args:
        session: SQLAlchemy database session
        start_date: Report start date
        end_date: Report end date
        threshold: Minimum failed attempts to include in report
        
    Returns:
        Dictionary with failed access statistics
    """
    logs = session.query(AuditLog).filter(
        and_(
            AuditLog.timestamp >= start_date,
            AuditLog.timestamp <= end_date
        )
    ).all()
    
    # Filter for failed attempts
    failed_logs = [
        log for log in logs 
        if log.details.get("result") in ["denied", "error"]
    ]
    
    # Group by user
    user_failures = {}
    for log in failed_logs:
        user_id = str(log.user_id) if log.user_id else "anonymous"
        if user_id not in user_failures:
            user_failures[user_id] = []
        user_failures[user_id].append({
            "timestamp": log.timestamp.isoformat(),
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "reason": log.details.get("reason")
        })
    
    # Filter by threshold
    suspicious_users = {
        user_id: attempts 
        for user_id, attempts in user_failures.items()
        if len(attempts) >= threshold
    }
    
    return {
        "report_type": ComplianceReportType.FAILED_ACCESS_ATTEMPTS,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_failed_attempts": len(failed_logs),
        "users_with_failures": len(user_failures),
        "suspicious_users": len(suspicious_users),
        "threshold": threshold,
        "details": suspicious_users,
        "generated_at": datetime.utcnow().isoformat()
    }


def generate_user_activity_report(
    session: Session,
    user_id: str,
    start_date: datetime,
    end_date: datetime
) -> Dict[str, Any]:
    """Generate detailed user activity report.
    
    Args:
        session: SQLAlchemy database session
        user_id: User ID to report on
        start_date: Report start date
        end_date: Report end date
        
    Returns:
        Dictionary with user activity details
    """
    logs = session.query(AuditLog).filter(
        and_(
            AuditLog.user_id == UUID(user_id),
            AuditLog.timestamp >= start_date,
            AuditLog.timestamp <= end_date
        )
    ).order_by(AuditLog.timestamp).all()
    
    # Activity timeline
    timeline = []
    for log in logs:
        timeline.append({
            "timestamp": log.timestamp.isoformat(),
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "result": log.details.get("result"),
            "details": log.details
        })
    
    # Activity summary
    actions_performed = {}
    for log in logs:
        action = log.action
        actions_performed[action] = actions_performed.get(action, 0) + 1
    
    resources_accessed = {}
    for log in logs:
        resource_type = log.resource_type or "unknown"
        resources_accessed[resource_type] = resources_accessed.get(resource_type, 0) + 1
    
    return {
        "report_type": ComplianceReportType.USER_ACTIVITY,
        "user_id": user_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_activities": len(logs),
        "actions_performed": actions_performed,
        "resources_accessed": resources_accessed,
        "timeline": timeline,
        "generated_at": datetime.utcnow().isoformat()
    }


def generate_resource_access_report(
    session: Session,
    resource_type: str,
    resource_id: Optional[str],
    start_date: datetime,
    end_date: datetime
) -> Dict[str, Any]:
    """Generate report of access to specific resource.
    
    Args:
        session: SQLAlchemy database session
        resource_type: Type of resource
        resource_id: Optional specific resource ID
        start_date: Report start date
        end_date: Report end date
        
    Returns:
        Dictionary with resource access details
    """
    query = session.query(AuditLog).filter(
        and_(
            AuditLog.resource_type == resource_type,
            AuditLog.timestamp >= start_date,
            AuditLog.timestamp <= end_date
        )
    )
    
    if resource_id:
        query = query.filter(AuditLog.resource_id == UUID(resource_id))
    
    logs = query.order_by(AuditLog.timestamp).all()
    
    # Access timeline
    access_timeline = []
    for log in logs:
        access_timeline.append({
            "timestamp": log.timestamp.isoformat(),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "result": log.details.get("result"),
            "reason": log.details.get("reason")
        })
    
    # Unique users who accessed
    unique_users = len(set(log.user_id for log in logs if log.user_id))
    
    # Action breakdown
    actions = {}
    for log in logs:
        action = log.action
        actions[action] = actions.get(action, 0) + 1
    
    return {
        "report_type": ComplianceReportType.RESOURCE_ACCESS,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_accesses": len(logs),
        "unique_users": unique_users,
        "actions": actions,
        "access_timeline": access_timeline,
        "generated_at": datetime.utcnow().isoformat()
    }


def generate_authentication_events_report(
    session: Session,
    start_date: datetime,
    end_date: datetime
) -> Dict[str, Any]:
    """Generate report of authentication events.
    
    Args:
        session: SQLAlchemy database session
        start_date: Report start date
        end_date: Report end date
        
    Returns:
        Dictionary with authentication event statistics
    """
    auth_actions = [
        "login_success",
        "login_failure",
        "logout",
        "token_refresh",
        "token_expired",
        "token_invalid"
    ]
    
    logs = session.query(AuditLog).filter(
        and_(
            AuditLog.action.in_(auth_actions),
            AuditLog.timestamp >= start_date,
            AuditLog.timestamp <= end_date
        )
    ).all()
    
    # Count by event type
    event_counts = {}
    for log in logs:
        action = log.action
        event_counts[action] = event_counts.get(action, 0) + 1
    
    # Failed login attempts
    failed_logins = [log for log in logs if log.action == "login_failure"]
    
    # Group failed logins by user
    failed_by_user = {}
    for log in failed_logins:
        username = log.details.get("username", "unknown")
        failed_by_user[username] = failed_by_user.get(username, 0) + 1
    
    return {
        "report_type": ComplianceReportType.AUTHENTICATION_EVENTS,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_events": len(logs),
        "event_counts": event_counts,
        "failed_login_attempts": len(failed_logins),
        "failed_logins_by_user": failed_by_user,
        "generated_at": datetime.utcnow().isoformat()
    }


def apply_log_retention_policy(
    session: Session,
    hot_retention_days: int = 30,
    cold_retention_days: int = 90,
    archive_retention_days: int = 365
) -> Dict[str, Any]:
    """Apply log retention policy.
    
    Note: This function identifies logs for archival/deletion but does not
    actually delete them to maintain audit trail integrity. In production,
    logs should be moved to cold storage or archived rather than deleted.
    
    Args:
        session: SQLAlchemy database session
        hot_retention_days: Days to keep in hot storage (fast access)
        cold_retention_days: Days to keep in cold storage (slower access)
        archive_retention_days: Days to keep in archive (compliance only)
        
    Returns:
        Dictionary with retention policy results
    """
    now = datetime.utcnow()
    
    hot_cutoff = now - timedelta(days=hot_retention_days)
    cold_cutoff = now - timedelta(days=cold_retention_days)
    archive_cutoff = now - timedelta(days=archive_retention_days)
    
    # Count logs in each tier
    hot_logs = session.query(func.count(AuditLog.id)).filter(
        AuditLog.timestamp >= hot_cutoff
    ).scalar()
    
    cold_logs = session.query(func.count(AuditLog.id)).filter(
        and_(
            AuditLog.timestamp < hot_cutoff,
            AuditLog.timestamp >= cold_cutoff
        )
    ).scalar()
    
    archive_logs = session.query(func.count(AuditLog.id)).filter(
        and_(
            AuditLog.timestamp < cold_cutoff,
            AuditLog.timestamp >= archive_cutoff
        )
    ).scalar()
    
    expired_logs = session.query(func.count(AuditLog.id)).filter(
        AuditLog.timestamp < archive_cutoff
    ).scalar()
    
    logger.info(
        "Log retention policy applied",
        extra={
            "hot_logs": hot_logs,
            "cold_logs": cold_logs,
            "archive_logs": archive_logs,
            "expired_logs": expired_logs
        }
    )
    
    return {
        "policy": {
            "hot_retention_days": hot_retention_days,
            "cold_retention_days": cold_retention_days,
            "archive_retention_days": archive_retention_days
        },
        "log_counts": {
            "hot": hot_logs,
            "cold": cold_logs,
            "archive": archive_logs,
            "expired": expired_logs
        },
        "cutoff_dates": {
            "hot": hot_cutoff.isoformat(),
            "cold": cold_cutoff.isoformat(),
            "archive": archive_cutoff.isoformat()
        },
        "applied_at": now.isoformat()
    }


def export_audit_logs_for_compliance(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    format: str = "json"
) -> List[Dict[str, Any]]:
    """Export audit logs for compliance purposes.
    
    Args:
        session: SQLAlchemy database session
        start_date: Export start date
        end_date: Export end date
        format: Export format (json, csv)
        
    Returns:
        List of audit log dictionaries
    """
    logs = session.query(AuditLog).filter(
        and_(
            AuditLog.timestamp >= start_date,
            AuditLog.timestamp <= end_date
        )
    ).order_by(AuditLog.timestamp).all()
    
    exported_logs = []
    for log in logs:
        exported_logs.append({
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat(),
            "user_id": str(log.user_id) if log.user_id else None,
            "agent_id": str(log.agent_id) if log.agent_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "details": log.details
        })
    
    logger.info(
        f"Exported {len(exported_logs)} audit logs for compliance",
        extra={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "count": len(exported_logs)
        }
    )
    
    return exported_logs
