#!/usr/bin/env python3
"""Run one reconcile/cleanup cycle for user-memory embeddings."""

import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from shared.logging import setup_logging
from user_memory.storage_cleanup import reconcile_user_memory_vectors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--no-compact", action="store_true")
    args = parser.parse_args()

    setup_logging()
    result = reconcile_user_memory_vectors(
        dry_run=bool(args.dry_run),
        batch_size=max(int(args.batch_size), 1),
        compact_on_cycle=not bool(args.no_compact),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
