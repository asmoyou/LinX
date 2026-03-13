"""Service layer for skill proposals and learned experiences."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.config import get_config
from skill_learning.repository import SkillProposalRepository, get_skill_proposal_repository
from skill_library.skill_registry import SkillInfo, SkillRegistry, get_skill_registry
from user_memory.materialized_view_retrieval import get_materialized_view_retrieval_service


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_skill_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "learned_skill"


class SkillProposalService:
    """Encapsulate skill-proposal read/review/publish flows."""

    def __init__(
        self,
        repository: Optional[SkillProposalRepository] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        self._repository = repository or get_skill_proposal_repository()
        self._skill_registry = skill_registry or get_skill_registry()

    def list_proposals(
        self,
        *,
        agent_ids: List[str],
        review_status: str,
        limit: int,
    ) -> List[Any]:
        return self._repository.list_proposals(
            agent_ids=agent_ids,
            review_status=review_status,
            limit=limit,
        )

    def get_proposal(self, proposal_id: int) -> Optional[Any]:
        return self._repository.get_proposal(proposal_id)

    @staticmethod
    def _build_skill_name(existing: Any) -> str:
        parts = [
            "learned",
            _sanitize_skill_name(str(getattr(existing, "agent_id", "") or "agent")),
            _sanitize_skill_name(str(getattr(existing, "proposal_key", "") or getattr(existing, "title", "skill"))),
        ]
        return "_".join(part for part in parts if part)[:255]

    @staticmethod
    def _build_skill_description(existing: Any, payload: Dict[str, Any]) -> str:
        goal = str(payload.get("goal") or getattr(existing, "goal", None) or getattr(existing, "title", "")).strip()
        why = str(payload.get("why_it_worked") or getattr(existing, "why_it_worked", None) or "").strip()
        if why:
            return f"{goal}: {why}"[:500]
        return goal[:500] if goal else "Learned execution skill"

    @staticmethod
    def _build_skill_md_content(existing: Any, payload: Dict[str, Any]) -> str:
        title = str(getattr(existing, "title", "") or payload.get("goal") or "Learned Skill").strip()
        steps = [str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()]
        why = str(payload.get("why_it_worked") or getattr(existing, "why_it_worked", None) or "").strip()
        applicability = str(payload.get("applicability") or getattr(existing, "applicability", None) or "").strip()
        avoid = str(payload.get("avoid") or getattr(existing, "avoid", None) or "").strip()

        lines = [f"# {title}", "", "## Goal", title, "", "## Successful Path"]
        if steps:
            lines.extend(f"- {step}" for step in steps)
        else:
            lines.append("- Follow the proven path recorded in this learned skill.")
        if why:
            lines.extend(["", "## Why It Worked", why])
        if applicability:
            lines.extend(["", "## Applicability", applicability])
        if avoid:
            lines.extend(["", "## Avoid", avoid])
        return "\n".join(lines)

    @staticmethod
    def _build_skill_interface(existing: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        goal = str(payload.get("goal") or getattr(existing, "goal", None) or getattr(existing, "title", "")).strip()
        return {
            "inputs": {
                "goal": "string",
                "task_context": "string",
                "constraints": "string",
            },
            "outputs": {
                "successful_path": "string",
                "applicability": "string",
                "avoid": "string",
            },
            "required_inputs": ["goal"],
            "default_goal": goal,
        }

    def _publish_to_skill_registry(
        self,
        *,
        existing: Any,
        reviewer_user_id: str,
        payload: Dict[str, Any],
    ) -> SkillInfo:
        registry = self._skill_registry
        publish_policy = get_config().get("skill_learning.publish_policy", {}) or {}
        reuse_existing_by_name = bool(publish_policy.get("reuse_existing_by_name", True))
        skill_type = str(publish_policy.get("skill_type") or "agent_skill").strip() or "agent_skill"
        storage_type = str(publish_policy.get("storage_type") or "inline").strip() or "inline"
        if getattr(existing, "published_skill_id", None):
            skill = registry.get_skill(getattr(existing, "published_skill_id"))
            if skill is not None:
                return skill

        skill_name = self._build_skill_name(existing)
        if reuse_existing_by_name:
            existing_skill = registry.get_skill_by_name(skill_name)
            if existing_skill is not None:
                return existing_skill

        return registry.register_skill(
            name=skill_name,
            description=self._build_skill_description(existing, payload),
            interface_definition=self._build_skill_interface(existing, payload),
            dependencies=[],
            version="1.0.0",
            skill_type=skill_type,
            storage_type=storage_type,
            code=None,
            config={
                "source": "skill_proposal",
                "proposal_id": int(getattr(existing, "id", 0) or 0),
                "agent_id": str(getattr(existing, "agent_id", "") or ""),
                "proposal_key": str(getattr(existing, "proposal_key", "") or ""),
            },
            skill_md_content=self._build_skill_md_content(existing, payload),
            skill_metadata={
                "source": "skill_proposal",
                "proposal_id": int(getattr(existing, "id", 0) or 0),
                "agent_id": str(getattr(existing, "agent_id", "") or ""),
                "proposal_key": str(getattr(existing, "proposal_key", "") or ""),
                "reviewed_at": _utc_now_iso(),
            },
            created_by=str(reviewer_user_id),
            validate=True,
        )

    def review_proposal(
        self,
        *,
        proposal_id: int,
        action: str,
        reviewer_user_id: str,
        summary: Optional[str],
        details: Optional[str],
        payload_updates: Dict[str, Any],
    ) -> Optional[Any]:
        existing = self._repository.get_proposal(proposal_id)
        if existing is None:
            return None

        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"publish", "reject", "revise"}:
            raise ValueError(f"Unsupported skill proposal action: {action}")

        payload = (
            dict(existing.materialized_data or {})
            if isinstance(existing.materialized_data, dict)
            else {}
        )
        payload.update(payload_updates)

        published_skill_id: Optional[str] = None
        review_status_value = {
            "publish": "published",
            "reject": "rejected",
            "revise": "pending",
        }[normalized_action]
        if normalized_action == "publish":
            skill = self._publish_to_skill_registry(
                existing=existing,
                reviewer_user_id=str(reviewer_user_id),
                payload=payload,
            )
            published_skill_id = str(skill.skill_id)
            payload["published_skill_id"] = published_skill_id
            payload["published_skill_name"] = skill.name

        payload.update(
            {
                "review_status": review_status_value,
                "reviewed_by": str(reviewer_user_id),
                "reviewed_at": _utc_now_iso(),
            }
        )

        updated = self._repository.update_proposal(
            proposal_id=int(getattr(existing, "id", proposal_id)),
            title=str(getattr(existing, "title", "") or payload.get("goal") or "") or None,
            summary=summary if summary is not None else str(payload.get("why_it_worked") or "") or None,
            details=details if details is not None else str(payload.get("review_content") or "") or None,
            review_status=review_status_value,
            review_note=str(payload.get("review_note") or "") or None,
            payload=payload,
            published_skill_id=published_skill_id,
        )
        return updated

    def publish_proposal(
        self,
        *,
        proposal_id: int,
        reviewer_user_id: str,
        summary: Optional[str],
        details: Optional[str],
        payload_updates: Dict[str, Any],
    ) -> Optional[Any]:
        return self.review_proposal(
            proposal_id=proposal_id,
            action="publish",
            reviewer_user_id=reviewer_user_id,
            summary=summary,
            details=details,
            payload_updates=payload_updates,
        )

    def list_published_experiences(
        self,
        *,
        agent_id: str,
        query_text: str,
        limit: int,
        min_score: Optional[float] = None,
    ) -> List[Any]:
        items = get_materialized_view_retrieval_service().retrieve_agent_experience(
            agent_id=str(agent_id),
            query_text=query_text,
            top_k=limit,
        )
        if min_score is None:
            return items
        return [item for item in items if float(item.similarity_score or 0.0) >= float(min_score)]


_skill_proposal_service: Optional[SkillProposalService] = None


def get_skill_proposal_service() -> SkillProposalService:
    """Return the shared skill-proposal service."""

    global _skill_proposal_service
    if _skill_proposal_service is None:
        _skill_proposal_service = SkillProposalService()
    return _skill_proposal_service
