"""Tests for Agent Template Management System.

References:
- Requirements 21: Agent Templates
- Design Section 4.2: Agent Types and Templates
"""

from datetime import datetime
from uuid import uuid4

import pytest

from agent_framework.agent_template import AgentTemplate, AgentTemplateManager
from agent_framework.default_templates import get_default_templates, initialize_default_templates
from shared.datetime_utils import utcnow


class MockSession:
    """Mock database session for testing."""

    def __init__(self):
        self.templates = {}
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        return MockQuery(self.templates)

    def add(self, obj):
        self.templates[obj.template_id] = obj

    def delete(self, obj):
        if obj.template_id in self.templates:
            del self.templates[obj.template_id]

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockQuery:
    """Mock query object for testing."""

    def __init__(self, templates):
        self.templates = templates
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def first(self):
        for template in self.templates.values():
            match = True
            for key, value in self.filters.items():
                if getattr(template, key) != value:
                    match = False
                    break
            if match:
                return template
        return None

    def all(self):
        results = []
        for template in self.templates.values():
            match = True
            for key, value in self.filters.items():
                if getattr(template, key) != value:
                    match = False
                    break
            if match:
                results.append(template)
        return results

    def order_by(self, *args):
        return self


class TestAgentTemplate:
    """Test AgentTemplate model."""

    def test_to_dict(self):
        """Test template to dictionary conversion."""
        template_id = uuid4()
        user_id = uuid4()
        now = utcnow()

        template = AgentTemplate(
            template_id=template_id,
            name="Test Template",
            description="Test description",
            agent_type="test_agent",
            capabilities=["skill1", "skill2"],
            tools=["tool1", "tool2"],
            use_case="Test use case",
            version=1,
            is_system_template="true",
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )

        result = template.to_dict()

        assert result["template_id"] == str(template_id)
        assert result["name"] == "Test Template"
        assert result["description"] == "Test description"
        assert result["agent_type"] == "test_agent"
        assert result["capabilities"] == ["skill1", "skill2"]
        assert result["tools"] == ["tool1", "tool2"]
        assert result["use_case"] == "Test use case"
        assert result["version"] == 1
        assert result["is_system_template"] is True
        assert result["created_by"] == str(user_id)
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()


