from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from database.models import Agent
from database.project_execution_models import (
    AgentProvisioningProfile,
    ExecutionNode,
    ExternalAgentDispatch,
    Project,
    ProjectAgentBinding,
    ProjectExtensionPackage,
    ProjectPlan,
    ProjectRun,
    ProjectSpace,
    ProjectTask,
    ProjectTaskChangeBundle,
    ProjectTaskContract,
    ProjectTaskDependency,
    ProjectTaskEvidenceBundle,
    ProjectTaskHandoff,
    ProjectTaskReviewIssue,
)
from project_execution.schemas import (
    AgentProvisioningProfileReadModel,
    ExecutionAttemptNodeReadModel,
    ExecutionAttemptReadModel,
    ExternalAgentDispatchReadModel,
    PlannerClarificationQuestionResponse,
    ProjectActivityItemResponse,
    ProjectAgentBindingReadModel,
    ProjectAgentSummaryReadModel,
    ProjectDeliverableResponse,
    ProjectDetailReadModel,
    ProjectSummaryReadModel,
    ProjectTaskDetailReadModel,
    TaskChangeBundleReadModel,
    TaskContractReadModel,
    TaskDependencyReadModel,
    TaskEvidenceBundleReadModel,
    TaskHandoffReadModel,
    TaskReviewIssueReadModel,
    ProjectTaskMetadataItemResponse,
    ProjectTaskSummaryReadModel,
    RunDetailReadModel,
    RunExecutorAssignmentReadModel,
    RuntimeSessionReadModel,
    RunSummaryReadModel,
)
from project_execution.execution_nodes import ensure_execution_nodes_for_run
from project_execution.service import reconcile_project_state, reconcile_run_state
from project_execution.task_dependencies import compute_task_readiness


_RUNNING_STEP_STATUSES = {"assigned", "queued", "leased", "acked", "running"}


def _execution_record_payload(record: Any) -> dict[str, Any]:
    return _as_record(
        getattr(
            record,
            "node_payload",
            getattr(record, "input_payload", {}),
        )
    )


def _execution_record_result(record: Any) -> dict[str, Any]:
    return _as_record(
        getattr(
            record,
            "result_payload",
            getattr(record, "output_payload", {}),
        )
    )


def _execution_record_type(record: Any) -> str:
    return str(getattr(record, "node_type", getattr(record, "step_type", "task")) or "task")


def _execution_record_id(record: Any) -> str:
    value = getattr(record, "node_id", "")
    return str(value) if value is not None else ""


def _load_execution_records_for_run(
    session: Session,
    *,
    run: ProjectRun,
) -> list[ExecutionNode]:
    return ensure_execution_nodes_for_run(session, run=run)


def _load_execution_records_for_runs(
    session: Session,
    *,
    runs: Sequence[ProjectRun],
) -> dict[str, list[ExecutionNode]]:
    records_by_run: dict[str, list[ExecutionNode]] = {}
    for run in runs:
        records_by_run[str(run.run_id)] = _load_execution_records_for_run(session, run=run)
    return records_by_run


def _as_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_optional_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            normalized.append(item.strip())
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            normalized.append(str(item))
        elif isinstance(item, dict):
            record = _as_record(item)
            label = (
                _as_optional_str(record.get("display_name"))
                or _as_optional_str(record.get("name"))
                or _as_optional_str(record.get("skill"))
                or _as_optional_str(record.get("slug"))
            )
            if label:
                normalized.append(label)
    return normalized


def _pick_first_str(record: dict[str, Any], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        value = _as_optional_str(record.get(key))
        if value:
            return value
    return None


def _pick_first_str_list(record: dict[str, Any], keys: Sequence[str]) -> list[str]:
    for key in keys:
        values = _as_str_list(record.get(key))
        if values:
            return values
    return []


def _latest_datetime(values: Iterable[Optional[datetime]]) -> Optional[datetime]:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def _humanize_token(value: str) -> str:
    normalized = str(value or "").replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in normalized.split())


def _truncate_text(value: Optional[str], limit: int = 160) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "No summary available yet."
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(limit - 1, 1)].rstrip()}…"


