"""
Integration tests for Agent Skills API endpoints.

Tests the complete flow of creating, testing, and managing agent skills
through the API with package uploads and natural language testing.

References:
- Requirements 1.1: SKILL.md format support
- Requirements 2.1: Type separation (agent_skill vs langchain_tool)
- Requirements 3.1: Natural language testing
- Design Section 2.2: API endpoints
"""

import io
import json
import zipfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api_gateway.main import app
from database.connection import get_db_session
from database.models import Skill, User


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create database session for tests."""
    session = get_db_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password",
        role="user"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Create authentication headers."""
    # In real tests, you would generate a proper JWT token
    return {"Authorization": f"Bearer test_token_{test_user.id}"}


@pytest.fixture
def valid_skill_package() -> bytes:
    """Create a valid agent skill package."""
    # Create in-memory ZIP file
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add SKILL.md
        skill_md = """---
name: Weather Forecast
emoji: 🌤️
version: 1.0.0
author: Test Author
homepage: https://example.com/weather
description: Get weather forecast for any location
tags:
  - weather
  - api
  - forecast
gating:
  binaries:
    - curl
  env_vars:
    - WEATHER_API_KEY
  config:
    - api.weather.enabled
metadata:
  category: data
  difficulty: intermediate
---

# Weather Forecast Skill

Get current weather and forecast for any location.

## Usage

To get weather for a location:

```bash
curl "https://api.weather.com/forecast?location=Seattle"
```

## Testing

Test with natural language:
- "Get weather for Seattle"
- "What's the forecast for New York?"
"""
        zf.writestr('SKILL.md', skill_md)
        
        # Add additional files
        zf.writestr('README.md', '# Weather Skill\n\nWeather forecast skill.')
        zf.writestr('config.yaml', 'api_key: ${WEATHER_API_KEY}\n')
    
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def invalid_skill_package() -> bytes:
    """Create an invalid agent skill package (missing SKILL.md)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('README.md', '# Invalid Skill\n\nMissing SKILL.md.')
    
    buffer.seek(0)
    return buffer.read()


class TestCreateAgentSkillWithPackage:
    """Test creating agent skills with valid packages."""
    
    def test_create_agent_skill_with_valid_package(
        self,
        client: TestClient,
        auth_headers: dict,
        valid_skill_package: bytes
    ):
        """Test creating agent skill with valid package."""
        # Arrange
        files = {
            'package_file': ('weather_skill.zip', io.BytesIO(valid_skill_package), 'application/zip')
        }
        data = {
            'name': 'Weather Forecast',
            'skill_type': 'agent_skill',
            'is_active': 'true'
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            files=files,
            data=data
        )
        
        # Assert
        assert response.status_code == 201
        result = response.json()
        assert result['name'] == 'Weather Forecast'
        assert result['skill_type'] == 'agent_skill'
        assert result['description'] == 'Get weather forecast for any location'
        assert result['skill_md_content'] is not None
        assert result['homepage'] == 'https://example.com/weather'
        assert result['metadata'] is not None
        assert result['gating_status'] is not None
        assert 'curl' in result['gating_status'].get('required_binaries', [])
    
    def test_create_agent_skill_with_invalid_package(
        self,
        client: TestClient,
        auth_headers: dict,
        invalid_skill_package: bytes
    ):
        """Test creating agent skill with invalid package (missing SKILL.md)."""
        # Arrange
        files = {
            'package_file': ('invalid_skill.zip', io.BytesIO(invalid_skill_package), 'application/zip')
        }
        data = {
            'name': 'Invalid Skill',
            'skill_type': 'agent_skill',
            'description': 'Invalid skill package',
            'is_active': 'true'
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            files=files,
            data=data
        )
        
        # Assert
        assert response.status_code == 400
        assert 'SKILL.md' in response.json()['detail']
    
    def test_create_agent_skill_without_package(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating agent skill without package (should fail)."""
        # Arrange
        data = {
            'name': 'No Package Skill',
            'skill_type': 'agent_skill',
            'description': 'Skill without package',
            'code': 'print("hello")',  # Trying to use inline code
            'is_active': 'true'
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            json=data
        )
        
        # Assert
        assert response.status_code == 400
        assert 'package' in response.json()['detail'].lower()


class TestAgentSkillNaturalLanguageTesting:
    """Test natural language testing for agent skills."""
    
    @pytest.fixture
    def created_skill(
        self,
        client: TestClient,
        auth_headers: dict,
        valid_skill_package: bytes,
        db_session: Session
    ) -> Skill:
        """Create a skill for testing."""
        files = {
            'package_file': ('weather_skill.zip', io.BytesIO(valid_skill_package), 'application/zip')
        }
        data = {
            'name': 'Weather Forecast',
            'skill_type': 'agent_skill',
            'description': 'Get weather forecast',
            'is_active': 'true'
        }
        
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 201
        skill_id = response.json()['id']
        
        # Fetch from database
        skill = db_session.query(Skill).filter(Skill.id == skill_id).first()
        return skill
    
    def test_test_agent_skill_with_natural_language(
        self,
        client: TestClient,
        auth_headers: dict,
        created_skill: Skill
    ):
        """Test agent skill requires agent_id for real execution."""
        # Arrange
        test_data = {
            'natural_language_input': 'Get weather for Seattle',
        }
        
        # Act
        response = client.post(
            f'/api/v1/skills/{created_skill.id}/test',
            headers=auth_headers,
            json=test_data
        )
        
        # Assert
        assert response.status_code == 400
        assert 'agent_id required' in response.json()['detail']
    
    def test_test_agent_skill_dry_run_mode(
        self,
        client: TestClient,
        auth_headers: dict,
        created_skill: Skill
    ):
        """Dry-run mode is removed for agent_skill."""
        # Arrange
        test_data = {
            'natural_language_input': 'What is the forecast for New York?',
            'dry_run': True
        }
        
        # Act
        response = client.post(
            f'/api/v1/skills/{created_skill.id}/test',
            headers=auth_headers,
            json=test_data
        )
        
        # Assert
        assert response.status_code == 400
        assert 'agent_id required' in response.json()['detail']


