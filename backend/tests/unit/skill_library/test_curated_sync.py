from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from skill_library.curated_sync import _definition_revision_checksum, sync_curated_skills


class _ConfigStub:
    def get(self, _key, default=None):
        return default


class _FakeQuery:
    def __init__(self, skill):
        self.skill = skill

    def options(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self.skill

    def one(self):
        if self.skill is None:
            raise AssertionError("Expected fake skill")
        return self.skill


class _FakeSession:
    def __init__(self, skill):
        self.skill = skill

    def query(self, _model):
        return _FakeQuery(self.skill)


def _session_factory(skill):
    @contextmanager
    def _manager():
        yield _FakeSession(skill)

    return _manager


def _write_curated_skill(tmp_path, *, description="Render docs"):
    skill_dir = tmp_path / "document-artifact-rendering"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: document-artifact-rendering
display_name: Document Artifact Rendering
description: %s
version: 1.0.0
metadata:
  curated: true
---

# Document Artifact Rendering

Use the bundled renderer.
"""
        % description,
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "render_document.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    return skill_dir


@pytest.mark.asyncio
async def test_sync_curated_skills_creates_missing_skill(tmp_path, monkeypatch):
    _write_curated_skill(tmp_path)

    create_skill = MagicMock()
    monkeypatch.setattr("skill_library.curated_sync.get_config", lambda: _ConfigStub())
    monkeypatch.setattr("skill_library.curated_sync.get_db_session", _session_factory(None))
    monkeypatch.setattr(
        "skill_library.curated_sync.PackageHandler",
        lambda *_args, **_kwargs: SimpleNamespace(upload_package=AsyncMock(return_value="skills/package.zip")),
    )
    monkeypatch.setattr("skill_library.curated_sync.get_minio_client", lambda: object())
    monkeypatch.setattr(
        "skill_library.curated_sync.get_canonical_skill_service",
        lambda: SimpleNamespace(create_skill=create_skill),
    )

    summary = await sync_curated_skills(
        run_on_startup=True,
        fail_soft=False,
        curated_root=str(tmp_path),
    )

    assert summary.created_count == 1
    assert summary.updated_count == 0
    create_skill.assert_called_once()


@pytest.mark.asyncio
async def test_sync_curated_skills_skips_unchanged_active_revision(tmp_path, monkeypatch):
    _write_curated_skill(tmp_path)

    monkeypatch.setattr("skill_library.curated_sync.get_config", lambda: _ConfigStub())
    definition_loader = __import__("skill_library.curated_sync", fromlist=["_load_curated_definition"])
    definition = definition_loader._load_curated_definition(tmp_path / "document-artifact-rendering")
    skill = SimpleNamespace(
        skill_id=uuid4(),
        active_revision=SimpleNamespace(checksum=_definition_revision_checksum(definition)),
        display_name=definition.display_name,
        description=definition.description,
        source_kind="curated",
        artifact_kind="instruction",
        runtime_mode="doc",
        visibility="public",
        lifecycle_state="active",
        skill_type="agent_skill",
        is_active=True,
        interface_definition={},
        manifest=definition.manifest,
        homepage=definition.homepage,
        skill_metadata=definition.manifest.get("skill_metadata"),
        gating_status=definition.manifest.get("gating_status"),
        config=definition.config,
    )
    monkeypatch.setattr("skill_library.curated_sync.get_db_session", _session_factory(skill))
    monkeypatch.setattr(
        "skill_library.curated_sync.PackageHandler",
        lambda *_args, **_kwargs: SimpleNamespace(upload_package=AsyncMock(return_value="skills/package.zip")),
    )
    monkeypatch.setattr("skill_library.curated_sync.get_minio_client", lambda: object())
    canonical_service = SimpleNamespace(create_revision=MagicMock(), activate_revision=MagicMock())
    monkeypatch.setattr("skill_library.curated_sync.get_canonical_skill_service", lambda: canonical_service)

    summary = await sync_curated_skills(
        run_on_startup=True,
        fail_soft=False,
        curated_root=str(tmp_path),
    )

    assert summary.skipped_count == 1
    canonical_service.create_revision.assert_not_called()


@pytest.mark.asyncio
async def test_sync_curated_skills_updates_when_package_changes(tmp_path, monkeypatch):
    _write_curated_skill(tmp_path, description="Render docs v2")

    monkeypatch.setattr("skill_library.curated_sync.get_config", lambda: _ConfigStub())
    skill = SimpleNamespace(
        skill_id=uuid4(),
        active_revision=SimpleNamespace(checksum="stale-checksum"),
        display_name="Old",
        description="Old",
        source_kind="manual",
        artifact_kind="instruction",
        runtime_mode="doc",
        visibility="private",
        lifecycle_state="deprecated",
        skill_type="agent_skill",
        is_active=False,
        interface_definition={},
        manifest={},
        homepage=None,
        skill_metadata=None,
        gating_status=None,
        config={},
    )
    monkeypatch.setattr("skill_library.curated_sync.get_db_session", _session_factory(skill))
    monkeypatch.setattr(
        "skill_library.curated_sync.PackageHandler",
        lambda *_args, **_kwargs: SimpleNamespace(upload_package=AsyncMock(return_value="skills/package.zip")),
    )
    monkeypatch.setattr("skill_library.curated_sync.get_minio_client", lambda: object())
    canonical_service = SimpleNamespace(
        create_revision=MagicMock(return_value=SimpleNamespace(revision_id=uuid4())),
        activate_revision=MagicMock(),
    )
    monkeypatch.setattr("skill_library.curated_sync.get_canonical_skill_service", lambda: canonical_service)

    summary = await sync_curated_skills(
        run_on_startup=True,
        fail_soft=False,
        curated_root=str(tmp_path),
    )

    assert summary.updated_count == 1
    canonical_service.create_revision.assert_called_once()
    canonical_service.activate_revision.assert_called_once()


def test_definition_revision_checksum_matches_curated_package_checksum(tmp_path):
    _write_curated_skill(tmp_path, description="Render docs v3")

    definition_loader = __import__("skill_library.curated_sync", fromlist=["_load_curated_definition"])
    definition = definition_loader._load_curated_definition(tmp_path / "document-artifact-rendering")

    assert _definition_revision_checksum(definition) == definition.package_checksum
