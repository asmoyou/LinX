"""Test script for Milvus connection and collections.

This script tests:
1. Milvus connection
2. Collection creation
3. Index creation
4. Partition management
5. Basic insert and search operations

Usage:
    python -m memory_system.test_milvus
"""

import logging
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from memory_system.collections import CollectionName, initialize_all_collections
from memory_system.milvus_connection import close_milvus_connection, get_milvus_connection
from memory_system.partitions import get_partition_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_connection():
    """Test Milvus connection."""
    logger.info("=" * 60)
    logger.info("Testing Milvus Connection")
    logger.info("=" * 60)

    try:
        manager = get_milvus_connection()

        # Check connection status
        status = manager.get_connection_status()
        logger.info(f"Connection status: {status}")

        # Perform health check
        is_healthy = manager.health_check()
        logger.info(f"Health check: {'PASSED' if is_healthy else 'FAILED'}")

        # List existing collections
        collections = manager.list_collections()
        logger.info(f"Existing collections: {collections}")

        return True

    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False


def test_collections():
    """Test collection creation."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Collection Creation")
    logger.info("=" * 60)

    try:
        # Initialize all collections
        collections = initialize_all_collections(drop_if_exists=False)

        logger.info(f"Created {len(collections)} collections:")
        for name, collection in collections.items():
            logger.info(f"  - {name}: {collection.num_entities} entities")

        # Get collection stats
        manager = get_milvus_connection()
        for name in collections.keys():
            stats = manager.get_collection_stats(name)
            logger.info(f"\nCollection: {name}")
            logger.info(f"  Entities: {stats['num_entities']}")
            logger.info(f"  Fields: {len(stats['schema']['fields'])}")
            logger.info(f"  Partitions: {len(stats.get('partitions', []))}")
            logger.info(f"  Indexes: {len(stats.get('indexes', []))}")

        return True

    except Exception as e:
        logger.error(f"Collection test failed: {e}")
        return False


def test_partitions():
    """Test partition management."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Partition Management")
    logger.info("=" * 60)

    try:
        partition_manager = get_partition_manager()

        # Initialize default partitions
        partition_manager.initialize_default_partitions()

        # Create test partitions
        test_agent_id = "test_agent_123"
        test_user_id = "test_user_456"

        agent_partition = partition_manager.create_agent_partition(test_agent_id)
        logger.info(f"Created agent partition: {agent_partition}")

        user_partition = partition_manager.create_user_partition(test_user_id)
        logger.info(f"Created user partition: {user_partition}")

        # List partitions for each collection
        for collection_name in [
            CollectionName.AGENT_MEMORIES,
            CollectionName.COMPANY_MEMORIES,
            CollectionName.KNOWLEDGE_EMBEDDINGS,
        ]:
            partitions = partition_manager.list_partitions(collection_name)
            logger.info(f"\nPartitions in {collection_name}:")
            for partition in partitions:
                logger.info(f"  - {partition}")

        return True

    except Exception as e:
        logger.error(f"Partition test failed: {e}")
        return False


def test_basic_operations():
    """Test basic insert and search operations."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Basic Operations")
    logger.info("=" * 60)

    try:
        import time

        import numpy as np

        manager = get_milvus_connection()
        collection = manager.get_collection(CollectionName.AGENT_MEMORIES)

        # Prepare test data
        test_agent_id = "test_agent_123"
        embedding_dim = 768  # Default dimension

        # Create test embeddings
        num_entities = 5
        embeddings = np.random.rand(num_entities, embedding_dim).tolist()

        # Prepare data
        data = [
            [test_agent_id] * num_entities,  # agent_id
            embeddings,  # embedding
            [f"Test memory content {i}" for i in range(num_entities)],  # content
            [int(time.time() * 1000) + i for i in range(num_entities)],  # timestamp
            [{"task_id": f"task_{i}", "importance": i} for i in range(num_entities)],  # metadata
        ]

        # Insert data
        logger.info(f"Inserting {num_entities} test entities...")
        insert_result = collection.insert(data)
        logger.info(f"Inserted entities: {insert_result.insert_count}")

        # Flush to ensure data is persisted
        collection.flush()
        logger.info("Data flushed to disk")

        # Load collection for search
        collection.load()
        logger.info("Collection loaded for search")

        # Perform a search
        search_params = {"metric_type": "L2", "params": {"nprobe": 16}}

        query_embedding = [embeddings[0]]  # Use first embedding as query

        logger.info("Performing similarity search...")
        results = collection.search(
            data=query_embedding,
            anns_field="embedding",
            param=search_params,
            limit=3,
            expr=f'agent_id == "{test_agent_id}"',
        )

        logger.info(f"Search returned {len(results[0])} results:")
        for i, hit in enumerate(results[0]):
            logger.info(f"  {i+1}. ID: {hit.id}, Distance: {hit.distance:.4f}")

        # Get entity count
        entity_count = collection.num_entities
        logger.info(f"\nTotal entities in collection: {entity_count}")

        return True

    except Exception as e:
        logger.error(f"Basic operations test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("Starting Milvus tests...")

    results = {
        "connection": False,
        "collections": False,
        "partitions": False,
        "operations": False,
    }

    try:
        # Test connection
        results["connection"] = test_connection()

        if results["connection"]:
            # Test collections
            results["collections"] = test_collections()

            # Test partitions
            results["partitions"] = test_partitions()

            # Test basic operations
            results["operations"] = test_basic_operations()

    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Close connection
        logger.info("\nClosing Milvus connection...")
        close_milvus_connection()

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        logger.info(f"{test_name.capitalize()}: {status}")

    all_passed = all(results.values())
    logger.info("\n" + ("=" * 60))
    if all_passed:
        logger.info("All tests PASSED! ✓")
    else:
        logger.info("Some tests FAILED! ✗")
    logger.info("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
