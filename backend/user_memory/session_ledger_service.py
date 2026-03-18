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
    projection_count: int


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

        return self.persist_turn_batch(
            session_id=str(session.session_id),
            agent_id=str(session.agent_id),
            user_id=str(session.user_id),
            started_at=session.created_at,
            reason=reason,
            turns=turns,
            agent_name=agent_name,
            extracted_signals=extracted_signals,
            extracted_agent_candidates=extracted_agent_candidates,
        )

    def persist_turn_batch(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str,
        started_at: datetime,
        reason: str,
        turns: List[Dict[str, Any]],
        agent_name: str,
        extracted_signals: List[Dict[str, Any]],
        extracted_agent_candidates: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        ended_at: Optional[datetime] = None,
        status: str = "completed",
    ) -> SessionLedgerPersistResult:
        """Persist one normalized turn batch into the session-ledger pipeline."""

        snapshot = MemorySessionSnapshot(
            session_id=str(session_id),
            agent_id=str(agent_id),
            user_id=str(user_id),
            started_at=started_at,
            ended_at=ended_at or _utc_now(),
            status=str(status or "completed"),
            end_reason=str(reason or "").strip() or None,
            metadata={
                "agent_name": str(agent_name or "").strip() or None,
                "turn_count": len(turns),
                "user_signal_count": len(extracted_signals),
                "skill_proposal_candidate_count": len(extracted_agent_candidates),
                **dict(metadata or {}),
            },
        )
        events = self._observation_builder.build_session_events(turns)
        user_observations, user_projections = (
            self._observation_builder.build_user_preference_observations(
                user_id=str(user_id),
                turns=turns,
                extracted_signals=extracted_signals,
            )
        )
        agent_observations, skill_proposal_projections = (
            self._observation_builder.build_skill_proposal_observations(
                agent_id=str(agent_id),
                agent_name=agent_name,
                turns=turns,
                extracted_agent_candidates=extracted_agent_candidates,
            )
        )
        observations = user_observations + agent_observations
        projections = user_projections + skill_proposal_projections
        session_row_id = self._repository.record_session_snapshot(
            snapshot=snapshot,
            events=events,
            observations=observations,
            projections=projections,
        )
        logger.info(
            "Persisted session ledger snapshot",
            extra={
                "session_id": session_id,
                "session_row_id": session_row_id,
                "event_count": len(events),
                "observation_count": len(observations),
                "projection_count": len(projections),
            },
        )
        return SessionLedgerPersistResult(
            session_row_id=session_row_id,
            event_count=len(events),
            observation_count=len(observations),
            projection_count=len(projections),
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
