#!/usr/bin/env python3
"""Diagnose memory visibility and indexing health for one agent.

Usage:
    cd backend
    .venv/bin/python scripts/diagnose_agent_memory.py --agent-id <uuid>
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

from api_gateway.routers.memory import _build_agent_memory_diagnostics_sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose agent memory health")
    parser.add_argument("--agent-id", required=True, help="Agent UUID")
    parser.add_argument(
        "--no-samples",
        action="store_true",
        help="Skip sample memory rows in output",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Max sample rows (default: 5, max: 20)",
    )
    parser.add_argument(
        "--milvus-scan-limit",
        type=int,
        default=10000,
        help="Max Milvus rows to scan for this agent (default: 10000)",
    )
    args = parser.parse_args()

    try:
        report = _build_agent_memory_diagnostics_sync(
            agent_id=args.agent_id,
            include_samples=not args.no_samples,
            sample_limit=args.sample_limit,
            milvus_scan_limit=args.milvus_scan_limit,
        )
    except ValueError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Failed to diagnose agent memory: {exc}", file=sys.stderr)
        return 1

    if not report:
        print(f"Agent not found: {args.agent_id}", file=sys.stderr)
        return 3

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
