"""Service layer for skill proposals and published learned skills."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from object_storage.minio_client import get_minio_client
from shared.config import get_config
from skill_learning.repository import SkillProposalRepository, get_skill_proposal_repository
from skill_library.skill_registry import SkillInfo, SkillRegistry, get_skill_registry
from user_memory.items import RetrievedMemoryItem

_STOP_TERMS = {
    "how",
    "what",
    "when",
    "where",
    "why",
    "with",
    "from",
    "this",
    "that",
    "into",
    "about",
    "请问",
    "怎么",
    "如何",
    "一下",
    "这个",
    "那个",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_skill_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "learned_skill"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _extract_query_terms(query_text: str, *, max_terms: int = 12) -> List[str]:
    normalized = _normalize_text(query_text)
    if not normalized or normalized == "*":
        return []

    terms = set()
    for token in re.findall(r"[a-z0-9][a-z0-9._-]{1,}", normalized):
        if token not in _STOP_TERMS:
            terms.add(token)

    split_terms = re.split(r"[\s,，。！？!?;；:：/\\|()\[\]{}【】\"'“”‘’]+", normalized)
    for token in split_terms:
        token = token.strip()
        if len(token) >= 2 and token not in _STOP_TERMS:
            terms.add(token)

    for fragment in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized):
        if len(fragment) >= 2 and fragment not in _STOP_TERMS:
            terms.add(fragment)

    return sorted(terms, key=lambda item: (-len(item), item))[: max(int(max_terms), 1)]


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
            _sanitize_skill_name(
                str(getattr(existing, "proposal_key", "") or getattr(existing, "title", "skill"))
            ),
        ]
        return "_".join(part for part in parts if part)[:255]

    @staticmethod
    def _build_skill_description(existing: Any, payload: Dict[str, Any]) -> str:
        goal = str(
            payload.get("goal") or getattr(existing, "goal", None) or getattr(existing, "title", "")
        ).strip()
        why = str(
            payload.get("why_it_worked") or getattr(existing, "why_it_worked", None) or ""
        ).strip()
        if why:
            return f"{goal}: {why}"[:500]
        return goal[:500] if goal else "Learned execution skill"

    @staticmethod
    def _build_skill_md_content(existing: Any, payload: Dict[str, Any]) -> str:
        title = str(
            getattr(existing, "title", "") or payload.get("goal") or "Learned Skill"
        ).strip()
        steps = [
            str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()
        ]
        why = str(
            payload.get("why_it_worked") or getattr(existing, "why_it_worked", None) or ""
        ).strip()
        applicability = str(
            payload.get("applicability") or getattr(existing, "applicability", None) or ""
        ).strip()
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
        goal = str(
            payload.get("goal") or getattr(existing, "goal", None) or getattr(existing, "title", "")
        ).strip()
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

    @staticmethod
    def _build_agent_skill_package_bytes(*, skill_name: str, skill_md_content: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{skill_name}/SKILL.md", skill_md_content)
        return buffer.getvalue()

    def _upload_agent_skill_package(
        self,
        *,
        skill_name: str,
        version: str,
        skill_md_content: str,
    ) -> str:
        package_bytes = self._build_agent_skill_package_bytes(
            skill_name=skill_name,
            skill_md_content=skill_md_content,
        )
        minio_client = get_minio_client()
        _bucket_name, object_key = minio_client.upload_file(
            bucket_type="artifacts",
            file_data=io.BytesIO(package_bytes),
            filename=f"{skill_name}-{version}.zip",
            user_id="system",
            content_type="application/zip",
            metadata={
                "skill_name": skill_name,
                "version": version,
                "package_type": "agent_skill",
                "source": "skill_proposal",
            },
        )
        return object_key

    @staticmethod
    def _build_runtime_skill_content(
        *,
        skill: SkillInfo,
        proposal: Any,
        payload: Dict[str, Any],
    ) -> str:
        goal = str(
            payload.get("goal") or getattr(proposal, "goal", None) or skill.description or ""
        ).strip()
        steps = [
            str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()
        ]
        why_it_worked = str(
            payload.get("why_it_worked")
            or getattr(proposal, "why_it_worked", None)
            or skill.description
            or ""
        ).strip()
        applicability = str(
            payload.get("applicability") or getattr(proposal, "applicability", None) or ""
        ).strip()
        avoid = str(payload.get("avoid") or getattr(proposal, "avoid", None) or "").strip()

        lines = [f"learned.skill.slug={skill.skill_slug}"]
        if goal:
            lines.append(f"learned.skill.goal={goal}")
        if steps:
            lines.append(f"learned.skill.successful_path={' | '.join(steps)}")
        if why_it_worked:
            lines.append(f"learned.skill.summary={why_it_worked}")
        if applicability:
            lines.append(f"learned.skill.applicability={applicability}")
        if avoid:
            lines.append(f"learned.skill.avoid={avoid}")
        return "\n".join(lines)

    @staticmethod
    def _build_runtime_skill_document(
        *,
        skill: SkillInfo,
        proposal: Any,
        payload: Dict[str, Any],
    ) -> str:
        parts: List[str] = [
            str(skill.display_name or ""),
            str(skill.skill_slug or ""),
            str(skill.description or ""),
            str(skill.skill_md_content or ""),
            str(getattr(proposal, "title", None) or ""),
            str(getattr(proposal, "goal", None) or ""),
            str(getattr(proposal, "why_it_worked", None) or ""),
        ]
        for item in payload.values():
            if isinstance(item, (list, tuple, set)):
                parts.extend(str(value or "") for value in item)
            elif isinstance(item, dict):
                parts.extend(str(value or "") for value in item.values())
            else:
                parts.append(str(item or ""))
        return _normalize_text(" ".join(part for part in parts if part))

    @staticmethod
    def _score_published_skill(
        *,
        skill: SkillInfo,
        proposal: Any,
        payload: Dict[str, Any],
        query_text: str,
        query_terms: List[str],
    ) -> float:
        document = SkillProposalService._build_runtime_skill_document(
            skill=skill,
            proposal=proposal,
            payload=payload,
        )
        if not document:
            return 0.0

        normalized_query = _normalize_text(query_text)
        exact_match = bool(
            normalized_query and normalized_query != "*" and normalized_query in document
        )
        confidence = payload.get("confidence", getattr(proposal, "confidence", 0.0))
        try:
            quality = min(max(float(confidence or 0.0), 0.0), 1.0)
        except (TypeError, ValueError):
            quality = 0.0

        if not query_terms:
            if not normalized_query or normalized_query == "*":
                return min(0.38 + 0.2 * quality, 0.9)
            return 0.0

        hit_count = sum(1 for term in query_terms if term and term in document)
        if hit_count == 0:
            return 0.0

        hit_ratio = hit_count / max(len(query_terms), 1)
        base = 0.28 + (0.12 if exact_match else 0.0)
        return min(base + 0.44 * hit_ratio + 0.16 * quality, 0.98)

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

        skill_slug = self._build_skill_name(existing)
        display_name = (
            str(getattr(existing, "title", "") or payload.get("goal") or "").strip() or skill_slug
        )
        if reuse_existing_by_name:
            existing_skill = registry.get_skill_by_slug(skill_slug)
            if existing_skill is not None:
                return existing_skill

        version = "1.0.0"
        skill_md_content = self._build_skill_md_content(existing, payload)
        storage_path = None
        manifest = None
        if skill_type == "agent_skill":
            storage_type = "minio"
            storage_path = self._upload_agent_skill_package(
                skill_name=skill_slug,
                version=version,
                skill_md_content=skill_md_content,
            )
            manifest = {
                "source": "skill_proposal",
                "skill_type": skill_type,
                "files": ["SKILL.md"],
            }

        return registry.register_skill(
            skill_slug=skill_slug,
            display_name=display_name,
            description=self._build_skill_description(existing, payload),
            interface_definition=self._build_skill_interface(existing, payload),
            dependencies=[],
            version=version,
            skill_type=skill_type,
            storage_type=storage_type,
            access_level="private",
            code=None,
            config={
                "source": "skill_proposal",
                "proposal_id": int(getattr(existing, "id", 0) or 0),
                "agent_id": str(getattr(existing, "agent_id", "") or ""),
                "proposal_key": str(getattr(existing, "proposal_key", "") or ""),
            },
            storage_path=storage_path,
            manifest=manifest,
            skill_md_content=skill_md_content,
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
            dict(existing.proposal_payload or {})
            if isinstance(existing.proposal_payload, dict)
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
            payload["published_skill_slug"] = skill.skill_slug
            payload["published_skill_display_name"] = skill.display_name

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
            summary=(
                summary if summary is not None else str(payload.get("why_it_worked") or "") or None
            ),
            details=(
                details if details is not None else str(payload.get("review_content") or "") or None
            ),
            review_status=review_status_value,
            review_note=str(payload.get("review_note") or "") or None,
            payload=payload,
            published_skill_id=published_skill_id,
        )
        return updated

    def delete_proposal(
        self,
        *,
        proposal_id: int,
        delete_published_skill: bool = True,
    ) -> bool:
        existing = self._repository.get_proposal(proposal_id)
        if existing is None:
            return False

        published_skill_id = getattr(existing, "published_skill_id", None)
        deleted = self._repository.delete_proposal(int(proposal_id))
        if not deleted:
            return False

        if delete_published_skill and published_skill_id:
            remaining_refs = self._repository.count_proposals_for_published_skill(
                published_skill_id=str(published_skill_id),
                exclude_proposal_id=int(proposal_id),
            )
            if remaining_refs == 0:
                try:
                    self._skill_registry.delete_skill(UUID(str(published_skill_id)))
                except Exception:
                    # Proposal deletion should still succeed even if the registry cleanup lags.
                    pass
        return True

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

    def list_published_skills(
        self,
        *,
        agent_id: str,
        query_text: str,
        limit: int,
        min_score: Optional[float] = None,
    ) -> List[RetrievedMemoryItem]:
        proposals = self._repository.list_proposals(
            agent_ids=[str(agent_id)],
            review_status="published",
            limit=max(max(int(limit), 1) * 4, 20),
        )
        query_terms = _extract_query_terms(query_text)
        scored_items: List[tuple[float, RetrievedMemoryItem]] = []

        for proposal in proposals:
            raw_skill_id = getattr(proposal, "published_skill_id", None)
            if raw_skill_id is None:
                continue
            try:
                skill_id = UUID(str(raw_skill_id))
            except (TypeError, ValueError):
                continue

            skill = self._skill_registry.get_skill(skill_id)
            if skill is None or not skill.is_active:
                continue

            payload = (
                dict(proposal.proposal_payload or {})
                if isinstance(getattr(proposal, "proposal_payload", None), dict)
                else {}
            )
            score = self._score_published_skill(
                skill=skill,
                proposal=proposal,
                payload=payload,
                query_text=query_text,
                query_terms=query_terms,
            )
            if min_score is not None and score < float(min_score):
                continue
            if score <= 0:
                continue

            timestamp = (
                getattr(skill, "updated_at", None)
                or getattr(skill, "created_at", None)
                or getattr(proposal, "updated_at", None)
                or getattr(proposal, "created_at", None)
            )
            item = RetrievedMemoryItem(
                id=int(getattr(proposal, "id", 0) or 0),
                content=self._build_runtime_skill_content(
                    skill=skill,
                    proposal=proposal,
                    payload=payload,
                ),
                memory_type="published_skill",
                agent_id=str(getattr(proposal, "agent_id", "") or "") or None,
                user_id=str(getattr(proposal, "user_id", "") or "") or None,
                timestamp=timestamp,
                metadata={
                    "search_method": "published_skill",
                    "memory_source": "skill_registry",
                    "record_type": "published_skill",
                    "signal_type": "published_skill",
                    "skill_id": str(skill.skill_id),
                    "skill_slug": skill.skill_slug,
                    "skill_display_name": skill.display_name,
                    "skill_type": skill.skill_type,
                    "storage_type": skill.storage_type,
                    "proposal_id": int(getattr(proposal, "id", 0) or 0),
                    "proposal_key": str(getattr(proposal, "proposal_key", "") or ""),
                    "review_status": str(getattr(proposal, "review_status", "") or "published"),
                    "source": "skill_proposal",
                },
                similarity_score=round(float(score), 4),
                summary=str(skill.description or getattr(proposal, "summary", None) or "").strip()
                or None,
            )
            scored_items.append((float(score), item))

        scored_items.sort(
            key=lambda item: (
                item[0],
                getattr(item[1], "timestamp", None) or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return [item for _, item in scored_items[: max(int(limit), 1)]]


_skill_proposal_service: Optional[SkillProposalService] = None


def get_skill_proposal_service() -> SkillProposalService:
    """Return the shared skill-proposal service."""

    global _skill_proposal_service
    if _skill_proposal_service is None:
        _skill_proposal_service = SkillProposalService()
    return _skill_proposal_service
