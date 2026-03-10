"""Legacy compatibility writer for session-memory migration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from memory_system.session_memory_builder import (
    build_agent_candidate_content,
    build_agent_candidate_seed_facts,
    build_user_preference_memory_content,
    build_user_preference_seed_facts,
    split_user_preference_content,
)
from memory_system.session_observation_builder import get_session_observation_builder
from shared.logging import get_logger

logger = get_logger(__name__)

_SESSION_MEMORY_USER_SIGNAL_TYPE = "user_preference"
_SESSION_MEMORY_AGENT_SIGNAL_TYPE = "agent_memory_candidate"
_SESSION_MEMORY_AGENT_REVIEW_PENDING = "pending"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class LegacySessionMemoryPersistResult:
    preference_created: int = 0
    preference_updated: int = 0
    preference_skipped: int = 0
    candidate_created: int = 0
    candidate_skipped: int = 0


class LegacyMemoryCompatibilityWriter:
    """Bridge new session observations into legacy memory_records until cutover."""

    def __init__(self):
        self._observation_builder = get_session_observation_builder()

    @staticmethod
    def load_existing_user_preference_map(user_id: str) -> Dict[str, Dict[str, Any]]:
        from memory_system.memory_interface import MemoryType
        from memory_system.memory_repository import get_memory_repository

        repo = get_memory_repository()
        rows = repo.list_memories(
            memory_type=MemoryType.USER_CONTEXT,
            user_id=str(user_id),
            limit=400,
        )

        latest_by_key: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            metadata = dict(row.metadata or {})
            signal_type = str(metadata.get("signal_type") or "").strip().lower()
            if signal_type != _SESSION_MEMORY_USER_SIGNAL_TYPE:
                continue

            key = str(metadata.get("preference_key") or "").strip()
            value = str(metadata.get("preference_value") or "").strip()
            if (not key or not value) and row.content:
                parsed_key, parsed_value = split_user_preference_content(str(row.content))
                key = key or str(parsed_key or "")
                value = value or str(parsed_value or "")
            if not key or not value:
                continue

            row_latest_ts = LegacyMemoryCompatibilityWriter._parse_or_none(
                metadata.get("latest_turn_ts")
            ) or LegacyMemoryCompatibilityWriter._parse_or_none(row.timestamp)
            existing = latest_by_key.get(key)
            if existing:
                existing_ts = LegacyMemoryCompatibilityWriter._parse_or_none(
                    existing.get("latest_turn_ts")
                ) or LegacyMemoryCompatibilityWriter._parse_or_none(existing.get("timestamp"))
                if existing_ts and row_latest_ts and existing_ts >= row_latest_ts:
                    continue

            latest_by_key[key] = {
                "memory_id": int(row.id),
                "value": value,
                "metadata": metadata,
                "latest_turn_ts": row_latest_ts.isoformat() if row_latest_ts else None,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }

        return latest_by_key

    @staticmethod
    def _parse_or_none(value: Any) -> Optional[datetime]:
        return get_session_observation_builder().parse_iso_datetime(value)

    @staticmethod
    def upsert_existing_user_preference_metadata(
        memory_id: int,
        metadata: Dict[str, Any],
    ) -> None:
        from memory_system.memory_repository import get_memory_repository

        repo = get_memory_repository()
        repo.update_record(
            memory_id,
            metadata=metadata,
            mark_vector_pending=False,
        )

    @staticmethod
    def load_existing_agent_candidate_fingerprints(
        *,
        agent_id: str,
        user_id: str,
    ) -> Set[str]:
        from memory_system.memory_interface import MemoryType
        from memory_system.memory_repository import get_memory_repository

        repo = get_memory_repository()
        rows = repo.list_memories(
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            user_id=str(user_id),
            limit=400,
        )

        fingerprints: Set[str] = set()
        for row in rows:
            metadata = dict(row.metadata or {})
            signal_type = str(metadata.get("signal_type") or "").strip().lower()
            if signal_type != _SESSION_MEMORY_AGENT_SIGNAL_TYPE:
                continue
            fingerprint = str(metadata.get("candidate_fingerprint") or "").strip()
            if fingerprint:
                fingerprints.add(fingerprint)

        return fingerprints

    def persist_session_memories(
        self,
        *,
        mem_interface: Any,
        session: Any,
        reason: str,
        agent_name: str,
        turn_count: int,
        extracted_signals: List[Dict[str, Any]],
        extracted_agent_candidates: List[Dict[str, Any]],
        load_existing_user_preference_map: Optional[
            Callable[[str], Dict[str, Dict[str, Any]]]
        ] = None,
        load_existing_agent_candidate_fingerprints: Optional[Callable[..., Set[str]]] = None,
        upsert_existing_user_preference_metadata: Optional[
            Callable[[int, Dict[str, Any]], None]
        ] = None,
    ) -> LegacySessionMemoryPersistResult:
        extracted_at = _utc_now_iso()
        metadata_base = {
            "source": "agent_test_preference_extractor",
            "session_id": session.session_id,
            "turn_count": turn_count,
            "session_end_reason": reason,
            "aggregated": True,
            "agent_name": agent_name,
            "extracted_at": extracted_at,
        }
        preference_metadata_base = {**metadata_base, "source": "agent_test_preference_extractor"}
        agent_candidate_metadata_base = {
            **metadata_base,
            "source": "agent_test_agent_candidate_extractor",
        }
        load_pref = load_existing_user_preference_map or self.load_existing_user_preference_map
        load_agent = (
            load_existing_agent_candidate_fingerprints
            or self.load_existing_agent_candidate_fingerprints
        )
        upsert_pref = (
            upsert_existing_user_preference_metadata
            or self.upsert_existing_user_preference_metadata
        )

        try:
            existing_preference_map = load_pref(str(session.user_id))
        except Exception as e:
            logger.warning(
                "Failed to load existing user preference memories before upsert",
                extra={"session_id": session.session_id, "error": str(e)},
            )
            existing_preference_map = {}

        result = LegacySessionMemoryPersistResult()
        for signal in extracted_signals:
            try:
                signal_key = str(signal.get("key") or "").strip()
                signal_value = str(signal.get("value") or "").strip()
                if not signal_key or not signal_value:
                    result.preference_skipped += 1
                    continue

                existing = existing_preference_map.get(signal_key)
                if existing and str(existing.get("value") or "").strip() == signal_value:
                    memory_id = existing.get("memory_id")
                    if memory_id:
                        existing_meta = dict(existing.get("metadata") or {})
                        existing_meta.update(
                            {
                                "evidence_count": max(
                                    int(existing_meta.get("evidence_count") or 0),
                                    int(signal.get("evidence_count") or 0),
                                ),
                                "confidence": max(
                                    float(existing_meta.get("confidence") or 0.0),
                                    float(signal.get("confidence") or 0.0),
                                ),
                                "latest_turn_ts": signal.get("latest_ts")
                                or existing_meta.get("latest_turn_ts"),
                                "updated_at_extracted": extracted_at,
                                "is_active": True,
                                "strong_signal": bool(
                                    signal.get("strong_signal")
                                    or existing_meta.get("strong_signal")
                                ),
                                "explicit_source": bool(
                                    signal.get("explicit_source")
                                    or existing_meta.get("explicit_source")
                                ),
                            }
                        )
                        upsert_pref(int(memory_id), existing_meta)
                        result.preference_updated += 1
                        continue
                    result.preference_skipped += 1
                    continue

                if existing and str(existing.get("value") or "").strip() != signal_value:
                    memory_id = existing.get("memory_id")
                    previous_value = str(existing.get("value") or "").strip()
                    if memory_id:
                        old_meta = dict(existing.get("metadata") or {})
                        old_meta.update(
                            {
                                "is_active": False,
                                "superseded_at": extracted_at,
                                "superseded_by_value": signal_value,
                            }
                        )
                        delete_applied = False
                        if previous_value:
                            delete_seed_facts = old_meta.get("facts", [])
                            if not isinstance(delete_seed_facts, list) or not delete_seed_facts:
                                delete_seed_facts = build_user_preference_seed_facts(
                                    {
                                        "key": signal_key,
                                        "value": previous_value,
                                        "persistent": bool(old_meta.get("strong_signal")),
                                        "confidence": max(
                                            self._observation_builder.coerce_confidence(
                                                old_meta.get("confidence"), default=0.0
                                            ),
                                            self._observation_builder.coerce_confidence(
                                                signal.get("confidence"), default=0.0
                                            ),
                                        ),
                                    }
                                )

                            delete_result = mem_interface.store_user_context(
                                user_id=session.user_id,
                                agent_id=session.agent_id,
                                content=f"user.preference.{signal_key}={previous_value}",
                                metadata={
                                    **preference_metadata_base,
                                    "signal_type": _SESSION_MEMORY_USER_SIGNAL_TYPE,
                                    "preference_key": signal_key,
                                    "preference_value": previous_value,
                                    "evidence_count": max(
                                        int(old_meta.get("evidence_count") or 0),
                                        int(signal.get("evidence_count") or 0),
                                    ),
                                    "confidence": max(
                                        self._observation_builder.coerce_confidence(
                                            old_meta.get("confidence"), default=0.0
                                        ),
                                        self._observation_builder.coerce_confidence(
                                            signal.get("confidence"), default=0.0
                                        ),
                                    ),
                                    "reason": "superseded_by_new_value",
                                    "latest_turn_ts": signal.get("latest_ts")
                                    or old_meta.get("latest_turn_ts"),
                                    "strong_signal": bool(
                                        signal.get("strong_signal") or old_meta.get("strong_signal")
                                    ),
                                    "explicit_source": bool(
                                        signal.get("explicit_source")
                                        or old_meta.get("explicit_source")
                                    ),
                                    "is_active": False,
                                    "superseded_at": extracted_at,
                                    "superseded_by_value": signal_value,
                                    "memory_action": "DELETE",
                                    "target_memory_id": int(memory_id),
                                    "skip_secondary_fact_extraction": True,
                                    "facts": delete_seed_facts,
                                },
                            )
                            delete_applied = bool(delete_result)

                        if not delete_applied:
                            upsert_pref(int(memory_id), old_meta)

                mem_interface.store_user_context(
                    user_id=session.user_id,
                    agent_id=session.agent_id,
                    content=build_user_preference_memory_content(signal),
                    metadata={
                        **preference_metadata_base,
                        "signal_type": _SESSION_MEMORY_USER_SIGNAL_TYPE,
                        "preference_key": signal_key,
                        "preference_value": signal_value,
                        "evidence_count": signal["evidence_count"],
                        "confidence": signal["confidence"],
                        "reason": signal.get("reason"),
                        "latest_turn_ts": signal.get("latest_ts"),
                        "strong_signal": bool(signal.get("strong_signal")),
                        "explicit_source": bool(signal.get("explicit_source")),
                        "is_active": True,
                        "skip_secondary_fact_extraction": True,
                        "facts": build_user_preference_seed_facts(signal),
                    },
                )
                existing_preference_map[signal_key] = {
                    "memory_id": None,
                    "value": signal_value,
                    "metadata": {
                        "signal_type": _SESSION_MEMORY_USER_SIGNAL_TYPE,
                        "preference_key": signal_key,
                        "preference_value": signal_value,
                        "latest_turn_ts": signal.get("latest_ts"),
                        "strong_signal": bool(signal.get("strong_signal")),
                        "explicit_source": bool(signal.get("explicit_source")),
                        "is_active": True,
                    },
                }
                result.preference_created += 1
            except Exception as e:
                logger.warning(
                    "Failed to store extracted user preference memory on session end",
                    extra={
                        "session_id": session.session_id,
                        "reason": reason,
                        "error": str(e),
                        "preference_key": signal.get("key"),
                    },
                )

        try:
            existing_candidate_fingerprints = load_agent(
                agent_id=str(session.agent_id),
                user_id=str(session.user_id),
            )
        except Exception as e:
            logger.warning(
                "Failed to load existing agent candidate fingerprints",
                extra={"session_id": session.session_id, "error": str(e)},
            )
            existing_candidate_fingerprints = set()

        for candidate in extracted_agent_candidates:
            fingerprint = str(candidate.get("fingerprint") or "").strip()
            if not fingerprint:
                result.candidate_skipped += 1
                continue
            if fingerprint in existing_candidate_fingerprints:
                result.candidate_skipped += 1
                continue

            try:
                mem_interface.store_agent_memory(
                    agent_id=session.agent_id,
                    user_id=session.user_id,
                    content=build_agent_candidate_content(candidate),
                    metadata={
                        **agent_candidate_metadata_base,
                        "signal_type": _SESSION_MEMORY_AGENT_SIGNAL_TYPE,
                        "candidate_type": candidate.get("candidate_type") or "sop",
                        "candidate_title": candidate.get("title") or candidate.get("topic"),
                        "candidate_summary": candidate.get("summary"),
                        "candidate_applicability": candidate.get("applicability"),
                        "candidate_avoid": candidate.get("avoid"),
                        "candidate_fingerprint": fingerprint,
                        "review_status": _SESSION_MEMORY_AGENT_REVIEW_PENDING,
                        "review_required": True,
                        "inject_policy": "only_published",
                        "confidence": candidate.get("confidence"),
                        "latest_turn_ts": candidate.get("latest_ts"),
                        "is_active": True,
                        "skip_secondary_fact_extraction": True,
                        "facts": build_agent_candidate_seed_facts(candidate),
                    },
                )
                existing_candidate_fingerprints.add(fingerprint)
                result.candidate_created += 1
            except Exception as e:
                logger.warning(
                    "Failed to store extracted agent memory candidate on session end",
                    extra={
                        "session_id": session.session_id,
                        "reason": reason,
                        "error": str(e),
                        "candidate_type": candidate.get("candidate_type"),
                    },
                )

        return result


_legacy_memory_compatibility_writer: Optional[LegacyMemoryCompatibilityWriter] = None


def get_legacy_memory_compatibility_writer() -> LegacyMemoryCompatibilityWriter:
    global _legacy_memory_compatibility_writer
    if _legacy_memory_compatibility_writer is None:
        _legacy_memory_compatibility_writer = LegacyMemoryCompatibilityWriter()
    return _legacy_memory_compatibility_writer
