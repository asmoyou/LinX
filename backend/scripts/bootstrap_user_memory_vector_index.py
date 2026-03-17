#!/usr/bin/env python3
"""Bootstrap the active user-memory Milvus collection and platform state."""

import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from shared.logging import setup_logging
from user_memory.vector_index import bootstrap_user_memory_vector_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-state", default="building", choices=["building", "ready", "failed"])
    args = parser.parse_args()

    setup_logging()
    state = bootstrap_user_memory_vector_index(build_state=args.build_state)
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
