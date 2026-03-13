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
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import ARRAY, JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from api_gateway.main import app
from access_control.jwt_auth import create_access_token
from database.connection import close_connection_pool
from database.models import Base, Skill, User


def _unique_skill_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _error_message(response) -> str:
    payload = response.json()
    return str(payload.get("detail") or payload.get("message") or payload)


@pytest.fixture(autouse=True)
def _disable_persistent_session_validation(monkeypatch):
    """Keep API skill tests focused on skills behavior rather than session revocation storage."""
    monkeypatch.setattr("access_control.permissions.ensure_session_not_revoked", lambda *_: None)


@pytest.fixture(autouse=True)
def _fake_minio_client(monkeypatch):
    """Replace MinIO with an in-memory object store for API skill tests."""

    class FakeMinioClient:
        def __init__(self):
            self.buckets = {
                "artifacts": "agent-artifacts",
                "documents": "documents",
            }
            self._objects = {}

        def upload_file(
            self,
            bucket_type,
            file_data,
            filename,
            user_id,
            task_id=None,
            agent_id=None,
            content_type=None,
            metadata=None,
        ):
            bucket_name = self.buckets.get(bucket_type, bucket_type)
            object_key = f"{user_id}/{uuid.uuid4()}_{filename}"
            payload = file_data.read() if hasattr(file_data, "read") else file_data
            self._objects[(bucket_name, object_key)] = (payload, metadata or {})
            return bucket_name, object_key

        def download_file(self, bucket_name, object_key):
            payload, metadata = self._objects[(bucket_name, object_key)]
            return io.BytesIO(payload), metadata

        def delete_file(self, bucket_name, object_key):
            self._objects.pop((bucket_name, object_key), None)

    fake_client = FakeMinioClient()
    monkeypatch.setattr("api_gateway.routers.skills.get_minio_client", lambda: fake_client)
    monkeypatch.setattr("object_storage.minio_client.get_minio_client", lambda: fake_client)
    yield fake_client


@pytest.fixture
def _sqlite_session_factory(monkeypatch, tmp_path) -> Generator[sessionmaker, None, None]:
    """Provide a file-backed SQLite session factory for API integration tests."""
    import skill_library.skill_model as skill_model_module
    import skill_library.skill_registry as skill_registry_module

    db_path = tmp_path / "agent_skills_api.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, ARRAY):
                column.type = JSON()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    @contextmanager
    def _get_db_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    close_connection_pool()
    monkeypatch.setattr("database.connection.get_db_session", _get_db_session)
    monkeypatch.setattr(skill_model_module, "get_db_session", _get_db_session)
    skill_model_module._skill_model = None
    skill_registry_module._skill_registry = None
    yield SessionLocal
    skill_model_module._skill_model = None
    skill_registry_module._skill_registry = None
    close_connection_pool()
    engine.dispose()


@pytest.fixture
def client(_sqlite_session_factory) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def db_session(_sqlite_session_factory) -> Generator[Session, None, None]:
    """Create database session for tests."""
    session = _sqlite_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create test user."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"testuser-{suffix}",
        email=f"test-{suffix}@example.com",
        password_hash="hashed_password",
        role="user"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Create real JWT auth headers for middleware-protected routes."""
    access_token = create_access_token(test_user.user_id, test_user.username, test_user.role)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def valid_skill_package() -> bytes:
    """Create a valid agent skill package."""
    # Create in-memory ZIP file
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add SKILL.md
        skill_md = """---
