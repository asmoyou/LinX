"""Skill registration and retrieval."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from access_control.skill_access import SkillAccessContext
from skill_library.canonical_service import get_canonical_skill_service
from skill_library.skill_model import SkillModel, get_skill_model
from skill_library.skill_validator import SkillValidator, get_skill_validator

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Skill information."""

    skill_id: UUID
    skill_slug: str
    display_name: str
    description: str
    version: str
    interface_definition: dict
    dependencies: List[str]
    skill_type: str = "langchain_tool"
    storage_type: str = "inline"
    code: Optional[str] = None
    config: Optional[dict] = None
    storage_path: Optional[str] = None
    manifest: Optional[dict] = None
    skill_md_content: Optional[str] = None
    homepage: Optional[str] = None
    skill_metadata: Optional[dict] = None
    gating_status: Optional[dict] = None
    access_level: str = "private"
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    source_kind: str = "manual"
    artifact_kind: str = "tool"
    runtime_mode: str = "tool"
    lifecycle_state: str = "active"
    active_revision_id: Optional[str] = None
    is_active: bool = True
    execution_count: int = 0
    last_executed_at: Optional[object] = None
    average_execution_time: Optional[float] = None
    created_at: Optional[object] = None
    updated_at: Optional[object] = None
    created_by: Optional[str] = None

    @property
    def name(self) -> str:
        return self.skill_slug


