"""Agent Template Management System.

This module provides functionality for managing pre-configured agent templates
that allow users to quickly create agents for common use cases.

References:
- Requirements 21: Agent Templates
- Design Section 4.2: Agent Types and Templates
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, Column, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session

from database.connection import get_db_session
from database.models import Base

logger = logging.getLogger(__name__)


class AgentTemplate(Base):
    """Agent template model for storing pre-configured agent configurations."""

    __tablename__ = "agent_templates"

    template_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(1000), nullable=False)
    agent_type = Column(String(100), nullable=False)
    capabilities = Column(JSON, nullable=False)  # List of skill names
    tools = Column(JSON, nullable=False)  # List of tool names
    use_case = Column(String(500), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    is_system_template = Column(String(10), nullable=False, default="true")
    created_by = Column(PGUUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary representation."""
        return {
            "template_id": str(self.template_id),
            "name": self.name,
            "description": self.description,
            "agent_type": self.agent_type,
            "capabilities": self.capabilities,
            "tools": self.tools,
            "use_case": self.use_case,
            "version": self.version,
            "is_system_template": self.is_system_template == "true",
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentTemplateManager:
    """Manager for agent template operations."""

    def __init__(self, session: Optional[Session] = None):
        """Initialize the template manager.

        Args:
            session: Optional database session. If not provided, a new session will be created.
        """
        self.session = session
        self._own_session = session is None

    def __enter__(self):
        """Context manager entry."""
        if self._own_session:
            self.session = get_db_session().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._own_session and self.session:
            self.session.__exit__(exc_type, exc_val, exc_tb)

    def create_template(
        self,
        name: str,
        description: str,
        agent_type: str,
        capabilities: List[str],
        tools: List[str],
        use_case: str,
        created_by: Optional[UUID] = None,
        is_system_template: bool = False,
    ) -> AgentTemplate:
        """Create a new agent template.

        Args:
            name: Template name
            description: Template description
            agent_type: Type of agent (e.g., "data_analyst", "content_writer")
            capabilities: List of skill names
            tools: List of tool names
            use_case: Description of the use case
            created_by: User ID who created the template (None for system templates)
            is_system_template: Whether this is a system-provided template

        Returns:
            Created AgentTemplate instance

        Raises:
            ValueError: If template with same name already exists
        """
        # Check if template with same name exists
        existing = self.session.query(AgentTemplate).filter_by(name=name).first()
        if existing:
            raise ValueError(f"Template with name '{name}' already exists")

        template = AgentTemplate(
            template_id=uuid4(),
            name=name,
            description=description,
            agent_type=agent_type,
            capabilities=capabilities,
            tools=tools,
            use_case=use_case,
            version=1,
            is_system_template="true" if is_system_template else "false",
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.session.add(template)
        self.session.commit()

        logger.info(
            "Created agent template",
            extra={
                "template_id": str(template.template_id),
                "name": name,
                "agent_type": agent_type,
                "is_system_template": is_system_template,
            },
        )

        return template

    def get_template(self, template_id: UUID) -> Optional[AgentTemplate]:
        """Get template by ID.

        Args:
            template_id: Template UUID

        Returns:
            AgentTemplate instance or None if not found
        """
        return self.session.query(AgentTemplate).filter_by(template_id=template_id).first()

    def get_template_by_name(self, name: str) -> Optional[AgentTemplate]:
        """Get template by name.

        Args:
            name: Template name

        Returns:
            AgentTemplate instance or None if not found
        """
        return self.session.query(AgentTemplate).filter_by(name=name).first()

    def list_templates(
        self, include_custom: bool = True, include_system: bool = True
    ) -> List[AgentTemplate]:
        """List all available templates.

        Args:
            include_custom: Whether to include custom templates
            include_system: Whether to include system templates

        Returns:
            List of AgentTemplate instances
        """
        query = self.session.query(AgentTemplate)

        if not include_custom and not include_system:
            return []

        if not include_custom:
            query = query.filter_by(is_system_template="true")
        elif not include_system:
            query = query.filter_by(is_system_template="false")

        return query.order_by(AgentTemplate.name).all()

    def update_template(
        self,
        template_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        use_case: Optional[str] = None,
        increment_version: bool = True,
    ) -> Optional[AgentTemplate]:
        """Update an existing template.

        Args:
            template_id: Template UUID
            name: New name (optional)
            description: New description (optional)
            capabilities: New capabilities list (optional)
            tools: New tools list (optional)
            use_case: New use case (optional)
            increment_version: Whether to increment version number

        Returns:
            Updated AgentTemplate instance or None if not found
        """
        template = self.get_template(template_id)
        if not template:
            return None

        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if capabilities is not None:
            template.capabilities = capabilities
        if tools is not None:
            template.tools = tools
        if use_case is not None:
            template.use_case = use_case

        if increment_version:
            template.version += 1

        template.updated_at = datetime.utcnow()

        self.session.commit()

        logger.info(
            "Updated agent template",
            extra={
                "template_id": str(template_id),
                "version": template.version,
            },
        )

        return template

    def delete_template(self, template_id: UUID) -> bool:
        """Delete a template.

        Args:
            template_id: Template UUID

        Returns:
            True if deleted, False if not found
        """
        template = self.get_template(template_id)
        if not template:
            return False

        # Don't allow deletion of system templates
        if template.is_system_template == "true":
            logger.warning(
                "Attempted to delete system template",
                extra={"template_id": str(template_id), "name": template.name},
            )
            raise ValueError("Cannot delete system templates")

        self.session.delete(template)
        self.session.commit()

        logger.info(
            "Deleted agent template",
            extra={"template_id": str(template_id), "name": template.name},
        )

        return True

    def instantiate_template(
        self, template_id: UUID, agent_name: str, owner_user_id: UUID
    ) -> Dict[str, Any]:
        """Instantiate an agent from a template.

        Args:
            template_id: Template UUID
            agent_name: Name for the new agent
            owner_user_id: User ID who owns the agent

        Returns:
            Dictionary with agent configuration

        Raises:
            ValueError: If template not found
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        agent_config = {
            "name": agent_name,
            "agent_type": template.agent_type,
            "owner_user_id": str(owner_user_id),
            "capabilities": template.capabilities,
            "tools": template.tools,
            "template_id": str(template_id),
            "template_version": template.version,
        }

        logger.info(
            "Instantiated agent from template",
            extra={
                "template_id": str(template_id),
                "template_name": template.name,
                "agent_name": agent_name,
                "owner_user_id": str(owner_user_id),
            },
        )

        return agent_config
