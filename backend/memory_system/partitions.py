"""Partition management for Milvus collections.

This module provides partition management functionality for efficient
data organization and filtering in Milvus collections.

Partitioning strategies:
- agent_memories: Partitioned by agent_id
- company_memories: Partitioned by user_id and memory_type
- knowledge_embeddings: Partitioned by access_level

References:
- Requirements 3.2: Vector Database for Semantic Search
- Design Section 3.1: Milvus Collections
"""

import logging
from typing import List, Optional, Set
from pymilvus import Collection, Partition

from memory_system.milvus_connection import get_milvus_connection
from memory_system.collections import CollectionName

logger = logging.getLogger(__name__)


class PartitionManager:
    """
    Manager for Milvus collection partitions.
    
    This class provides functionality to create and manage partitions
    for efficient data organization and filtering.
    """
    
    def __init__(self):
        """Initialize the partition manager."""
        self._manager = get_milvus_connection()
    
    def create_agent_partition(
        self,
        agent_id: str,
        collection_name: str = CollectionName.AGENT_MEMORIES
    ) -> str:
        """
        Create a partition for an agent in the agent_memories collection.
        
        Args:
            agent_id: Agent identifier
            collection_name: Name of the collection (default: agent_memories)
            
        Returns:
            str: Partition name
        """
        partition_name = f"agent_{agent_id}"
        
        try:
            collection = self._manager.get_collection(collection_name)
            
            # Check if partition already exists
            if collection.has_partition(partition_name):
                logger.debug(f"Partition already exists: {partition_name}")
                return partition_name
            
            # Create partition
            collection.create_partition(partition_name)
            logger.info(f"Created agent partition: {partition_name}")
            
            return partition_name
            
        except Exception as e:
            logger.error(f"Failed to create agent partition '{partition_name}': {e}")
            raise
    
    def create_user_partition(
        self,
        user_id: str,
        collection_name: str = CollectionName.COMPANY_MEMORIES
    ) -> str:
        """
        Create a partition for a user in the company_memories collection.
        
        Args:
            user_id: User identifier
            collection_name: Name of the collection (default: company_memories)
            
        Returns:
            str: Partition name
        """
        partition_name = f"user_{user_id}"
        
        try:
            collection = self._manager.get_collection(collection_name)
            
            # Check if partition already exists
            if collection.has_partition(partition_name):
                logger.debug(f"Partition already exists: {partition_name}")
                return partition_name
            
            # Create partition
            collection.create_partition(partition_name)
            logger.info(f"Created user partition: {partition_name}")
            
            return partition_name
            
        except Exception as e:
            logger.error(f"Failed to create user partition '{partition_name}': {e}")
            raise
    
    def create_memory_type_partition(
        self,
        memory_type: str,
        collection_name: str = CollectionName.COMPANY_MEMORIES
    ) -> str:
        """
        Create a partition for a memory type in the company_memories collection.
        
        Args:
            memory_type: Memory type (user_context, task_context, general)
            collection_name: Name of the collection (default: company_memories)
            
        Returns:
            str: Partition name
        """
        partition_name = f"type_{memory_type}"
        
        try:
            collection = self._manager.get_collection(collection_name)
            
            # Check if partition already exists
            if collection.has_partition(partition_name):
                logger.debug(f"Partition already exists: {partition_name}")
                return partition_name
            
            # Create partition
            collection.create_partition(partition_name)
            logger.info(f"Created memory type partition: {partition_name}")
            
            return partition_name
            
        except Exception as e:
            logger.error(f"Failed to create memory type partition '{partition_name}': {e}")
            raise
    
    def create_access_level_partition(
        self,
        access_level: str,
        collection_name: str = CollectionName.KNOWLEDGE_EMBEDDINGS
    ) -> str:
        """
        Create a partition for an access level in the knowledge_embeddings collection.
        
        Args:
            access_level: Access level (private, team, public)
            collection_name: Name of the collection (default: knowledge_embeddings)
            
        Returns:
            str: Partition name
        """
        partition_name = f"access_{access_level}"
        
        try:
            collection = self._manager.get_collection(collection_name)
            
            # Check if partition already exists
            if collection.has_partition(partition_name):
                logger.debug(f"Partition already exists: {partition_name}")
                return partition_name
            
            # Create partition
            collection.create_partition(partition_name)
            logger.info(f"Created access level partition: {partition_name}")
            
            return partition_name
            
        except Exception as e:
            logger.error(f"Failed to create access level partition '{partition_name}': {e}")
            raise
    
    def list_partitions(self, collection_name: str) -> List[str]:
        """
        List all partitions in a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            List[str]: List of partition names
        """
        try:
            collection = self._manager.get_collection(collection_name)
            partitions = collection.partitions
            return [p.name for p in partitions]
            
        except Exception as e:
            logger.error(f"Failed to list partitions for '{collection_name}': {e}")
            return []
    
    def drop_partition(self, collection_name: str, partition_name: str) -> None:
        """
        Drop a partition from a collection.
        
        Args:
            collection_name: Name of the collection
            partition_name: Name of the partition to drop
        """
        try:
            collection = self._manager.get_collection(collection_name)
            
            # Check if partition exists
            if not collection.has_partition(partition_name):
                logger.warning(f"Partition does not exist: {partition_name}")
                return
            
            # Drop partition
            collection.drop_partition(partition_name)
            logger.info(f"Dropped partition: {collection_name}.{partition_name}")
            
        except Exception as e:
            logger.error(f"Failed to drop partition '{partition_name}' from '{collection_name}': {e}")
            raise
    
    def get_partition_stats(
        self,
        collection_name: str,
        partition_name: str
    ) -> dict:
        """
        Get statistics for a partition.
        
        Args:
            collection_name: Name of the collection
            partition_name: Name of the partition
            
        Returns:
            dict: Partition statistics
        """
        try:
            collection = self._manager.get_collection(collection_name)
            
            # Check if partition exists
            if not collection.has_partition(partition_name):
                raise ValueError(f"Partition '{partition_name}' does not exist")
            
            # Get partition
            partition = Partition(collection, partition_name)
            
            return {
                'name': partition_name,
                'collection': collection_name,
                'num_entities': partition.num_entities,
                'is_empty': partition.is_empty,
            }
            
        except Exception as e:
            logger.error(f"Failed to get partition stats for '{partition_name}': {e}")
            raise
    
    def initialize_default_partitions(self) -> None:
        """
        Initialize default partitions for all collections.
        
        This creates commonly used partitions:
        - company_memories: user_context, task_context, general partitions
        - knowledge_embeddings: private, team, public partitions
        """
        logger.info("Initializing default partitions...")
        
        try:
            # Create memory type partitions for company_memories
            memory_types = ['user_context', 'task_context', 'general']
            for memory_type in memory_types:
                self.create_memory_type_partition(memory_type)
            
            # Create access level partitions for knowledge_embeddings
            access_levels = ['private', 'team', 'public']
            for access_level in access_levels:
                self.create_access_level_partition(access_level)
            
            logger.info("Successfully initialized default partitions")
            
        except Exception as e:
            logger.error(f"Failed to initialize default partitions: {e}")
            raise
    
    def ensure_agent_partition(self, agent_id: str) -> str:
        """
        Ensure a partition exists for an agent, creating it if necessary.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            str: Partition name
        """
        return self.create_agent_partition(agent_id)
    
    def ensure_user_partition(self, user_id: str) -> str:
        """
        Ensure a partition exists for a user, creating it if necessary.
        
        Args:
            user_id: User identifier
            
        Returns:
            str: Partition name
        """
        return self.create_user_partition(user_id)
    
    def get_partitions_for_search(
        self,
        collection_name: str,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        access_level: Optional[str] = None
    ) -> List[str]:
        """
        Get the list of partitions to search based on filters.
        
        Args:
            collection_name: Name of the collection
            agent_id: Agent identifier (for agent_memories)
            user_id: User identifier (for company_memories)
            memory_type: Memory type (for company_memories)
            access_level: Access level (for knowledge_embeddings)
            
        Returns:
            List[str]: List of partition names to search
        """
        partitions = []
        
        try:
            if collection_name == CollectionName.AGENT_MEMORIES and agent_id:
                # Search specific agent partition
                partition_name = f"agent_{agent_id}"
                if self._manager.get_collection(collection_name).has_partition(partition_name):
                    partitions.append(partition_name)
            
            elif collection_name == CollectionName.COMPANY_MEMORIES:
                # Search user and/or memory type partitions
                if user_id:
                    partition_name = f"user_{user_id}"
                    if self._manager.get_collection(collection_name).has_partition(partition_name):
                        partitions.append(partition_name)
                
                if memory_type:
                    partition_name = f"type_{memory_type}"
                    if self._manager.get_collection(collection_name).has_partition(partition_name):
                        partitions.append(partition_name)
            
            elif collection_name == CollectionName.KNOWLEDGE_EMBEDDINGS and access_level:
                # Search specific access level partition
                partition_name = f"access_{access_level}"
                if self._manager.get_collection(collection_name).has_partition(partition_name):
                    partitions.append(partition_name)
            
            # If no specific partitions found, search all partitions
            if not partitions:
                all_partitions = self.list_partitions(collection_name)
                # Exclude the default "_default" partition if it exists
                partitions = [p for p in all_partitions if p != "_default"]
            
            return partitions if partitions else None  # None means search all
            
        except Exception as e:
            logger.error(f"Failed to get partitions for search: {e}")
            return None  # Search all partitions on error


# Global partition manager instance
_partition_manager: Optional[PartitionManager] = None


def get_partition_manager() -> PartitionManager:
    """
    Get the global partition manager instance.
    
    Returns:
        PartitionManager: Global partition manager instance
    """
    global _partition_manager
    
    if _partition_manager is None:
        _partition_manager = PartitionManager()
    
    return _partition_manager
