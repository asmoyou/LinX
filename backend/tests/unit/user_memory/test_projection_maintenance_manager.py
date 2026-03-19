from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from user_memory.projection_maintenance_manager import (
    ProjectionMaintenanceSettings,
    load_projection_maintenance_settings,
    run_projection_maintenance_once,
)


class _ConfigStub:
    def __init__(self, section):
        self._section = section

    def get(self, key, default=None):
        if key == "user_memory.consolidation":
            return self._section
        return default


def test_load_projection_maintenance_settings_uses_current_keys_only() -> None:
    settings = load_projection_maintenance_settings(_ConfigStub({"enabled": True, "limit": 1200}))

    assert settings.enabled is True
    assert settings.limit == 1200
    assert settings.run_on_startup is True
    assert settings.interval_seconds == 21600


@patch("user_memory.projection_maintenance_manager._acquire_advisory_lock")
@patch("user_memory.projection_maintenance_manager.get_projection_maintenance_service")
def test_run_projection_maintenance_once_delegates_without_backfill_flags(
    mock_get_service,
    mock_acquire,
) -> None:
    mock_acquire.return_value = None
    settings = ProjectionMaintenanceSettings(enabled=True, use_advisory_lock=False)

    service = MagicMock()
    service.run_maintenance.return_value = SimpleNamespace()
    service.to_dict.return_value = {
        "consolidation": {
            "user_status_updates": 1,
            "skill_candidate_status_updates": 2,
            "skill_candidate_duplicate_supersedes": 3,
            "user_entry_status_updates": 4,
            "user_duplicate_entry_supersedes": 5,
        }
    }
    mock_get_service.return_value = service

    result = run_projection_maintenance_once(settings, reason="manual")

    assert result["status"] == "ok"
    assert result["total_updates"] == 15
    assert service.run_maintenance.call_args.kwargs == {
        "dry_run": False,
        "limit": 5000,
    }
