"""Dedicated repository facade for reset-era user memory."""

from __future__ import annotations

from typing import List, Optional

from user_memory.session_ledger_repository import (
    MemoryEntryData,
    MemoryMaterializationData,
    SessionLedgerRepository,
    get_session_ledger_repository,
)


class UserMemoryRepository:
    """Focused persistence facade over user-memory entries and views."""

    def __init__(self, repository: Optional[SessionLedgerRepository] = None):
        self._repository = repository or get_session_ledger_repository()

    def upsert_entry(self, *, entry: MemoryEntryData, source_session_id: Optional[int] = None) -> int:
        return self._repository.upsert_entry(
            entry=entry,
            source_session_id=source_session_id,
        )

    def upsert_view(
        self,
        *,
        view: MemoryMaterializationData,
        source_session_id: Optional[int] = None,
    ) -> int:
        return self._repository.upsert_materialization(
            materialization=view,
            source_session_id=source_session_id,
        )

    def get_entry(self, *, user_id: str, entry_key: str):
        return self._repository.get_entry(
            owner_type="user",
            owner_id=str(user_id),
            entry_type="user_fact",
            entry_key=str(entry_key),
        )

    def list_entries(
        self,
        *,
        user_id: str,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[object]:
        return self._repository.list_entries(
            owner_type="user",
            owner_id=str(user_id),
            entry_type="user_fact",
            status=status,
            limit=limit,
        )

    def list_views(
        self,
        *,
        user_id: str,
        view_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[object]:
        return self._repository.list_materializations(
            owner_type="user",
            owner_id=str(user_id),
            materialization_type=view_type,
            status=status,
            limit=limit,
        )


_user_memory_repository: Optional[UserMemoryRepository] = None


def get_user_memory_repository() -> UserMemoryRepository:
    global _user_memory_repository
    if _user_memory_repository is None:
        _user_memory_repository = UserMemoryRepository()
    return _user_memory_repository
