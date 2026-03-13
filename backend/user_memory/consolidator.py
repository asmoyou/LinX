"""Consolidation facade for reset-era user memory."""

from __future__ import annotations

from typing import Optional

from user_memory.materialization_maintenance_service import (
    MaterializationConsolidationResult,
    MaterializationMaintenanceService,
    get_materialization_maintenance_service,
)


class UserMemoryConsolidator:
    """Consolidate duplicate or superseded user-memory facts and views."""

    def __init__(self, service: Optional[MaterializationMaintenanceService] = None):
        self._service = service or get_materialization_maintenance_service()

    def consolidate(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> MaterializationConsolidationResult:
        return self._service.consolidate_materializations(
            dry_run=dry_run,
            user_id=user_id,
            agent_id=None,
            limit=limit,
        )


_user_memory_consolidator: Optional[UserMemoryConsolidator] = None


def get_user_memory_consolidator() -> UserMemoryConsolidator:
    global _user_memory_consolidator
    if _user_memory_consolidator is None:
        _user_memory_consolidator = UserMemoryConsolidator()
    return _user_memory_consolidator