def _summarize_record(value: Optional[dict[str, Any]]) -> Optional[str]:
    if not value:
        return None

    for key in ("summary", "output", "result", "error", "reason", "review_feedback", "message"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return _truncate_text(candidate, 180)

    flattened = []
    for key, candidate in value.items():
        if isinstance(candidate, (str, int, float, bool)):
            flattened.append(f"{_humanize_token(str(key))}: {candidate}")
        if len(flattened) >= 3:
            break
    if flattened:
        return " · ".join(flattened)
    return None


def _to_platform_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    mapping = {
        "requirements": "planning",
        "planning": "planning",
        "queued": "queued",
        "pending": "queued",
        "assigned": "assigned",
        "scheduled": "scheduled",
        "executing": "running",
        "running": "running",
        "in_progress": "running",
        "reviewing": "reviewing",
        "qa": "reviewing",
        "review": "reviewing",
        "blocked": "blocked",
        "busy": "working",
        "available": "idle",
        "disabled": "offline",
    }
    return mapping.get(normalized, normalized or "draft")


def _activity_level_from_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if "fail" in normalized or "error" in normalized or normalized == "cancelled":
        return "error"
    if "review" in normalized or "blocked" in normalized or "clarification" in normalized:
        return "warning"
    if (
        "complete" in normalized
        or "success" in normalized
        or "approved" in normalized
    ):
        return "success"
    return "info"


def _is_completed_status(status: str) -> bool:
    return str(status or "").strip().lower() in {
        "completed",
        "done",
        "success",
        "succeeded",
        "approved",
    }


def _is_failed_status(status: str) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {"cancelled", "canceled", "error", "failed"} or "fail" in normalized


def _is_closed_run_status(status: str) -> bool:
    return str(status or "").strip().lower() in {
        "completed",
        "done",
        "success",
        "succeeded",
        "failed",
        "cancelled",
        "canceled",
    }


def _is_terminal_run_status(status: str) -> bool:
    return str(status or "").strip().lower() in {
        "completed",
        "done",
        "success",
        "succeeded",
        "failed",
        "cancelled",
        "canceled",
        "blocked",
    }


def _is_active_run_status(status: str) -> bool:
    return str(status or "").strip().lower() in {"running", "executing", "in_progress"}


def _is_queued_run_status(status: str) -> bool:
    return str(status or "").strip().lower() in {"queued", "assigned", "scheduled", "pending"}


def _is_blocked_status(status: str) -> bool:
    return str(status or "").strip().lower() == "blocked"


def _priority_to_number(value: Any) -> int:
    parsed = _as_optional_int(value)
    if parsed is not None:
        return parsed

    normalized = str(value or "").strip().lower()
    mapping = {
        "urgent": 4,
        "critical": 4,
        "high": 3,
        "medium": 2,
        "normal": 2,
        "low": 1,
    }
    return mapping.get(normalized, 2)


def _build_progress(completed_tasks: int, total_tasks: int, status: str) -> int:
    if total_tasks <= 0:
        return 100 if status == "completed" else 0
    return max(0, min(100, round((completed_tasks / total_tasks) * 100)))


def _normalize_workspace_artifact_path(value: str) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    if normalized.startswith("/"):
        return normalized
    if normalized.startswith("workspace/"):
        return f"/{normalized}"
    return f"/workspace/{normalized}"


def _is_deliverable_workspace_artifact_path(path: str) -> bool:
    normalized = _normalize_workspace_artifact_path(path)
    if not normalized or normalized == "/workspace/output":
        return False
    if not normalized.startswith("/workspace/output/"):
        return False

    suffix = ""
    suffix_index = normalized.rfind(".")
    if suffix_index >= 0:
        suffix = normalized[suffix_index:].lower()
    return suffix not in {".ttf", ".otf", ".ttc", ".woff", ".woff2", ".eot"}


def _deliverable_from_unknown(value: Any) -> Optional[ProjectDeliverableResponse]:
    record = _as_record(value)
    path = _pick_first_str(record, ("path", "file_reference", "uri"))
    filename = _pick_first_str(record, ("filename", "name"))
    if not filename and path:
        filename = path.split("/")[-1]

    if not filename or not path:
        return None

    return ProjectDeliverableResponse(
        filename=filename,
        path=path,
        size=_as_optional_int(record.get("size")) or _as_optional_int(record.get("file_size")) or 0,
        download_url=_pick_first_str(record, ("download_url", "downloadUrl", "url")),
        is_target=(
            _as_optional_bool(record.get("is_target"))
            if _as_optional_bool(record.get("is_target")) is not None
            else _as_optional_bool(record.get("isTarget")) or False
        ),
        source_scope=_pick_first_str(record, ("source_scope", "sourceScope", "scope")),
    )


def _artifact_deliverable_from_unknown(value: Any) -> Optional[ProjectDeliverableResponse]:
    record = _as_record(value)
    path = _pick_first_str(record, ("path", "file_path", "uri"))
    if not path:
        return None
    if _as_optional_bool(record.get("is_directory")) or _as_optional_bool(record.get("is_dir")):
        return None
    if not _is_deliverable_workspace_artifact_path(path):
        return None

    normalized_path = _normalize_workspace_artifact_path(path)
    filename = _pick_first_str(record, ("filename", "name")) or normalized_path.split("/")[-1]
    return ProjectDeliverableResponse(
        filename=filename,
        path=normalized_path,
        size=_as_optional_int(record.get("size")) or _as_optional_int(record.get("file_size")) or 0,
        download_url=_pick_first_str(record, ("download_url", "downloadUrl", "url")),
        is_target=True,
        source_scope="run_workspace",
    )


def _collect_deliverables_from_payloads(
    payloads: Sequence[dict[str, Any]],
) -> list[ProjectDeliverableResponse]:
    mapped: dict[str, ProjectDeliverableResponse] = {}

    for payload in payloads:
        raw_deliverables = payload.get("deliverables")
        if isinstance(raw_deliverables, list):
            for item in raw_deliverables:
                deliverable = _deliverable_from_unknown(item)
                if deliverable:
                    mapped[deliverable.path] = deliverable

        raw_artifacts = payload.get("artifacts")
        if isinstance(raw_artifacts, list):
            for item in raw_artifacts:
                deliverable = _artifact_deliverable_from_unknown(item)
                if deliverable:
                    mapped[deliverable.path] = deliverable

    return list(mapped.values())


def _get_task_dependencies_from_payload(payloads: Sequence[dict[str, Any]]) -> list[str]:
    for payload in payloads:
        values = _pick_first_str_list(payload, ("dependencies", "dependency_ids", "blocked_by"))
        if values:
            return values
    return []


def _get_task_acceptance_from_payload(payloads: Sequence[dict[str, Any]]) -> Optional[str]:
    for payload in payloads:
        acceptance = _pick_first_str(payload, ("acceptance_criteria", "acceptanceCriteria"))
        if acceptance:
            return acceptance
    return None


def _get_task_review_status_from_payload(payloads: Sequence[dict[str, Any]]) -> Optional[str]:
    for payload in payloads:
        review_status = _pick_first_str(payload, ("review_status", "reviewStatus"))
        if review_status:
            return review_status
    return None


def _get_task_skill_names_from_payload(payloads: Sequence[dict[str, Any]]) -> list[str]:
    for payload in payloads:
        skills = _pick_first_str_list(payload, ("skill_names", "skillNames", "skills"))
        if skills:
            return skills
    return []


def _get_task_assignee_name_from_payload(payloads: Sequence[dict[str, Any]]) -> Optional[str]:
    for payload in payloads:
        assignee = _pick_first_str(
            payload,
            ("assigned_agent_name", "assignee_name", "owner_name"),
        )
        if assignee:
            return assignee
    return None


def _get_task_execution_mode_from_payload(
    payloads: Sequence[dict[str, Any]],
) -> Optional[str]:
    for payload in payloads:
        execution_mode = _pick_first_str(payload, ("execution_mode", "executionMode"))
        if execution_mode:
            return execution_mode
    return None


def _get_planner_questions_from_payload(
    payloads: Sequence[dict[str, Any]],
) -> list[PlannerClarificationQuestionResponse]:
    for payload in payloads:
        raw_questions = payload.get("planner_clarification_questions")
        if not isinstance(raw_questions, list):
            continue
        questions: list[PlannerClarificationQuestionResponse] = []
        for raw_question in raw_questions:
            record = _as_record(raw_question)
            question = _pick_first_str(record, ("question",))
            if question:
                questions.append(
                    PlannerClarificationQuestionResponse(
                        question=question,
                        importance=_pick_first_str(record, ("importance",)),
                    )
                )
        return questions
    return []


def _build_run_alert_signature(
    *,
    status: str,
    task_id: Optional[str],
    task_title: Optional[str],
    failure_reason: Optional[str],
    latest_signal: Optional[str],
) -> str:
    return json.dumps(
        {
            "status": status,
            "taskId": task_id,
            "taskTitle": task_title,
            "failureReason": failure_reason,
            "latestSignal": latest_signal,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _extract_run_planner_metrics(
    runtime_context: dict[str, Any],
    run_steps: Sequence[Any],
) -> dict[str, Any]:
    planner_summary = _pick_first_str(runtime_context, ("planner_summary",))
    planner_source = _pick_first_str(runtime_context, ("planner_source",))
    step_total = _as_optional_int(runtime_context.get("step_count")) or len(run_steps)
    completed_step_count = sum(1 for step in run_steps if _is_completed_status(step.status))
    active_step_count = sum(1 for step in run_steps if step.status.lower() in _RUNNING_STEP_STATUSES)
    current_step = next(
        (
            step
            for step in sorted(run_steps, key=lambda item: item.sequence_number)
            if step.status.lower() not in {"completed", "failed", "cancelled", "blocked"}
        ),
        None,
    )
    parallel_groups = {
        value
        for value in (
            _pick_first_str(_execution_record_payload(step), ("parallel_group",))
            for step in run_steps
        )
        if value
    }
    suggested_agent_ids = (
        _as_str_list(_execution_record_payload(current_step).get("suggested_agent_ids"))
        if current_step is not None
        else []
    )
    clarification_questions = _get_planner_questions_from_payload((runtime_context,))
    return {
        "planner_summary": planner_summary,
        "planner_source": planner_source,
        "step_total": step_total,
        "completed_step_count": completed_step_count,
        "active_step_count": active_step_count,
        "parallel_group_count": len(parallel_groups),
        "current_step_title": current_step.name if current_step is not None else None,
        "suggested_agent_ids": suggested_agent_ids,
        "needs_clarification": bool(clarification_questions),
        "clarification_questions": clarification_questions,
    }


def _resolve_run_lifecycle(
    run: ProjectRun,
    tasks: Sequence[ProjectTask],
    run_steps: Sequence[Any],
) -> dict[str, Any]:
    raw_status = str(run.status or "").lower()
    fallback_completed_at = _latest_datetime(
        [
            run.completed_at,
            *(task.updated_at for task in tasks),
            *(step.completed_at for step in run_steps),
            *(step.updated_at for step in run_steps),
            run.updated_at,
            run.started_at,
        ]
    )

    if _is_closed_run_status(raw_status):
        return {
            "status": _to_platform_status(run.status),
            "completed_at": run.completed_at or fallback_completed_at,
        }

    if not tasks:
        if run.started_at:
            return {
                "status": "failed" if any(_is_failed_status(step.status) for step in run_steps) else "completed",
                "completed_at": run.completed_at or fallback_completed_at,
            }
        return {"status": _to_platform_status(run.status), "completed_at": run.completed_at}

    if all(_is_completed_status(task.status) or _is_failed_status(task.status) for task in tasks):
        return {
            "status": (
                "failed"
                if any(_is_failed_status(task.status) for task in tasks)
                or any(_is_failed_status(step.status) for step in run_steps)
                else "completed"
            ),
            "completed_at": run.completed_at or fallback_completed_at,
        }

    return {"status": _to_platform_status(run.status), "completed_at": run.completed_at}


def _resolve_project_lifecycle(
    project: Project,
    tasks: Sequence[ProjectTask],
    runs: Sequence[ProjectRun],
) -> dict[str, Any]:
    task_statuses = [str(task.status or "").lower() for task in tasks]
    run_statuses = [str(run.status or "").lower() for run in runs]

    if not task_statuses and not run_statuses:
        return {"status": _to_platform_status(project.status), "completed_at": None}

    if any(status == "running" for status in task_statuses) or any(
        _is_active_run_status(status) for status in run_statuses
    ):
        return {"status": "running", "completed_at": None}

    if any(_is_queued_run_status(status) for status in task_statuses) or any(
        _is_queued_run_status(status) for status in run_statuses
    ):
        return {"status": "queued", "completed_at": None}

    if runs:
        latest_run = max(
            runs,
            key=lambda item: _latest_datetime(
                (item.updated_at, item.completed_at, item.started_at, item.created_at)
            )
            or datetime.min,
        )
        latest_run_status = str(latest_run.status or "").lower()
        if _is_blocked_status(latest_run_status):
            return {"status": "blocked", "completed_at": None}
        if _is_failed_status(latest_run_status):
            return {"status": "failed", "completed_at": latest_run.completed_at}
        if _is_closed_run_status(latest_run_status):
            return {"status": "completed", "completed_at": latest_run.completed_at}

    if tasks:
        latest_task = max(
            tasks,
            key=lambda item: _latest_datetime((item.updated_at, item.created_at)) or datetime.min,
        )
        latest_task_status = str(latest_task.status or "").lower()
        if _is_blocked_status(latest_task_status):
            return {"status": "blocked", "completed_at": None}
        if _is_failed_status(latest_task_status):
            return {"status": "failed", "completed_at": latest_task.updated_at}
        if _is_completed_status(latest_task_status):
            return {"status": "completed", "completed_at": latest_task.updated_at}

    return {"status": _to_platform_status(project.status), "completed_at": None}


def _build_task_summary(
    task: ProjectTask,
    *,
    agent_lookup: dict[str, Agent],
    readiness: Optional[dict[str, Any]] = None,
    open_issue_count: int = 0,
    latest_change_bundle_status: Optional[str] = None,
) -> ProjectTaskSummaryReadModel:
    payloads = (_as_record(task.input_payload), _as_record(task.output_payload))
    agent = agent_lookup.get(str(task.assignee_agent_id)) if task.assignee_agent_id else None
    assigned_agent_name = (
        agent.name if agent is not None else _get_task_assignee_name_from_payload(payloads)
    )
    ready = bool((readiness or {}).get("ready", True))
    blocking_dependency_count = int((readiness or {}).get("blocking_dependency_count", 0))
    next_action: Optional[str] = None
    blocker_reason: Optional[str] = None
    normalized_status = str(task.status or "").strip().lower()

    if not ready and blocking_dependency_count > 0:
        blocker_reason = f"Waiting on {blocking_dependency_count} upstream dependenc{'y' if blocking_dependency_count == 1 else 'ies'}."
        next_action = "Resolve upstream dependencies"
    elif open_issue_count > 0:
        blocker_reason = f"{open_issue_count} open review issue{'s' if open_issue_count != 1 else ''}."
        next_action = "Address review issues"
    elif normalized_status in {"queued", "assigned", "scheduled"}:
        next_action = "Monitor attempt assignment"
    elif normalized_status in {"running", "in_progress"}:
        next_action = "Monitor active execution"
    elif normalized_status in {"reviewing", "in_review"}:
        next_action = "Review latest delivery"
    elif normalized_status in {"completed", "approved", "pending_acceptance"}:
        next_action = "Validate and close task"
    else:
        next_action = "Refine contract and prepare execution"

    return ProjectTaskSummaryReadModel(
        id=str(task.project_task_id),
        title=task.title,
        status=_to_platform_status(task.status),
        priority=_priority_to_number(task.priority),
        updated_at=task.updated_at,
        assigned_agent_id=str(task.assignee_agent_id) if task.assignee_agent_id else None,
        assigned_agent_name=assigned_agent_name,
        dependency_ids=_get_task_dependencies_from_payload(payloads),
        review_status=_get_task_review_status_from_payload(payloads),
        ready=ready,
        blocking_dependency_count=blocking_dependency_count,
        open_issue_count=open_issue_count,
        latest_change_bundle_status=latest_change_bundle_status,
        next_action=next_action,
        blocker_reason=blocker_reason,
    )


def _build_project_summary(
    project: Project,
    *,
    tasks: Sequence[ProjectTask],
    runs: Sequence[ProjectRun],
    plans: Sequence[ProjectPlan],
    active_node_count: int,
) -> ProjectSummaryReadModel:
    lifecycle = _resolve_project_lifecycle(project, tasks, runs)
    latest_plan = max(plans, key=lambda item: item.updated_at, default=None)
    latest_plan_definition = _as_record(latest_plan.definition) if latest_plan else {}
    latest_run = max(runs, key=lambda item: item.updated_at, default=None)
    latest_task = max(tasks, key=lambda item: item.updated_at, default=None)
    completed_tasks = sum(1 for task in tasks if _is_completed_status(task.status))
    failed_tasks = sum(1 for task in tasks if _is_failed_status(task.status))
    updated_at = _latest_datetime(
        [project.updated_at, *(task.updated_at for task in tasks), *(run.updated_at for run in runs)]
    ) or project.updated_at
    configuration = _as_record(project.configuration)

    return ProjectSummaryReadModel(
        id=str(project.project_id),
        title=project.name,
        summary=(
            project.description
            or (latest_plan.goal if latest_plan else None)
            or _pick_first_str(latest_plan_definition, ("summary", "goal", "instructions"))
            or _pick_first_str(configuration, ("summary", "goal", "instructions"))
            or "No summary available yet."
        ),
        status=lifecycle["status"],
        progress=_build_progress(completed_tasks, len(tasks), lifecycle["status"]),
        created_at=project.created_at,
        updated_at=updated_at,
        started_at=_latest_datetime(run.started_at for run in runs),
        completed_at=lifecycle["completed_at"],
        total_tasks=len(tasks),
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        active_node_count=active_node_count,
        needs_clarification=any(
            "clarification" in str(task.status or "").lower() for task in tasks
        ),
        latest_signal=(
            latest_run.error_message
            if latest_run and latest_run.error_message
            else _summarize_record(_as_record(latest_run.runtime_context)) if latest_run else None
        )
        or (latest_task.error_message if latest_task else None)
        or _summarize_record(_as_record(latest_task.output_payload)) if latest_task else None
        or (latest_plan.goal if latest_plan else None)
        or project.description
        or _pick_first_str(configuration, ("summary", "goal")),
    )


def _build_project_activity(
    project: Project,
    *,
    tasks: Sequence[ProjectTask],
    plans: Sequence[ProjectPlan],
    extensions: Sequence[ProjectExtensionPackage],
    project_space: Optional[ProjectSpace],
    agent_lookup: dict[str, Agent],
) -> list[ProjectActivityItemResponse]:
    items: list[ProjectActivityItemResponse] = [
        ProjectActivityItemResponse(
            id=f"project-{project.project_id}",
            title="Project updated",
            description=project.description or "Project metadata synchronized.",
            timestamp=project.updated_at,
            level=_activity_level_from_status(project.status),
        )
    ]

    for plan in plans:
        items.append(
            ProjectActivityItemResponse(
                id=f"plan-{plan.plan_id}",
                title=f"Plan {plan.name}",
                description=(
                    plan.goal
                    or _summarize_record(_as_record(plan.definition))
                    or f"{_humanize_token(plan.status)} v{plan.version} plan."
                ),
                timestamp=plan.updated_at,
                level=_activity_level_from_status(plan.status),
            )
        )

    for task in tasks:
        payloads = (_as_record(task.input_payload), _as_record(task.output_payload))
        agent = agent_lookup.get(str(task.assignee_agent_id)) if task.assignee_agent_id else None
        items.append(
            ProjectActivityItemResponse(
                id=f"task-{task.project_task_id}",
                title=task.title,
                description=(
                    task.error_message
                    or _summarize_record(_as_record(task.output_payload))
                    or f"{_humanize_token(task.status)} task update."
                ),
                timestamp=task.updated_at,
                level=_activity_level_from_status(task.status),
                actor=agent.name if agent is not None else _get_task_assignee_name_from_payload(payloads),
                task_id=str(task.project_task_id),
            )
        )

    for extension in extensions:
        items.append(
            ProjectActivityItemResponse(
                id=f"extension-{extension.extension_package_id}",
                title=f"Extension {extension.name}",
                description=(
                    extension.source_uri
                    or f"{_humanize_token(extension.status)} "
                    f"{_humanize_token(extension.package_type)} package."
                ),
                timestamp=extension.updated_at,
                level=_activity_level_from_status(extension.status),
            )
        )

    if project_space is not None:
        items.append(
            ProjectActivityItemResponse(
                id=f"project-space-{project_space.project_space_id}",
                title="Project space updated",
                description=(
                    project_space.root_path
                    or project_space.storage_uri
                    or f"{_humanize_token(project_space.status)} workspace synced."
                ),
                timestamp=project_space.last_synced_at or project_space.updated_at,
                level=_activity_level_from_status(project_space.status),
            )
        )

    return sorted(items, key=lambda item: item.timestamp, reverse=True)[:20]


def _build_run_summary(
    run: ProjectRun,
    *,
    project: Project,
    tasks: Sequence[ProjectTask],
    run_steps: Sequence[Any],
) -> RunSummaryReadModel:
    lifecycle = _resolve_run_lifecycle(run, tasks, run_steps)
    runtime_context = _as_record(run.runtime_context)
    failed_step = next(
        (step for step in sorted(run_steps, key=lambda item: item.updated_at, reverse=True)
         if _is_failed_status(step.status) or step.error_message),
        None,
    )
    failed_task = next(
        (task for task in sorted(tasks, key=lambda item: item.updated_at, reverse=True)
         if _is_failed_status(task.status) or task.error_message),
        None,
    )
    primary_task = max(tasks, key=lambda item: item.updated_at, default=None)
    task_id = _pick_first_str(runtime_context, ("project_task_id",)) or (
        str(primary_task.project_task_id) if primary_task else None
    )
    task_title = _pick_first_str(runtime_context, ("task_title",)) or (
        primary_task.title if primary_task else None
    )
    execution_mode = (
        _pick_first_str(runtime_context, ("execution_mode",))
        or _get_task_execution_mode_from_payload(
            (_as_record(primary_task.input_payload),) if primary_task else ()
        )
        or (
            "external_runtime"
            if str(_pick_first_str(runtime_context, ("runtime_type",)) or "").startswith("external")
            else None
        )
    )
    failure_reason = (
        run.error_message
        or (failed_task.error_message if failed_task else None)
        or (failed_step.error_message if failed_step else None)
    )
    handled_at = _pick_first_str(_as_record(runtime_context.get("alert_state")), ("handled_at", "handledAt")) or _pick_first_str(
        runtime_context, ("handled_at", "handledAt")
    )
    latest_signal = (
        failure_reason
        or _summarize_record(runtime_context)
        or (failed_step.error_message if failed_step else None)
    )
    handled_signature = _pick_first_str(
        _as_record(runtime_context.get("alert_state")), ("handled_signature", "handledSignature")
    )
    planner_metrics = _extract_run_planner_metrics(runtime_context, run_steps)

    external_agent_ids: set[str] = set()
    for step in run_steps:
        payload = _execution_record_payload(step)
        agent_id = _pick_first_str(payload, ("assigned_agent_id",))
        runtime_type = str(_pick_first_str(payload, ("runtime_type",)) or "")
        if agent_id and (
            runtime_type.startswith("external") or runtime_type == "remote_session"
        ):
            external_agent_ids.add(agent_id)

    return RunSummaryReadModel(
        id=str(run.run_id),
        project_id=str(run.project_id),
        project_title=project.name,
        status=lifecycle["status"],
        created_at=run.created_at,
        trigger_source=run.trigger_source,
        execution_mode=execution_mode,
        planner_source=planner_metrics["planner_source"],
        planner_summary=planner_metrics["planner_summary"],
        step_total=planner_metrics["step_total"],
        completed_step_count=planner_metrics["completed_step_count"],
        active_step_count=planner_metrics["active_step_count"],
        parallel_group_count=planner_metrics["parallel_group_count"],
        current_step_title=planner_metrics["current_step_title"],
        suggested_agent_ids=planner_metrics["suggested_agent_ids"],
        needs_clarification=planner_metrics["needs_clarification"],
        clarification_questions=planner_metrics["clarification_questions"],
        task_id=task_id,
        task_title=task_title,
        failure_reason=failure_reason,
        handled_at=handled_at,
        handled_signature=handled_signature,
        alert_signature=_build_run_alert_signature(
            status=lifecycle["status"],
            task_id=task_id,
            task_title=task_title,
            failure_reason=failure_reason,
            latest_signal=latest_signal,
        ),
        started_at=run.started_at,
        completed_at=lifecycle["completed_at"],
        updated_at=run.updated_at,
        total_tasks=len(tasks),
        completed_tasks=sum(1 for task in tasks if _is_completed_status(task.status)),
        failed_tasks=sum(1 for task in tasks if _is_failed_status(task.status)),
        external_agent_count=len(external_agent_ids),
        latest_signal=latest_signal,
    )


def _activity_from_run_step(step: Any) -> ProjectActivityItemResponse:
    return ProjectActivityItemResponse(
        id=_execution_record_id(step),
        title=step.name,
        description=(
            step.error_message
            or _summarize_record(_execution_record_result(step))
            or f"{_humanize_token(step.status)} {_humanize_token(_execution_record_type(step))} step."
        ),
        timestamp=step.completed_at or step.started_at or step.updated_at or step.created_at,
        level=_activity_level_from_status(step.status),
        task_id=str(step.project_task_id) if step.project_task_id else None,
    )


def _serialize_handoff(handoff: ProjectTaskHandoff) -> TaskHandoffReadModel:
    return TaskHandoffReadModel(
        id=str(handoff.handoff_id),
        task_id=str(handoff.project_task_id),
        run_id=str(handoff.run_id) if handoff.run_id else None,
        node_id=str(handoff.node_id) if handoff.node_id else None,
        stage=handoff.stage,
        from_actor=handoff.from_actor,
        to_actor=handoff.to_actor,
        status_from=handoff.status_from,
        status_to=handoff.status_to,
        title=handoff.title,
        summary=handoff.summary,
        payload=_as_record(handoff.payload),
        created_at=handoff.created_at,
        updated_at=handoff.updated_at,
    )


def _serialize_change_bundle(bundle: ProjectTaskChangeBundle) -> TaskChangeBundleReadModel:
    return TaskChangeBundleReadModel(
        id=str(bundle.change_bundle_id),
        task_id=str(bundle.project_task_id),
        run_id=str(bundle.run_id) if bundle.run_id else None,
        node_id=str(bundle.node_id) if bundle.node_id else None,
        bundle_kind=bundle.bundle_kind,
        status=bundle.status,
        base_ref=bundle.base_ref,
        head_ref=bundle.head_ref,
        summary=bundle.summary,
        commit_count=bundle.commit_count,
        changed_files=list(bundle.changed_files or []),
        artifact_manifest=_as_record(bundle.artifact_manifest),
        created_at=bundle.created_at,
        updated_at=bundle.updated_at,
    )


def _serialize_evidence_bundle(
    evidence: ProjectTaskEvidenceBundle,
) -> TaskEvidenceBundleReadModel:
    return TaskEvidenceBundleReadModel(
        id=str(evidence.evidence_bundle_id),
        task_id=str(evidence.project_task_id),
        run_id=str(evidence.run_id) if evidence.run_id else None,
        node_id=str(evidence.node_id) if evidence.node_id else None,
        summary=evidence.summary,
        status=evidence.status,
        bundle=_as_record(evidence.bundle),
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


def _serialize_review_issue(issue: ProjectTaskReviewIssue) -> TaskReviewIssueReadModel:
    return TaskReviewIssueReadModel(
        id=str(issue.review_issue_id),
        task_id=str(issue.project_task_id),
        change_bundle_id=str(issue.change_bundle_id) if issue.change_bundle_id else None,
        evidence_bundle_id=str(issue.evidence_bundle_id) if issue.evidence_bundle_id else None,
        handoff_id=str(issue.handoff_id) if issue.handoff_id else None,
        issue_key=issue.issue_key,
        severity=issue.severity,
        category=issue.category,
        acceptance_ref=issue.acceptance_ref,
        summary=issue.summary,
        suggestion=issue.suggestion,
        status=issue.status,
        resolved_at=issue.resolved_at,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


def _serialize_attempt(
    run: ProjectRun,
    *,
    task_id: str,
    project: Project,
    tasks: Sequence[ProjectTask],
    run_steps: Sequence[Any],
    external_dispatches: Sequence[ExternalAgentDispatch],
) -> ExecutionAttemptReadModel:
    summary = _build_run_summary(run, project=project, tasks=tasks, run_steps=run_steps)
    return ExecutionAttemptReadModel(
        id=str(run.run_id),
        task_id=task_id,
        status=summary.status,
        created_at=run.created_at,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        trigger_source=run.trigger_source,
        execution_mode=summary.execution_mode,
        current_step_title=summary.current_step_title,
        failure_reason=summary.failure_reason,
        total_nodes=len(run_steps),
        completed_nodes=sum(1 for step in run_steps if _is_completed_status(step.status)),
        active_runtime_sessions=sum(
            1
            for dispatch in external_dispatches
            if str(dispatch.status or "").strip().lower()
            not in {"completed", "failed", "cancelled", "canceled"}
        ),
    )


def build_task_attempt_read_models(
    session: Session,
    *,
    task: ProjectTask,
    project: Project,
) -> list[ExecutionAttemptReadModel]:
    run_id_set: set[UUID] = set()
    if task.run_id is not None:
        run_id_set.add(task.run_id)

    step_run_ids = (
        session.query(ExecutionNode.run_id)
        .filter(ExecutionNode.project_task_id == task.project_task_id)
        .distinct()
        .all()
    )
    run_id_set.update(run_id for (run_id,) in step_run_ids if run_id is not None)

    if not run_id_set:
        return []

    runs = (
        session.query(ProjectRun)
        .filter(ProjectRun.run_id.in_(run_id_set))
        .order_by(ProjectRun.created_at.desc())
        .all()
    )

    steps_by_run = _load_execution_records_for_runs(session, runs=runs)

    tasks_by_run: dict[str, list[ProjectTask]] = defaultdict(list)
    for related_task in (
        session.query(ProjectTask)
        .filter(ProjectTask.run_id.in_(run_id_set))
        .all()
    ):
        if related_task.run_id is not None:
            tasks_by_run[str(related_task.run_id)].append(related_task)

    dispatches_by_run: dict[str, list[ExternalAgentDispatch]] = defaultdict(list)
    for dispatch in (
        session.query(ExternalAgentDispatch)
        .filter(ExternalAgentDispatch.run_id.in_(run_id_set))
        .order_by(ExternalAgentDispatch.created_at.desc())
        .all()
    ):
        if dispatch.run_id is not None:
            dispatches_by_run[str(dispatch.run_id)].append(dispatch)

    return [
        _serialize_attempt(
            run,
            task_id=str(task.project_task_id),
            project=project,
            tasks=tasks_by_run.get(str(run.run_id), []),
            run_steps=steps_by_run.get(str(run.run_id), []),
            external_dispatches=dispatches_by_run.get(str(run.run_id), []),
        )
        for run in runs
    ]


def build_run_node_read_models(
    session: Session,
    *,
    run: ProjectRun,
) -> list[ExecutionAttemptNodeReadModel]:
    node_rows = (
        _load_execution_records_for_run(session, run=run)
    )
    result: list[ExecutionAttemptNodeReadModel] = []
    if node_rows:
        for row in node_rows:
            payload = _as_record(row.node_payload)
            dependency_ids = _as_str_list(payload.get("dependency_node_ids"))
            if not dependency_ids:
                dependency_ids = _as_str_list(payload.get("dependency_step_ids"))
            if not dependency_ids:
                dependency_ids = _as_str_list(row.dependency_node_ids)
            result.append(
                ExecutionAttemptNodeReadModel(
                    id=str(row.node_id),
                    run_id=str(row.run_id),
                    task_id=str(row.project_task_id) if row.project_task_id else None,
                    name=row.name,
                    node_type=row.node_type,
                    status=_to_platform_status(row.status),
                    sequence_number=row.sequence_number,
                    execution_mode=_pick_first_str(payload, ("execution_mode",)),
                    executor_kind=_pick_first_str(payload, ("executor_kind",)),
                    runtime_type=_pick_first_str(payload, ("runtime_type",)),
                    suggested_agent_ids=_as_str_list(payload.get("suggested_agent_ids")),
                    dependency_step_ids=dependency_ids,
                    node_payload=payload,
                    result_payload=_as_record(row.result_payload),
                    error_message=row.error_message,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
    return result


def build_run_runtime_session_read_models(
    session: Session,
    *,
    run: ProjectRun,
) -> list[RuntimeSessionReadModel]:
    runtime_context = _as_record(run.runtime_context)
    sessions: list[RuntimeSessionReadModel] = []

    run_workspace = _as_record(runtime_context.get("run_workspace"))
    if run_workspace:
        sessions.append(
            RuntimeSessionReadModel(
                id=f"workspace:{run.run_id}",
                run_id=str(run.run_id),
                session_type="run_workspace",
                status=_to_platform_status(run.status),
                runtime_type=_pick_first_str(runtime_context, ("execution_mode", "runtime_type")),
                workspace_root=_pick_first_str(run_workspace, ("root_path",)),
                metadata=run_workspace,
                created_at=run.created_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
                updated_at=run.updated_at,
            )
        )

    dispatches = (
        session.query(ExternalAgentDispatch)
        .filter(ExternalAgentDispatch.run_id == run.run_id)
        .order_by(ExternalAgentDispatch.created_at.asc())
        .all()
    )
    for dispatch in dispatches:
        sessions.append(
            RuntimeSessionReadModel(
                id=str(dispatch.dispatch_id),
                run_id=str(run.run_id),
                node_id=str(dispatch.node_id) if dispatch.node_id else None,
                session_type="external_dispatch",
                status=_to_platform_status(dispatch.status),
                runtime_type=dispatch.runtime_type,
                agent_id=str(dispatch.agent_id),
                binding_id=str(dispatch.binding_id),
                workspace_root=_pick_first_str(
                    _as_record(dispatch.request_payload), ("run_workspace_root",)
                ),
                metadata={
                    "source_type": dispatch.source_type,
                    "source_id": dispatch.source_id,
                    "request_payload": dispatch.request_payload or {},
                    "result_payload": dispatch.result_payload or {},
                    "error_message": dispatch.error_message,
                },
                created_at=dispatch.created_at,
                started_at=dispatch.started_at,
                completed_at=dispatch.completed_at,
                updated_at=dispatch.updated_at,
            )
        )
    return sessions


def _activity_from_handoff(handoff: ProjectTaskHandoff) -> ProjectActivityItemResponse:
    return ProjectActivityItemResponse(
        id=f"handoff-{handoff.handoff_id}",
        title=handoff.title or f"Handoff {_humanize_token(handoff.stage)}",
        description=handoff.summary,
        timestamp=handoff.created_at,
        level="info",
        actor=handoff.from_actor,
        task_id=str(handoff.project_task_id),
    )


def _activity_from_change_bundle(
    bundle: ProjectTaskChangeBundle,
) -> ProjectActivityItemResponse:
    return ProjectActivityItemResponse(
        id=f"change-bundle-{bundle.change_bundle_id}",
        title=f"Change Bundle {_humanize_token(bundle.status)}",
        description=bundle.summary
        or f"{bundle.commit_count} commit(s), {len(bundle.changed_files or [])} changed file(s).",
        timestamp=bundle.created_at,
        level=_activity_level_from_status(bundle.status),
        task_id=str(bundle.project_task_id),
    )


def _activity_from_evidence_bundle(
    evidence: ProjectTaskEvidenceBundle,
) -> ProjectActivityItemResponse:
    return ProjectActivityItemResponse(
        id=f"evidence-bundle-{evidence.evidence_bundle_id}",
        title=f"Evidence {_humanize_token(evidence.status)}",
        description=evidence.summary,
        timestamp=evidence.created_at,
        level="info",
        task_id=str(evidence.project_task_id),
    )


def _activity_from_review_issue(
    issue: ProjectTaskReviewIssue,
) -> ProjectActivityItemResponse:
    return ProjectActivityItemResponse(
        id=f"review-issue-{issue.review_issue_id}",
        title=f"Issue {_humanize_token(issue.severity)}",
        description=issue.summary,
        timestamp=issue.created_at,
        level=(
            "success"
            if str(issue.status or "").strip().lower() == "resolved"
            else "warning"
        ),
        task_id=str(issue.project_task_id),
    )


def _build_task_detail(
    task: ProjectTask,
    *,
    project: Project,
    run_steps: Sequence[Any],
    agent_lookup: dict[str, Agent],
    latest_contract: Optional[ProjectTaskContract],
    dependency_snapshots: Sequence[dict[str, Any]],
    handoffs: Sequence[ProjectTaskHandoff],
    change_bundles: Sequence[ProjectTaskChangeBundle],
    evidence_bundles: Sequence[ProjectTaskEvidenceBundle],
    review_issues: Sequence[ProjectTaskReviewIssue],
    attempts: Sequence[ExecutionAttemptReadModel],
    readiness: Optional[dict[str, Any]] = None,
) -> ProjectTaskDetailReadModel:
    payloads = (_as_record(task.input_payload), _as_record(task.output_payload))
    metadata: list[ProjectTaskMetadataItemResponse] = []

    if task.plan_id:
        metadata.append(ProjectTaskMetadataItemResponse(label="Plan", value=str(task.plan_id)))
    if task.run_id:
        metadata.append(ProjectTaskMetadataItemResponse(label="Run", value=str(task.run_id)))

    review_status = _get_task_review_status_from_payload(payloads)
    if review_status:
        metadata.append(
            ProjectTaskMetadataItemResponse(
                label="Review",
                value=_humanize_token(review_status),
            )
        )

    assignment_source = _pick_first_str(_as_record(task.input_payload), ("assignment_source",))
    if assignment_source:
        metadata.append(
            ProjectTaskMetadataItemResponse(label="Assignment source", value=assignment_source)
        )

    agent = agent_lookup.get(str(task.assignee_agent_id)) if task.assignee_agent_id else None
    assigned_agent_name = agent.name if agent is not None else _get_task_assignee_name_from_payload(payloads)
    if assigned_agent_name:
        metadata.append(
            ProjectTaskMetadataItemResponse(label="Assigned Agent", value=assigned_agent_name)
        )

    executor_kind = _pick_first_str(
        _as_record(task.input_payload), ("executor_kind", "step_kind")
    )
    if executor_kind:
        metadata.append(
            ProjectTaskMetadataItemResponse(
                label="Executor Kind",
                value=_humanize_token(executor_kind),
            )
        )

    selection_reason = _pick_first_str(_as_record(task.input_payload), ("selection_reason",))
    if selection_reason:
        metadata.append(
            ProjectTaskMetadataItemResponse(label="Scheduler Decision", value=selection_reason)
        )

    runtime_type = _pick_first_str(_as_record(task.input_payload), ("runtime_type",))
    if runtime_type:
        metadata.append(
            ProjectTaskMetadataItemResponse(
                label="Runtime Type",
                value=_humanize_token(runtime_type),
            )
        )

    execution_node_name = _pick_first_str(
        _as_record(task.input_payload), ("execution_node_name",)
    )
    if execution_node_name:
        metadata.append(
            ProjectTaskMetadataItemResponse(label="Execution Node", value=execution_node_name)
        )

    execution_mode = _get_task_execution_mode_from_payload(payloads)
    if execution_mode:
        metadata.append(
            ProjectTaskMetadataItemResponse(
                label="Execution Mode",
                value=_humanize_token(execution_mode),
            )
        )

    run_workspace_root = _pick_first_str(
        _as_record(task.output_payload), ("run_workspace_root",)
    )
    if run_workspace_root:
        metadata.append(
            ProjectTaskMetadataItemResponse(label="Run Workspace", value=run_workspace_root)
        )

    planner_summary = _pick_first_str(_as_record(task.input_payload), ("planner_summary",))
    planner_source = _pick_first_str(_as_record(task.input_payload), ("planner_source",))
    step_total = _as_optional_int(_as_record(task.input_payload).get("step_count")) or len(run_steps)
    completed_step_count = sum(1 for step in run_steps if _is_completed_status(step.status))
    active_step_count = sum(1 for step in run_steps if step.status.lower() in _RUNNING_STEP_STATUSES)
    current_step = next(
        (
            step
            for step in sorted(run_steps, key=lambda item: item.sequence_number)
            if step.status.lower() not in {"completed", "failed", "cancelled", "blocked"}
        ),
        None,
    )
    parallel_group_count = len(
        {
            value
            for value in (
                _pick_first_str(_execution_record_payload(step), ("parallel_group",))
                for step in run_steps
            )
            if value
        }
    )
    clarification_questions = _get_planner_questions_from_payload((_as_record(task.input_payload),))
    events = sorted(
        [
            *[
                _activity_from_run_step(step)
                for step in run_steps
                if step.project_task_id == task.project_task_id
            ],
            *[_activity_from_handoff(item) for item in handoffs],
            *[_activity_from_change_bundle(item) for item in change_bundles],
            *[_activity_from_evidence_bundle(item) for item in evidence_bundles],
            *[_activity_from_review_issue(item) for item in review_issues],
        ],
        key=lambda item: item.timestamp,
        reverse=True,
    )
    if not events:
        events = [
            ProjectActivityItemResponse(
                id=f"task-{task.project_task_id}",
                title=task.title,
                description=(
                    task.error_message
                    or _summarize_record(_as_record(task.output_payload))
                    or f"{_humanize_token(task.status)} task update."
                ),
                timestamp=task.updated_at,
                level=_activity_level_from_status(task.status),
                task_id=str(task.project_task_id),
            )
        ]

    return ProjectTaskDetailReadModel(
        **_build_task_summary(task, agent_lookup=agent_lookup, readiness=readiness).model_dump(),
        project_id=str(project.project_id),
        project_title=project.name,
        project_status=_to_platform_status(project.status),
        description=task.description or task.title,
        execution_mode=execution_mode,
        planner_source=planner_source,
        planner_summary=planner_summary,
        step_total=step_total,
        completed_step_count=completed_step_count,
        active_step_count=active_step_count,
        parallel_group_count=parallel_group_count,
        current_step_title=current_step.name if current_step is not None else None,
        suggested_agent_ids=(
            _as_str_list(_execution_record_payload(current_step).get("suggested_agent_ids"))
            if current_step is not None
            else []
        ),
        clarification_questions=clarification_questions,
        acceptance_criteria=(
            _get_task_acceptance_from_payload(payloads)
            or (
                " / ".join(latest_contract.acceptance_criteria or [])
                if latest_contract is not None and latest_contract.acceptance_criteria
                else None
            )
        ),
        assigned_skill_names=_get_task_skill_names_from_payload(payloads),
        latest_result=task.error_message or _summarize_record(_as_record(task.output_payload)),
        contract=(
            TaskContractReadModel(
                id=str(latest_contract.contract_id),
                task_id=str(latest_contract.project_task_id),
                version=latest_contract.version,
                goal=latest_contract.goal,
                scope=list(latest_contract.scope or []),
                constraints=list(latest_contract.constraints or []),
                deliverables=list(latest_contract.deliverables or []),
                acceptance_criteria=list(latest_contract.acceptance_criteria or []),
                assumptions=list(latest_contract.assumptions or []),
                evidence_required=list(latest_contract.evidence_required or []),
                allowed_surface=_as_record(latest_contract.allowed_surface),
                created_at=latest_contract.created_at,
                updated_at=latest_contract.updated_at,
            )
            if latest_contract is not None
            else None
        ),
        dependencies=[
            TaskDependencyReadModel(
                id=item["id"],
                project_task_id=item["project_task_id"],
                depends_on_task_id=item["depends_on_task_id"],
                depends_on_task_title=item.get("depends_on_task_title"),
                depends_on_task_status=item.get("depends_on_task_status"),
                required_state=item["required_state"],
                dependency_type=item["dependency_type"],
                artifact_selector=_as_record(item.get("artifact_selector")),
                satisfied=bool(item["satisfied"]),
                created_at=item["created_at"],
                updated_at=item["updated_at"],
            )
            for item in dependency_snapshots
        ],
        handoffs=[_serialize_handoff(item) for item in handoffs],
        latest_change_bundle=(
            _serialize_change_bundle(change_bundles[0]) if change_bundles else None
        ),
        latest_evidence_bundle=(
            _serialize_evidence_bundle(evidence_bundles[0]) if evidence_bundles else None
        ),
        review_issues=[_serialize_review_issue(item) for item in review_issues],
        attempts=list(attempts),
        metadata=metadata,
        events=events,
    )


def _build_run_detail(
    session: Session,
    run: ProjectRun,
    *,
    project: Project,
    tasks: Sequence[ProjectTask],
    run_steps: Sequence[Any],
    external_dispatches: Sequence[ExternalAgentDispatch],
    plans: Sequence[ProjectPlan],
    project_space: Optional[ProjectSpace],
) -> RunDetailReadModel:
    summary = _build_run_summary(run, project=project, tasks=tasks, run_steps=run_steps)
    timeline = [
        ProjectActivityItemResponse(
            id=f"run-{run.run_id}-created",
            title="Run created",
            description=f"Triggered via {run.trigger_source}.",
            timestamp=run.created_at,
            level="info",
        ),
        *(
            [
                ProjectActivityItemResponse(
                    id=f"run-{run.run_id}-started",
                    title="Run started",
                    description="Execution is in progress.",
                    timestamp=run.started_at,
                    level="info",
                )
            ]
            if run.started_at
            else []
        ),
        *[_activity_from_run_step(step) for step in run_steps],
        *(
            [
                ProjectActivityItemResponse(
                    id=f"run-{run.run_id}-status",
                    title=f"Run {_humanize_token(run.status)}",
                    description=summary.failure_reason
                    or _summarize_record(_as_record(run.runtime_context))
                    or "Run completed.",
                    timestamp=run.completed_at or run.updated_at,
                    level=_activity_level_from_status(run.status),
                )
            ]
            if run.completed_at or _is_terminal_run_status(run.status) or summary.failure_reason
            else []
        ),
    ]
    timeline.sort(key=lambda item: item.timestamp)

    project_summary = _build_project_summary(
        project,
        tasks=tasks,
        runs=[run],
        plans=plans,
        active_node_count=len(
            {
                str(task.assignee_agent_id)
                for task in tasks
                if task.assignee_agent_id and not _is_completed_status(task.status)
                and not _is_failed_status(task.status)
            }
        ),
    )
    deliverables = _collect_deliverables_from_payloads(
        [
            _as_record(project.configuration),
            *(_as_record(plan.definition) for plan in plans),
            _as_record(project_space.space_metadata) if project_space is not None else {},
            _as_record(run.runtime_context),
            *(_as_record(task.output_payload) for task in tasks),
            *(_execution_record_result(step) for step in run_steps),
        ]
    )
    runtime_context = _as_record(run.runtime_context)
    assignment_candidate = runtime_context.get("agent_assignment") or runtime_context.get(
        "executor_assignment"
    )
    assignment = _as_record(assignment_candidate)
    run_workspace = _as_record(runtime_context.get("run_workspace"))

    return RunDetailReadModel(
        **summary.model_dump(),
        project_summary=project_summary.summary,
        timeline=timeline,
        deliverables=deliverables,
        run_workspace_root=_pick_first_str(run_workspace, ("root_path",)),
        executor_assignment=(
            RunExecutorAssignmentReadModel(
                executor_kind=_pick_first_str(assignment, ("executor_kind",)),
                agent_id=_pick_first_str(assignment, ("agent_id",)),
                node_id=_pick_first_str(assignment, ("node_id",)),
                selection_reason=_pick_first_str(assignment, ("selection_reason",)),
                provisioned_agent=_as_optional_bool(assignment.get("provisioned_agent")) or False,
                runtime_type=_pick_first_str(assignment, ("runtime_type",)),
            )
            if assignment
            else None
        ),
        external_dispatches=[
            ExternalAgentDispatchReadModel(
                id=str(dispatch.dispatch_id),
                agent_id=str(dispatch.agent_id),
                binding_id=str(dispatch.binding_id),
                project_id=str(dispatch.project_id) if dispatch.project_id else "",
                run_id=str(dispatch.run_id) if dispatch.run_id else "",
                node_id=str(dispatch.node_id) if dispatch.node_id else "",
                source_type=dispatch.source_type,
                source_id=dispatch.source_id,
                runtime_type=dispatch.runtime_type,
                status=_to_platform_status(dispatch.status),
                error_message=dispatch.error_message,
                request_payload=_as_record(dispatch.request_payload),
                result_payload=_as_record(dispatch.result_payload),
                acked_at=dispatch.acked_at,
                started_at=dispatch.started_at,
                completed_at=dispatch.completed_at,
                expires_at=dispatch.expires_at,
                created_at=dispatch.created_at,
                updated_at=dispatch.updated_at,
            )
            for dispatch in external_dispatches
        ],
        nodes=build_run_node_read_models(session, run=run),
        runtime_sessions=build_run_runtime_session_read_models(session, run=run),
    )


def _build_project_agent_summaries(
    *,
    bindings: Sequence[ProjectAgentBinding],
    tasks: Sequence[ProjectTask],
    agent_lookup: dict[str, Agent],
) -> list[ProjectAgentSummaryReadModel]:
    assigned_at_by_agent: dict[str, datetime] = {}
    for task in tasks:
        if task.assignee_agent_id:
            agent_key = str(task.assignee_agent_id)
            current = assigned_at_by_agent.get(agent_key)
            assigned_at_by_agent[agent_key] = (
                min(current, task.updated_at) if current is not None else task.updated_at
            )

    seen_agent_ids: set[str] = set()
    summaries: list[ProjectAgentSummaryReadModel] = []
    for binding in bindings:
        agent_key = str(binding.agent_id)
        agent = agent_lookup.get(agent_key)
        if agent is None or agent_key in seen_agent_ids:
            continue
        seen_agent_ids.add(agent_key)
        summaries.append(
            ProjectAgentSummaryReadModel(
                id=agent_key,
                name=agent.name,
                role=binding.role_hint or agent.agent_type,
                status=_to_platform_status(agent.status),
                is_temporary=bool(agent.is_ephemeral),
                avatar=agent.avatar,
                assigned_at=assigned_at_by_agent.get(agent_key),
            )
        )
    return summaries


def build_project_detail_read_model(
    session: Session,
    *,
    project: Project,
) -> ProjectDetailReadModel:
    tasks = (
        session.query(ProjectTask)
        .filter(ProjectTask.project_id == project.project_id)
        .order_by(ProjectTask.sort_order.asc(), ProjectTask.created_at.asc())
        .all()
    )
    runs = (
        session.query(ProjectRun)
        .filter(ProjectRun.project_id == project.project_id)
        .order_by(ProjectRun.created_at.desc())
        .all()
    )
    for run in runs:
        reconcile_run_state(session, run=run)
    reconcile_project_state(session, project=project)

    plans = (
        session.query(ProjectPlan)
        .filter(ProjectPlan.project_id == project.project_id)
        .order_by(ProjectPlan.updated_at.desc())
        .all()
    )
    project_space = (
        session.query(ProjectSpace)
        .filter(ProjectSpace.project_id == project.project_id)
        .first()
    )
    extensions = (
        session.query(ProjectExtensionPackage)
        .filter(ProjectExtensionPackage.project_id == project.project_id)
        .all()
    )
    bindings = (
        session.query(ProjectAgentBinding)
        .filter(ProjectAgentBinding.project_id == project.project_id)
        .order_by(ProjectAgentBinding.priority.desc(), ProjectAgentBinding.created_at.asc())
        .all()
    )
    provisioning_profiles = (
        session.query(AgentProvisioningProfile)
        .filter(AgentProvisioningProfile.project_id == project.project_id)
        .order_by(AgentProvisioningProfile.step_kind.asc())
        .all()
    )

    run_ids = [run.run_id for run in runs]
    run_steps = [
        step
        for run in runs
        for step in _load_execution_records_for_run(session, run=run)
    ] if run_ids else []

    agent_db_ids = {
        agent_id
        for agent_id in (
            [*(binding.agent_id for binding in bindings), *(task.assignee_agent_id for task in tasks)]
        )
        if agent_id is not None
    }
    agents = (
        session.query(Agent).filter(Agent.agent_id.in_(agent_db_ids)).all()
        if agent_db_ids
        else []
    )
    agent_lookup = {str(agent.agent_id): agent for agent in agents}
    readiness_by_task_id = {
        str(task.project_task_id): compute_task_readiness(
            session, project_task_id=task.project_task_id
        )
        for task in tasks
    }
    review_issues = (
        session.query(ProjectTaskReviewIssue)
        .filter(ProjectTaskReviewIssue.project_task_id.in_([task.project_task_id for task in tasks]))
        .all()
        if tasks
        else []
    )
    open_issue_count_by_task_id: dict[str, int] = defaultdict(int)
    for issue in review_issues:
        if str(issue.status or "").strip().lower() not in {"resolved", "wont_fix"}:
            open_issue_count_by_task_id[str(issue.project_task_id)] += 1

    change_bundles = (
        session.query(ProjectTaskChangeBundle)
        .filter(ProjectTaskChangeBundle.project_task_id.in_([task.project_task_id for task in tasks]))
        .order_by(ProjectTaskChangeBundle.created_at.desc())
        .all()
        if tasks
        else []
    )
    latest_change_bundle_status_by_task_id: dict[str, str] = {}
    for bundle in change_bundles:
        latest_change_bundle_status_by_task_id.setdefault(str(bundle.project_task_id), bundle.status)

    tasks_by_run: dict[str, list[ProjectTask]] = defaultdict(list)
    for task in tasks:
        if task.run_id:
            tasks_by_run[str(task.run_id)].append(task)

    steps_by_run: dict[str, list[Any]] = defaultdict(list)
    for step in run_steps:
        steps_by_run[str(step.run_id)].append(step)

    active_node_count = len(
        {
            str(task.assignee_agent_id)
            for task in tasks
            if task.assignee_agent_id
            and not _is_completed_status(task.status)
            and not _is_failed_status(task.status)
        }
    )
    summary = _build_project_summary(
        project,
        tasks=tasks,
        runs=runs,
        plans=plans,
        active_node_count=active_node_count,
    )
    latest_plan = max(plans, key=lambda item: item.updated_at, default=None)
    latest_plan_definition = _as_record(latest_plan.definition) if latest_plan else {}
    configuration = _as_record(project.configuration)

    return ProjectDetailReadModel(
        **summary.model_dump(),
        instructions=(
            _pick_first_str(configuration, ("instructions", "brief", "goal", "summary"))
            or (latest_plan.goal if latest_plan else None)
            or _pick_first_str(latest_plan_definition, ("instructions", "summary", "goal"))
            or project.description
            or "No instructions available yet."
        ),
        department_id=_pick_first_str(configuration, ("department_id", "departmentId")),
        workspace_bucket=(
            project_space.storage_uri
            if project_space is not None and project_space.storage_uri
            else project_space.root_path if project_space is not None else None
        )
        or _pick_first_str(configuration, ("workspace_bucket", "workspaceBucket")),
        project_workspace_root=project_space.root_path if project_space is not None else None,
        configuration=configuration,
        tasks=sorted(
            (
                _build_task_summary(
                    task,
                    agent_lookup=agent_lookup,
                    readiness=readiness_by_task_id.get(str(task.project_task_id)),
                    open_issue_count=open_issue_count_by_task_id.get(str(task.project_task_id), 0),
                    latest_change_bundle_status=latest_change_bundle_status_by_task_id.get(str(task.project_task_id)),
                )
                for task in tasks
            ),
            key=lambda item: (-item.priority, item.updated_at),
        ),
        runs=sorted(
            (
                _build_run_summary(
                    run,
                    project=project,
                    tasks=tasks_by_run.get(str(run.run_id), []),
                    run_steps=steps_by_run.get(str(run.run_id), []),
                )
                for run in runs
            ),
            key=lambda item: item.updated_at,
            reverse=True,
        ),
        agents=_build_project_agent_summaries(
            bindings=bindings,
            tasks=tasks,
            agent_lookup=agent_lookup,
        ),
        agent_bindings=[
            ProjectAgentBindingReadModel(
                id=str(binding.binding_id),
                project_id=str(binding.project_id),
                agent_id=str(binding.agent_id),
                agent_name=agent_lookup.get(str(binding.agent_id)).name
                if agent_lookup.get(str(binding.agent_id))
                else str(binding.agent_id),
                agent_type=agent_lookup.get(str(binding.agent_id)).agent_type
                if agent_lookup.get(str(binding.agent_id))
                else None,
                role_hint=binding.role_hint,
                priority=binding.priority,
                status=_to_platform_status(binding.status),
                allowed_step_kinds=list(binding.allowed_step_kinds or []),
                preferred_skills=list(binding.preferred_skills or []),
                preferred_runtime_types=list(binding.preferred_runtime_types or []),
                created_at=binding.created_at,
                updated_at=binding.updated_at,
            )
            for binding in bindings
        ],
        provisioning_profiles=[
            AgentProvisioningProfileReadModel(
                id=str(profile.profile_id),
                project_id=str(profile.project_id),
                step_kind=profile.step_kind,
                agent_type=profile.agent_type,
                template_id=profile.template_id,
                default_skill_ids=list(profile.default_skill_ids or []),
                default_provider=profile.default_provider,
                default_model=profile.default_model,
                runtime_type=profile.runtime_type,
                sandbox_mode=profile.sandbox_mode,
                ephemeral=profile.ephemeral,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
            for profile in provisioning_profiles
        ],
        deliverables=_collect_deliverables_from_payloads(
            [
                configuration,
                *(_as_record(plan.definition) for plan in plans),
                _as_record(project_space.space_metadata) if project_space is not None else {},
                *(_as_record(task.output_payload) for task in tasks),
                *(_as_record(run.runtime_context) for run in runs),
                *(_execution_record_result(step) for step in run_steps),
                *(_as_record(extension.manifest) for extension in extensions),
            ]
        ),
        recent_activity=_build_project_activity(
            project,
            tasks=tasks,
            plans=plans,
            extensions=extensions,
            project_space=project_space,
            agent_lookup=agent_lookup,
        ),
    )


def build_project_task_detail_read_model(
    session: Session,
    *,
    task: ProjectTask,
) -> ProjectTaskDetailReadModel:
    project = session.query(Project).filter(Project.project_id == task.project_id).first()
    if project is None:
        raise ValueError("Project not found for task")

    run_steps = []
    if task.run_id:
        run = session.query(ProjectRun).filter(ProjectRun.run_id == task.run_id).first()
        if run is not None:
            run_steps = _load_execution_records_for_run(session, run=run)
    agent_db_ids = {task.assignee_agent_id} if task.assignee_agent_id else set()
    agents = (
        session.query(Agent).filter(Agent.agent_id.in_(agent_db_ids)).all()
        if agent_db_ids
        else []
    )
    agent_lookup = {str(agent.agent_id): agent for agent in agents}
    latest_contract = (
        session.query(ProjectTaskContract)
        .filter(ProjectTaskContract.project_task_id == task.project_task_id)
        .order_by(ProjectTaskContract.version.desc(), ProjectTaskContract.created_at.desc())
        .first()
    )
    handoffs = (
        session.query(ProjectTaskHandoff)
        .filter(ProjectTaskHandoff.project_task_id == task.project_task_id)
        .order_by(ProjectTaskHandoff.created_at.desc())
        .all()
    )
    change_bundles = (
        session.query(ProjectTaskChangeBundle)
        .filter(ProjectTaskChangeBundle.project_task_id == task.project_task_id)
        .order_by(ProjectTaskChangeBundle.created_at.desc())
        .all()
    )
    evidence_bundles = (
        session.query(ProjectTaskEvidenceBundle)
        .filter(ProjectTaskEvidenceBundle.project_task_id == task.project_task_id)
        .order_by(ProjectTaskEvidenceBundle.created_at.desc())
        .all()
    )
    review_issues = (
        session.query(ProjectTaskReviewIssue)
        .filter(ProjectTaskReviewIssue.project_task_id == task.project_task_id)
        .order_by(ProjectTaskReviewIssue.created_at.desc())
        .all()
    )
    readiness = compute_task_readiness(session, project_task_id=task.project_task_id)
    attempts = build_task_attempt_read_models(session, task=task, project=project)
    return _build_task_detail(
        task,
        project=project,
        run_steps=run_steps,
        agent_lookup=agent_lookup,
        latest_contract=latest_contract,
        dependency_snapshots=readiness["dependencies"],
        handoffs=handoffs,
        change_bundles=change_bundles,
        evidence_bundles=evidence_bundles,
        review_issues=review_issues,
        attempts=attempts,
        readiness=readiness,
    )


def build_run_detail_read_model(
    session: Session,
    *,
    run: ProjectRun,
) -> RunDetailReadModel:
    project = session.query(Project).filter(Project.project_id == run.project_id).first()
    if project is None:
        raise ValueError("Project not found for run")

    reconcile_run_state(session, run=run)
    tasks = (
        session.query(ProjectTask)
        .filter(ProjectTask.run_id == run.run_id)
        .order_by(ProjectTask.updated_at.desc())
        .all()
    )
    run_steps = _load_execution_records_for_run(session, run=run)
    plans = (
        session.query(ProjectPlan)
        .filter(ProjectPlan.plan_id == run.plan_id)
        .all()
        if run.plan_id
        else []
    )
    project_space = (
        session.query(ProjectSpace)
        .filter(ProjectSpace.project_id == run.project_id)
        .first()
    )
    external_dispatches = (
        session.query(ExternalAgentDispatch)
        .filter(ExternalAgentDispatch.run_id == run.run_id)
        .order_by(ExternalAgentDispatch.created_at.asc())
        .all()
    )
    return _build_run_detail(
        session,
        run,
        project=project,
        tasks=tasks,
        run_steps=run_steps,
        external_dispatches=external_dispatches,
        plans=plans,
        project_space=project_space,
    )
