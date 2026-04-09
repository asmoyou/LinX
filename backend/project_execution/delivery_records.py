from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.project_execution_models import (
    ProjectTask,
    ProjectTaskChangeBundle,
    ProjectTaskEvidenceBundle,
    ProjectTaskHandoff,
    ProjectTaskReviewIssue,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_task_handoff(
    session: Session,
    *,
    task: ProjectTask,
    actor_user_id: Optional[UUID],
    payload: dict[str, Any],
) -> ProjectTaskHandoff:
    handoff = ProjectTaskHandoff(
        project_task_id=task.project_task_id,
        run_id=payload.get("run_id"),
        node_id=payload.get("node_id"),
        stage=str(payload.get("stage") or "").strip(),
        from_actor=str(payload.get("from_actor") or "").strip(),
        to_actor=str(payload.get("to_actor") or "").strip() or None,
        status_from=str(payload.get("status_from") or "").strip() or None,
        status_to=str(payload.get("status_to") or "").strip() or None,
        title=str(payload.get("title") or "").strip() or None,
        summary=str(payload.get("summary") or "").strip(),
        payload=payload.get("payload") or {},
        created_by_user_id=actor_user_id,
    )
    session.add(handoff)
    session.flush()
    return handoff


def create_task_change_bundle(
    session: Session,
    *,
    task: ProjectTask,
    actor_user_id: Optional[UUID],
    payload: dict[str, Any],
) -> ProjectTaskChangeBundle:
    bundle = ProjectTaskChangeBundle(
        project_task_id=task.project_task_id,
        run_id=payload.get("run_id"),
        node_id=payload.get("node_id"),
        bundle_kind=str(payload.get("bundle_kind") or "patchset").strip() or "patchset",
        status=str(payload.get("status") or "draft").strip() or "draft",
        base_ref=str(payload.get("base_ref") or "").strip() or None,
        head_ref=str(payload.get("head_ref") or "").strip() or None,
        summary=str(payload.get("summary") or "").strip() or None,
        commit_count=int(payload.get("commit_count") or 0),
        changed_files=payload.get("changed_files") or [],
        artifact_manifest=payload.get("artifact_manifest") or {},
        created_by_user_id=actor_user_id,
    )
    session.add(bundle)
    session.flush()
    return bundle


def create_task_evidence_bundle(
    session: Session,
    *,
    task: ProjectTask,
    actor_user_id: Optional[UUID],
    payload: dict[str, Any],
) -> ProjectTaskEvidenceBundle:
    evidence = ProjectTaskEvidenceBundle(
        project_task_id=task.project_task_id,
        run_id=payload.get("run_id"),
        node_id=payload.get("node_id"),
        summary=str(payload.get("summary") or "").strip(),
        status=str(payload.get("status") or "collected").strip() or "collected",
        bundle=payload.get("bundle") or {},
        created_by_user_id=actor_user_id,
    )
    session.add(evidence)
    session.flush()
    return evidence


def create_task_review_issue(
    session: Session,
    *,
    task: ProjectTask,
    actor_user_id: Optional[UUID],
    payload: dict[str, Any],
) -> ProjectTaskReviewIssue:
    issue = ProjectTaskReviewIssue(
        project_task_id=task.project_task_id,
        change_bundle_id=payload.get("change_bundle_id"),
        evidence_bundle_id=payload.get("evidence_bundle_id"),
        handoff_id=payload.get("handoff_id"),
        issue_key=str(payload.get("issue_key") or "").strip() or None,
        severity=str(payload.get("severity") or "medium").strip() or "medium",
        category=str(payload.get("category") or "other").strip() or "other",
        acceptance_ref=str(payload.get("acceptance_ref") or "").strip() or None,
        summary=str(payload.get("summary") or "").strip(),
        suggestion=str(payload.get("suggestion") or "").strip() or None,
        status=str(payload.get("status") or "open").strip() or "open",
        created_by_user_id=actor_user_id,
        resolved_at=_utc_now() if str(payload.get("status") or "").strip().lower() == "resolved" else None,
    )
    session.add(issue)
    session.flush()
    return issue


def update_task_review_issue(
    session: Session,
    *,
    issue: ProjectTaskReviewIssue,
    payload: dict[str, Any],
) -> ProjectTaskReviewIssue:
    for field_name in ("severity", "category", "acceptance_ref", "summary", "suggestion", "status"):
        if field_name in payload and payload[field_name] is not None:
            value = payload[field_name]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(issue, field_name, value)

    normalized_status = str(issue.status or "").strip().lower()
    issue.resolved_at = _utc_now() if normalized_status == "resolved" else None
    session.flush()
    return issue
