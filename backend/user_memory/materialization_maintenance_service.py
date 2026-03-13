"""Consolidation utilities for user-memory materializations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from user_memory.session_ledger_repository import (
    SessionLedgerRepository,
    get_session_ledger_repository,
)
from user_memory.session_observation_builder import get_session_observation_builder

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    consolidation: MaterializationConsolidationResult


class MaterializationMaintenanceService:
    """Normalize materialized user-memory and skill-learning views."""

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
        return _AGENT_REVIEW_TO_STATUS.get(normalized, "pending_review")

    @staticmethod
    def _desired_user_status(row: Any) -> str:
        payload = dict(row.materialized_data or {})
        return "active" if bool(payload.get("is_active", True)) else "superseded"

    @staticmethod
    def _desired_user_entry_status(row: Any) -> str:
        payload = dict(getattr(row, "entry_data", None) or {})
        return "active" if bool(payload.get("is_active", True)) else "superseded"

    def _agent_signature(self, row: Any) -> Optional[str]:
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

    def _desired_agent_status(self, row: Any) -> str:
        payload = dict(row.materialized_data or {})
        review_status = payload.get("review_status")
        if review_status is None:
            return self._normalize_status(row.status, default="pending_review")
        return self._status_from_review(review_status)

    def _entry_signature(self, row: Any) -> Optional[str]:
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

    def _desired_agent_entry_status(self, row: Any) -> str:
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
        """Normalize status drift and supersede duplicate materializations/entries."""

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

    def run_maintenance(
        self,
        *,
        dry_run: bool = True,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> MaterializationMaintenanceResult:
        return MaterializationMaintenanceResult(
            consolidation=self.consolidate_materializations(
                dry_run=dry_run,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
            )
        )

    @staticmethod
    def to_dict(result: MaterializationMaintenanceResult) -> Dict[str, Any]:
        return {
            "consolidation": asdict(result.consolidation),
        }


_materialization_maintenance_service: Optional[MaterializationMaintenanceService] = None


def get_materialization_maintenance_service() -> MaterializationMaintenanceService:
    global _materialization_maintenance_service
    if _materialization_maintenance_service is None:
        _materialization_maintenance_service = MaterializationMaintenanceService()
    return _materialization_maintenance_service
