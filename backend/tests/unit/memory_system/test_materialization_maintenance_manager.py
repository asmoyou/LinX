"""Unit tests for scheduled materialization maintenance."""

from unittest.mock import Mock, patch

import pytest

from memory_system.materialization_maintenance_manager import (
    MaterializationMaintenanceManager,
    MaterializationMaintenanceSettings,
    load_materialization_maintenance_settings,
    run_materialization_maintenance_once,
)


class _ConfigStub:
    def __init__(self, section):
        self._section = section

    def get(self, key, default=None):
        if key == "memory.materialization_maintenance":
            return self._section
        return default


def test_load_materialization_maintenance_settings_uses_defaults_for_missing_fields():
    settings = load_materialization_maintenance_settings(_ConfigStub({"enabled": True}))

    assert settings.enabled is True
    assert settings.run_on_startup is True
    assert settings.startup_delay_seconds == 180
    assert settings.interval_seconds == 21600
    assert settings.limit == 5000
    assert settings.include_backfill is True
    assert settings.include_consolidation is True


def test_run_materialization_maintenance_once_returns_disabled_when_not_enabled():
    result = run_materialization_maintenance_once(
        MaterializationMaintenanceSettings(enabled=False),
        reason="scheduled",
    )

    assert result["status"] == "disabled"
    assert result["reason"] == "scheduled"
    assert result["maintenance"] is None


@patch("memory_system.materialization_maintenance_manager._acquire_advisory_lock")
def test_run_materialization_maintenance_once_skips_when_lock_unavailable(mock_acquire):
    mock_acquire.return_value = None
    settings = MaterializationMaintenanceSettings(enabled=True).with_defaults()

    result = run_materialization_maintenance_once(settings, reason="scheduled")

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "lock_not_acquired"


@patch("memory_system.materialization_maintenance_manager._release_advisory_lock")
@patch("memory_system.materialization_maintenance_manager._acquire_advisory_lock")
@patch("memory_system.materialization_maintenance_manager.get_materialization_maintenance_service")
def test_run_materialization_maintenance_once_delegates_to_service(
    mock_get_service,
    mock_acquire,
    mock_release,
):
    lock_session = object()
    mock_acquire.return_value = lock_session
    mock_service = Mock()
    mock_service.run_maintenance.return_value = object()
    mock_service.to_dict.return_value = {
        "backfill": {
            "dry_run": False,
            "user_profile_upserts": 2,
            "agent_experience_upserts": 1,
        },
        "consolidation": {
            "dry_run": False,
            "user_status_updates": 3,
            "agent_status_updates": 4,
            "agent_duplicate_supersedes": 1,
        },
    }
    mock_get_service.return_value = mock_service

    result = run_materialization_maintenance_once(
        MaterializationMaintenanceSettings(
            enabled=True,
            dry_run=False,
            limit=250,
            include_backfill=True,
            include_consolidation=True,
            user_id="user-123",
            agent_id="agent-123",
        ),
        reason="startup",
    )

    assert result["status"] == "ok"
    assert result["total_upserts"] == 3
    assert result["total_updates"] == 8
    mock_service.run_maintenance.assert_called_once_with(
        dry_run=False,
        user_id="user-123",
        agent_id="agent-123",
        limit=250,
        include_backfill=True,
        include_consolidation=True,
    )
    mock_release.assert_called_once_with(73012020, lock_session)


@pytest.mark.asyncio
async def test_materialization_maintenance_manager_start_returns_false_when_disabled():
    manager = MaterializationMaintenanceManager(
        MaterializationMaintenanceSettings(enabled=False),
    )

    started = await manager.start()

    assert started is False
