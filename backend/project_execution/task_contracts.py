from __future__ import annotations

import hashlib
import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.project_execution_models import ProjectTask, ProjectTaskContract

_SECTION_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+\.))\s+(?:\[[ xX]\]\s*)?")
_SECTION_ALIASES = {
    "goal": ("任务目标", "目标", "objective", "goal"),
    "scope": ("实施范围", "实现范围", "范围", "scope"),
    "constraints": ("关键约束", "约束", "constraints"),
    "deliverables": ("交付物", "deliverables"),
    "acceptance_criteria": ("验收标准", "acceptance criteria", "acceptance"),
    "assumptions": ("假设", "待确认", "assumptions"),
    "evidence_required": ("证据要求", "evidence required", "evidence"),
    "allowed_surface": ("允许交付面", "allowed surface"),
}
_CONCRETE_PATH_RE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+|[A-Za-z0-9_.-]+\.(?:py|js|ts|tsx|jsx|sh|md|html|css|json|yaml|yml)"
)


def _clip_text(text: str, limit: int = 240) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(limit - 1, 1)].rstrip()}…"


def _normalize_section_name(raw: str) -> str:
    candidate = re.sub(r"[\s:：_-]+", "", str(raw or "").strip().lower())
    for key, aliases in _SECTION_ALIASES.items():
        for alias in aliases:
            alias_normalized = re.sub(r"[\s:：_-]+", "", alias.strip().lower())
            if candidate == alias_normalized:
                return key
    return ""


