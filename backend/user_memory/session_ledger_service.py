"""Session-ledger service for the memory-system migration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_framework.session_manager import ConversationSession
from user_memory.session_ledger_repository import (
    MemorySessionSnapshot,
    SessionLedgerRepository,
    get_session_ledger_repository,
)
from user_memory.session_observation_builder import get_session_observation_builder

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SessionLedgerPersistResult:
    """Result summary for one persisted session snapshot."""

    session_row_id: int
    event_count: int
    observation_count: int
    materialization_count: int


class MemorySessionLedgerService:
    """Build and persist the first-stage session ledger and projections."""

    def __init__(self, repository: Optional[SessionLedgerRepository] = None):
        self._repository = repository or get_session_ledger_repository()
        self._observation_builder = get_session_observation_builder()

    def persist_conversation_session(
        self,
        *,
        session: ConversationSession,
        reason: str,
        turns: List[Dict[str, Any]],
        agent_name: str,
        extracted_signals: List[Dict[str, Any]],
        extracted_agent_candidates: List[Dict[str, Any]],
    ) -> SessionLedgerPersistResult:
        """Persist a dual-written session ledger snapshot."""

        snapshot = MemorySessionSnapshot(
            session_id=str(session.session_id),
            agent_id=str(session.agent_id),
            user_id=str(session.user_id),
            started_at=session.created_at,
            ended_at=_utc_now(),
            status="completed",
            end_reason=str(reason or "").strip() or None,
            metadata={
                "agent_name": str(agent_name or "").strip() or None,
                "turn_count": len(turns),
                "user_signal_count": len(extracted_signals),
                "agent_experience_count": len(extracted_agent_candidates),
            },
        )
        events = self._observation_builder.build_session_events(turns)
        user_observations, user_materializations = (
            self._observation_builder.build_user_preference_observations(
                user_id=str(session.user_id),
                turns=turns,
                extracted_signals=extracted_signals,
            )
        )
        agent_observations, agent_materializations = (
            self._observation_builder.build_agent_experience_observations(
                agent_id=str(session.agent_id),
                agent_name=agent_name,
                turns=turns,
                extracted_agent_candidates=extracted_agent_candidates,
            )
        )
        observations = user_observations + agent_observations
        materializations = user_materializations + agent_materializations
        session_row_id = self._repository.record_session_snapshot(
            snapshot=snapshot,
            events=events,
            observations=observations,
            materializations=materializations,
        )
        logger.info(
            "Persisted session ledger snapshot",
            extra={
                "session_id": session.session_id,
                "session_row_id": session_row_id,
                "event_count": len(events),
                "observation_count": len(observations),
                "materialization_count": len(materializations),
            },
        )
        return SessionLedgerPersistResult(
            session_row_id=session_row_id,
            event_count=len(events),
            observation_count=len(observations),
            materialization_count=len(materializations),
        )


_memory_session_ledger_service: Optional[MemorySessionLedgerService] = None


def get_memory_session_ledger_service() -> MemorySessionLedgerService:
    """Return a process-wide singleton session-ledger service."""

    global _memory_session_ledger_service
    if _memory_session_ledger_service is None:
        _memory_session_ledger_service = MemorySessionLedgerService()
    return _memory_session_ledger_service


SessionLedgerService = MemorySessionLedgerService


def get_session_ledger_service() -> SessionLedgerService:
    """Return the shared session-ledger service."""

    return get_memory_session_ledger_service()


__all__ = [
    "SessionLedgerPersistResult",
    "SessionLedgerService",
    "get_memory_session_ledger_service",
    "get_session_ledger_service",
]
