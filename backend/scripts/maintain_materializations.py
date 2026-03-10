#!/usr/bin/env python3
"""Run materialization backfill and consolidation maintenance.

Examples:
    cd backend
    .venv/bin/python scripts/maintain_materializations.py --dry-run
    .venv/bin/python scripts/maintain_materializations.py --apply
    .venv/bin/python scripts/maintain_materializations.py --apply --agent-id <uuid>
    .venv/bin/python scripts/maintain_materializations.py --apply --skip-backfill
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make backend package imports work when running as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory_system.materialization_maintenance_service import (
    get_materialization_maintenance_service,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill and consolidate memory materializations",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Default is dry-run.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Only process one user for user_profile maintenance",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Only process one agent for agent_experience maintenance",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max legacy rows/materializations to scan in this run",
    )
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="Skip legacy memory_records -> materialization backfill",
    )
    parser.add_argument(
        "--skip-consolidation",
        action="store_true",
        help="Skip status-sync and duplicate consolidation",
    )
    args = parser.parse_args()

    if args.skip_backfill and args.skip_consolidation:
        print(
            "Nothing to do: both --skip-backfill and --skip-consolidation were set.",
            file=sys.stderr,
        )
        return 2

    try:
        result = get_materialization_maintenance_service().run_maintenance(
            dry_run=not args.apply,
            user_id=args.user_id,
            agent_id=args.agent_id,
            limit=args.limit,
            include_backfill=not args.skip_backfill,
            include_consolidation=not args.skip_consolidation,
        )
    except Exception as exc:
        print(f"Materialization maintenance failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            get_materialization_maintenance_service().to_dict(result),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
