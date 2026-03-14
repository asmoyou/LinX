from unittest.mock import MagicMock

from user_memory.consolidator import UserMemoryConsolidator


def test_user_memory_consolidator_delegates_to_maintenance_service() -> None:
    service = MagicMock()
    service.consolidate_projections.return_value = {"ok": True}

    consolidator = UserMemoryConsolidator(service=service)
    result = consolidator.consolidate(dry_run=False, user_id="user-1", limit=25)

    assert result == {"ok": True}
    assert service.consolidate_projections.call_args.kwargs == {
        "dry_run": False,
        "user_id": "user-1",
        "agent_id": None,
        "limit": 25,
    }