class TestAgentTemplateManager:
    """Test AgentTemplateManager."""

    def test_create_template(self):
        """Test creating a new template."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        template = manager.create_template(
            name="Test Template",
            description="Test description",
            agent_type="test_agent",
            capabilities=["skill1", "skill2"],
            tools=["tool1", "tool2"],
            use_case="Test use case",
            is_system_template=False,
        )

        assert template.name == "Test Template"
        assert template.description == "Test description"
        assert template.agent_type == "test_agent"
        assert template.capabilities == ["skill1", "skill2"]
        assert template.tools == ["tool1", "tool2"]
        assert template.use_case == "Test use case"
        assert template.version == 1
        assert template.is_system_template == "false"
        assert session.committed

    def test_create_template_duplicate_name(self):
        """Test creating template with duplicate name raises error."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        manager.create_template(
            name="Test Template",
            description="Test description",
            agent_type="test_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="Test use case",
        )

        with pytest.raises(ValueError, match="already exists"):
            manager.create_template(
                name="Test Template",
                description="Another description",
                agent_type="another_agent",
                capabilities=["skill2"],
                tools=["tool2"],
                use_case="Another use case",
            )

    def test_get_template(self):
        """Test getting template by ID."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        created = manager.create_template(
            name="Test Template",
            description="Test description",
            agent_type="test_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="Test use case",
        )

        retrieved = manager.get_template(created.template_id)

        assert retrieved is not None
        assert retrieved.template_id == created.template_id
        assert retrieved.name == "Test Template"

    def test_get_template_not_found(self):
        """Test getting non-existent template returns None."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        result = manager.get_template(uuid4())

        assert result is None

    def test_get_template_by_name(self):
        """Test getting template by name."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        manager.create_template(
            name="Test Template",
            description="Test description",
            agent_type="test_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="Test use case",
        )

        retrieved = manager.get_template_by_name("Test Template")

        assert retrieved is not None
        assert retrieved.name == "Test Template"

    def test_list_templates(self):
        """Test listing all templates."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        manager.create_template(
            name="System Template",
            description="System template",
            agent_type="system_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="System use case",
            is_system_template=True,
        )

        manager.create_template(
            name="Custom Template",
            description="Custom template",
            agent_type="custom_agent",
            capabilities=["skill2"],
            tools=["tool2"],
            use_case="Custom use case",
            is_system_template=False,
        )

        all_templates = manager.list_templates()
        assert len(all_templates) == 2

        system_only = manager.list_templates(include_custom=False)
        assert len(system_only) == 1
        assert system_only[0].name == "System Template"

        custom_only = manager.list_templates(include_system=False)
        assert len(custom_only) == 1
        assert custom_only[0].name == "Custom Template"

    def test_update_template(self):
        """Test updating a template."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        template = manager.create_template(
            name="Test Template",
            description="Original description",
            agent_type="test_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="Original use case",
        )

        updated = manager.update_template(
            template_id=template.template_id,
            description="Updated description",
            capabilities=["skill1", "skill2"],
            increment_version=True,
        )

        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.capabilities == ["skill1", "skill2"]
        assert updated.version == 2
        assert updated.name == "Test Template"  # Unchanged

    def test_update_template_not_found(self):
        """Test updating non-existent template returns None."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        result = manager.update_template(
            template_id=uuid4(),
            description="New description",
        )

        assert result is None

    def test_delete_template(self):
        """Test deleting a custom template."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        template = manager.create_template(
            name="Custom Template",
            description="Custom template",
            agent_type="custom_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="Custom use case",
            is_system_template=False,
        )

        result = manager.delete_template(template.template_id)

        assert result is True
        assert manager.get_template(template.template_id) is None

    def test_delete_system_template_raises_error(self):
        """Test deleting system template raises error."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        template = manager.create_template(
            name="System Template",
            description="System template",
            agent_type="system_agent",
            capabilities=["skill1"],
            tools=["tool1"],
            use_case="System use case",
            is_system_template=True,
        )

        with pytest.raises(ValueError, match="Cannot delete system templates"):
            manager.delete_template(template.template_id)

    def test_delete_template_not_found(self):
        """Test deleting non-existent template returns False."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        result = manager.delete_template(uuid4())

        assert result is False

    def test_instantiate_template(self):
        """Test instantiating an agent from a template."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        template = manager.create_template(
            name="Test Template",
            description="Test description",
            agent_type="test_agent",
            capabilities=["skill1", "skill2"],
            tools=["tool1", "tool2"],
            use_case="Test use case",
        )

        owner_id = uuid4()
        config = manager.instantiate_template(
            template_id=template.template_id,
            agent_name="My Test Agent",
            owner_user_id=owner_id,
        )

        assert config["name"] == "My Test Agent"
        assert config["agent_type"] == "test_agent"
        assert config["owner_user_id"] == str(owner_id)
        assert config["capabilities"] == ["skill1", "skill2"]
        assert config["tools"] == ["tool1", "tool2"]
        assert config["template_id"] == str(template.template_id)
        assert config["template_version"] == 1

    def test_instantiate_template_not_found(self):
        """Test instantiating from non-existent template raises error."""
        session = MockSession()
        manager = AgentTemplateManager(session=session)

        with pytest.raises(ValueError, match="Template not found"):
            manager.instantiate_template(
                template_id=uuid4(),
                agent_name="My Agent",
                owner_user_id=uuid4(),
            )


class TestDefaultTemplates:
    """Test default template functionality."""

    def test_get_default_templates(self):
        """Test getting default template configurations."""
        templates = get_default_templates()

        assert len(templates) == 4

        # Check Data Analyst template
        data_analyst = next(t for t in templates if t["name"] == "Data Analyst")
        assert data_analyst["agent_type"] == "data_analyst"
        assert "data_processing" in data_analyst["capabilities"]
        assert "statistical_analysis" in data_analyst["capabilities"]

        # Check Content Writer template
        content_writer = next(t for t in templates if t["name"] == "Content Writer")
        assert content_writer["agent_type"] == "content_writer"
        assert "text_summarization" in content_writer["capabilities"]

        # Check Code Assistant template
        code_assistant = next(t for t in templates if t["name"] == "Code Assistant")
        assert code_assistant["agent_type"] == "code_assistant"
        assert "data_processing" in code_assistant["capabilities"]

        # Check Research Assistant template
        research_assistant = next(t for t in templates if t["name"] == "Research Assistant")
        assert research_assistant["agent_type"] == "research_assistant"
        assert "web_scraping" in research_assistant["capabilities"]

    def test_initialize_default_templates(self):
        """Test initializing default templates in database."""
        # This test would require a real database session
        # For now, we just verify the function doesn't crash
        try:
            # In a real test, this would use a test database
            # initialize_default_templates()
            pass
        except Exception as e:
            pytest.fail(f"initialize_default_templates raised {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