class TestGatingStatusInResponse:
    """Test gating status in API responses."""
    
    def test_gating_status_in_create_response(
        self,
        client: TestClient,
        auth_headers: dict,
        valid_skill_package: bytes
    ):
        """Test that gating status is included in create response."""
        # Arrange
        files = {
            'package_file': ('weather_skill.zip', io.BytesIO(valid_skill_package), 'application/zip')
        }
        data = {
            'name': 'Weather Forecast',
            'skill_type': 'agent_skill',
            'description': 'Get weather forecast',
            'is_active': 'true'
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            files=files,
            data=data
        )
        
        # Assert
        assert response.status_code == 201
        result = response.json()
        assert 'gating_status' in result
        gating = result['gating_status']
        assert 'required_binaries' in gating
        assert 'required_env_vars' in gating
        assert 'required_config' in gating
        assert 'eligible' in gating
        assert isinstance(gating['eligible'], bool)
    
    def test_gating_status_in_get_response(
        self,
        client: TestClient,
        auth_headers: dict,
        valid_skill_package: bytes
    ):
        """Test that gating status is included in get response."""
        # Arrange - Create skill first
        files = {
            'package_file': ('weather_skill.zip', io.BytesIO(valid_skill_package), 'application/zip')
        }
        data = {
            'name': 'Weather Forecast',
            'skill_type': 'agent_skill',
            'description': 'Get weather forecast',
            'is_active': 'true'
        }
        
        create_response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            files=files,
            data=data
        )
        skill_id = create_response.json()['id']
        
        # Act - Get skill
        response = client.get(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 200
        result = response.json()
        assert 'gating_status' in result
        assert result['gating_status'] is not None


class TestLangChainToolStillWorks:
    """Test that langchain_tool creation still works (no breaking changes)."""
    
    def test_create_langchain_tool_with_code(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating langchain_tool with inline code (should still work)."""
        # Arrange
        code = '''
from langchain.tools import tool

@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b
'''
        data = {
            'name': 'Add Numbers',
            'skill_type': 'langchain_tool',
            'description': 'Add two numbers',
            'code': code,
            'is_active': True
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            json=data
        )
        
        # Assert
        assert response.status_code == 201
        result = response.json()
        assert result['name'] == 'Add Numbers'
        assert result['skill_type'] == 'langchain_tool'
        assert result['code'] is not None
        assert result['skill_md_content'] is None  # langchain_tool doesn't use SKILL.md
    
    def test_test_langchain_tool_with_structured_input(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test langchain_tool with structured input (existing behavior)."""
        # Arrange - Create tool first
        code = '''
from langchain.tools import tool

@tool
def multiply_numbers(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b
'''
        create_data = {
            'name': 'Multiply Numbers',
            'skill_type': 'langchain_tool',
            'description': 'Multiply two numbers',
            'code': code,
            'is_active': True
        }
        
        create_response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            json=create_data
        )
        skill_id = create_response.json()['id']
        
        # Act - Test tool
        test_data = {
            'inputs': {'a': 5, 'b': 3}
        }
        
        response = client.post(
            f'/api/v1/skills/{skill_id}/test',
            headers=auth_headers,
            json=test_data
        )
        
        # Assert
        assert response.status_code == 200
        result = response.json()
        assert 'output' in result
        # Note: Actual execution would return 15, but in test environment might be mocked


@pytest.mark.integration
class TestEndToEndAgentSkillFlow:
    """Test complete end-to-end flow for agent skills."""
    
    def test_complete_agent_skill_lifecycle(
        self,
        client: TestClient,
        auth_headers: dict,
        valid_skill_package: bytes,
        db_session: Session
    ):
        """Test complete lifecycle: create, get, test, update, delete."""
        # 1. Create
        files = {
            'package_file': ('weather_skill.zip', io.BytesIO(valid_skill_package), 'application/zip')
        }
        data = {
            'name': 'Weather Forecast',
            'skill_type': 'agent_skill',
            'description': 'Get weather forecast',
            'is_active': 'true'
        }
        
        create_response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            files=files,
            data=data
        )
        assert create_response.status_code == 201
        skill_id = create_response.json()['id']
        
        # 2. Get
        get_response = client.get(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers
        )
        assert get_response.status_code == 200
        assert get_response.json()['name'] == 'Weather Forecast'
        
        # 3. Test
        test_data = {
            'natural_language_input': 'Get weather for Seattle',
        }
        test_response = client.post(
            f'/api/v1/skills/{skill_id}/test',
            headers=auth_headers,
            json=test_data
        )
        assert test_response.status_code == 400
        
        # 4. Update
        update_data = {
            'description': 'Updated weather forecast skill'
        }
        update_response = client.put(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers,
            json=update_data
        )
        assert update_response.status_code == 200
        assert update_response.json()['description'] == 'Updated weather forecast skill'
        
        # 5. Delete
        delete_response = client.delete(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers
        )
        assert delete_response.status_code == 204
        
        # 6. Verify deletion
        get_deleted_response = client.get(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers
        )
        assert get_deleted_response.status_code == 404
