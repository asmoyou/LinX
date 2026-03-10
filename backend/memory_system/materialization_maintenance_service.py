"""Backfill and consolidation utilities for memory materializations."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from memory_system.memory_interface import MemoryType
from memory_system.memory_repository import MemoryRecordData, get_memory_repository
from memory_system.session_ledger_repository import (
    MemoryEntryData,
    MemoryMaterializationData,
    SessionLedgerRepository,
    get_session_ledger_repository,
)
from memory_system.session_memory_builder import split_user_preference_content
from memory_system.session_observation_builder import get_session_observation_builder
from shared.logging import get_logger

logger = get_logger(__name__)

_USER_SIGNAL_TYPE = "user_preference"
_AGENT_SIGNAL_TYPE = "agent_memory_candidate"
_AGENT_REVIEW_TO_STATUS = {
    "published": "active",
    "pending": "pending_review",
    "rejected": "rejected",
}
_STATUS_RANK = {
    "active": 3,
    "pending_review": 2,
    "superseded": 1,
    "rejected": 0,
}
_LINE_PATTERN = re.compile(r"^(?P<key>[a-z0-9._-]+)=(?P<value>.*)$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class MaterializationBackfillResult:
    scanned_user_context_rows: int = 0
    scanned_agent_rows: int = 0
    user_profile_candidates: int = 0
    agent_experience_candidates: int = 0
    user_entry_candidates: int = 0
    agent_entry_candidates: int = 0
    user_profile_upserts: int = 0
    agent_experience_upserts: int = 0
    user_entry_upserts: int = 0
    agent_entry_upserts: int = 0
    dry_run: bool = True


@dataclass
class MaterializationConsolidationResult:
    scanned_user_profiles: int = 0
    scanned_agent_experiences: int = 0
    scanned_user_entries: int = 0
    scanned_agent_entries: int = 0
    user_status_updates: int = 0
    agent_status_updates: int = 0
    user_entry_status_updates: int = 0
    agent_entry_status_updates: int = 0
    agent_duplicate_supersedes: int = 0
    user_duplicate_entry_supersedes: int = 0
    agent_duplicate_entry_supersedes: int = 0
    dry_run: bool = True


@dataclass
class MaterializationMaintenanceResult:
    backfill: MaterializationBackfillResult
    consolidation: MaterializationConsolidationResult


class MaterializationMaintenanceService:
    """Maintain `memory_materializations` by backfilling legacy rows and consolidating drift."""

    def __init__(
        self,
        *,
        session_repository: Optional[SessionLedgerRepository] = None,
        memory_repository=None,
    ) -> None:
        self._session_repository = session_repository or get_session_ledger_repository()
        self._memory_repository = memory_repository or get_memory_repository()
        self._observation_builder = get_session_observation_builder()

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        return get_session_observation_builder().parse_iso_datetime(value)

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _normalize_status(status: Any, default: str = "active") -> str:
        normalized = str(status or "").strip().lower()
        return normalized or default

    def _status_rank(self, status: Any) -> int:
        return _STATUS_RANK.get(self._normalize_status(status, default="superseded"), -1)

    def _parse_agent_candidate_content(self, content: str) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {}
        for raw_line in str(content or "").splitlines():
            match = _LINE_PATTERN.match(raw_line.strip())
            if not match:
                continue
            key = str(match.group("key") or "").strip().lower()
            value = str(match.group("value") or "").strip()
            if not key or not value:
                continue
            parsed[key] = value
        steps = [
            step.strip()
            for step in str(parsed.get("interaction.sop.steps") or "").split("|")
            if step.strip()
        ]
        if steps:
            parsed["steps"] = steps
        return parsed

    def _status_from_review(self, review_status: Any) -> str:
        normalized = self._normalize_status(review_status, default="pending")
        return _AGENT_REVIEW_TO_STATUS.get(normalized, "pending_review")

    def _normalize_agent_experience_materialization(
        self,
        *,
        record: MemoryRecordData,
        review_status_override: Optional[str] = None,
    ) -> Optional[MemoryMaterializationData]:
        metadata = dict(record.metadata or {})
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != _AGENT_SIGNAL_TYPE:
            return None
        owner_id = str(record.agent_id or record.owner_agent_id or "").strip()
        if not owner_id:
            return None

        parsed_content = self._parse_agent_candidate_content(str(record.content or ""))
        title = str(
            metadata.get("candidate_title")
            or parsed_content.get("interaction.sop.title")
            or parsed_content.get("interaction.sop.topic")
            or ""
        ).strip()
        summary = (
            str(
                metadata.get("candidate_summary")
                or parsed_content.get("interaction.sop.summary")
                or ""
            ).strip()
            or None
        )
        steps = parsed_content.get("steps") or []
        if not isinstance(steps, list):
            steps = []
        steps = [
            self._observation_builder.normalize_text(step, max_chars=96) for step in steps if step
        ]
        steps = [step for step in steps if step]
        applicability = (
            str(
                metadata.get("candidate_applicability")
                or parsed_content.get("interaction.sop.applicability")
                or ""
            ).strip()
            or None
        )
        avoid = (
            str(
                metadata.get("candidate_avoid") or parsed_content.get("interaction.sop.avoid") or ""
            ).strip()
            or None
        )
        if not title or not steps:
            return None

        fingerprint = str(metadata.get("candidate_fingerprint") or "").strip()
        if not fingerprint:
            fingerprint = self._observation_builder.build_agent_candidate_fingerprint(title, steps)

        review_status = review_status_override or str(metadata.get("review_status") or "pending")
        status = self._status_from_review(review_status)
        payload = {
            "goal": title,
            "successful_path": steps,
            "why_it_worked": summary,
            "applicability": applicability,
            "avoid": avoid,
            "agent_name": str(
                metadata.get("agent_name") or parsed_content.get("agent.identity.name") or ""
            ).strip()
            or None,
            "skill_candidate": True,
            "review_status": self._normalize_status(review_status, default="pending"),
            "review_required": bool(metadata.get("review_required", True)),
            "inject_policy": str(metadata.get("inject_policy") or "only_published"),
            "confidence": self._coerce_float(metadata.get("confidence"), default=0.72),
            "latest_turn_ts": metadata.get("latest_turn_ts"),
            "legacy_memory_id": int(record.id),
            "legacy_backfilled": True,
        }
        details = " -> ".join(steps)
        return MemoryMaterializationData(
            owner_type="agent",
            owner_id=owner_id,
            materialization_type="agent_experience",
            materialization_key=fingerprint,
            title=title,
            summary=summary,
            details=details,
            status=status,
            payload=payload,
        )

    def _normalize_user_profile_materialization(
        self,
        *,
        record: MemoryRecordData,
    ) -> Optional[MemoryMaterializationData]:
        metadata = dict(record.metadata or {})
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != _USER_SIGNAL_TYPE:
            return None
        owner_id = str(record.user_id or record.owner_user_id or "").strip()
        if not owner_id:
            return None
        key = str(metadata.get("preference_key") or "").strip()
        value = str(metadata.get("preference_value") or "").strip()
        if (not key or not value) and record.content:
            parsed_key, parsed_value = split_user_preference_content(str(record.content))
            key = key or str(parsed_key or "")
            value = value or str(parsed_value or "")
        if not key or not value:
            return None

        is_active = bool(metadata.get("is_active", True))
        confidence = self._coerce_float(metadata.get("confidence"), default=0.78)
        importance = (
            0.9 if bool(metadata.get("strong_signal") or metadata.get("persistent")) else 0.74
        )
        payload = {
            "key": key,
            "value": value,
            "confidence": confidence,
            "importance": importance,
            "persistent": bool(metadata.get("strong_signal") or metadata.get("persistent")),
            "explicit_source": bool(metadata.get("explicit_source")),
            "latest_turn_ts": metadata.get("latest_turn_ts"),
            "is_active": is_active,
            "legacy_memory_id": int(record.id),
            "legacy_backfilled": True,
        }
        return MemoryMaterializationData(
            owner_type="user",
            owner_id=owner_id,
            materialization_type="user_profile",
            materialization_key=key,
            title=f"User preference: {key}",
            summary=value,
            details=str(metadata.get("reason") or "").strip() or None,
            status="active" if is_active else "superseded",
            payload=payload,
        )

    def _normalize_agent_entry(
        self,
        *,
        record: MemoryRecordData,
        review_status_override: Optional[str] = None,
    ) -> Optional[MemoryEntryData]:
        metadata = dict(record.metadata or {})
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != _AGENT_SIGNAL_TYPE:
            return None
        owner_id = str(record.agent_id or record.owner_agent_id or "").strip()
        if not owner_id:
            return None

        parsed_content = self._parse_agent_candidate_content(str(record.content or ""))
        title = str(
            metadata.get("candidate_title")
            or parsed_content.get("interaction.sop.title")
            or parsed_content.get("interaction.sop.topic")
            or ""
        ).strip()
        steps = parsed_content.get("steps") or []
        if not isinstance(steps, list):
            steps = []
        steps = [
            self._observation_builder.normalize_text(step, max_chars=96) for step in steps if step
        ]
        steps = [step for step in steps if step]
        if not title or not steps:
            return None

        fingerprint = str(metadata.get("candidate_fingerprint") or "").strip()
        if not fingerprint:
            fingerprint = self._observation_builder.build_agent_candidate_fingerprint(title, steps)

        summary = (
            str(
                metadata.get("candidate_summary")
                or parsed_content.get("interaction.sop.summary")
                or ""
            ).strip()
            or None
        )
        applicability = (
            str(
                metadata.get("candidate_applicability")
                or parsed_content.get("interaction.sop.applicability")
                or ""
            ).strip()
            or None
        )
        avoid = (
            str(
                metadata.get("candidate_avoid") or parsed_content.get("interaction.sop.avoid") or ""
            ).strip()
            or None
        )
        review_status = review_status_override or str(metadata.get("review_status") or "pending")
        status = self._status_from_review(review_status)
        lines = [f"agent.experience.goal={title}"]
        lines.append(f"agent.experience.successful_path={' | '.join(steps)}")
        if summary:
            lines.append(f"agent.experience.why_it_worked={summary}")
        if applicability:
            lines.append(f"agent.experience.applicability={applicability}")
        if avoid:
            lines.append(f"agent.experience.avoid={avoid}")
        return MemoryEntryData(
            owner_type="agent",
            owner_id=owner_id,
            entry_type="agent_skill_candidate",
            entry_key=fingerprint,
            canonical_text="\n".join(lines),
            summary=summary,
            details=" -> ".join(steps),
            confidence=self._coerce_float(metadata.get("confidence"), default=0.72),
            importance=0.82,
            status=status,
            payload={
                "goal": title,
                "successful_path": steps,
                "why_it_worked": summary,
                "applicability": applicability,
                "avoid": avoid,
                "review_status": self._normalize_status(review_status, default="pending"),
                "review_required": bool(metadata.get("review_required", True)),
                "inject_policy": str(metadata.get("inject_policy") or "only_published"),
                "confidence": self._coerce_float(metadata.get("confidence"), default=0.72),
                "latest_turn_ts": metadata.get("latest_turn_ts"),
                "legacy_memory_id": int(record.id),
                "legacy_backfilled": True,
            },
        )

    def _normalize_user_entry(
        self,
        *,
        record: MemoryRecordData,
    ) -> Optional[MemoryEntryData]:
        metadata = dict(record.metadata or {})
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != _USER_SIGNAL_TYPE:
            return None
        owner_id = str(record.user_id or record.owner_user_id or "").strip()
        if not owner_id:
            return None
        key = str(metadata.get("preference_key") or "").strip()
        value = str(metadata.get("preference_value") or "").strip()
        if (not key or not value) and record.content:
            parsed_key, parsed_value = split_user_preference_content(str(record.content))
            key = key or str(parsed_key or "")
            value = value or str(parsed_value or "")
        if not key or not value:
            return None

        is_active = bool(metadata.get("is_active", True))
        confidence = self._coerce_float(metadata.get("confidence"), default=0.78)
        importance = (
            0.9 if bool(metadata.get("strong_signal") or metadata.get("persistent")) else 0.74
        )
        return MemoryEntryData(
            owner_type="user",
            owner_id=owner_id,
            entry_type="user_fact",
            entry_key=key,
            canonical_text=f"user.preference.{key}={value}",
            summary=value,
            details=str(metadata.get("reason") or "").strip() or None,
            confidence=confidence,
            importance=importance,
            status="active" if is_active else "superseded",
            payload={
                "key": key,
                "value": value,
                "confidence": confidence,
                "importance": importance,
                "persistent": bool(metadata.get("strong_signal") or metadata.get("persistent")),
                "explicit_source": bool(metadata.get("explicit_source")),
                "latest_turn_ts": metadata.get("latest_turn_ts"),
                "is_active": is_active,
                "legacy_memory_id": int(record.id),
                "legacy_backfilled": True,
            },
        )

    def _materialization_sort_key(
        self,
        materialization: MemoryMaterializationData,
        *,
        timestamp_hint: Optional[datetime],
    ) -> Tuple[int, datetime, float, str]:
        payload = dict(materialization.payload or {})
        latest_ts = (
            self._parse_timestamp(payload.get("latest_turn_ts")) or timestamp_hint or datetime.min
        )
        confidence = self._coerce_float(payload.get("confidence"), default=0.0)
        return (
            self._status_rank(materialization.status),
            latest_ts,
            confidence,
            str(materialization.materialization_key),
        )

    def backfill_materializations(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> MaterializationBackfillResult:
        """Project legacy `memory_records` into `memory_materializations`."""

        result = MaterializationBackfillResult(dry_run=bool(dry_run))

        user_rows = self._memory_repository.list_memories(
            memory_type=MemoryType.USER_CONTEXT,
            user_id=user_id,
            limit=limit,
        )
        result.scanned_user_context_rows = len(user_rows)
        user_candidates: Dict[
            Tuple[str, str], Tuple[MemoryMaterializationData, Optional[datetime]]
        ] = {}
        user_entry_candidates: Dict[Tuple[str, str], Tuple[MemoryEntryData, Optional[datetime]]] = (
            {}
        )
        for row in user_rows:
            candidate = self._normalize_user_profile_materialization(record=row)
            if candidate is None:
                continue
            result.user_profile_candidates += 1
            identity = (candidate.owner_id, candidate.materialization_key)
            current = user_candidates.get(identity)
            timestamp_hint = self._parse_timestamp(row.timestamp)
            if current is None or self._materialization_sort_key(
                candidate,
                timestamp_hint=timestamp_hint,
            ) >= self._materialization_sort_key(current[0], timestamp_hint=current[1]):
                user_candidates[identity] = (candidate, timestamp_hint)
            entry_candidate = self._normalize_user_entry(record=row)
            if entry_candidate is None:
                continue
            result.user_entry_candidates += 1
            entry_identity = (entry_candidate.owner_id, entry_candidate.entry_key)
            current_entry = user_entry_candidates.get(entry_identity)
            if current_entry is None or self._materialization_sort_key(
                MemoryMaterializationData(
                    owner_type=entry_candidate.owner_type,
                    owner_id=entry_candidate.owner_id,
                    materialization_type="user_profile",
                    materialization_key=entry_candidate.entry_key,
                    title=entry_candidate.entry_key,
                    summary=entry_candidate.summary,
                    details=entry_candidate.details,
                    status=entry_candidate.status,
                    payload=entry_candidate.payload,
                ),
                timestamp_hint=timestamp_hint,
            ) >= self._materialization_sort_key(
                MemoryMaterializationData(
                    owner_type=current_entry[0].owner_type,
                    owner_id=current_entry[0].owner_id,
                    materialization_type="user_profile",
                    materialization_key=current_entry[0].entry_key,
                    title=current_entry[0].entry_key,
                    summary=current_entry[0].summary,
                    details=current_entry[0].details,
                    status=current_entry[0].status,
                    payload=current_entry[0].payload,
                ),
                timestamp_hint=current_entry[1],
            ):
                user_entry_candidates[entry_identity] = (entry_candidate, timestamp_hint)

        agent_rows = self._memory_repository.list_memories(
            memory_type=MemoryType.AGENT,
            agent_id=agent_id,
            user_id=user_id,
            limit=limit,
        )
        result.scanned_agent_rows = len(agent_rows)
        agent_candidates: Dict[
            Tuple[str, str], Tuple[MemoryMaterializationData, Optional[datetime]]
        ] = {}
        agent_entry_candidates: Dict[
            Tuple[str, str], Tuple[MemoryEntryData, Optional[datetime]]
        ] = {}
        for row in agent_rows:
            candidate = self._normalize_agent_experience_materialization(record=row)
            if candidate is None:
                continue
            result.agent_experience_candidates += 1
            identity = (candidate.owner_id, candidate.materialization_key)
            current = agent_candidates.get(identity)
            timestamp_hint = self._parse_timestamp(row.timestamp)
            if current is None or self._materialization_sort_key(
                candidate,
                timestamp_hint=timestamp_hint,
            ) >= self._materialization_sort_key(current[0], timestamp_hint=current[1]):
                agent_candidates[identity] = (candidate, timestamp_hint)
            entry_candidate = self._normalize_agent_entry(record=row)
            if entry_candidate is None:
                continue
            result.agent_entry_candidates += 1
            entry_identity = (entry_candidate.owner_id, entry_candidate.entry_key)
            current_entry = agent_entry_candidates.get(entry_identity)
            if current_entry is None or self._materialization_sort_key(
                MemoryMaterializationData(
                    owner_type=entry_candidate.owner_type,
                    owner_id=entry_candidate.owner_id,
                    materialization_type="agent_experience",
                    materialization_key=entry_candidate.entry_key,
                    title=entry_candidate.payload.get("goal") or entry_candidate.entry_key,
                    summary=entry_candidate.summary,
                    details=entry_candidate.details,
                    status=entry_candidate.status,
                    payload=entry_candidate.payload,
                ),
                timestamp_hint=timestamp_hint,
            ) >= self._materialization_sort_key(
                MemoryMaterializationData(
                    owner_type=current_entry[0].owner_type,
                    owner_id=current_entry[0].owner_id,
                    materialization_type="agent_experience",
                    materialization_key=current_entry[0].entry_key,
                    title=current_entry[0].payload.get("goal") or current_entry[0].entry_key,
                    summary=current_entry[0].summary,
                    details=current_entry[0].details,
                    status=current_entry[0].status,
                    payload=current_entry[0].payload,
                ),
                timestamp_hint=current_entry[1],
            ):
                agent_entry_candidates[entry_identity] = (entry_candidate, timestamp_hint)

        if dry_run:
            return result

        for candidate, _timestamp_hint in user_candidates.values():
            self._session_repository.upsert_materialization(materialization=candidate)
            result.user_profile_upserts += 1
        for candidate, _timestamp_hint in agent_candidates.values():
            self._session_repository.upsert_materialization(materialization=candidate)
            result.agent_experience_upserts += 1
        for candidate, _timestamp_hint in user_entry_candidates.values():
            self._session_repository.upsert_entry(entry=candidate)
            result.user_entry_upserts += 1
        for candidate, _timestamp_hint in agent_entry_candidates.values():
            self._session_repository.upsert_entry(entry=candidate)
            result.agent_entry_upserts += 1

        return result

    def _desired_user_status(self, row) -> str:
        payload = dict(row.materialized_data or {})
        return "active" if bool(payload.get("is_active", True)) else "superseded"

    def _desired_user_entry_status(self, row) -> str:
        payload = dict(getattr(row, "entry_data", None) or {})
        return "active" if bool(payload.get("is_active", True)) else "superseded"

    def _agent_signature(self, row) -> Optional[str]:
        payload = dict(row.materialized_data or {})
        goal = self._observation_builder.normalize_text(
            payload.get("goal") or row.title or "",
            max_chars=120,
        ).lower()
        steps = [
            self._observation_builder.normalize_text(step, max_chars=96).lower()
            for step in (payload.get("successful_path") or [])
            if step
        ]
        if not goal or not steps:
            return None
        return f"{goal}||{'|'.join(steps)}"

    def _desired_agent_status(self, row) -> str:
        payload = dict(row.materialized_data or {})
        review_status = payload.get("review_status")
        if review_status is None:
            return self._normalize_status(row.status, default="pending_review")
        return self._status_from_review(review_status)

    def _entry_signature(self, row) -> Optional[str]:
        payload = dict(getattr(row, "entry_data", None) or {})
        entry_type = str(getattr(row, "entry_type", "") or "").strip().lower()
        if entry_type == "user_fact":
            key = str(payload.get("key") or getattr(row, "entry_key", "") or "").strip().lower()
            if not key:
                return None
            return key
        if entry_type == "agent_skill_candidate":
            goal = self._observation_builder.normalize_text(
                payload.get("goal") or getattr(row, "summary", "") or "",
                max_chars=120,
            ).lower()
            steps = [
                self._observation_builder.normalize_text(step, max_chars=96).lower()
                for step in (payload.get("successful_path") or [])
                if step
            ]
            if not goal or not steps:
                return None
            return f"{goal}||{'|'.join(steps)}"
        return None

    def _desired_agent_entry_status(self, row) -> str:
        payload = dict(getattr(row, "entry_data", None) or {})
        review_status = payload.get("review_status")
        if review_status is None:
            return self._normalize_status(getattr(row, "status", None), default="pending_review")
        return self._status_from_review(review_status)

    def consolidate_materializations(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> MaterializationConsolidationResult:
        """Normalize status drift and supersede duplicate agent experiences."""

        result = MaterializationConsolidationResult(dry_run=bool(dry_run))

        user_rows = self._session_repository.list_materializations(
            owner_type="user",
            owner_id=user_id,
            materialization_type="user_profile",
            status=None,
            limit=limit,
        )
        result.scanned_user_profiles = len(user_rows)
        for row in user_rows:
            desired_status = self._desired_user_status(row)
            if str(row.status or "") == desired_status:
                continue
            result.user_status_updates += 1
            if dry_run:
                continue
            payload = dict(row.materialized_data or {})
            payload["status_sync_reason"] = "payload_is_active"
            self._session_repository.update_materialization(
                int(row.id),
                status=desired_status,
                payload=payload,
            )

        agent_rows = self._session_repository.list_materializations(
            owner_type="agent",
            owner_id=agent_id,
            materialization_type="agent_experience",
            status=None,
            limit=limit,
        )
        result.scanned_agent_experiences = len(agent_rows)

        for row in agent_rows:
            desired_status = self._desired_agent_status(row)
            if str(row.status or "") == desired_status:
                continue
            result.agent_status_updates += 1
            if dry_run:
                continue
            payload = dict(row.materialized_data or {})
            payload["status_sync_reason"] = "review_status"
            self._session_repository.update_materialization(
                int(row.id),
                status=desired_status,
                payload=payload,
            )
            row.status = desired_status
            row.materialized_data = payload

        grouped: Dict[Tuple[str, str], List[Any]] = {}
        for row in agent_rows:
            signature = self._agent_signature(row)
            if not signature:
                continue
            grouped.setdefault((str(row.owner_id), signature), []).append(row)

        for (_owner_id, _signature), rows in grouped.items():
            if len(rows) < 2:
                continue
            rows.sort(
                key=lambda row: (
                    self._status_rank(row.status),
                    self._coerce_float(
                        dict(row.materialized_data or {}).get("confidence"), default=0.0
                    ),
                    getattr(row, "updated_at", None)
                    or getattr(row, "created_at", None)
                    or datetime.min,
                    int(getattr(row, "id", 0) or 0),
                ),
                reverse=True,
            )
            canonical = rows[0]
            duplicate_ids = [int(getattr(item, "id", 0) or 0) for item in rows[1:]]
            for duplicate in rows[1:]:
                if str(duplicate.status or "") == "superseded":
                    continue
                result.agent_duplicate_supersedes += 1
                if dry_run:
                    continue
                payload = dict(duplicate.materialized_data or {})
                payload.update(
                    {
                        "superseded_by_materialization_id": int(canonical.id),
                        "superseded_by_key": str(canonical.materialization_key),
                        "superseded_at": _utc_now_iso(),
                    }
                )
                self._session_repository.update_materialization(
                    int(duplicate.id),
                    status="superseded",
                    payload=payload,
                )
            if not dry_run and duplicate_ids:
                canonical_payload = dict(canonical.materialized_data or {})
                merged_ids = list(
                    dict.fromkeys(
                        [
                            *(canonical_payload.get("merged_materialization_ids") or []),
                            *duplicate_ids,
                        ]
                    )
                )
                canonical_payload["merged_materialization_ids"] = merged_ids
                self._session_repository.update_materialization(
                    int(canonical.id),
                    payload=canonical_payload,
                )

        user_entry_rows = self._session_repository.list_entries(
            owner_type="user",
            owner_id=user_id,
            entry_type="user_fact",
            status=None,
            limit=limit,
        )
        result.scanned_user_entries = len(user_entry_rows)
        for row in user_entry_rows:
            desired_status = self._desired_user_entry_status(row)
            if str(getattr(row, "status", "") or "") == desired_status:
                continue
            result.user_entry_status_updates += 1
            if dry_run:
                continue
            payload = dict(getattr(row, "entry_data", None) or {})
            payload["status_sync_reason"] = "payload_is_active"
            self._session_repository.update_entry(
                int(row.id),
                status=desired_status,
                payload=payload,
            )
            row.status = desired_status
            row.entry_data = payload

        agent_entry_rows = self._session_repository.list_entries(
            owner_type="agent",
            owner_id=agent_id,
            entry_type="agent_skill_candidate",
            status=None,
            limit=limit,
        )
        result.scanned_agent_entries = len(agent_entry_rows)
        for row in agent_entry_rows:
            desired_status = self._desired_agent_entry_status(row)
            if str(getattr(row, "status", "") or "") == desired_status:
                continue
            result.agent_entry_status_updates += 1
            if dry_run:
                continue
            payload = dict(getattr(row, "entry_data", None) or {})
            payload["status_sync_reason"] = "review_status"
            self._session_repository.update_entry(
                int(row.id),
                status=desired_status,
                payload=payload,
            )
            row.status = desired_status
            row.entry_data = payload

        grouped_user_entries: Dict[Tuple[str, str], List[Any]] = {}
        for row in user_entry_rows:
            signature = self._entry_signature(row)
            if not signature:
                continue
            grouped_user_entries.setdefault((str(row.owner_id), signature), []).append(row)

        for (_owner_id, _signature), rows in grouped_user_entries.items():
            if len(rows) < 2:
                continue
            rows.sort(
                key=lambda row: (
                    self._status_rank(getattr(row, "status", None)),
                    self._coerce_float(
                        dict(getattr(row, "entry_data", None) or {}).get("confidence"),
                        default=0.0,
                    ),
                    getattr(row, "updated_at", None)
                    or getattr(row, "created_at", None)
                    or datetime.min,
                    int(getattr(row, "id", 0) or 0),
                ),
                reverse=True,
            )
            canonical = rows[0]
            for duplicate in rows[1:]:
                if str(getattr(duplicate, "status", "") or "") == "superseded":
                    continue
                result.user_duplicate_entry_supersedes += 1
                if dry_run:
                    continue
                payload = dict(getattr(duplicate, "entry_data", None) or {})
                payload.update(
                    {
                        "superseded_by_entry_id": int(canonical.id),
                        "superseded_by_key": str(canonical.entry_key),
                        "superseded_at": _utc_now_iso(),
                    }
                )
                self._session_repository.update_entry(
                    int(duplicate.id),
                    status="superseded",
                    payload=payload,
                )

        grouped_agent_entries: Dict[Tuple[str, str], List[Any]] = {}
        for row in agent_entry_rows:
            signature = self._entry_signature(row)
            if not signature:
                continue
            grouped_agent_entries.setdefault((str(row.owner_id), signature), []).append(row)

        for (_owner_id, _signature), rows in grouped_agent_entries.items():
            if len(rows) < 2:
                continue
            rows.sort(
                key=lambda row: (
                    self._status_rank(getattr(row, "status", None)),
                    self._coerce_float(
                        dict(getattr(row, "entry_data", None) or {}).get("confidence"),
                        default=0.0,
                    ),
                    getattr(row, "updated_at", None)
                    or getattr(row, "created_at", None)
                    or datetime.min,
                    int(getattr(row, "id", 0) or 0),
                ),
                reverse=True,
            )
            canonical = rows[0]
            for duplicate in rows[1:]:
                if str(getattr(duplicate, "status", "") or "") == "superseded":
                    continue
                result.agent_duplicate_entry_supersedes += 1
                if dry_run:
                    continue
                payload = dict(getattr(duplicate, "entry_data", None) or {})
                payload.update(
                    {
                        "superseded_by_entry_id": int(canonical.id),
                        "superseded_by_key": str(canonical.entry_key),
                        "superseded_at": _utc_now_iso(),
                    }
                )
                self._session_repository.update_entry(
                    int(duplicate.id),
                    status="superseded",
                    payload=payload,
                )

        return result

    def sync_agent_candidate_materialization(
        self,
        *,
        record: MemoryRecordData,
        review_status: Optional[str] = None,
    ) -> Optional[int]:
        """Mirror one reviewed legacy candidate into `memory_materializations`."""

        materialization = self._normalize_agent_experience_materialization(
            record=record,
            review_status_override=review_status,
        )
        entry = self._normalize_agent_entry(
            record=record,
            review_status_override=review_status,
        )
        if materialization is None:
            return None
        materialization_id = self._session_repository.upsert_materialization(
            materialization=materialization
        )
        if entry is not None:
            self._session_repository.upsert_entry(entry=entry)
        return materialization_id

    def run_maintenance(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
        include_backfill: bool = True,
        include_consolidation: bool = True,
    ) -> MaterializationMaintenanceResult:
        backfill_result = MaterializationBackfillResult(dry_run=bool(dry_run))
        consolidation_result = MaterializationConsolidationResult(dry_run=bool(dry_run))
        if include_backfill:
            backfill_result = self.backfill_materializations(
                dry_run=dry_run,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
            )
        if include_consolidation:
            consolidation_result = self.consolidate_materializations(
                dry_run=dry_run,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
            )
        return MaterializationMaintenanceResult(
            backfill=backfill_result,
            consolidation=consolidation_result,
        )

    @staticmethod
    def to_dict(result: MaterializationMaintenanceResult) -> Dict[str, Any]:
        return {
            "backfill": asdict(result.backfill),
            "consolidation": asdict(result.consolidation),
        }


_materialization_maintenance_service: Optional[MaterializationMaintenanceService] = None


def get_materialization_maintenance_service() -> MaterializationMaintenanceService:
    global _materialization_maintenance_service
    if _materialization_maintenance_service is None:
        _materialization_maintenance_service = MaterializationMaintenanceService()
    return _materialization_maintenance_service
