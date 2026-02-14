#!/usr/bin/env python3
"""Backfill missing user_id for agent memories.

Examples:
    cd backend
    .venv/bin/python scripts/backfill_agent_memory_user_ids.py --dry-run
    .venv/bin/python scripts/backfill_agent_memory_user_ids.py --apply
    .venv/bin/python scripts/backfill_agent_memory_user_ids.py --apply --reindex-vectors
    .venv/bin/python scripts/backfill_agent_memory_user_ids.py --agent-id <uuid> --apply
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

from memory_system.agent_memory_backfill import backfill_agent_memory_user_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing user_id on agent memories")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Default is dry-run.",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Only backfill one agent UUID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to scan/update in this run",
    )
    parser.add_argument(
        "--reindex-vectors",
        action="store_true",
        help="After DB backfill, rebuild Milvus vectors for updated rows",
    )
    args = parser.parse_args()

    if args.reindex_vectors and not args.apply:
        print("--reindex-vectors requires --apply", file=sys.stderr)
        return 2

    try:
        result = backfill_agent_memory_user_ids(
            dry_run=not args.apply,
            agent_id=args.agent_id,
            limit=args.limit,
            reindex_vectors=args.reindex_vectors,
        )
    except Exception as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
