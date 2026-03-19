"""Canonical runtime registry for bound skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import joinedload

from access_control.skill_access import build_skill_access_context_for_user_id, can_read_skill
from database.connection import get_db_session
from database.models import AgentSkillBinding, Skill, SkillRevision, User
from user_memory.items import RetrievedMemoryItem


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _extract_query_terms(query_text: str) -> List[str]:
    normalized = _normalize_text(query_text)
    if not normalized:
        return []
    tokens = re.findall(r"[a-z0-9_\-\u3400-\u9fff]{2,}", normalized)
    return list(dict.fromkeys(tokens))


@dataclass(frozen=True)
class RuntimeSkillDescriptor:
    binding_id: UUID
    skill_id: UUID
    revision_id: UUID
    binding_mode: str
    source: str
    skill_source_kind: str
    auto_update_policy: str
    priority: int
    slug: str
    display_name: str
    description: str
    artifact_kind: str
    runtime_mode: str
    visibility: str
    instruction_md: Optional[str]
    tool_code: Optional[str]
    interface_definition: Optional[dict]
    manifest: Optional[dict]
    config: Optional[dict]
    search_document: str
    artifact_ref: Optional[str]
    artifact_storage_kind: str


class SkillRuntimeRegistry:
    """Resolve bound skills and runtime retrieval snippets from canonical tables."""

    @staticmethod
    def _resolve_effective_revision(skill: Skill, binding: AgentSkillBinding) -> Optional[SkillRevision]:
        if binding.revision_pin_id is not None:
            for revision in getattr(skill, "revisions", []) or []:
                if revision.revision_id == binding.revision_pin_id:
                    return revision
        return getattr(skill, "active_revision", None)

    def _list_bound_descriptors(
        self,
        *,
        agent_id: UUID,
        user_id: UUID,
    ) -> List[RuntimeSkillDescriptor]:
        with get_db_session() as session:
            user = session.query(User).filter(User.user_id == user_id).one_or_none()
            access_context = build_skill_access_context_for_user_id(
                session,
                user_id=str(user_id),
                role=str(getattr(user, "role", "") or ""),
            )
            rows = (
                session.query(AgentSkillBinding)
                .options(
                    joinedload(AgentSkillBinding.skill).joinedload(Skill.active_revision),
                    joinedload(AgentSkillBinding.skill).joinedload(Skill.revisions),
                )
                .filter(AgentSkillBinding.agent_id == agent_id, AgentSkillBinding.enabled.is_(True))
                .order_by(AgentSkillBinding.priority.asc(), AgentSkillBinding.created_at.asc())
                .all()
            )
            descriptors: List[RuntimeSkillDescriptor] = []
            for binding in rows:
                skill = getattr(binding, "skill", None)
                if skill is None or not can_read_skill(skill, access_context):
                    continue
                if not bool(getattr(skill, "is_active", True)):
                    continue
                if str(getattr(skill, "lifecycle_state", "active") or "active") != "active":
                    continue
                revision = self._resolve_effective_revision(skill, binding)
                if revision is None:
                    continue
                if str(getattr(revision, "review_state", "approved") or "approved") != "approved":
                    continue
                descriptors.append(
                    RuntimeSkillDescriptor(
                        binding_id=binding.binding_id,
                        skill_id=skill.skill_id,
                        revision_id=revision.revision_id,
                        binding_mode=str(binding.binding_mode or "doc"),
                        source=str(binding.source or "manual"),
                        skill_source_kind=str(skill.source_kind or "manual"),
                        auto_update_policy=str(
                            binding.auto_update_policy or "follow_active"
                        ),
                        priority=int(binding.priority or 0),
                        slug=str(skill.skill_slug or ""),
                        display_name=str(skill.display_name or ""),
                        description=str(skill.description or ""),
                        artifact_kind=str(skill.artifact_kind or "tool"),
                        runtime_mode=str(skill.runtime_mode or "tool"),
                        visibility=str(skill.visibility or "private"),
                        instruction_md=revision.instruction_md,
                        tool_code=revision.tool_code,
                        interface_definition=dict(revision.interface_definition or {})
                        if revision.interface_definition
                        else None,
                        manifest=dict(revision.manifest or {}) if revision.manifest else None,
                        config=dict(revision.config or {}) if revision.config else None,
                        search_document=str(revision.search_document or ""),
                        artifact_ref=revision.artifact_ref,
                        artifact_storage_kind=str(revision.artifact_storage_kind or "inline"),
                    )
                )
            return descriptors

    def list_doc_skills(self, *, agent_id: UUID, user_id: UUID) -> List[RuntimeSkillDescriptor]:
        return [
            item
            for item in self._list_bound_descriptors(agent_id=agent_id, user_id=user_id)
            if item.binding_mode in {"doc", "hybrid"} and item.runtime_mode in {"doc", "hybrid"}
            and item.instruction_md
        ]

    def list_tool_skills(self, *, agent_id: UUID, user_id: UUID) -> List[RuntimeSkillDescriptor]:
        return [
            item
            for item in self._list_bound_descriptors(agent_id=agent_id, user_id=user_id)
            if item.binding_mode in {"tool", "hybrid"} and item.runtime_mode in {"tool", "hybrid"}
            and item.tool_code
        ]

    @staticmethod
    def _score_descriptor(item: RuntimeSkillDescriptor, query_text: str) -> float:
        document = _normalize_text(item.search_document or item.description or item.display_name)
        query = _normalize_text(query_text)
        if not document:
            return 0.0
        if not query:
            return 0.2
        terms = _extract_query_terms(query_text)
        if not terms:
            return 0.0
        hit_count = sum(1 for term in terms if term in document)
        if hit_count == 0:
            return 0.0
        exact = 1.0 if query in document else 0.0
        ratio = hit_count / max(len(terms), 1)
        return min(0.3 + ratio * 0.5 + exact * 0.2, 0.98)

    @staticmethod
    def _format_retrieval_content(item: RuntimeSkillDescriptor) -> str:
        config = item.config or {}
        steps = config.get("successful_path") or config.get("key_steps") or []
        if not isinstance(steps, list):
            steps = []
        when_to_use = (
            str(config.get("applicability") or config.get("when_to_use") or item.description or "")
            .strip()
        )
        avoid = str(config.get("avoid") or "").strip()
        lines = [
            f"skill.slug={item.slug}",
            f"skill.name={item.display_name}",
            f"skill.summary={item.description}",
        ]
        if when_to_use:
            lines.append(f"skill.when_to_use={when_to_use}")
        if steps:
            lines.append("skill.key_steps=" + " | ".join(str(step).strip() for step in steps if str(step).strip()))
        if avoid:
            lines.append(f"skill.avoid={avoid}")
        lines.append(f"skill.source_kind={item.skill_source_kind}")
        return "\n".join(lines)

    def retrieve_skills(
        self,
        *,
        agent_id: UUID,
        user_id: UUID,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[RetrievedMemoryItem]:
        descriptors = [
            item
            for item in self._list_bound_descriptors(agent_id=agent_id, user_id=user_id)
            if item.binding_mode in {"retrieval", "hybrid"}
            and item.runtime_mode in {"retrieval", "hybrid"}
        ]
        scored: List[tuple[float, RuntimeSkillDescriptor]] = []
        for item in descriptors:
            score = self._score_descriptor(item, query)
            if min_similarity is not None and score < float(min_similarity):
                continue
            if score <= 0:
                continue
            scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], -pair[1].priority), reverse=True)
        return [
            RetrievedMemoryItem(
                id=None,
                content=self._format_retrieval_content(item),
                memory_type="skill_runtime",
                agent_id=str(agent_id),
                user_id=str(user_id),
                metadata={
                    "memory_source": "skill_runtime_registry",
                    "record_type": "skill_runtime",
                    "signal_type": "skill_runtime",
                    "skill_id": str(item.skill_id),
                    "revision_id": str(item.revision_id),
                    "skill_slug": item.slug,
                    "skill_display_name": item.display_name,
                    "artifact_kind": item.artifact_kind,
                    "runtime_mode": item.runtime_mode,
                    "binding_mode": item.binding_mode,
                    "source_kind": item.skill_source_kind,
                    "binding_source": item.source,
                },
                similarity_score=round(score, 4),
                summary=item.description,
            )
            for score, item in scored[: max(int(top_k), 1)]
        ]

    def capability_labels(self, *, agent_id: UUID, user_id: UUID) -> List[str]:
        labels = []
        for item in self._list_bound_descriptors(agent_id=agent_id, user_id=user_id):
            label = item.display_name or item.slug
            if label and label not in labels:
                labels.append(label)
        return labels


_runtime_registry: Optional[SkillRuntimeRegistry] = None


def get_skill_runtime_registry() -> SkillRuntimeRegistry:
    global _runtime_registry
    if _runtime_registry is None:
        _runtime_registry = SkillRuntimeRegistry()
    return _runtime_registry
