#!/usr/bin/env python3
"""Recreate the active reset-era Milvus collection for knowledge only."""

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

setup_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        logger.info("Starting knowledge-base Milvus collection recreation...")

        knowledge_dim = get_knowledge_embedding_dimension()
        logger.info("Using knowledge embedding dimension: %s", knowledge_dim)

        knowledge_collection = recreate_knowledge_embeddings_collection()

        logger.info(
            "Successfully recreated %s with %s entities",
            KNOWLEDGE_EMBEDDINGS_COLLECTION,
            knowledge_collection.num_entities,
        )
    except Exception as exc:
        logger.error("Failed to recreate knowledge Milvus collection: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
