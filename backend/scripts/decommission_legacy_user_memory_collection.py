#!/usr/bin/env python3
"""Drop the retired legacy Milvus collection for user-memory vectors."""

import logging
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from shared.logging import setup_logging
from user_memory.storage_cleanup import drop_legacy_user_memory_vector_collection

setup_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        logger.info("Checking for retired legacy user-memory Milvus collection...")
        result = drop_legacy_user_memory_vector_collection()
        if result.get("error"):
            logger.error("Legacy collection decommission failed: %s", result["error"])
            sys.exit(1)
        if result.get("dropped"):
            logger.info("Dropped retired legacy collection: %s", result["collection"])
            return
        if result.get("exists") is False:
            logger.info("Legacy collection already absent: %s", result["collection"])
            return
        logger.info("No destructive action taken for legacy collection: %s", result)
    except Exception as exc:
        logger.error("Failed to decommission legacy user-memory collection: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