class SkillRegistry:
    """Skill registration and retrieval service."""

    def __init__(
        self,
        skill_model: Optional[SkillModel] = None,
        skill_validator: Optional[SkillValidator] = None,
    ):
        self.skill_model = skill_model or get_skill_model()
        self.skill_validator = skill_validator or get_skill_validator()
        logger.info("SkillRegistry initialized")

    @staticmethod
    def _to_skill_info(skill) -> SkillInfo:
        department = getattr(skill, "department", None)
        return SkillInfo(
            skill_id=skill.skill_id,
            skill_slug=skill.skill_slug,
            display_name=skill.display_name,
            description=skill.description,
            version=skill.version,
            interface_definition=skill.interface_definition,
            dependencies=skill.dependencies or [],
            skill_type=skill.skill_type,
            storage_type=skill.storage_type,
            code=skill.code,
            config=skill.config,
            storage_path=skill.storage_path,
            manifest=skill.manifest,
            skill_md_content=getattr(skill, "skill_md_content", None),
            homepage=getattr(skill, "homepage", None),
            skill_metadata=getattr(skill, "skill_metadata", None),
            gating_status=getattr(skill, "gating_status", None),
            access_level=getattr(skill, "access_level", "private"),
            department_id=(
                str(getattr(skill, "department_id", None)) if getattr(skill, "department_id", None) else None
            ),
            department_name=getattr(department, "name", None),
            source_kind=str(getattr(skill, "source_kind", "manual") or "manual"),
            artifact_kind=str(getattr(skill, "artifact_kind", "tool") or "tool"),
            runtime_mode=str(getattr(skill, "runtime_mode", "tool") or "tool"),
            lifecycle_state=str(getattr(skill, "lifecycle_state", "active") or "active"),
            active_revision_id=(
                str(getattr(skill, "active_revision_id", None))
                if getattr(skill, "active_revision_id", None)
                else None
            ),
            is_active=skill.is_active,
            execution_count=skill.execution_count,
            last_executed_at=skill.last_executed_at,
            average_execution_time=skill.average_execution_time,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=str(skill.created_by) if getattr(skill, "created_by", None) else None,
        )

    def register_skill(
        self,
        *,
        skill_slug: str,
        display_name: str,
        description: str,
        interface_definition: dict,
        dependencies: Optional[List[str]] = None,
        version: str = "1.0.0",
        skill_type: str = "langchain_tool",
        storage_type: str = "inline",
        code: Optional[str] = None,
        config: Optional[dict] = None,
        storage_path: Optional[str] = None,
        manifest: Optional[dict] = None,
        skill_md_content: Optional[str] = None,
        homepage: Optional[str] = None,
        skill_metadata: Optional[dict] = None,
        gating_status: Optional[dict] = None,
        access_level: str = "private",
        department_id: Optional[str] = None,
        is_active: bool = True,
        created_by: Optional[str] = None,
        validate: bool = True,
    ) -> SkillInfo:
        if validate:
            validation = self.skill_validator.validate_skill(
                skill_slug,
                interface_definition=interface_definition,
                dependencies=dependencies or [],
            )
            if not validation.is_valid:
                raise ValueError(f"Skill validation failed: {validation.errors}")

        existing = self.skill_model.get_skill_by_slug(skill_slug)
        if existing:
            raise ValueError(f"Skill {skill_slug} already exists")

        artifact_kind = "tool" if skill_type == "langchain_tool" else "instruction"
        runtime_mode = "tool" if skill_type == "langchain_tool" else "doc"
        manifest_payload = dict(manifest or {})
        if homepage:
            manifest_payload["homepage"] = homepage
        if skill_metadata is not None:
            manifest_payload["skill_metadata"] = skill_metadata
        if gating_status is not None:
            manifest_payload["gating_status"] = gating_status

        canonical_skill = get_canonical_skill_service().create_skill(
            slug=skill_slug,
            display_name=display_name,
            description=description,
            source_kind="manual",
            artifact_kind=artifact_kind,
            runtime_mode=runtime_mode,
            visibility=access_level,
            owner_user_id=created_by,
            department_id=department_id,
            dependencies=dependencies,
            revision_payload={
                "version": version,
                "instruction_md": skill_md_content if skill_type != "langchain_tool" else None,
                "tool_code": code if skill_type == "langchain_tool" else None,
                "interface_definition": interface_definition,
                "artifact_storage_kind": storage_type,
                "artifact_ref": storage_path,
                "manifest": manifest_payload or None,
                "config": config,
                "review_state": "approved",
                "change_note": "Initial revision",
            },
            lifecycle_state="active" if is_active else "deprecated",
        )
        skill = self.skill_model.get_skill_by_id(canonical_skill.skill_id)
        if skill is None:
            raise ValueError(f"Failed to load created skill: {skill_slug}")

        logger.info(
            "Skill registered",
            extra={
                "skill_slug": skill_slug,
                "version": version,
                "skill_type": skill_type,
                "storage_type": storage_type,
                "access_level": access_level,
            },
        )
        return self._to_skill_info(skill)

    def get_skill(self, skill_id: UUID) -> Optional[SkillInfo]:
        skill = self.skill_model.get_skill_by_id(skill_id)
        return self._to_skill_info(skill) if skill else None

    def get_visible_skill(
        self, *, skill_id: UUID, access_context: SkillAccessContext
    ) -> Optional[SkillInfo]:
        skill = self.skill_model.get_visible_skill_by_id(skill_id=skill_id, access_context=access_context)
        return self._to_skill_info(skill) if skill else None

    def get_skill_by_slug(self, skill_slug: str, version: Optional[str] = None) -> Optional[SkillInfo]:
        skill = self.skill_model.get_skill_by_slug(skill_slug, version)
        return self._to_skill_info(skill) if skill else None

    def get_skill_by_name(self, name: str, version: Optional[str] = None) -> Optional[SkillInfo]:
        return self.get_skill_by_slug(name, version)

    def list_skills(self, limit: int = 100, offset: int = 0) -> List[SkillInfo]:
        return [self._to_skill_info(skill) for skill in self.skill_model.list_skills(limit, offset)]

    def list_visible_skills(
        self,
        *,
        access_context: SkillAccessContext,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SkillInfo]:
        return [
            self._to_skill_info(skill)
            for skill in self.skill_model.list_visible_skills(
                access_context=access_context,
                limit=limit,
                offset=offset,
            )
        ]

    def count_visible_skills(
        self,
        *,
        access_context: SkillAccessContext,
    ) -> int:
        return self.skill_model.count_visible_skills(access_context=access_context)

    def search_skills(self, query: str) -> List[SkillInfo]:
        return [self._to_skill_info(skill) for skill in self.skill_model.search_skills(query)]

    def search_visible_skills(
        self,
        *,
        query: str,
        access_context: SkillAccessContext,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SkillInfo]:
        return [
            self._to_skill_info(skill)
            for skill in self.skill_model.search_visible_skills(
                query=query,
                access_context=access_context,
                limit=limit,
                offset=offset,
            )
        ]

    def count_search_visible_skills(
        self,
        *,
        query: str,
        access_context: SkillAccessContext,
    ) -> int:
        return self.skill_model.count_search_visible_skills(
            query=query,
            access_context=access_context,
        )

    def update_skill(
        self,
        *,
        skill_id: UUID,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        interface_definition: Optional[dict] = None,
        dependencies: Optional[List[str]] = None,
        code: Optional[str] = None,
        config: Optional[dict] = None,
        access_level: Optional[str] = None,
        department_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        storage_path: Optional[str] = None,
        manifest: Optional[dict] = None,
        skill_md_content: Optional[str] = None,
        homepage: Optional[str] = None,
        skill_metadata: Optional[dict] = None,
        gating_status: Optional[dict] = None,
    ) -> Optional[SkillInfo]:
        current = self.skill_model.get_skill_by_id(skill_id)
        if current is None:
            return None

        revision_fields_changed = any(
            value is not None
            for value in (
                interface_definition,
                code,
                config,
                storage_path,
                manifest,
                skill_md_content,
                homepage,
                skill_metadata,
                gating_status,
            )
        )

        if revision_fields_changed:
            merged_manifest = dict(current.manifest or {})
            if manifest:
                merged_manifest.update(manifest)
            if homepage is not None:
                merged_manifest["homepage"] = homepage
            if skill_metadata is not None:
                merged_manifest["skill_metadata"] = skill_metadata
            if gating_status is not None:
                merged_manifest["gating_status"] = gating_status

            revision = get_canonical_skill_service().create_revision(
                skill_id=skill_id,
                owner_user_id=str(current.created_by) if getattr(current, "created_by", None) else None,
                revision_payload={
                    "version": self._next_revision_version(str(current.version or "1.0.0")),
                    "instruction_md": (
                        skill_md_content
                        if skill_md_content is not None
                        else getattr(current, "skill_md_content", None)
                    ),
                    "tool_code": code if code is not None else getattr(current, "code", None),
                    "interface_definition": (
                        interface_definition
                        if interface_definition is not None
                        else dict(getattr(current, "interface_definition", {}) or {})
                    ),
                    "artifact_storage_kind": str(getattr(current, "storage_type", "inline") or "inline"),
                    "artifact_ref": (
                        storage_path if storage_path is not None else getattr(current, "storage_path", None)
                    ),
                    "manifest": merged_manifest or None,
                    "config": config if config is not None else getattr(current, "config", None),
                    "review_state": "approved",
                    "change_note": "Updated via skill registry",
                },
            )
            get_canonical_skill_service().activate_revision(
                skill_id=skill_id,
                revision_id=revision.revision_id,
                actor_user_id=str(current.created_by) if getattr(current, "created_by", None) else None,
            )

        skill = self.skill_model.update_skill(
            skill_id=skill_id,
            display_name=display_name,
            description=description,
            dependencies=dependencies,
            access_level=access_level,
            department_id=department_id,
            is_active=is_active,
        )
        return self._to_skill_info(skill) if skill else None

    @staticmethod
    def _next_revision_version(version: str) -> str:
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", str(version or "").strip())
        if not match:
            return "1.0.1"
        major, minor, patch = (int(part) for part in match.groups())
        return f"{major}.{minor}.{patch + 1}"

    def delete_skill(self, skill_id: UUID) -> bool:
        return self.skill_model.delete_skill(skill_id)


_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get or create the skill registry singleton."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