name: weather_forecast
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
            'name': _unique_skill_name('Weather-Forecast'),
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
        assert result['name'] == data['name']
        assert result['skill_type'] == 'agent_skill'
        assert result['description'] == 'Get weather forecast for any location'
        assert result['skill_md_content'] is not None
        assert result['homepage'] == 'https://example.com/weather'
        assert result['skill_metadata'] is not None
        assert result['gating_status'] is not None
        assert 'missing_bins' in result['gating_status']
        assert 'missing_env' in result['gating_status']
        assert 'missing_config' in result['gating_status']
    
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
            'name': _unique_skill_name('Invalid-Skill'),
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
        assert 'SKILL.md' in _error_message(response)
    
    def test_create_agent_skill_without_package(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating agent skill without package (should fail)."""
        # Arrange
        data = {
            'name': _unique_skill_name('No-Package-Skill'),
            'skill_type': 'agent_skill',
            'description': 'Skill without package',
            'code': 'print("hello")',  # Trying to use inline code
            'is_active': 'true'
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            data=data
        )

        # Assert
        assert response.status_code == 400
        assert 'package' in _error_message(response).lower()


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
            'name': _unique_skill_name('Weather-Forecast'),
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
        skill_id = uuid.UUID(response.json()['skill_id'])

        # Fetch from database
        skill = db_session.query(Skill).filter(Skill.skill_id == skill_id).first()
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
            f'/api/v1/skills/{created_skill.skill_id}/test',
            headers=auth_headers,
            json=test_data
        )

        # Assert
        assert response.status_code == 400
        assert 'agent_id required' in _error_message(response)
    
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
            f'/api/v1/skills/{created_skill.skill_id}/test',
            headers=auth_headers,
            json=test_data
        )

        # Assert
        assert response.status_code == 400
        assert 'agent_id required' in _error_message(response)


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
            'name': _unique_skill_name('Weather-Forecast'),
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
        assert 'missing_bins' in gating
        assert 'missing_env' in gating
        assert 'missing_config' in gating
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
            'name': _unique_skill_name('Weather-Forecast'),
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
        skill_id = create_response.json()['skill_id']
        
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
            'name': _unique_skill_name('Add-Numbers'),
            'skill_type': 'langchain_tool',
            'description': 'Add two numbers',
            'code': code,
            'is_active': True
        }
        
        # Act
        response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            data=data
        )
        
        # Assert
        assert response.status_code == 201
        result = response.json()
        assert result['name'] == data['name']
        assert result['skill_type'] == 'langchain_tool'
        assert result['code'] is None
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
            'name': _unique_skill_name('Multiply-Numbers'),
            'skill_type': 'langchain_tool',
            'description': 'Multiply two numbers',
            'code': code,
            'is_active': True
        }
        
        create_response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            data=create_data
        )
        skill_id = create_response.json()['skill_id']
        
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
    """Test complete end-to-end flow for skill CRUD lifecycle."""
    
    def test_complete_agent_skill_lifecycle(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Test complete lifecycle: create, get, test, update, delete."""
        # 1. Create
        code = '''
from langchain.tools import tool

@tool
def subtract_numbers(a: int, b: int) -> int:
    """Subtract two numbers."""
    return a - b
'''
        data = {
            'name': _unique_skill_name('Subtract-Numbers'),
            'skill_type': 'langchain_tool',
            'description': 'Subtract two numbers',
            'code': code,
            'is_active': True,
        }
        
        create_response = client.post(
            '/api/v1/skills',
            headers=auth_headers,
            data=data
        )
        assert create_response.status_code == 201
        skill_id = create_response.json()['skill_id']
        
        # 2. Get
        get_response = client.get(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers
        )
        assert get_response.status_code == 200
        assert get_response.json()['name'] == data['name']
        
        # 3. Test
        test_data = {
            'inputs': {'a': 9, 'b': 4},
        }
        test_response = client.post(
            f'/api/v1/skills/{skill_id}/test',
            headers=auth_headers,
            json=test_data
        )
        assert test_response.status_code == 200
        
        # 4. Update
        update_data = {
            'description': 'Updated subtraction skill'
        }
        update_response = client.put(
            f'/api/v1/skills/{skill_id}',
            headers=auth_headers,
            json=update_data
        )
        assert update_response.status_code == 200
        assert update_response.json()['description'] == 'Updated subtraction skill'
        
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
