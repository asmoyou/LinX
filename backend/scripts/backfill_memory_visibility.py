#!/usr/bin/env python3
"""Backfill memory visibility to match current policy defaults.

Rules:
1. company memory:
   - missing/empty visibility -> department_tree
   - account -> department_tree
2. user_context memory:
   - only private/explicit are allowed
   - others (including empty/account) -> private

Examples:
    cd backend
    .venv/bin/python scripts/backfill_memory_visibility.py --dry-run
    .venv/bin/python scripts/backfill_memory_visibility.py --apply
    .venv/bin/python scripts/backfill_memory_visibility.py --dry-run --limit 500
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

# Make backend package imports work when running as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_session
from database.models import MemoryRecord


USER_CONTEXT_ALLOWED = {"private", "explicit"}


def _normalize_visibility(memory_type: str, configured: str) -> str:
    mem_type = str(memory_type or "").strip().lower()
    value = str(configured or "").strip().lower()

    if mem_type == "user_context":
        if value in USER_CONTEXT_ALLOWED:
            return value
        return "private"

    if mem_type == "company":
        if not value or value == "account":
            return "department_tree"
        return value

    return value


def _classify_reason(memory_type: str, configured: str, normalized: str) -> str:
    mem_type = str(memory_type or "").strip().lower()
    value = str(configured or "").strip().lower()

    if mem_type == "company":
        if not value:
            return "company_missing_to_department_tree"
        if value == "account":
            return "company_account_to_department_tree"
        if value != normalized:
            return "company_normalized"
        return "company_synced"

    if mem_type == "user_context":
        if value not in USER_CONTEXT_ALLOWED:
            return "user_context_invalid_to_private"
        if value != normalized:
            return "user_context_normalized"
        return "user_context_synced"

    return "other"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def run_backfill(*, dry_run: bool, limit: Optional[int] = None) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "dry_run": dry_run,
        "scanned": 0,
        "updated": 0,
        "updated_by_type": {"company": 0, "user_context": 0},
        "reasons": {},
        "sample_updates": [],
    }
    reasons = Counter()

    with get_db_session() as session:
        query = (
            session.query(MemoryRecord)
            .filter(MemoryRecord.is_deleted.is_(False))
            .filter(MemoryRecord.memory_type.in_(["company", "user_context"]))
            .order_by(MemoryRecord.id.asc())
        )
        if limit is not None:
            query = query.limit(max(int(limit), 1))

        rows = query.all()
        summary["scanned"] = len(rows)

        for row in rows:
            metadata = dict(row.memory_metadata or {})
            row_visibility = _normalize_text(row.visibility)
            meta_visibility = _normalize_text(metadata.get("visibility"))
            configured = meta_visibility or row_visibility

            normalized = _normalize_visibility(row.memory_type, configured)
            reason = _classify_reason(row.memory_type, configured, normalized)

            metadata_target = _normalize_text(metadata.get("visibility"))
            requires_update = row_visibility != normalized or metadata_target != normalized
            if not requires_update:
                continue

            summary["updated"] += 1
            if row.memory_type in summary["updated_by_type"]:
                summary["updated_by_type"][row.memory_type] += 1
            reasons[reason] += 1

            if len(summary["sample_updates"]) < 30:
                summary["sample_updates"].append(
                    {
                        "id": int(row.id),
                        "memory_type": row.memory_type,
                        "from_row_visibility": row_visibility or None,
                        "from_metadata_visibility": metadata_target or None,
                        "to_visibility": normalized,
                        "reason": reason,
                    }
                )

            if not dry_run:
                row.visibility = normalized
                metadata["visibility"] = normalized
                row.memory_metadata = metadata

        if not dry_run:
            session.flush()

    summary["reasons"] = dict(reasons)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill memory visibility policy defaults")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Default is dry-run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode (default when --apply is absent).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to scan in this run",
    )
    args = parser.parse_args()

    dry_run = True
    if args.apply:
        dry_run = False
    if args.dry_run:
        dry_run = True

    try:
        result = run_backfill(dry_run=dry_run, limit=args.limit)
    except Exception as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
