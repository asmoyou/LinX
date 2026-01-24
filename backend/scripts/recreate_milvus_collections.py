#!/usr/bin/env python3
"""Recreate Milvus collections with correct embedding dimensions.

This script drops and recreates all Milvus collections to fix dimension mismatches.
"""

import sys
import logging
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from memory_system.collections import initialize_all_collections, get_embedding_dimension
from shared.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def main():
    """Recreate all Milvus collections."""
    try:
        logger.info("Starting Milvus collection recreation...")
        
        # Get correct embedding dimension from config
        embedding_dim = get_embedding_dimension()
        logger.info(f"Using embedding dimension: {embedding_dim}")
        
        # Initialize all collections (drop and recreate)
        logger.info("Dropping and recreating all collections...")
        collections = initialize_all_collections(drop_if_exists=True)
        
        logger.info(f"Successfully recreated {len(collections)} collections:")
        for collection_name, collection in collections.items():
            logger.info(f"  - {collection_name}: {collection.num_entities} entities")
        
        logger.info(f"All collections now use {embedding_dim}-dimensional embeddings")
        
    except Exception as e:
        logger.error(f"Failed to recreate collections: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
