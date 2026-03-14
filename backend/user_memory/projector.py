"""Projection helpers for reset-era user memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from user_memory.builder import UserMemoryBuilder, get_user_memory_builder
from user_memory.session_ledger_repository import (
    MemoryEntryData,
    MemoryProjectionData,
    MemoryObservationData,
    SessionLedgerSnapshot,
    SessionLedgerRepository,
    get_session_ledger_repository,
)


class UserMemoryProjector:
    """Turn extracted session signals into durable user-memory facts and views."""

    def __init__(
        self,
        builder: Optional[UserMemoryBuilder] = None,
        session_repository: Optional[SessionLedgerRepository] = None,
    ):
        self._builder = builder or get_user_memory_builder()
        self._session_repository = session_repository or get_session_ledger_repository()

    def build_observations_and_views(
        self,
        *,
        user_id: str,
        turns: List[Dict[str, Any]],
        extracted_signals: List[Dict[str, Any]],
    ) -> Tuple[List[MemoryObservationData], List[MemoryProjectionData]]:
        return self._builder.build_user_preference_observations(
            user_id=str(user_id),
            turns=turns,
            extracted_signals=extracted_signals,
        )

    def project_entries_and_views(
        self,
        *,
        snapshot: SessionLedgerSnapshot,
        turns: List[Dict[str, Any]],
        extracted_signals: List[Dict[str, Any]],
    ) -> Tuple[List[MemoryEntryData], List[MemoryProjectionData]]:
        observations, views = self.build_observations_and_views(
            user_id=str(snapshot.user_id),
            turns=turns,
            extracted_signals=extracted_signals,
        )
        entries = [
            entry
            for entry in (
                self._session_repository._build_entry_from_observation(  # noqa: SLF001
                    snapshot=snapshot,
                    observation=observation,
                )
                for observation in observations
            )
            if entry is not None
        ]
        return entries, views


_user_memory_projector: Optional[UserMemoryProjector] = None


def get_user_memory_projector() -> UserMemoryProjector:
    global _user_memory_projector
    if _user_memory_projector is None:
        _user_memory_projector = UserMemoryProjector()
    return _user_memory_projector
