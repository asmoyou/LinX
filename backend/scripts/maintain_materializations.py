#!/usr/bin/env python3
"""Run materialization consolidation maintenance.

Examples:
    cd backend
    .venv/bin/python scripts/maintain_materializations.py --dry-run
    .venv/bin/python scripts/maintain_materializations.py --apply
    .venv/bin/python scripts/maintain_materializations.py --apply --agent-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from user_memory.materialization_maintenance_service import (
    get_materialization_maintenance_service,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidate user-memory materializations",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Default is dry-run.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Only process one user for user-profile consolidation",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Only process one agent for skill-proposal consolidation",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max materializations/entries to scan in this run",
    )
    args = parser.parse_args()

    try:
        service = get_materialization_maintenance_service()
        result = service.run_maintenance(
            dry_run=not args.apply,
            user_id=args.user_id,
            agent_id=args.agent_id,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"Materialization maintenance failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(service.to_dict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
