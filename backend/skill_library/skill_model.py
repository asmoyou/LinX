"""Skill model and database operations."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import joinedload

from access_control.skill_access import (
    SKILL_ACCESS_PUBLIC,
    SKILL_ACCESS_TEAM,
    SkillAccessContext,
)
from database.connection import get_db_session
from database.models import AgentSkillBinding, Skill

logger = logging.getLogger(__name__)


class SkillModel:
    """Database operations for skills."""

    @staticmethod
    def _base_query(session):
        return session.query(Skill).options(joinedload(Skill.department))

    @staticmethod
    def _apply_visibility_filter(query, access_context: SkillAccessContext):
        if access_context.is_admin:
            return query

        visibility_clauses = [Skill.access_level == SKILL_ACCESS_PUBLIC]
        if access_context.user_id:
            visibility_clauses.append(Skill.created_by == UUID(str(access_context.user_id)))
        if access_context.department_ancestor_ids:
            visibility_clauses.append(
                and_(
                    Skill.access_level == SKILL_ACCESS_TEAM,
                    Skill.department_id.in_([UUID(item) for item in access_context.department_ancestor_ids]),
                )
            )

        if not visibility_clauses:
            return query.filter(False)
        return query.filter(or_(*visibility_clauses))

    def create_skill(
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
    ) -> Skill:
        """Create a new skill in the database."""
        with get_db_session() as session:
            created_by_uuid = UUID(str(created_by)) if created_by else None
            department_uuid = UUID(str(department_id)) if department_id else None

            skill = Skill(
                skill_slug=skill_slug,
                display_name=display_name,
                description=description,
                interface_definition=interface_definition,
                dependencies=dependencies or [],
                version=version,
                skill_type=skill_type,
                storage_type=storage_type,
                code=code,
                config=config,
                storage_path=storage_path,
                manifest=manifest,
                skill_md_content=skill_md_content,
                homepage=homepage,
                skill_metadata=skill_metadata,
                gating_status=gating_status,
                access_level=access_level,
                department_id=department_uuid,
                is_active=is_active,
                created_by=created_by_uuid,
            )
            session.add(skill)
            session.commit()
            session.refresh(skill)

            logger.info(
                "Skill created",
                extra={
                    "skill_id": str(skill.skill_id),
                    "skill_slug": skill.skill_slug,
                    "display_name": skill.display_name,
                    "skill_version": version,
                    "skill_type": skill_type,
                    "storage_type": storage_type,
                    "access_level": access_level,
                },
            )

            return self._base_query(session).filter(Skill.skill_id == skill.skill_id).first()

    def get_skill_by_id(self, skill_id: UUID) -> Optional[Skill]:
        with get_db_session() as session:
            return self._base_query(session).filter(Skill.skill_id == skill_id).first()

    def get_visible_skill_by_id(
        self, *, skill_id: UUID, access_context: SkillAccessContext
    ) -> Optional[Skill]:
        with get_db_session() as session:
            query = self._apply_visibility_filter(self._base_query(session), access_context)
            return query.filter(Skill.skill_id == skill_id).first()

    def get_skill_by_slug(self, skill_slug: str, version: Optional[str] = None) -> Optional[Skill]:
        with get_db_session() as session:
            query = self._base_query(session).filter(Skill.skill_slug == skill_slug)
            if version:
                query = query.filter(Skill.version == version)
            else:
                query = query.order_by(Skill.created_at.desc())
            return query.first()

    def get_skill_by_name(self, name: str, version: Optional[str] = None) -> Optional[Skill]:
        """Internal alias for slug-based lookups."""
        return self.get_skill_by_slug(name, version)

    def list_skills(self, limit: int = 100, offset: int = 0) -> List[Skill]:
        with get_db_session() as session:
            return (
                self._base_query(session)
                .order_by(Skill.created_at.desc(), Skill.skill_id.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

    def list_visible_skills(
        self,
        *,
        access_context: SkillAccessContext,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Skill]:
        with get_db_session() as session:
            query = self._apply_visibility_filter(self._base_query(session), access_context)
            return (
                query.order_by(Skill.created_at.desc(), Skill.skill_id.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

    def get_overview_stats(self, *, access_context: Optional[SkillAccessContext] = None) -> Dict[str, Any]:
        """Get aggregated overview statistics for the skills library."""
        skills: List[Skill]
        if access_context is not None:
            skills = self.list_visible_skills(access_context=access_context, limit=1000, offset=0)
        else:
            skills = self.list_skills(limit=1000, offset=0)

        active_skills = [skill for skill in skills if skill.is_active is not False]
        dependency_count = sum(
            1 for skill in skills if isinstance(skill.dependencies, list) and skill.dependencies
        )
        avg_samples = [
            float(skill.average_execution_time or 0.0)
            for skill in skills
            if (skill.execution_count or 0) > 0 and skill.average_execution_time is not None
        ]
        last_executed_at = max(
            (skill.last_executed_at for skill in skills if skill.last_executed_at),
            default=None,
        )

        return {
            "total_skills": len(skills),
            "active_skills": len(active_skills),
            "inactive_skills": max(len(skills) - len(active_skills), 0),
            "agent_skills": sum(1 for skill in skills if skill.skill_type == "agent_skill"),
            "langchain_tool_skills": sum(
                1 for skill in skills if skill.skill_type == "langchain_tool"
            ),
            "skills_with_dependencies": dependency_count,
            "total_execution_count": sum(int(skill.execution_count or 0) for skill in skills),
            "average_execution_time": (sum(avg_samples) / len(avg_samples) if avg_samples else 0.0),
            "last_executed_at": last_executed_at.isoformat() if last_executed_at else None,
        }

    def update_skill(
        self,
        *,
        skill_id: UUID,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        code: Optional[str] = None,
        interface_definition: Optional[dict] = None,
        dependencies: Optional[List[str]] = None,
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
    ) -> Optional[Skill]:
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).first()
            if not skill:
                return None

            if display_name is not None:
                skill.display_name = display_name
            if description is not None:
                skill.description = description
            if code is not None:
                skill.code = code
            if interface_definition is not None:
                skill.interface_definition = interface_definition
            if dependencies is not None:
                skill.dependencies = dependencies
            if config is not None:
                skill.config = config
            if access_level is not None:
                skill.access_level = access_level
            if department_id is not None:
                skill.department_id = UUID(str(department_id)) if department_id else None
            if is_active is not None:
                skill.is_active = is_active
                skill.lifecycle_state = "active" if is_active else "deprecated"
            if storage_path is not None:
                skill.storage_path = storage_path
            if manifest is not None:
                skill.manifest = manifest
            if skill_md_content is not None:
                skill.skill_md_content = skill_md_content
            if homepage is not None:
                skill.homepage = homepage
            if skill_metadata is not None:
                skill.skill_metadata = skill_metadata
            if gating_status is not None:
                skill.gating_status = gating_status

            session.commit()
            session.refresh(skill)

            logger.info("Skill updated", extra={"skill_id": str(skill_id)})
            return self._base_query(session).filter(Skill.skill_id == skill.skill_id).first()

    def delete_skill(self, skill_id: UUID) -> bool:
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).first()
            if not skill:
                return False

            binding_count = (
                session.query(AgentSkillBinding)
                .filter(AgentSkillBinding.skill_id == skill_id, AgentSkillBinding.enabled.is_(True))
                .count()
            )
            if binding_count:
                raise ValueError("Cannot delete a skill while active agent bindings exist")

            session.delete(skill)
            session.commit()

            logger.info(
                "Skill deleted",
                extra={
                    "skill_id": str(skill.skill_id),
                    "skill_slug": skill.skill_slug,
                },
            )
            return True

    def search_skills(self, query: str) -> List[Skill]:
        with get_db_session() as session:
            search_pattern = f"%{query}%"
            return (
                self._base_query(session)
                .filter(
                    or_(
                        Skill.display_name.ilike(search_pattern),
                        Skill.skill_slug.ilike(search_pattern),
                        Skill.description.ilike(search_pattern),
                    )
                )
                .order_by(Skill.created_at.desc(), Skill.skill_id.desc())
                .all()
            )

    def search_visible_skills(
        self,
        *,
        query: str,
        access_context: SkillAccessContext,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Skill]:
        with get_db_session() as session:
            search_pattern = f"%{query}%"
            filtered = self._apply_visibility_filter(self._base_query(session), access_context)
            return (
                filtered.filter(
                    or_(
                        Skill.display_name.ilike(search_pattern),
                        Skill.skill_slug.ilike(search_pattern),
                        Skill.description.ilike(search_pattern),
                    )
                )
                .order_by(Skill.created_at.desc(), Skill.skill_id.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )


_skill_model: Optional[SkillModel] = None


def get_skill_model() -> SkillModel:
    """Get or create the skill model singleton."""
    global _skill_model
    if _skill_model is None:
        _skill_model = SkillModel()
    return _skill_model
