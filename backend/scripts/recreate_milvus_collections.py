#!/usr/bin/env python3
"""Recreate reset-era Milvus collections for knowledge and user memory."""

import logging
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from knowledge_base.vector_collection import (
    KNOWLEDGE_EMBEDDINGS_COLLECTION,
    get_knowledge_embedding_dimension,
    recreate_knowledge_embeddings_collection,
)
from shared.logging import setup_logging
from user_memory.vector_collection import (
    USER_MEMORY_ENTRIES_COLLECTION,
    get_user_memory_embedding_dimension,
    recreate_user_memory_entries_collection,
)

setup_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        logger.info("Starting reset-era Milvus collection recreation...")

        knowledge_dim = get_knowledge_embedding_dimension()
        user_memory_dim = get_user_memory_embedding_dimension()
        logger.info("Using knowledge embedding dimension: %s", knowledge_dim)
        logger.info("Using user-memory embedding dimension: %s", user_memory_dim)

        knowledge_collection = recreate_knowledge_embeddings_collection()
        user_memory_collection = recreate_user_memory_entries_collection()

        logger.info(
            "Successfully recreated %s with %s entities",
            KNOWLEDGE_EMBEDDINGS_COLLECTION,
            knowledge_collection.num_entities,
        )
        logger.info(
            "Successfully recreated %s with %s entities",
            USER_MEMORY_ENTRIES_COLLECTION,
            user_memory_collection.num_entities,
        )
    except Exception as exc:
        logger.error("Failed to recreate Milvus collections: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
