"""Canonical skill platform service layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from access_control.skill_access import SkillAccessContext, can_read_skill
from database.connection import get_db_session
from database.models import Agent, AgentSkillBinding, Skill, SkillRevision


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def build_skill_search_document(
    *,
    slug: str,
    display_name: str,
    description: str,
    instruction_md: Optional[str],
    extra_sections: Optional[Iterable[str]] = None,
) -> str:
    parts = [
        _normalize_text(display_name),
        _normalize_text(slug),
        _normalize_text(description),
        _normalize_text(instruction_md),
    ]
    for section in extra_sections or []:
        normalized = _normalize_text(section)
        if normalized:
            parts.append(normalized)
    return "\n".join(part for part in parts if part)


def compute_revision_checksum(
    *,
    version: str,
    instruction_md: Optional[str],
    tool_code: Optional[str],
    interface_definition: Optional[dict],
    config: Optional[dict],
) -> str:
    payload = "||".join(
        [
            _normalize_text(version),
            _normalize_text(instruction_md),
            _normalize_text(tool_code),
            _normalize_text(interface_definition),
            _normalize_text(config),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SkillRevisionInfo:
    revision_id: UUID
    skill_id: UUID
    version: str
    review_state: str
    instruction_md: Optional[str]
    tool_code: Optional[str]
    interface_definition: Optional[dict]
    artifact_storage_kind: str
    artifact_ref: Optional[str]
    manifest: Optional[dict]
    config: Optional[dict]
    search_document: Optional[str]
    checksum: Optional[str]
    change_note: Optional[str]
    created_by: Optional[str]
    created_at: Any


@dataclass(frozen=True)
class CanonicalSkillInfo:
    skill_id: UUID
    slug: str
    display_name: str
    description: str
    source_kind: str
    artifact_kind: str
    runtime_mode: str
    lifecycle_state: str
    visibility: str
    owner_user_id: Optional[str]
    department_id: Optional[str]
    active_revision_id: Optional[str]
    is_active: bool
    active_revision: Optional[SkillRevisionInfo]
    created_at: Any
    updated_at: Any


@dataclass(frozen=True)
class AgentSkillBindingInfo:
    binding_id: UUID
    agent_id: UUID
    skill_id: UUID
    revision_pin_id: Optional[UUID]
    binding_mode: str
    enabled: bool
    priority: int
    source: str
    auto_update_policy: str
    created_at: Any
    updated_at: Any


class CanonicalSkillService:
    """Manage canonical skills, revisions, and bindings."""

    @staticmethod
    def _manifest_skill_fields(manifest: Optional[dict]) -> Dict[str, Any]:
        payload = dict(manifest or {})
        return {
            "homepage": payload.get("homepage"),
            "skill_metadata": payload.get("skill_metadata") or payload.get("metadata"),
            "gating_status": payload.get("gating_status"),
        }

    @staticmethod
    def _to_revision_info(row: Optional[SkillRevision]) -> Optional[SkillRevisionInfo]:
        if row is None:
            return None
        return SkillRevisionInfo(
            revision_id=row.revision_id,
            skill_id=row.skill_id,
            version=str(row.version or "1.0.0"),
            review_state=str(row.review_state or "draft"),
            instruction_md=row.instruction_md,
            tool_code=row.tool_code,
            interface_definition=dict(row.interface_definition or {}) if row.interface_definition else None,
            artifact_storage_kind=str(row.artifact_storage_kind or "inline"),
            artifact_ref=row.artifact_ref,
            manifest=dict(row.manifest or {}) if row.manifest else None,
            config=dict(row.config or {}) if row.config else None,
            search_document=row.search_document,
            checksum=row.checksum,
            change_note=row.change_note,
            created_by=str(row.created_by) if row.created_by else None,
            created_at=row.created_at,
        )

    @classmethod
    def _to_skill_info(cls, row: Skill) -> CanonicalSkillInfo:
        return CanonicalSkillInfo(
            skill_id=row.skill_id,
            slug=str(row.skill_slug or ""),
            display_name=str(row.display_name or ""),
            description=str(row.description or ""),
            source_kind=str(row.source_kind or "manual"),
            artifact_kind=str(row.artifact_kind or "tool"),
            runtime_mode=str(row.runtime_mode or "tool"),
            lifecycle_state=str(row.lifecycle_state or "active"),
            visibility=str(row.visibility or "private"),
            owner_user_id=str(row.owner_user_id) if row.owner_user_id else None,
            department_id=str(row.department_id) if row.department_id else None,
            active_revision_id=str(row.active_revision_id) if row.active_revision_id else None,
            is_active=bool(row.lifecycle_state == "active"),
            active_revision=cls._to_revision_info(getattr(row, "active_revision", None)),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _to_binding_info(row: AgentSkillBinding) -> AgentSkillBindingInfo:
        return AgentSkillBindingInfo(
            binding_id=row.binding_id,
            agent_id=row.agent_id,
            skill_id=row.skill_id,
            revision_pin_id=row.revision_pin_id,
            binding_mode=str(row.binding_mode or "doc"),
            enabled=bool(row.enabled),
            priority=int(row.priority or 0),
            source=str(row.source or "manual"),
            auto_update_policy=str(row.auto_update_policy or "follow_active"),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_skills(
        self,
        *,
        access_context: SkillAccessContext,
        lifecycle: Optional[str] = None,
        artifact_kind: Optional[str] = None,
        visibility: Optional[str] = None,
        source_kind: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalSkillInfo]:
        with get_db_session() as session:
            query = (
                session.query(Skill)
                .options(joinedload(Skill.active_revision))
                .order_by(Skill.created_at.desc(), Skill.skill_id.desc())
            )
            rows = query.limit(limit).offset(offset).all()
            results: List[CanonicalSkillInfo] = []
            for row in rows:
                if not can_read_skill(row, access_context):
                    continue
                if lifecycle and str(row.lifecycle_state or "") != str(lifecycle):
                    continue
                if artifact_kind and str(row.artifact_kind or "") != str(artifact_kind):
                    continue
                if visibility and str(row.visibility or "") != str(visibility):
                    continue
                if source_kind and str(row.source_kind or "") != str(source_kind):
                    continue
                results.append(self._to_skill_info(row))
            return results

    def get_skill(
        self,
        *,
        skill_id: UUID,
        access_context: SkillAccessContext,
    ) -> Optional[CanonicalSkillInfo]:
        with get_db_session() as session:
            row = (
                session.query(Skill)
                .options(joinedload(Skill.active_revision))
                .filter(Skill.skill_id == skill_id)
                .one_or_none()
            )
            if row is None or not can_read_skill(row, access_context):
                return None
            return self._to_skill_info(row)

    def list_revisions(
        self,
        *,
        skill_id: UUID,
        access_context: SkillAccessContext,
    ) -> List[SkillRevisionInfo]:
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).one_or_none()
            if skill is None or not can_read_skill(skill, access_context):
                return []
            rows = (
                session.query(SkillRevision)
                .filter(SkillRevision.skill_id == skill_id)
                .order_by(SkillRevision.created_at.desc(), SkillRevision.revision_id.desc())
                .all()
            )
            return [self._to_revision_info(row) for row in rows if row is not None]

    def create_skill(
        self,
        *,
        slug: str,
        display_name: str,
        description: str,
        source_kind: str,
        artifact_kind: str,
        runtime_mode: str,
        visibility: str,
        owner_user_id: Optional[str],
        department_id: Optional[str],
        dependencies: Optional[List[str]] = None,
        revision_payload: dict,
        lifecycle_state: str = "active",
    ) -> CanonicalSkillInfo:
        with get_db_session() as session:
            existing = session.query(Skill).filter(Skill.skill_slug == slug).one_or_none()
            if existing is not None:
                raise ValueError(f"Skill slug already exists: {slug}")
            owner_uuid = UUID(str(owner_user_id)) if owner_user_id else None
            department_uuid = UUID(str(department_id)) if department_id else None
            manifest_fields = self._manifest_skill_fields(revision_payload.get("manifest"))
            skill = Skill(
                skill_slug=slug,
                display_name=display_name,
                description=description,
                source_kind=source_kind,
                artifact_kind=artifact_kind,
                runtime_mode=runtime_mode,
                lifecycle_state=lifecycle_state,
                access_level=visibility,
                created_by=owner_uuid,
                updated_by=owner_uuid,
                department_id=department_uuid,
                skill_type="langchain_tool" if artifact_kind == "tool" else "agent_skill",
                storage_type=str(revision_payload.get("artifact_storage_kind") or "inline"),
                storage_path=revision_payload.get("artifact_ref"),
                code=revision_payload.get("tool_code"),
                config=revision_payload.get("config"),
                manifest=revision_payload.get("manifest"),
                skill_md_content=revision_payload.get("instruction_md"),
                homepage=manifest_fields["homepage"],
                skill_metadata=manifest_fields["skill_metadata"],
                gating_status=manifest_fields["gating_status"],
                interface_definition=revision_payload.get("interface_definition") or {},
                dependencies=list(dependencies or []),
                version=str(revision_payload.get("version") or "1.0.0"),
                is_active=lifecycle_state == "active",
            )
            session.add(skill)
            session.flush()
            revision = self._create_revision_row(
                skill=skill,
                owner_user_id=owner_user_id,
                revision_payload=revision_payload,
            )
            session.add(revision)
            session.flush()
            skill.active_revision_id = revision.revision_id
            session.flush()
            session.refresh(skill)
            return self._to_skill_info(skill)

    def _create_revision_row(
        self,
        *,
        skill: Skill,
        owner_user_id: Optional[str],
        revision_payload: dict,
    ) -> SkillRevision:
        version = str(revision_payload.get("version") or "1.0.0")
        instruction_md = revision_payload.get("instruction_md")
        tool_code = revision_payload.get("tool_code")
        interface_definition = revision_payload.get("interface_definition") or {}
        config = revision_payload.get("config") or {}
        search_document = str(
            revision_payload.get("search_document")
            or build_skill_search_document(
                slug=str(skill.skill_slug or ""),
                display_name=str(skill.display_name or ""),
                description=str(skill.description or ""),
                instruction_md=instruction_md,
                extra_sections=[
                    revision_payload.get("change_note"),
                    str(config.get("why_it_worked") or ""),
                    str(config.get("applicability") or ""),
                    str(config.get("avoid") or ""),
                ],
            )
        )
        return SkillRevision(
            revision_id=uuid4(),
            skill_id=skill.skill_id,
            version=version,
            review_state=str(revision_payload.get("review_state") or "approved"),
            instruction_md=instruction_md,
            tool_code=tool_code,
            interface_definition=interface_definition,
            artifact_storage_kind=str(revision_payload.get("artifact_storage_kind") or "inline"),
            artifact_ref=revision_payload.get("artifact_ref"),
            manifest=revision_payload.get("manifest"),
            config=config,
            search_document=search_document,
            checksum=compute_revision_checksum(
                version=version,
                instruction_md=instruction_md,
                tool_code=tool_code,
                interface_definition=interface_definition,
                config=config,
            ),
            change_note=revision_payload.get("change_note"),
            created_by=UUID(str(owner_user_id)) if owner_user_id else None,
        )

    def create_revision(
        self,
        *,
        skill_id: UUID,
        owner_user_id: Optional[str],
        revision_payload: dict,
    ) -> SkillRevisionInfo:
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).one_or_none()
            if skill is None:
                raise ValueError("Skill not found")
            version = str(revision_payload.get("version") or "1.0.0")
            existing = (
                session.query(SkillRevision)
                .filter(SkillRevision.skill_id == skill_id, SkillRevision.version == version)
                .one_or_none()
            )
            if existing is not None:
                candidate = self._create_revision_row(
                    skill=skill,
                    owner_user_id=owner_user_id,
                    revision_payload=revision_payload,
                )
                if str(existing.checksum or "") != str(candidate.checksum or ""):
                    if str(getattr(skill, "source_kind", "") or "") == "curated" and owner_user_id is None:
                        existing.review_state = candidate.review_state
                        existing.instruction_md = candidate.instruction_md
                        existing.tool_code = candidate.tool_code
                        existing.interface_definition = candidate.interface_definition
                        existing.artifact_storage_kind = candidate.artifact_storage_kind
                        existing.artifact_ref = candidate.artifact_ref
                        existing.manifest = candidate.manifest
                        existing.config = candidate.config
                        existing.search_document = candidate.search_document
                        existing.checksum = candidate.checksum
                        existing.change_note = candidate.change_note
                        existing.created_by = candidate.created_by
                        session.flush()
                        session.refresh(existing)
                        return self._to_revision_info(existing)
                    raise ValueError(
                        f"Revision version {version} already exists with different content"
                    )
                return self._to_revision_info(existing)
            revision = self._create_revision_row(
                skill=skill,
                owner_user_id=owner_user_id,
                revision_payload=revision_payload,
            )
            session.add(revision)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                existing = (
                    session.query(SkillRevision)
                    .filter(SkillRevision.skill_id == skill_id, SkillRevision.version == version)
                    .one_or_none()
                )
                if existing is None:
                    raise
                if str(existing.checksum or "") != str(revision.checksum or ""):
                    raise ValueError(
                        f"Revision version {version} already exists with different content"
                    )
                return self._to_revision_info(existing)
            session.refresh(revision)
            return self._to_revision_info(revision)

    def review_revision(
        self,
        *,
        skill_id: UUID,
        revision_id: UUID,
        review_state: str,
    ) -> SkillRevisionInfo:
        with get_db_session() as session:
            row = (
                session.query(SkillRevision)
                .filter(SkillRevision.skill_id == skill_id, SkillRevision.revision_id == revision_id)
                .one_or_none()
            )
            if row is None:
                raise ValueError("Revision not found")
            row.review_state = review_state
            session.flush()
            session.refresh(row)
            return self._to_revision_info(row)

    def activate_revision(
        self,
        *,
        skill_id: UUID,
        revision_id: UUID,
        actor_user_id: Optional[str],
    ) -> CanonicalSkillInfo:
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).one_or_none()
            if skill is None:
                raise ValueError("Skill not found")
            revision = (
                session.query(SkillRevision)
                .filter(SkillRevision.skill_id == skill_id, SkillRevision.revision_id == revision_id)
                .one_or_none()
            )
            if revision is None:
                raise ValueError("Revision not found")
            if str(revision.review_state or "") != "approved":
                raise ValueError("Only approved revisions can be activated")
            skill.active_revision_id = revision.revision_id
            skill.version = revision.version
            skill.skill_md_content = revision.instruction_md
            skill.code = revision.tool_code
            skill.interface_definition = revision.interface_definition or {}
            skill.storage_type = revision.artifact_storage_kind
            skill.storage_path = revision.artifact_ref
            skill.manifest = revision.manifest
            skill.config = revision.config
            manifest_fields = self._manifest_skill_fields(revision.manifest)
            skill.homepage = manifest_fields["homepage"]
            skill.skill_metadata = manifest_fields["skill_metadata"]
            skill.gating_status = manifest_fields["gating_status"]
            skill.skill_type = "langchain_tool" if skill.artifact_kind == "tool" else "agent_skill"
            skill.is_active = True
            skill.lifecycle_state = "active"
            skill.updated_by = UUID(str(actor_user_id)) if actor_user_id else None
            session.flush()
            session.refresh(skill)
            return self._to_skill_info(skill)

    def list_bindings(self, *, agent_id: UUID) -> List[AgentSkillBindingInfo]:
        with get_db_session() as session:
            rows = (
                session.query(AgentSkillBinding)
                .filter(AgentSkillBinding.agent_id == agent_id)
                .order_by(AgentSkillBinding.priority.asc(), AgentSkillBinding.created_at.asc())
                .all()
            )
            return [self._to_binding_info(row) for row in rows]

    @staticmethod
    def _validate_binding_mode(*, skill: Skill, binding_mode: str) -> None:
        skill_mode = str(skill.runtime_mode or "tool")
        if binding_mode == skill_mode:
            return
        if skill_mode == "hybrid" and binding_mode in {"tool", "doc", "retrieval", "hybrid"}:
            return
        raise ValueError(
            f"Binding mode '{binding_mode}' is not compatible with skill runtime mode '{skill_mode}'"
        )

    def replace_bindings(
        self,
        *,
        agent_id: UUID,
        bindings: List[dict],
        access_context: SkillAccessContext,
    ) -> List[AgentSkillBindingInfo]:
        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).one_or_none()
            if agent is None:
                raise ValueError("Agent not found")
            session.query(AgentSkillBinding).filter(AgentSkillBinding.agent_id == agent_id).delete()
            created: List[AgentSkillBinding] = []
            for index, payload in enumerate(bindings):
                skill_id = UUID(str(payload["skill_id"]))
                skill = (
                    session.query(Skill)
                    .options(joinedload(Skill.active_revision))
                    .filter(Skill.skill_id == skill_id)
                    .one_or_none()
                )
                if skill is None or not can_read_skill(skill, access_context):
                    raise ValueError(f"Skill not found or inaccessible: {skill_id}")
                binding_mode = str(payload.get("binding_mode") or skill.runtime_mode or "doc")
                self._validate_binding_mode(skill=skill, binding_mode=binding_mode)
                revision_pin_id = payload.get("revision_pin_id")
                if revision_pin_id:
                    revision_pin_id = UUID(str(revision_pin_id))
                created.append(
                    AgentSkillBinding(
                        binding_id=uuid4(),
                        agent_id=agent_id,
                        skill_id=skill_id,
                        revision_pin_id=revision_pin_id,
                        binding_mode=binding_mode,
                        enabled=bool(payload.get("enabled", True)),
                        priority=int(payload.get("priority", index)),
                        source=str(payload.get("source") or "manual"),
                        auto_update_policy=str(
                            payload.get("auto_update_policy") or "follow_active"
                        ),
                    )
                )
            session.add_all(created)
            session.flush()
            agent.capabilities = [str(row.skill_id) for row in created if row.enabled]
            return [self._to_binding_info(row) for row in created]

    def ensure_binding(
        self,
        *,
        agent_id: UUID,
        skill_id: UUID,
        binding_mode: str,
        source: str,
        auto_update_policy: str = "follow_active",
    ) -> AgentSkillBindingInfo:
        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).one_or_none()
            if agent is None:
                raise ValueError("Agent not found")
            row = (
                session.query(AgentSkillBinding)
                .filter(AgentSkillBinding.agent_id == agent_id, AgentSkillBinding.skill_id == skill_id)
                .one_or_none()
            )
            if row is None:
                max_priority = (
                    session.query(AgentSkillBinding.priority)
                    .filter(AgentSkillBinding.agent_id == agent_id)
                    .order_by(AgentSkillBinding.priority.desc())
                    .limit(1)
                    .scalar()
                )
                row = AgentSkillBinding(
                    binding_id=uuid4(),
                    agent_id=agent_id,
                    skill_id=skill_id,
                    binding_mode=binding_mode,
                    enabled=True,
                    priority=int(max_priority or 0) + 1,
                    source=source,
                    auto_update_policy=auto_update_policy,
                )
                session.add(row)
            else:
                row.binding_mode = binding_mode
                row.enabled = True
                row.source = source
                row.auto_update_policy = auto_update_policy
            capabilities = list(agent.capabilities or []) if isinstance(agent.capabilities, list) else []
            normalized_skill_id = str(skill_id)
            if normalized_skill_id not in capabilities:
                capabilities.append(normalized_skill_id)
            agent.capabilities = capabilities
            session.flush()
            session.refresh(row)
            return self._to_binding_info(row)

    def delete_skill(self, *, skill_id: UUID) -> bool:
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).one_or_none()
            if skill is None:
                return False
            binding_count = (
                session.query(AgentSkillBinding)
                .filter(AgentSkillBinding.skill_id == skill_id, AgentSkillBinding.enabled.is_(True))
                .count()
            )
            if binding_count:
                raise ValueError("Cannot delete a skill while active agent bindings exist")
            session.delete(skill)
            session.flush()
            return True


_canonical_skill_service: Optional[CanonicalSkillService] = None


def get_canonical_skill_service() -> CanonicalSkillService:
    global _canonical_skill_service
    if _canonical_skill_service is None:
        _canonical_skill_service = CanonicalSkillService()
    return _canonical_skill_service
