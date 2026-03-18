"""Segmented memory extraction for persistent agent conversations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from shared.config import Config, get_config
from user_memory.builder import get_user_memory_builder
from user_memory.conversation_memory_repository import (
    ClaimedConversationMemoryBatch,
    get_conversation_memory_repository,
)
from user_memory.session_ledger_service import get_session_ledger_service

logger = logging.getLogger(__name__)

_FORCED_FLUSH_REASONS = {"client_release", "runtime_expired", "delete", "shutdown"}


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _cfg_int(
    value: Any,
    default: int,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


@dataclass(frozen=True)
class ConversationMemoryExtractionSettings:
    """Settings for segmented conversation-memory extraction."""

    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 30
    interval_seconds: int = 300
    idle_timeout_minutes: int = 30
    overlap_turns: int = 2
    max_new_turns_per_run: int = 8
    advisory_lock_id: int = 73012024
    use_advisory_lock: bool = True
    run_lease_seconds: int = 300
    scan_limit: int = 200
    max_batches_per_invocation: int = 3

    def with_defaults(self) -> "ConversationMemoryExtractionSettings":
        return ConversationMemoryExtractionSettings(
            enabled=self.enabled,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            idle_timeout_minutes=self.idle_timeout_minutes,
            overlap_turns=self.overlap_turns,
            max_new_turns_per_run=self.max_new_turns_per_run,
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
            run_lease_seconds=self.run_lease_seconds,
            scan_limit=self.scan_limit,
            max_batches_per_invocation=self.max_batches_per_invocation,
        )


def load_conversation_memory_extraction_settings(
    config: Optional[Config] = None,
) -> ConversationMemoryExtractionSettings:
    """Load settings from ``user_memory.conversation_extraction``."""

    cfg = config or get_config()
    raw = cfg.get("user_memory.conversation_extraction", {}) or {}
    settings = ConversationMemoryExtractionSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 30, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 300, minimum=60),
        idle_timeout_minutes=_cfg_int(raw.get("idle_timeout_minutes"), 30, minimum=1),
        overlap_turns=_cfg_int(raw.get("overlap_turns"), 2, minimum=0, maximum=8),
        max_new_turns_per_run=_cfg_int(raw.get("max_new_turns_per_run"), 8, minimum=1, maximum=16),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012024),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
        run_lease_seconds=_cfg_int(raw.get("run_lease_seconds"), 300, minimum=60),
        scan_limit=_cfg_int(raw.get("scan_limit"), 200, minimum=1, maximum=5000),
        max_batches_per_invocation=_cfg_int(
            raw.get("max_batches_per_invocation"), 3, minimum=1, maximum=10
        ),
    )
    return settings.with_defaults()


class ConversationMemoryService:
    """Run segmented memory extraction on persistent conversation threads."""

    def __init__(
        self,
        *,
        settings: Optional[ConversationMemoryExtractionSettings] = None,
    ) -> None:
        self.settings = (settings or load_conversation_memory_extraction_settings()).with_defaults()
        self._repository = get_conversation_memory_repository()
        self._builder = get_user_memory_builder()
        self._ledger_service = get_session_ledger_service()

    async def flush_conversation_memory_delta(
        self,
        conversation_id: UUID,
        reason: str,
    ) -> Dict[str, Any]:
        """Flush one or more pending turn batches for one conversation."""

        if not self.settings.enabled:
            return {"status": "disabled", "reason": reason, "conversation_id": str(conversation_id)}

        normalized_reason = self._normalize_reason(reason)
        max_batches = (
            self.settings.max_batches_per_invocation
            if normalized_reason in _FORCED_FLUSH_REASONS
            else 1
        )
        runs: List[Dict[str, Any]] = []
        for _ in range(max_batches):
            batch = self._repository.claim_conversation_delta(
                conversation_id=conversation_id,
                reason=normalized_reason,
                overlap_turns=self.settings.overlap_turns,
                max_new_turns=self.settings.max_new_turns_per_run,
                lease_seconds=self.settings.run_lease_seconds,
            )
            if batch is None:
                break
            result = await self._flush_claimed_batch(batch)
            runs.append(result)
            if result.get("status") != "ok":
                break

        if not runs:
            return {
                "status": "skipped",
                "reason": normalized_reason,
                "conversation_id": str(conversation_id),
                "skip_reason": "no_claimable_delta",
            }
        ok_runs = [run for run in runs if run.get("status") == "ok"]
        status = "ok" if ok_runs and len(ok_runs) == len(runs) else runs[-1].get("status") or "error"
        return {
            "status": status,
            "reason": normalized_reason,
            "conversation_id": str(conversation_id),
            "runs": runs,
            "run_count": len(runs),
        }

    async def scan_idle_conversations(
        self,
        *,
        limit: Optional[int] = None,
        reason: str = "scheduled",
        include_all_pending: bool = False,
    ) -> List[UUID]:
        """Flush candidate conversations selected by idle cutoff or pending state."""

        if not self.settings.enabled:
            return []
        candidates = self._repository.list_candidate_conversation_ids(
            limit=limit or self.settings.scan_limit,
            idle_timeout_minutes=self.settings.idle_timeout_minutes,
            include_all_pending=include_all_pending,
        )
        processed: List[UUID] = []
        for conversation_id in candidates:
            result = await self.flush_conversation_memory_delta(conversation_id, reason)
            if result.get("status") in {"ok", "skipped"}:
                processed.append(conversation_id)
        return processed

    async def _flush_claimed_batch(self, batch: ClaimedConversationMemoryBatch) -> Dict[str, Any]:
        combined_turns = batch.combined_turn_dicts()
        new_turns = batch.new_turn_dicts()
        new_turn_indexes = set(
            range(len(batch.overlap_turns) + 1, len(batch.overlap_turns) + len(batch.new_turns) + 1)
        )
        try:
            extracted_signals, extracted_agent_candidates = (
                await self._builder.extract_session_memory_signals_with_llm(
                    turns=combined_turns,
                    agent_id=batch.agent_id,
                    agent_name=batch.agent_name,
                    session_id=batch.synthetic_session_id,
                )
            )
            extracted_signals = self._filter_signals_with_new_evidence(
                extracted_signals,
                new_turn_indexes=new_turn_indexes,
                has_overlap=bool(batch.overlap_turns),
            )
            extracted_agent_candidates = self._filter_candidates_with_new_evidence(
                extracted_agent_candidates,
                new_turn_indexes=new_turn_indexes,
                has_overlap=bool(batch.overlap_turns),
            )
            if not extracted_signals:
                extracted_signals = self._dedupe_user_preference_signals(
                    self._builder.extract_user_preference_signals(new_turns)
                )

            first_new_message_id = None
            if batch.new_turns and batch.new_turns[0].user_message_ids:
                first_new_message_id = str(batch.new_turns[0].user_message_ids[0])
            ledger_result = self._ledger_service.persist_turn_batch(
                session_id=batch.synthetic_session_id,
                agent_id=str(batch.agent_id),
                user_id=str(batch.user_id),
                started_at=batch.new_turns[0].started_at or batch.conversation_created_at,
                reason=batch.reason,
                turns=new_turns,
                agent_name=batch.agent_name,
                extracted_signals=extracted_signals,
                extracted_agent_candidates=extracted_agent_candidates,
                metadata={
                    "conversation_id": str(batch.conversation_id),
                    "target_assistant_message_id": str(batch.target_assistant_message_id),
                    "trigger_reason": batch.reason,
                    "new_turn_count": len(batch.new_turns),
                    "overlap_turn_count": len(batch.overlap_turns),
                    "last_processed_assistant_message_id": (
                        str(batch.last_processed_assistant_message_id)
                        if batch.last_processed_assistant_message_id
                        else None
                    ),
                    "first_new_message_id": first_new_message_id,
                    "message_id_range": {
                        "start": first_new_message_id,
                        "end": str(batch.target_assistant_message_id),
                    },
                    "run_sequence": batch.run_sequence,
                },
            )
            committed = self._repository.complete_claim(
                conversation_id=batch.conversation_id,
                run_token=batch.run_token,
                target_assistant_message_id=batch.target_assistant_message_id,
                target_assistant_created_at=batch.target_assistant_created_at,
                processed_turn_count=batch.processed_turn_count,
                reason=batch.reason,
                session_ledger_id=ledger_result.session_row_id,
            )
            return {
                "status": "ok",
                "conversation_id": str(batch.conversation_id),
                "session_id": batch.synthetic_session_id,
                "session_row_id": ledger_result.session_row_id,
                "new_turn_count": len(batch.new_turns),
                "overlap_turn_count": len(batch.overlap_turns),
                "user_signal_count": len(extracted_signals),
                "agent_candidate_count": len(extracted_agent_candidates),
                "cursor_committed": committed,
            }
        except Exception as exc:
            self._repository.fail_claim(
                conversation_id=batch.conversation_id,
                run_token=batch.run_token,
                target_assistant_message_id=batch.target_assistant_message_id,
                reason=batch.reason,
                error_text=str(exc),
            )
            logger.warning(
                "Persistent conversation memory flush failed",
                extra={
                    "conversation_id": str(batch.conversation_id),
                    "session_id": batch.synthetic_session_id,
                    "reason": batch.reason,
                    "error": str(exc),
                },
            )
            return {
                "status": "error",
                "conversation_id": str(batch.conversation_id),
                "session_id": batch.synthetic_session_id,
                "error": str(exc),
            }

    @staticmethod
    def _normalize_reason(reason: str) -> str:
        normalized = str(reason or "").strip().lower()
        if normalized == "user":
            return "client_release"
        if normalized == "expired":
            return "runtime_expired"
        return normalized or "manual"

    @staticmethod
    def _dedupe_user_preference_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: Dict[str, Dict[str, Any]] = {}
        for signal in signals:
            signal_key = str(signal.get("key") or "").strip()
            signal_value = str(signal.get("value") or "").strip()
            if not signal_key or not signal_value:
                continue
            existing = deduped.get(signal_key)
            if existing is None:
                deduped[signal_key] = signal
                continue
            current_score = (
                int(bool(signal.get("persistent"))),
                int(signal.get("evidence_count") or 0),
                float(signal.get("confidence") or 0.0),
                str(signal.get("latest_ts") or ""),
            )
            existing_score = (
                int(bool(existing.get("persistent"))),
                int(existing.get("evidence_count") or 0),
                float(existing.get("confidence") or 0.0),
                str(existing.get("latest_ts") or ""),
            )
            if current_score >= existing_score:
                deduped[signal_key] = signal
        return list(deduped.values())

    @staticmethod
    def _filter_signals_with_new_evidence(
        signals: List[Dict[str, Any]],
        *,
        new_turn_indexes: set[int],
        has_overlap: bool,
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for signal in signals:
            evidence_turns = [
                int(turn_idx)
                for turn_idx in list(signal.get("evidence_turns") or [])
                if isinstance(turn_idx, int)
            ]
            if evidence_turns:
                if not any(turn_idx in new_turn_indexes for turn_idx in evidence_turns):
                    continue
            elif has_overlap:
                continue
            filtered.append(signal)
        return filtered

    @staticmethod
    def _filter_candidates_with_new_evidence(
        candidates: List[Dict[str, Any]],
        *,
        new_turn_indexes: set[int],
        has_overlap: bool,
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for candidate in candidates:
            evidence_turns = [
                int(turn_idx)
                for turn_idx in list(candidate.get("evidence_turns") or [])
                if isinstance(turn_idx, int)
            ]
            if evidence_turns:
                if not any(turn_idx in new_turn_indexes for turn_idx in evidence_turns):
                    continue
            elif has_overlap:
                continue
            filtered.append(candidate)
        return filtered


_conversation_memory_service: Optional[ConversationMemoryService] = None


def get_conversation_memory_service() -> ConversationMemoryService:
    """Return the shared persistent-conversation memory service."""

    global _conversation_memory_service
    if _conversation_memory_service is None:
        _conversation_memory_service = ConversationMemoryService()
    return _conversation_memory_service


__all__ = [
    "ConversationMemoryExtractionSettings",
    "ConversationMemoryService",
    "get_conversation_memory_service",
    "load_conversation_memory_extraction_settings",
]