def _parse_sections(description: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key = ""
    buffer: list[str] = []
    for raw_line in str(description or "").splitlines():
        match = _SECTION_HEADING_RE.match(raw_line)
        if match:
            if current_key:
                body = "\n".join(buffer).strip()
                if body:
                    previous = sections.get(current_key)
                    sections[current_key] = f"{previous}\n{body}".strip() if previous else body
            current_key = _normalize_section_name(match.group(1))
            buffer = []
            continue
        if current_key:
            buffer.append(raw_line)

    if current_key:
        body = "\n".join(buffer).strip()
        if body:
            previous = sections.get(current_key)
            sections[current_key] = f"{previous}\n{body}".strip() if previous else body
    return sections


def _section_items(body: str, *, max_items: int = 12, item_limit: int = 240) -> list[str]:
    items: list[str] = []
    current = ""
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        is_item = bool(_LIST_PREFIX_RE.match(stripped))
        content = _LIST_PREFIX_RE.sub("", stripped).strip() if is_item else stripped
        if not content:
            continue
        if is_item:
            if current:
                items.append(_clip_text(current, item_limit))
                if len(items) >= max_items:
                    return items
            current = content
        elif current:
            current = f"{current} {content}".strip()
        else:
            current = content
    if current and len(items) < max_items:
        items.append(_clip_text(current, item_limit))
    return items


def _looks_like_concrete_surface_path(value: str) -> bool:
    normalized = str(value or "").strip().lstrip("./")
    if not normalized or any(char.isspace() for char in normalized):
        return False
    if normalized.endswith("/"):
        return False
    basename = normalized.rsplit("/", 1)[-1]
    if "." in basename:
        return True
    return normalized.count("/") >= 1


def _normalize_allowed_surface(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        raw = {}

    roots = []
    files = []
    for item in raw.get("roots") or []:
        if isinstance(item, str) and item.strip():
            roots.append(item.strip())
    for item in raw.get("files") or []:
        if isinstance(item, str) and item.strip():
            files.append(item.strip())
    return {
        "roots": sorted(set(roots)),
        "files": sorted(set(files)),
    }


def _infer_allowed_surface(deliverables: list[str]) -> dict[str, list[str]]:
    files = [
        item.strip().lstrip("./")
        for item in deliverables
        if _looks_like_concrete_surface_path(item)
    ]
    roots = sorted({item.split("/", 1)[0] for item in files if "/" in item})
    return {
        "roots": roots,
        "files": sorted(set(files)),
    }


def _extract_goal(description: str, sections: dict[str, str]) -> Optional[str]:
    goal_items = _section_items(sections.get("goal", ""), max_items=1)
    if goal_items:
        return goal_items[0]

    for raw_line in str(description or "").splitlines():
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#"):
            return _clip_text(_LIST_PREFIX_RE.sub("", stripped).strip(), 240)
    return None


def compile_contract_payload(
    *,
    title: str,
    description: Optional[str],
) -> dict[str, Any]:
    normalized_description = str(description or "").strip()
    sections = _parse_sections(normalized_description)

    deliverables = _section_items(sections.get("deliverables", ""))
    allowed_surface = _normalize_allowed_surface(
        _infer_allowed_surface(deliverables)
        if not sections.get("allowed_surface")
        else {
            "files": _section_items(sections.get("allowed_surface", ""), max_items=20),
            "roots": [],
        }
    )

    goal = _extract_goal(normalized_description, sections) or title.strip()
    return {
        "goal": goal,
        "scope": _section_items(sections.get("scope", "")),
        "constraints": _section_items(sections.get("constraints", "")),
        "deliverables": deliverables,
        "acceptance_criteria": _section_items(sections.get("acceptance_criteria", "")),
        "assumptions": _section_items(sections.get("assumptions", "")),
        "evidence_required": _section_items(sections.get("evidence_required", "")),
        "allowed_surface": allowed_surface,
        "source_description_hash": hashlib.sha256(
            normalized_description.encode("utf-8")
        ).hexdigest()
        if normalized_description
        else None,
    }


def get_latest_task_contract(
    session: Session,
    *,
    project_task_id: UUID,
) -> Optional[ProjectTaskContract]:
    return (
        session.query(ProjectTaskContract)
        .filter(ProjectTaskContract.project_task_id == project_task_id)
        .order_by(ProjectTaskContract.version.desc(), ProjectTaskContract.created_at.desc())
        .first()
    )


def ensure_task_contract(
    session: Session,
    *,
    task: ProjectTask,
    actor_user_id: Optional[UUID],
) -> ProjectTaskContract:
    compiled = compile_contract_payload(title=task.title, description=task.description)
    latest = get_latest_task_contract(session, project_task_id=task.project_task_id)
    if latest and latest.source_description_hash == compiled["source_description_hash"]:
        return latest

    next_version = (latest.version + 1) if latest is not None else 1
    contract = ProjectTaskContract(
        project_task_id=task.project_task_id,
        version=next_version,
        goal=compiled["goal"],
        scope=compiled["scope"],
        constraints=compiled["constraints"],
        deliverables=compiled["deliverables"],
        acceptance_criteria=compiled["acceptance_criteria"],
        assumptions=compiled["assumptions"],
        evidence_required=compiled["evidence_required"],
        allowed_surface=compiled["allowed_surface"],
        source_description_hash=compiled["source_description_hash"],
        created_by_user_id=actor_user_id,
    )
    session.add(contract)
    session.flush()
    return contract


def create_manual_task_contract(
    session: Session,
    *,
    task: ProjectTask,
    actor_user_id: Optional[UUID],
    payload: dict[str, Any],
) -> ProjectTaskContract:
    latest = get_latest_task_contract(session, project_task_id=task.project_task_id)
    next_version = (latest.version + 1) if latest is not None else 1
    contract = ProjectTaskContract(
        project_task_id=task.project_task_id,
        version=next_version,
        goal=str(payload.get("goal") or "").strip() or task.title,
        scope=[str(item).strip() for item in (payload.get("scope") or []) if str(item).strip()],
        constraints=[
            str(item).strip() for item in (payload.get("constraints") or []) if str(item).strip()
        ],
        deliverables=[
            str(item).strip() for item in (payload.get("deliverables") or []) if str(item).strip()
        ],
        acceptance_criteria=[
            str(item).strip()
            for item in (payload.get("acceptance_criteria") or payload.get("acceptanceCriteria") or [])
            if str(item).strip()
        ],
        assumptions=[
            str(item).strip() for item in (payload.get("assumptions") or []) if str(item).strip()
        ],
        evidence_required=[
            str(item).strip()
            for item in (payload.get("evidence_required") or payload.get("evidenceRequired") or [])
            if str(item).strip()
        ],
        allowed_surface=_normalize_allowed_surface(
            payload.get("allowed_surface") or payload.get("allowedSurface") or {}
        ),
        source_description_hash=hashlib.sha256(
            str(task.description or "").encode("utf-8")
        ).hexdigest()
        if task.description
        else None,
        created_by_user_id=actor_user_id,
    )
    session.add(contract)
    session.flush()
    return contract
