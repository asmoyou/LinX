"""Unit tests for scheduled user-memory session-ledger retention cleanup."""

from unittest.mock import Mock, patch

import pytest

from user_memory.retention_manager import (
    SessionLedgerRetentionManager,
    SessionLedgerRetentionSettings,
    load_session_ledger_retention_settings,
    run_session_ledger_retention_once,
)


class _ConfigStub:
    def __init__(self, section):
        self._section = section

    def get(self, key, default=None):
        if key == "session_ledger":
            return self._section
        return default


def test_load_session_ledger_retention_settings_uses_defaults_for_missing_fields():
    settings = load_session_ledger_retention_settings(_ConfigStub({"enabled": True}))

    assert settings.enabled is True
    assert settings.retention_days == 14
    assert settings.batch_size == 1000


def test_run_session_ledger_retention_once_returns_disabled_when_not_enabled():
    result = run_session_ledger_retention_once(
        SessionLedgerRetentionSettings(enabled=False),
        reason="scheduled",
    )

    assert result["status"] == "disabled"
    assert result["cleanup"] is None


@patch("user_memory.retention_manager._acquire_advisory_lock")
def test_run_session_ledger_retention_once_skips_when_lock_unavailable(mock_acquire):
    mock_acquire.return_value = None
    settings = SessionLedgerRetentionSettings(enabled=True).with_defaults()

    result = run_session_ledger_retention_once(settings, reason="scheduled")

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "lock_not_acquired"


@patch("user_memory.retention_manager._release_advisory_lock")
@patch("user_memory.retention_manager._acquire_advisory_lock")
@patch("user_memory.retention_manager.get_session_ledger_repository")
def test_run_session_ledger_retention_once_delegates_to_repository(
    mock_get_repository,
    mock_acquire,
    mock_release,
):
    lock_session = object()
    mock_acquire.return_value = lock_session
    mock_repo = Mock()
    mock_repo.cleanup_sessions_ended_before.return_value = {"deleted_sessions": 4}
    mock_get_repository.return_value = mock_repo

    result = run_session_ledger_retention_once(
        SessionLedgerRetentionSettings(
            enabled=True,
            retention_days=21,
            dry_run=False,
            batch_size=250,
        ),
        reason="startup",
    )

    assert result["status"] == "ok"
    assert result["cleanup"]["deleted_sessions"] == 4
    mock_release.assert_called_once_with(73012021, lock_session)


@pytest.mark.asyncio
async def test_session_ledger_retention_manager_start_returns_false_when_disabled():
    manager = SessionLedgerRetentionManager(SessionLedgerRetentionSettings(enabled=False))

    started = await manager.start()

    assert started is False
