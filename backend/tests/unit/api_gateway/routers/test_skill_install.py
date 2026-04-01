from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from access_control.permissions import CurrentUser
from api_gateway.routers import skills as skills_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(skills_router.router, prefix="/skills")
    app.dependency_overrides[skills_router.get_current_user] = lambda: CurrentUser(
        user_id="00000000-0000-0000-0000-000000000001",
        username="alice",
        role="admin",
    )
    return TestClient(app)


def _curated_skill(skill_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        skill_id=skill_id,
        skill_slug="document-artifact-rendering",
        display_name="Document Artifact Rendering",
        description="Render document artifacts",
        version="1.0.0",
        interface_definition={"inputs": {}, "outputs": {}},
        dependencies=[],
        access_level="public",
        created_by=None,
        department_id=None,
        department_name=None,
        runtime_mode="doc",
        artifact_kind="instruction",
        skill_type="agent_skill",
        source_kind="curated",
        storage_type="minio",
        storage_path="skills/document/package.zip",
        manifest={"skill_metadata": {"curated": True}},
        config={},
        skill_md_content="# skill",
        code=None,
        active_revision_id=str(uuid4()),
        lifecycle_state="active",
        is_active=True,
        execution_count=0,
        average_execution_time=0.0,
        last_executed_at=None,
        created_at=None,
        updated_at=None,
    )


def test_list_store_skills_marks_install_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_id = str(uuid4())
    monkeypatch.setattr(
        skills_router,
        "get_skill_registry",
        lambda: SimpleNamespace(
            list_visible_skills=lambda **_kwargs: [_curated_skill(skill_id)],
        ),
    )
    monkeypatch.setattr(
        skills_router,
        "_find_installed_curated_skill",
        lambda **_kwargs: SimpleNamespace(skill_id="installed-1", skill_slug="installed-skill"),
    )

    response = client.get("/skills/store")

    assert response.status_code == 200
    assert response.json()[0]["skill_id"] == skill_id
    assert response.json()[0]["isInstalled"] is True
    assert response.json()[0]["installedSkillId"] == "installed-1"


def test_install_store_skill_creates_installed_copy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical_skill_id = str(uuid4())
    installed_skill_id = str(uuid4())
    installed_slug = "document-artifact-rendering-installed-00000000"

    monkeypatch.setattr(
        skills_router,
        "get_skill_registry",
        lambda: SimpleNamespace(
            get_skill=lambda skill_uuid: _curated_skill(str(skill_uuid))
            if str(skill_uuid) == canonical_skill_id
            else SimpleNamespace(skill_id=installed_skill_id, skill_slug=installed_slug, source_kind="curated_install"),
        ),
    )
    monkeypatch.setattr(skills_router, "_find_installed_curated_skill", lambda **_kwargs: None)
    monkeypatch.setattr(skills_router, "generate_unique_skill_slug", lambda *_args, **_kwargs: installed_slug)
    create_calls = []
    monkeypatch.setattr(
        skills_router,
        "get_canonical_skill_service",
        lambda: SimpleNamespace(
            create_skill=lambda **kwargs: create_calls.append(kwargs) or SimpleNamespace(skill_id=installed_skill_id)
        ),
    )

    response = client.post(f"/skills/{canonical_skill_id}/install")

    assert response.status_code == 201
    assert response.json() == {
        "installedSkillId": installed_skill_id,
        "installedSkillSlug": installed_slug,
        "canonicalSkillId": canonical_skill_id,
        "source": "curated_install",
    }
    assert create_calls[0]["source_kind"] == "curated_install"
    assert create_calls[0]["visibility"] == "private"


def test_uninstall_store_skill_deletes_installed_copy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical_skill_id = str(uuid4())
    installed_skill_id = uuid4()
    monkeypatch.setattr(
        skills_router,
        "_find_installed_curated_skill",
        lambda **_kwargs: SimpleNamespace(skill_id=installed_skill_id),
    )
    deleted = []
    monkeypatch.setattr(
        skills_router,
        "get_canonical_skill_service",
        lambda: SimpleNamespace(delete_skill=lambda **kwargs: deleted.append(kwargs) or True),
    )

    response = client.delete(f"/skills/{canonical_skill_id}/install")

    assert response.status_code == 204
    assert deleted == [{"skill_id": installed_skill_id}]
