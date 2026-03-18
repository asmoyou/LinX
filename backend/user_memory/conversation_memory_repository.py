"""State and turn assembly helpers for segmented conversation memory extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, or_

from database.connection import get_db_session
from database.models import Agent, AgentConversation, AgentConversationMemoryState, AgentConversationMessage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_reason(reason: str) -> str:
    normalized = str(reason or "").strip().lower()
    if normalized == "user":
        return "client_release"
    if normalized == "expired":
        return "runtime_expired"
    return normalized or "manual"


def _coerce_positive_int(value: object, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed >= minimum else default


@dataclass(frozen=True)
class ConversationMemoryTurn:
    """One complete user->assistant turn extracted from persisted messages."""

    user_message: str
    agent_response: str
    agent_name: str
    started_at: datetime
    completed_at: datetime
    user_message_ids: tuple[UUID, ...]
    assistant_message_id: UUID

    def to_turn_dict(self, *, origin: str) -> dict[str, str]:
        return {
            "user_message": self.user_message,
            "agent_response": self.agent_response,
            "agent_name": self.agent_name,
            "timestamp": self.completed_at.isoformat(),
            "turn_origin": str(origin or "new").strip().lower() or "new",
        }


@dataclass(frozen=True)
class ClaimedConversationMemoryBatch:
    """A frozen delta window claimed for one memory extraction attempt."""

    conversation_id: UUID
    agent_id: UUID
    user_id: UUID
    agent_name: str
    conversation_created_at: datetime
    run_token: str
    run_sequence: int
    reason: str
    synthetic_session_id: str
    last_processed_assistant_message_id: Optional[UUID]
    target_assistant_message_id: UUID
    target_assistant_created_at: datetime
    overlap_turns: tuple[ConversationMemoryTurn, ...]
    new_turns: tuple[ConversationMemoryTurn, ...]
    last_processed_turn_count: int
    previous_failures: int

    @property
    def processed_turn_count(self) -> int:
        return int(self.last_processed_turn_count) + len(self.new_turns)

    def combined_turn_dicts(self) -> list[dict[str, str]]:
        turns: list[dict[str, str]] = []
        for turn in self.overlap_turns:
            turns.append(turn.to_turn_dict(origin="overlap"))
        for turn in self.new_turns:
            turns.append(turn.to_turn_dict(origin="new"))
        return turns

    def new_turn_dicts(self) -> list[dict[str, str]]:
        return [turn.to_turn_dict(origin="new") for turn in self.new_turns]


class ConversationMemoryRepository:
    """Persisted cursor and lease management for conversation memory extraction."""

    _RECENT_HISTORY_MESSAGE_LIMIT = 24

    @staticmethod
    def get_or_create_state(conversation_id: UUID) -> AgentConversationMemoryState | None:
        with get_db_session() as session:
            row = (
                session.query(AgentConversationMemoryState)
                .filter(AgentConversationMemoryState.conversation_id == conversation_id)
                .first()
            )
            if row is not None:
                return row
            conversation = (
                session.query(AgentConversation.conversation_id)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                return None
            row = AgentConversationMemoryState(conversation_id=conversation_id)
            session.add(row)
            session.flush()
            return row

    def list_candidate_conversation_ids(
        self,
        *,
        limit: int,
        idle_timeout_minutes: Optional[int],
        include_all_pending: bool = False,
    ) -> list[UUID]:
        now = _utc_now()
        query_limit = _coerce_positive_int(limit, 200)
        idle_cutoff = None
        if not include_all_pending:
            timeout_minutes = _coerce_positive_int(idle_timeout_minutes, 30)
            idle_cutoff = now - timedelta(minutes=timeout_minutes)

        with get_db_session() as session:
            query = (
                session.query(AgentConversation.conversation_id)
                .outerjoin(
                    AgentConversationMemoryState,
                    AgentConversationMemoryState.conversation_id == AgentConversation.conversation_id,
                )
                .filter(AgentConversation.status == "active")
                .filter(AgentConversation.last_message_at.isnot(None))
                .filter(
                    or_(
                        AgentConversationMemoryState.conversation_id.is_(None),
                        AgentConversationMemoryState.retry_after.is_(None),
                        AgentConversationMemoryState.retry_after <= now,
                    )
                )
                .filter(
                    or_(
                        AgentConversationMemoryState.conversation_id.is_(None),
                        AgentConversationMemoryState.run_state != "running",
                        AgentConversationMemoryState.lease_until.is_(None),
                        AgentConversationMemoryState.lease_until <= now,
                    )
                )
            )
            if idle_cutoff is not None:
                query = query.filter(AgentConversation.last_message_at <= idle_cutoff)
            rows = (
                query.order_by(
                    AgentConversation.last_message_at.asc(),
                    AgentConversation.conversation_id.asc(),
                )
                .limit(query_limit)
                .all()
            )
            return [row.conversation_id for row in rows]

    def claim_conversation_delta(
        self,
        *,
        conversation_id: UUID,
        reason: str,
        overlap_turns: int,
        max_new_turns: int,
        lease_seconds: int,
    ) -> ClaimedConversationMemoryBatch | None:
        normalized_reason = _normalize_reason(reason)
        safe_overlap_turns = max(int(overlap_turns or 0), 0)
        safe_max_new_turns = _coerce_positive_int(max_new_turns, 8)
        safe_lease_seconds = _coerce_positive_int(lease_seconds, 300, minimum=60)
        now = _utc_now()

        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .join(Agent, Agent.agent_id == AgentConversation.agent_id)
                .filter(AgentConversation.conversation_id == conversation_id)
                .with_for_update()
                .first()
            )
            if conversation is None:
                return None

            state = (
                session.query(AgentConversationMemoryState)
                .filter(AgentConversationMemoryState.conversation_id == conversation_id)
                .with_for_update()
                .first()
            )
            if state is None:
                state = AgentConversationMemoryState(conversation_id=conversation_id)
                session.add(state)
                session.flush()

            if state.retry_after and state.retry_after > now:
                return None
            if (
                str(state.run_state or "idle") == "running"
                and state.lease_until is not None
                and state.lease_until > now
            ):
                return None

            recent_messages = self._load_recent_messages_after_cursor(
                session=session,
                conversation_id=conversation_id,
                state=state,
            )
            agent_name = str(getattr(conversation.agent, "name", "") or "").strip()
            new_turns = self._build_complete_turns(recent_messages, agent_name=agent_name)
            if not new_turns:
                self._clear_run_lease(state)
                session.flush()
                return None

            selected_new_turns = tuple(new_turns[:safe_max_new_turns])
            target_turn = selected_new_turns[-1]
            overlap = ()
            if safe_overlap_turns > 0 and state.last_processed_assistant_message_id is not None:
                previous_messages = self._load_recent_messages_before_cursor(
                    session=session,
                    conversation_id=conversation_id,
                    state=state,
                )
                previous_turns = self._build_complete_turns(previous_messages, agent_name=agent_name)
                overlap = tuple(previous_turns[-safe_overlap_turns:])

            run_sequence = int(state.last_run_sequence or 0) + 1
            run_token = uuid4().hex
            state.last_run_sequence = run_sequence
            state.run_state = "running"
            state.run_token = run_token
            state.lease_until = now + timedelta(seconds=safe_lease_seconds)
            state.target_assistant_message_id = target_turn.assistant_message_id
            state.target_assistant_created_at = target_turn.completed_at
            state.last_extraction_started_at = now
            state.last_extraction_reason = normalized_reason
            state.last_error = None
            session.flush()

            return ClaimedConversationMemoryBatch(
                conversation_id=conversation.conversation_id,
                agent_id=conversation.agent_id,
                user_id=conversation.owner_user_id,
                agent_name=agent_name,
                conversation_created_at=conversation.created_at,
                run_token=run_token,
                run_sequence=run_sequence,
                reason=normalized_reason,
                synthetic_session_id=(
                    f"agent-conversation:{conversation.conversation_id}:"
                    f"until:{target_turn.assistant_message_id}"
                ),
                last_processed_assistant_message_id=state.last_processed_assistant_message_id,
                target_assistant_message_id=target_turn.assistant_message_id,
                target_assistant_created_at=target_turn.completed_at,
                overlap_turns=overlap,
                new_turns=selected_new_turns,
                last_processed_turn_count=int(state.last_processed_turn_count or 0),
                previous_failures=int(state.consecutive_failures or 0),
            )

    def complete_claim(
        self,
        *,
        conversation_id: UUID,
        run_token: str,
        target_assistant_message_id: UUID,
        target_assistant_created_at: datetime,
        processed_turn_count: int,
        reason: str,
        session_ledger_id: Optional[int],
    ) -> bool:
        with get_db_session() as session:
            state = (
                session.query(AgentConversationMemoryState)
                .filter(AgentConversationMemoryState.conversation_id == conversation_id)
                .with_for_update()
                .first()
            )
            if not self._matches_claim(
                state=state,
                run_token=run_token,
                target_assistant_message_id=target_assistant_message_id,
            ):
                return False

            state.last_processed_assistant_message_id = target_assistant_message_id
            state.last_processed_assistant_created_at = target_assistant_created_at
            state.last_processed_turn_count = int(processed_turn_count or 0)
            state.last_extraction_completed_at = _utc_now()
            state.last_extraction_reason = _normalize_reason(reason)
            state.last_successful_session_ledger_id = (
                int(session_ledger_id) if session_ledger_id is not None else None
            )
            state.consecutive_failures = 0
            state.retry_after = None
            state.last_error = None
            self._clear_run_lease(state)
            session.flush()
            return True

    def fail_claim(
        self,
        *,
        conversation_id: UUID,
        run_token: str,
        target_assistant_message_id: UUID,
        reason: str,
        error_text: str,
    ) -> bool:
        with get_db_session() as session:
            state = (
                session.query(AgentConversationMemoryState)
                .filter(AgentConversationMemoryState.conversation_id == conversation_id)
                .with_for_update()
                .first()
            )
            if not self._matches_claim(
                state=state,
                run_token=run_token,
                target_assistant_message_id=target_assistant_message_id,
            ):
                return False

            next_failures = int(state.consecutive_failures or 0) + 1
            state.consecutive_failures = next_failures
            state.retry_after = _utc_now() + timedelta(
                minutes=self._failure_backoff_minutes(next_failures)
            )
            state.last_error = str(error_text or "").strip() or None
            state.last_extraction_completed_at = _utc_now()
            state.last_extraction_reason = _normalize_reason(reason)
            self._clear_run_lease(state)
            session.flush()
            return True

    @staticmethod
    def _failure_backoff_minutes(failure_count: int) -> int:
        if failure_count <= 1:
            return 1
        if failure_count == 2:
            return 5
        if failure_count == 3:
            return 15
        return 60

    @staticmethod
    def _matches_claim(
        *,
        state: Optional[AgentConversationMemoryState],
        run_token: str,
        target_assistant_message_id: UUID,
    ) -> bool:
        if state is None:
            return False
        return (
            str(state.run_token or "") == str(run_token or "")
            and state.target_assistant_message_id == target_assistant_message_id
        )

    @staticmethod
    def _clear_run_lease(state: AgentConversationMemoryState) -> None:
        state.run_state = "idle"
        state.run_token = None
        state.lease_until = None
        state.target_assistant_message_id = None
        state.target_assistant_created_at = None

    @staticmethod
    def _load_recent_messages_after_cursor(
        *,
        session,
        conversation_id: UUID,
        state: AgentConversationMemoryState,
    ) -> list[AgentConversationMessage]:
        query = (
            session.query(AgentConversationMessage)
            .filter(AgentConversationMessage.conversation_id == conversation_id)
            .order_by(
                AgentConversationMessage.created_at.asc(),
                AgentConversationMessage.message_id.asc(),
            )
        )
        if state.last_processed_assistant_message_id is None:
            return list(query.all())
        if state.last_processed_assistant_created_at is None:
            return list(query.all())
        return list(
            query.filter(
                or_(
                    AgentConversationMessage.created_at > state.last_processed_assistant_created_at,
                    and_(
                        AgentConversationMessage.created_at
                        == state.last_processed_assistant_created_at,
                        AgentConversationMessage.message_id > state.last_processed_assistant_message_id,
                    ),
                )
            ).all()
        )

    def _load_recent_messages_before_cursor(
        self,
        *,
        session,
        conversation_id: UUID,
        state: AgentConversationMemoryState,
    ) -> list[AgentConversationMessage]:
        if (
            state.last_processed_assistant_message_id is None
            or state.last_processed_assistant_created_at is None
        ):
            return []
        rows = (
            session.query(AgentConversationMessage)
            .filter(AgentConversationMessage.conversation_id == conversation_id)
            .filter(
                or_(
                    AgentConversationMessage.created_at < state.last_processed_assistant_created_at,
                    and_(
                        AgentConversationMessage.created_at
                        == state.last_processed_assistant_created_at,
                        AgentConversationMessage.message_id <= state.last_processed_assistant_message_id,
                    ),
                )
            )
            .order_by(
                AgentConversationMessage.created_at.desc(),
                AgentConversationMessage.message_id.desc(),
            )
            .limit(self._RECENT_HISTORY_MESSAGE_LIMIT)
            .all()
        )
        return list(reversed(rows))

    @staticmethod
    def _build_complete_turns(
        messages: Iterable[AgentConversationMessage],
        *,
        agent_name: str,
    ) -> list[ConversationMemoryTurn]:
        turns: list[ConversationMemoryTurn] = []
        pending_user_chunks: list[str] = []
        pending_user_ids: list[UUID] = []
        pending_started_at: Optional[datetime] = None

        for message in messages:
            role = str(message.role or "").strip().lower()
            content = str(message.content_text or "").strip()
            created_at = message.created_at or _utc_now()
            if role == "user":
                if not content:
                    continue
                pending_user_chunks.append(content)
                pending_user_ids.append(message.message_id)
                if pending_started_at is None:
                    pending_started_at = created_at
                continue
            if role != "assistant" or not pending_user_chunks or not content:
                continue
            turns.append(
                ConversationMemoryTurn(
                    user_message="\n\n".join(pending_user_chunks).strip(),
                    agent_response=content,
                    agent_name=agent_name,
                    started_at=pending_started_at or created_at,
                    completed_at=created_at,
                    user_message_ids=tuple(pending_user_ids),
                    assistant_message_id=message.message_id,
                )
            )
            pending_user_chunks = []
            pending_user_ids = []
            pending_started_at = None

        return turns


_conversation_memory_repository: Optional[ConversationMemoryRepository] = None


def get_conversation_memory_repository() -> ConversationMemoryRepository:
    """Return the shared conversation-memory repository."""

    global _conversation_memory_repository
    if _conversation_memory_repository is None:
        _conversation_memory_repository = ConversationMemoryRepository()
    return _conversation_memory_repository


__all__ = [
    "ClaimedConversationMemoryBatch",
    "ConversationMemoryRepository",
    "ConversationMemoryTurn",
    "get_conversation_memory_repository",
]
