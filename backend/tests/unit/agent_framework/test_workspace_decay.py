from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from agent_framework.conversation_workspace_decay import (
    ConversationWorkspaceDecayService,
    ConversationWorkspaceDecaySettings,
    RETENTION_CLASS_DURABLE,
    RETENTION_CLASS_EPHEMERAL,
    RETENTION_CLASS_REBUILDABLE,
    RETENTION_CLASS_STATEFUL_RUNTIME,
)


def test_classify_relative_path_uses_expected_classes() -> None:
    service = ConversationWorkspaceDecayService(
        settings=ConversationWorkspaceDecaySettings(enabled=True)
    )

    assert service.classify_relative_path("output/report.md") == RETENTION_CLASS_DURABLE
    assert service.classify_relative_path("shared/final.csv") == RETENTION_CLASS_DURABLE
    assert service.classify_relative_path("input/source.pdf") == RETENTION_CLASS_REBUILDABLE
    assert service.classify_relative_path("logs/run.log") == RETENTION_CLASS_EPHEMERAL
    assert service.classify_relative_path("tasks/step.txt") == RETENTION_CLASS_EPHEMERAL
    assert (
        service.classify_relative_path(".linx_runtime/python_deps/pkg/file.py")
        == RETENTION_CLASS_STATEFUL_RUNTIME
    )


def test_decay_workspace_deletes_ephemeral_and_old_rebuildable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    keep_file = workdir / "output" / "final.md"
    keep_file.parent.mkdir(parents=True, exist_ok=True)
    keep_file.write_text("deliverable", encoding="utf-8")

    ephemeral_file = workdir / "logs" / "run.log"
    ephemeral_file.parent.mkdir(parents=True, exist_ok=True)
    ephemeral_file.write_text("temp", encoding="utf-8")

    rebuildable_file = workdir / "input" / "data.csv"
    rebuildable_file.parent.mkdir(parents=True, exist_ok=True)
    rebuildable_file.write_text("old", encoding="utf-8")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    Path(rebuildable_file).touch()
    import os

    os.utime(rebuildable_file, (old_timestamp, old_timestamp))

    service = ConversationWorkspaceDecayService(
        settings=ConversationWorkspaceDecaySettings(
            enabled=True,
            rebuildable_ttl_hours=24,
            soft_limit_mb=500,
            hard_limit_mb=1024,
        )
    )
    monkeypatch.setattr(service, "_load_recent_durable_paths", lambda conversation_id: set())

    result = service.decay_workspace(
        conversation_id=uuid4(),
        workdir=workdir,
    )

    assert not ephemeral_file.exists()
    assert not rebuildable_file.exists()
    assert keep_file.exists()
    assert "logs/run.log" in result["deleted_paths"]
    assert "input/data.csv" in result["deleted_paths"]
    assert result["retention_index"]["output/final.md"] == RETENTION_CLASS_DURABLE


def test_decay_workspace_never_deletes_workdir_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "workspace"
    log_file = workdir / "logs" / "run.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("temp", encoding="utf-8")

    service = ConversationWorkspaceDecayService(
        settings=ConversationWorkspaceDecaySettings(enabled=True)
    )
    monkeypatch.setattr(service, "_load_recent_durable_paths", lambda conversation_id: set())

    service.decay_workspace(conversation_id=uuid4(), workdir=workdir)

    assert workdir.exists()
    assert workdir.is_dir()
