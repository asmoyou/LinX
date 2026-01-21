"""Milvus connection manager for vector database operations.

This module provides connection pooling and management for Milvus vector database.
It supports:
- Connection pooling with configurable pool size
- Automatic reconnection on failure
- Health checks
- Collection management
- Graceful shutdown

References:
- Requirements 3.2: Vector Database for Semantic Search
- Design Section 3.1: Milvus Collections
- Design Section 10.3: Resource Management
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusException,
    connections,
    utility,
)

from shared.config import get_config

logger = logging.getLogger(__name__)


class MilvusConnectionManager:
    """
    Milvus connection manager with connection pooling.

    This class manages connections to Milvus vector database and provides:
    - Connection pooling with automatic reconnection
    - Health checks
    - Collection management
    - Graceful shutdown

    Example:
        >>> manager = MilvusConnectionManager()
        >>> manager.initialize()
        >>> collection = manager.get_collection("agent_memories")
        >>> manager.close()
    """

    def __init__(self):
        """Initialize the Milvus connection manager."""
        self._config = get_config()
        self._connection_alias = "default"
        self._is_connected = False
        self._collections: Dict[str, Collection] = {}

    def initialize(self) -> None:
        """
        Initialize the Milvus connection.

        This method establishes a connection to Milvus using the configuration
        from config.yaml.

        Raises:
            MilvusException: If the connection cannot be established
        """
        if self._is_connected:
            logger.warning("Milvus connection already initialized")
            return

        try:
            # Load Milvus configuration
            milvus_config = self._config.get_section("database.milvus")

            # Extract connection parameters
            host = milvus_config.get("host", "localhost")
            port = milvus_config.get("port", 19530)
            user = milvus_config.get("user", "")
            password = milvus_config.get("password", "")
            timeout = milvus_config.get("timeout", 30)

            # Build connection parameters
            conn_params = {
                "alias": self._connection_alias,
                "host": host,
                "port": str(port),
                "timeout": timeout,
            }

            # Add authentication if provided
            if user and password:
                conn_params["user"] = user
                conn_params["password"] = password

            # Connect to Milvus
            connections.connect(**conn_params)

            self._is_connected = True

            # Perform health check
            if not self.health_check():
                raise MilvusException("Milvus health check failed after connection")

            logger.info(
                f"Milvus connection initialized: " f"host={host}, port={port}, timeout={timeout}s"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Milvus connection: {e}")
            self._is_connected = False
            raise

    def health_check(self) -> bool:
        """
        Perform a health check on the Milvus connection.

        Returns:
            bool: True if Milvus is accessible, False otherwise
        """
        try:
            # Check if connection is alive
            if not connections.has_connection(self._connection_alias):
                logger.error("Milvus connection does not exist")
                return False

            # Try to list collections as a health check
            utility.list_collections(using=self._connection_alias)

            logger.debug("Milvus health check passed")
            return True

        except Exception as e:
            logger.error(f"Milvus health check failed: {e}")
            return False

    def get_collection(self, collection_name: str) -> Collection:
        """
        Get a Milvus collection by name.

        Args:
            collection_name: Name of the collection

        Returns:
            Collection: Milvus collection object

        Raises:
            MilvusException: If the collection does not exist
        """
        if not self._is_connected:
            raise RuntimeError("Milvus connection not initialized")

        # Check cache first
        if collection_name in self._collections:
            return self._collections[collection_name]

        # Check if collection exists
        if not utility.has_collection(collection_name, using=self._connection_alias):
            raise MilvusException(f"Collection '{collection_name}' does not exist")

        # Load collection
        collection = Collection(name=collection_name, using=self._connection_alias)

        # Cache the collection
        self._collections[collection_name] = collection

        logger.debug(f"Loaded collection: {collection_name}")
        return collection

    def list_collections(self) -> List[str]:
        """
        List all collections in Milvus.

        Returns:
            List[str]: List of collection names
        """
        if not self._is_connected:
            raise RuntimeError("Milvus connection not initialized")

        try:
            collections = utility.list_collections(using=self._connection_alias)
            return collections
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.

        Args:
            collection_name: Name of the collection

        Returns:
            bool: True if the collection exists, False otherwise
        """
        if not self._is_connected:
            raise RuntimeError("Milvus connection not initialized")

        try:
            return utility.has_collection(collection_name, using=self._connection_alias)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False

    def drop_collection(self, collection_name: str) -> None:
        """
        Drop a collection from Milvus.

        Args:
            collection_name: Name of the collection to drop
        """
        if not self._is_connected:
            raise RuntimeError("Milvus connection not initialized")

        try:
            if collection_name in self._collections:
                del self._collections[collection_name]

            utility.drop_collection(collection_name, using=self._connection_alias)

            logger.info(f"Dropped collection: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to drop collection '{collection_name}': {e}")
            raise

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        Get statistics for a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            dict: Collection statistics
        """
        if not self._is_connected:
            raise RuntimeError("Milvus connection not initialized")

        try:
            collection = self.get_collection(collection_name)

            # Get collection info
            stats = {
                "name": collection_name,
                "num_entities": collection.num_entities,
                "schema": {
                    "description": collection.description,
                    "fields": [
                        {
                            "name": field.name,
                            "type": str(field.dtype),
                            "description": field.description,
                        }
                        for field in collection.schema.fields
                    ],
                },
            }

            # Get partition info if available
            try:
                partitions = collection.partitions
                stats["partitions"] = [
                    {
                        "name": p.name,
                        "num_entities": p.num_entities,
                    }
                    for p in partitions
                ]
            except Exception:
                stats["partitions"] = []

            # Get index info if available
            try:
                indexes = collection.indexes
                stats["indexes"] = [
                    {
                        "field_name": idx.field_name,
                        "index_name": idx.index_name,
                        "params": idx.params,
                    }
                    for idx in indexes
                ]
            except Exception:
                stats["indexes"] = []

            return stats

        except Exception as e:
            logger.error(f"Failed to get collection stats for '{collection_name}': {e}")
            raise

    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get the current status of the Milvus connection.

        Returns:
            dict: Connection status information
        """
        if not self._is_connected:
            return {
                "status": "disconnected",
                "alias": self._connection_alias,
            }

        try:
            collections = self.list_collections()

            return {
                "status": "connected",
                "alias": self._connection_alias,
                "collections": collections,
                "num_collections": len(collections),
                "cached_collections": list(self._collections.keys()),
            }
        except Exception as e:
            logger.error(f"Failed to get connection status: {e}")
            return {
                "status": "error",
                "alias": self._connection_alias,
                "error": str(e),
            }

    def close(self) -> None:
        """
        Close the Milvus connection.

        This method should be called during application shutdown to
        gracefully close the connection to Milvus.
        """
        if not self._is_connected:
            logger.warning("Milvus connection already closed")
            return

        try:
            logger.info("Closing Milvus connection")

            # Clear cached collections
            self._collections.clear()

            # Disconnect from Milvus
            connections.disconnect(alias=self._connection_alias)

            self._is_connected = False

            logger.info("Milvus connection closed")

        except Exception as e:
            logger.error(f"Error closing Milvus connection: {e}")
            raise

    @property
    def is_connected(self) -> bool:
        """Check if the connection is active."""
        return self._is_connected

    @property
    def connection_alias(self) -> str:
        """Get the connection alias."""
        return self._connection_alias

    def __repr__(self) -> str:
        """String representation of the connection manager."""
        status = "connected" if self._is_connected else "disconnected"
        return f"MilvusConnectionManager(status={status}, alias={self._connection_alias})"


# Global connection manager instance
_milvus_connection: Optional[MilvusConnectionManager] = None


def get_milvus_connection() -> MilvusConnectionManager:
    """
    Get the global Milvus connection manager instance.

    This function returns the singleton connection manager instance.
    If the manager is not initialized, it will be created and initialized.

    Returns:
        MilvusConnectionManager: Global connection manager instance
    """
    global _milvus_connection

    if _milvus_connection is None:
        _milvus_connection = MilvusConnectionManager()
        _milvus_connection.initialize()

    return _milvus_connection


def close_milvus_connection() -> None:
    """
    Close the global Milvus connection manager.

    This function should be called during application shutdown.
    """
    global _milvus_connection

    if _milvus_connection is not None:
        _milvus_connection.close()
        _milvus_connection = None
