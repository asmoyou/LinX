"""Skill model and database operations.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import case, func

from database.connection import get_db_session
from database.models import Agent, Skill

logger = logging.getLogger(__name__)


class SkillModel:
    """Database operations for skills."""

    def create_skill(
        self,
        name: str,
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
        is_active: bool = True,
        is_system: bool = False,
        created_by: Optional[str] = None,
    ) -> Skill:
        """Create a new skill in the database.

        Args:
            name: Unique skill name
            description: Skill description
            interface_definition: Interface definition (inputs, outputs)
            dependencies: List of required dependencies
            version: Skill version
            skill_type: Type of skill (langchain_tool, agent_skill)
            storage_type: Storage type (inline, minio)
            code: Python code for inline skills
            config: Configuration for API/DB skills
            storage_path: MinIO path for package skills
            manifest: Parsed manifest for package skills
            skill_md_content: SKILL.md content for agent_skill (required for agent_skill)
            homepage: Homepage URL for agent_skill
            skill_metadata: Additional metadata (emoji, tags, etc.)
            gating_status: Gating check results
            is_active: Whether skill is active
            is_system: Whether skill is system skill
            created_by: User ID who created the skill (string UUID)

        Returns:
            Created Skill object
        """
        from uuid import UUID as UUIDType
        
        with get_db_session() as session:
            # Convert created_by to UUID if it's a string
            created_by_uuid = None
            if created_by:
                try:
                    created_by_uuid = UUIDType(created_by) if isinstance(created_by, str) else created_by
                except (ValueError, TypeError):
                    logger.warning(f"Invalid created_by UUID: {created_by}")
            
            skill = Skill(
                name=name,
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
                is_active=is_active,
                is_system=is_system,
                created_by=created_by_uuid,
            )
            session.add(skill)
            session.commit()
            session.refresh(skill)

            logger.info(
                "Skill created",
                extra={
                    "skill_id": str(skill.skill_id),
                    "skill_name": name,
                    "skill_version": version,
                    "skill_type": skill_type,
                    "storage_type": storage_type,
                    "has_code": bool(code),
                },
            )

            return skill

    def get_skill_by_id(self, skill_id: UUID) -> Optional[Skill]:
        """Get skill by ID.

        Args:
            skill_id: Skill UUID

        Returns:
            Skill object or None if not found
        """
        with get_db_session() as session:
            return session.query(Skill).filter(Skill.skill_id == skill_id).first()

    def get_skill_by_name(self, name: str, version: Optional[str] = None) -> Optional[Skill]:
        """Get skill by name and optional version.

        Args:
            name: Skill name
            version: Optional specific version

        Returns:
            Skill object or None if not found
        """
        with get_db_session() as session:
            query = session.query(Skill).filter(Skill.name == name)

            if version:
                query = query.filter(Skill.version == version)
            else:
                # Get latest version
                query = query.order_by(Skill.created_at.desc())

            return query.first()

    def list_skills(self, limit: int = 100, offset: int = 0) -> List[Skill]:
        """List all skills with pagination.

        Args:
            limit: Maximum number of skills to return
            offset: Number of skills to skip

        Returns:
            List of Skill objects
        """
        with get_db_session() as session:
            return session.query(Skill).limit(limit).offset(offset).all()

    def get_overview_stats(self) -> Dict[str, Any]:
        """Get aggregated overview statistics for the skills library."""
        with get_db_session() as session:
            aggregate_row = (
                session.query(
                    func.count(Skill.skill_id).label("total_skills"),
                    func.coalesce(
                        func.sum(case((Skill.is_active.is_(True), 1), else_=0)),
                        0,
                    ).label("active_skills"),
                    func.coalesce(
                        func.sum(case((Skill.is_active.is_(False), 1), else_=0)),
                        0,
                    ).label("inactive_skills"),
                    func.coalesce(
                        func.sum(case((Skill.skill_type == "agent_skill", 1), else_=0)),
                        0,
                    ).label("agent_skills"),
                    func.coalesce(
                        func.sum(case((Skill.skill_type == "langchain_tool", 1), else_=0)),
                        0,
                    ).label("langchain_tool_skills"),
                    func.coalesce(func.sum(Skill.execution_count), 0).label("total_execution_count"),
                    func.max(Skill.last_executed_at).label("last_executed_at"),
                )
                .one()
            )

            avg_execution_time = (
                session.query(func.avg(Skill.average_execution_time))
                .filter(Skill.execution_count > 0)
                .filter(Skill.average_execution_time.isnot(None))
                .scalar()
                or 0.0
            )

            dependency_rows = session.query(Skill.dependencies).all()
            skills_with_dependencies = sum(
                1
                for (dependencies,) in dependency_rows
                if isinstance(dependencies, list) and len(dependencies) > 0
            )

            last_executed_at = aggregate_row.last_executed_at
            return {
                "total_skills": int(aggregate_row.total_skills or 0),
                "active_skills": int(aggregate_row.active_skills or 0),
                "inactive_skills": int(aggregate_row.inactive_skills or 0),
                "agent_skills": int(aggregate_row.agent_skills or 0),
                "langchain_tool_skills": int(aggregate_row.langchain_tool_skills or 0),
                "skills_with_dependencies": skills_with_dependencies,
                "total_execution_count": int(aggregate_row.total_execution_count or 0),
                "average_execution_time": float(avg_execution_time),
                "last_executed_at": last_executed_at.isoformat() if last_executed_at else None,
            }

    def update_skill(
        self,
        skill_id: UUID,
        description: Optional[str] = None,
        code: Optional[str] = None,
        interface_definition: Optional[dict] = None,
        dependencies: Optional[List[str]] = None,
    ) -> Optional[Skill]:
        """Update skill properties.

        Args:
            skill_id: Skill UUID
            description: New description
            code: New code
            interface_definition: New interface definition
            dependencies: New dependencies

        Returns:
            Updated Skill object or None if not found
        """
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).first()

            if not skill:
                return None

            if description is not None:
                skill.description = description
            if code is not None:
                skill.code = code
            if interface_definition is not None:
                skill.interface_definition = interface_definition
            if dependencies is not None:
                skill.dependencies = dependencies

            session.commit()
            session.refresh(skill)

            logger.info(f"Skill updated: {skill_id}")
            return skill

    def delete_skill(self, skill_id: UUID) -> bool:
        """Delete a skill.

        Args:
            skill_id: Skill UUID

        Returns:
            True if deleted, False if not found
        """
        with get_db_session() as session:
            skill = session.query(Skill).filter(Skill.skill_id == skill_id).first()

            if not skill:
                return False

            skill_name = skill.name
            detached_agent_ids: List[str] = []

            # Keep agent capability lists in sync with active skills.
            # Agent capabilities are stored as skill names, so deleting a skill
            # should remove stale names from all agents that reference it.
            agents = (
                session.query(Agent)
                .filter(Agent.capabilities.isnot(None))
                .filter(Agent.capabilities.contains([skill_name]))
                .all()
            )
            for agent in agents:
                capabilities = agent.capabilities if isinstance(agent.capabilities, list) else []
                normalized = [name for name in capabilities if name != skill_name]
                if normalized != capabilities:
                    agent.capabilities = normalized
                    detached_agent_ids.append(str(agent.agent_id))

            session.delete(skill)
            session.commit()

            logger.info(
                "Skill deleted and detached from agent capabilities",
                extra={
                    "skill_id": str(skill_id),
                    "skill_name": skill_name,
                    "detached_agent_count": len(detached_agent_ids),
                    "detached_agent_ids": detached_agent_ids[:20],
                },
            )
            return True

    def search_skills(self, query: str) -> List[Skill]:
        """Search skills by name or description.

        Args:
            query: Search query

        Returns:
            List of matching Skill objects
        """
        with get_db_session() as session:
            return (
                session.query(Skill)
                .filter((Skill.name.ilike(f"%{query}%")) | (Skill.description.ilike(f"%{query}%")))
                .all()
            )


# Singleton instance
_skill_model: Optional[SkillModel] = None


def get_skill_model() -> SkillModel:
    """Get or create the skill model singleton.

    Returns:
        SkillModel instance
    """
    global _skill_model
    if _skill_model is None:
        _skill_model = SkillModel()
    return _skill_model
