"""Consolidation utilities for reset-era user-memory views and skill proposals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from user_memory.fact_identity import normalize_identity_text
from user_memory.session_ledger_repository import (
    MemoryProjectionData,
    SessionLedgerRepository,
    get_session_ledger_repository,
)
from user_memory.session_observation_builder import get_session_observation_builder

_REVIEW_TO_STATUS = {
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ProjectionConsolidationResult:
    scanned_user_profiles: int = 0
    scanned_skill_proposals: int = 0
    scanned_user_entries: int = 0
    episode_view_upserts: int = 0
    user_status_updates: int = 0
    skill_proposal_status_updates: int = 0
    user_entry_status_updates: int = 0
    skill_proposal_duplicate_supersedes: int = 0
    user_duplicate_entry_supersedes: int = 0
    dry_run: bool = True


@dataclass
class ProjectionMaintenanceResult:
    consolidation: ProjectionConsolidationResult


class ProjectionMaintenanceService:
    """Normalize reset-era projection rows and remove duplicate drift."""

    def __init__(
        self,
        *,
        session_repository: Optional[SessionLedgerRepository] = None,
    ) -> None:
        self._session_repository = session_repository or get_session_ledger_repository()
        self._observation_builder = get_session_observation_builder()

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

    def _status_from_review(self, review_status: Any) -> str:
        normalized = self._normalize_status(review_status, default="pending")
        return _REVIEW_TO_STATUS.get(normalized, "pending_review")

    @staticmethod
    def _desired_user_status(row: Any) -> str:
        payload = dict(getattr(row, "view_data", None) or {})
        return "active" if bool(payload.get("is_active", True)) else "superseded"

    @staticmethod
    def _desired_user_entry_status(row: Any) -> str:
        payload = dict(getattr(row, "entry_data", None) or {})
        return "active" if bool(payload.get("is_active", True)) else "superseded"

    def _build_episode_view_from_entry(self, row: Any) -> Optional[MemoryProjectionData]:
        payload = dict(getattr(row, "entry_data", None) or {})
        if str(getattr(row, "fact_kind", "") or "").strip().lower() != "event":
            return None

        canonical_statement = str(
            payload.get("canonical_statement") or getattr(row, "canonical_text", "") or ""
        ).strip()
        value = str(
            payload.get("value") or getattr(row, "summary", "") or canonical_statement
        ).strip()
        event_time = (
            str(payload.get("event_time") or getattr(row, "event_time", "") or "").strip() or None
        )
        topic = str(payload.get("topic") or getattr(row, "topic", "") or "").strip() or None
        stable_key = str(payload.get("key") or getattr(row, "entry_key", "") or "").strip()
        episode_key = self._observation_builder._build_user_episode_view_key(  # noqa: SLF001
            stable_key=stable_key,
            canonical_statement=canonical_statement,
            event_time=event_time,
            value=value,
        )
        title = self._observation_builder._build_user_episode_title(  # noqa: SLF001
            canonical_statement=canonical_statement,
            event_time=event_time,
            topic=topic,
            value=value,
        )
        details = str(payload.get("details") or getattr(row, "details", None) or "").strip() or None
        return MemoryProjectionData(
            owner_type="user",
            owner_id=str(getattr(row, "owner_id", None) or getattr(row, "user_id", "")),
            projection_type="episode",
            projection_key=episode_key,
            title=title,
            summary=canonical_statement or value or title,
            details=details,
            status="active",
            payload={
                "key": stable_key,
                "semantic_key": payload.get("semantic_key"),
                "value": value,
                "fact_kind": "event",
                "canonical_statement": canonical_statement or None,
                "predicate": payload.get("predicate"),
                "object": payload.get("object"),
                "event_time": event_time,
                "persons": list(payload.get("persons") or getattr(row, "persons", None) or []),
                "entities": list(payload.get("entities") or getattr(row, "entities", None) or []),
                "location": payload.get("location") or getattr(row, "location", None),
                "topic": topic,
                "confidence": payload.get("confidence", getattr(row, "confidence", None)),
                "importance": payload.get("importance", getattr(row, "importance", None)),
                "source_entry_key": stable_key,
                "source_entry_id": int(getattr(row, "id", 0) or 0),
                "is_active": str(getattr(row, "status", "") or "active") == "active",
            },
        )

    def _proposal_signature(self, row: Any) -> Optional[str]:
        payload = dict(getattr(row, "proposal_payload", None) or {})
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

    def _desired_skill_proposal_status(self, row: Any) -> str:
        payload = dict(getattr(row, "proposal_payload", None) or {})
        review_status = payload.get("review_status")
        if review_status is None:
            return self._normalize_status(getattr(row, "status", None), default="pending_review")
        return self._status_from_review(review_status)

    def _entry_signature(self, row: Any) -> Optional[str]:
        payload = dict(getattr(row, "entry_data", None) or {})
        if str(getattr(row, "entry_type", "") or "").strip().lower() != "user_fact":
            return None
        identity_signature = str(payload.get("identity_signature") or "").strip()
        if identity_signature:
            return identity_signature
        fact_kind = (
            str(payload.get("fact_kind") or getattr(row, "fact_kind", "") or "").strip().lower()
        )
        canonical = self._normalize_signature_text(
            payload.get("canonical_statement")
            or getattr(row, "canonical_text", "")
            or getattr(row, "summary", "")
            or payload.get("value")
            or ""
        )
        event_time = str(payload.get("event_time") or getattr(row, "event_time", "") or "").strip()
        if fact_kind == "event" and canonical:
            return f"event::{event_time}::{canonical}"
        if fact_kind in {"preference", "identity", "constraint", "habit"} and canonical:
            return f"{fact_kind}::{canonical}"
        key = str(payload.get("key") or getattr(row, "entry_key", "") or "").strip().lower()
        return key or canonical or None

    def _view_signature(self, row: Any) -> Optional[str]:
        payload = dict(getattr(row, "view_data", None) or {})
        view_type = str(getattr(row, "view_type", "") or "").strip().lower()
        identity_signature = str(payload.get("identity_signature") or "").strip()
        if identity_signature:
            return identity_signature
        canonical = self._normalize_signature_text(
            payload.get("canonical_statement")
            or getattr(row, "content", "")
            or getattr(row, "summary", "")
            or getattr(row, "title", "")
            or ""
        )
        event_time = str(payload.get("event_time") or "").strip()
        fact_kind = str(payload.get("fact_kind") or "").strip().lower()
        if view_type == "episode" and canonical:
            return f"episode::{event_time}::{canonical}"
        if view_type == "user_profile" and canonical:
            return f"profile::{fact_kind or 'generic'}::{canonical}"
        key = str(getattr(row, "view_key", "") or "").strip().lower()
        return key or canonical or None

    @staticmethod
    def _normalize_signature_text(value: Any) -> str:
        text = normalize_identity_text(value)
        if not text:
            return ""
        return "".join(ch for ch in text if not ch.isspace())

    def _looks_like_ephemeral_relationship_entry(self, row: Any) -> bool:
        payload = dict(getattr(row, "entry_data", None) or {})
        if str(getattr(row, "fact_kind", "") or "").strip().lower() != "relationship":
            return False
        return self._observation_builder._looks_like_ephemeral_relationship_signal(  # noqa: SLF001
            semantic_key=str(payload.get("semantic_key") or getattr(row, "entry_key", "") or ""),
            predicate=payload.get("predicate") or getattr(row, "predicate", None),
            value=str(
                payload.get("value")
                or payload.get("fact_value")
                or getattr(row, "object_text", "")
                or ""
            ),
            canonical_statement=str(
                payload.get("canonical_statement") or getattr(row, "canonical_text", "") or ""
            ),
            event_time=str(payload.get("event_time") or getattr(row, "event_time", "") or "")
            or None,
        )

    def _looks_like_ephemeral_relationship_view(self, row: Any) -> bool:
        payload = dict(getattr(row, "view_data", None) or {})
        if str(getattr(row, "view_type", "") or "").strip().lower() != "user_profile":
            return False
        if str(payload.get("fact_kind") or "").strip().lower() != "relationship":
            return False
        return self._observation_builder._looks_like_ephemeral_relationship_signal(  # noqa: SLF001
            semantic_key=str(payload.get("semantic_key") or getattr(row, "view_key", "") or ""),
            predicate=payload.get("predicate"),
            value=str(payload.get("value") or payload.get("object") or ""),
            canonical_statement=str(
                payload.get("canonical_statement")
                or getattr(row, "content", "")
                or getattr(row, "summary", "")
                or ""
            ),
            event_time=str(payload.get("event_time") or "") or None,
        )

    def consolidate_projections(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> ProjectionConsolidationResult:
        """Normalize status drift and supersede duplicate projections/entries."""

        result = ProjectionConsolidationResult(dry_run=bool(dry_run))

        user_rows = self._session_repository.list_projections(
            owner_type="user",
            owner_id=user_id,
            projection_type=None,
            status=None,
            limit=limit,
        )
        result.scanned_user_profiles = len(user_rows)
        for row in user_rows:
            desired_status = self._desired_user_status(row)
            payload = dict(getattr(row, "view_data", None) or {})
            if self._looks_like_ephemeral_relationship_view(row):
                desired_status = "superseded"
                payload["is_active"] = False
                payload["cleanup_reason"] = "ephemeral_relative_relationship"
            if str(row.status or "") == desired_status:
                continue
            result.user_status_updates += 1
            if dry_run:
                continue
            payload.setdefault("status_sync_reason", "payload_is_active")
            self._session_repository.update_projection(
                int(row.id),
                status=desired_status,
                payload=payload,
            )
            row.status = desired_status
            row.view_data = payload

        proposal_rows = self._session_repository.list_projections(
            owner_type="agent",
            owner_id=agent_id,
            projection_type="skill_proposal",
            status=None,
            limit=limit,
        )
        result.scanned_skill_proposals = len(proposal_rows)

        for row in proposal_rows:
            desired_status = self._desired_skill_proposal_status(row)
            if str(row.status or "") == desired_status:
                continue
            result.skill_proposal_status_updates += 1
            if dry_run:
                continue
            payload = dict(getattr(row, "proposal_payload", None) or {})
            payload["status_sync_reason"] = "review_status"
            self._session_repository.update_projection(
                int(row.id),
                status=desired_status,
                payload=payload,
            )
            row.status = desired_status
            row.proposal_payload = payload

        grouped_proposals: Dict[Tuple[str, str], List[Any]] = {}
        for row in proposal_rows:
            signature = self._proposal_signature(row)
            if not signature:
                continue
            grouped_proposals.setdefault((str(row.owner_id), signature), []).append(row)

        for (_owner_id, _signature), rows in grouped_proposals.items():
            if len(rows) < 2:
                continue
            rows.sort(
                key=lambda row: (
                    self._status_rank(row.status),
                    self._coerce_float(
                        dict(getattr(row, "proposal_payload", None) or {}).get("confidence"),
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
            duplicate_ids = [int(getattr(item, "id", 0) or 0) for item in rows[1:]]
            for duplicate in rows[1:]:
                if str(duplicate.status or "") == "superseded":
                    continue
                result.skill_proposal_duplicate_supersedes += 1
                if dry_run:
                    continue
                payload = dict(getattr(duplicate, "proposal_payload", None) or {})
                payload.update(
                    {
                        "superseded_by_proposal_id": int(canonical.id),
                        "superseded_by_key": str(canonical.proposal_key),
                        "superseded_at": _utc_now_iso(),
                    }
                )
                self._session_repository.update_projection(
                    int(duplicate.id),
                    status="superseded",
                    payload=payload,
                )
            if not dry_run and duplicate_ids:
                canonical_payload = dict(getattr(canonical, "proposal_payload", None) or {})
                merged_ids = list(
                    dict.fromkeys(
                        [
                            *(canonical_payload.get("merged_proposal_ids") or []),
                            *duplicate_ids,
                        ]
                    )
                )
                canonical_payload["merged_proposal_ids"] = merged_ids
                self._session_repository.update_projection(
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
            payload = dict(getattr(row, "entry_data", None) or {})
            if self._looks_like_ephemeral_relationship_entry(row):
                desired_status = "superseded"
                payload["is_active"] = False
                payload["cleanup_reason"] = "ephemeral_relative_relationship"
            if str(getattr(row, "status", "") or "") == desired_status:
                continue
            result.user_entry_status_updates += 1
            if dry_run:
                continue
            payload.setdefault("status_sync_reason", "payload_is_active")
            self._session_repository.update_entry(
                int(row.id),
                status=desired_status,
                payload=payload,
            )
            row.status = desired_status
            row.entry_data = payload

        for row in user_entry_rows:
            desired_view = self._build_episode_view_from_entry(row)
            if desired_view is None:
                continue
            existing_view = self._session_repository.get_projection(
                owner_type="user",
                owner_id=str(desired_view.owner_id),
                projection_type="episode",
                projection_key=str(desired_view.projection_key),
            )
            current_payload = (
                dict(getattr(existing_view, "view_data", None) or {})
                if existing_view is not None
                else None
            )
            if (
                existing_view is not None
                and str(getattr(existing_view, "title", "") or "") == str(desired_view.title)
                and str(getattr(existing_view, "summary", "") or "") == str(desired_view.summary)
                and str(getattr(existing_view, "status", "") or "") == str(desired_view.status)
                and current_payload == dict(desired_view.payload or {})
            ):
                continue
            result.episode_view_upserts += 1
            if dry_run:
                continue
            self._session_repository.upsert_projection(
                projection=desired_view,
                source_session_id=getattr(row, "source_session_id", None),
            )

        grouped_user_views: Dict[Tuple[str, str], List[Any]] = {}
        for row in user_rows:
            signature = self._view_signature(row)
            if not signature:
                continue
            grouped_user_views.setdefault((str(row.owner_id), signature), []).append(row)

        for (_owner_id, _signature), rows in grouped_user_views.items():
            if len(rows) < 2:
                continue
            rows.sort(
                key=lambda row: (
                    self._status_rank(getattr(row, "status", None)),
                    self._coerce_float(
                        dict(getattr(row, "view_data", None) or {}).get("confidence"),
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
                result.user_status_updates += 1
                if dry_run:
                    continue
                payload = dict(getattr(duplicate, "view_data", None) or {})
                payload.update(
                    {
                        "is_active": False,
                        "cleanup_reason": "duplicate_projection",
                        "superseded_by_view_id": int(canonical.id),
                        "superseded_by_key": str(canonical.view_key),
                        "superseded_at": _utc_now_iso(),
                    }
                )
                self._session_repository.update_projection(
                    int(duplicate.id),
                    status="superseded",
                    payload=payload,
                )

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
                        "is_active": False,
                        "cleanup_reason": "duplicate_entry",
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

    def run_maintenance(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> ProjectionMaintenanceResult:
        return ProjectionMaintenanceResult(
            consolidation=self.consolidate_projections(
                dry_run=dry_run,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
            )
        )

    @staticmethod
    def to_dict(result: ProjectionMaintenanceResult) -> Dict[str, Any]:
        return {
            "consolidation": asdict(result.consolidation),
        }


_projection_maintenance_service: Optional[ProjectionMaintenanceService] = None


def get_projection_maintenance_service() -> ProjectionMaintenanceService:
    global _projection_maintenance_service
    if _projection_maintenance_service is None:
        _projection_maintenance_service = ProjectionMaintenanceService()
    return _projection_maintenance_service
