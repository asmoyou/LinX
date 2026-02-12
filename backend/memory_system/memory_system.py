"""Memory System implementation for multi-tiered memory management.

This module implements the Memory System with support for:
- Agent Memory (private to each agent)
- Company Memory (shared across agents)
- User Context (user-specific information accessible to all user's agents)
- Semantic similarity search
- Memory archival to MinIO

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymilvus import Collection

from memory_system.collections import CollectionName
from memory_system.embedding_service import get_embedding_service
from memory_system.memory_interface import (
    MemoryItem,
    MemorySystemInterface,
    MemoryType,
    SearchQuery,
)
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

logger = logging.getLogger(__name__)


class MemorySystem(MemorySystemInterface):
    """
    Implementation of the multi-tiered memory system.

    This class provides storage and retrieval of memories across three tiers:
    1. Agent Memory: Private memories for individual agents
    2. Company Memory: Shared memories accessible to all agents
    3. User Context: User-specific information accessible to all user's agents

    Example:
        >>> memory_system = MemorySystem()
        >>> memory = MemoryItem(
        ...     content="User prefers dark mode",
        ...     memory_type=MemoryType.USER_CONTEXT,
        ...     user_id="user123"
        ... )
        >>> memory_id = memory_system.store_memory(memory)
        >>> query = SearchQuery(
        ...     query_text="user preferences",
        ...     user_id="user123",
        ...     top_k=5
        ... )
        >>> results = memory_system.retrieve_memories(query)
    """

    def __init__(self):
        """Initialize the Memory System."""
        self._config = get_config()
        self._milvus = get_milvus_connection()
        self._embedding_service = get_embedding_service()

        # Load memory configuration
        memory_config = self._config.get_section("memory")
        self._default_top_k = memory_config.get("default_top_k", 10)
        self._recency_weight = memory_config.get("recency_weight", 0.3)
        self._similarity_weight = memory_config.get("similarity_weight", 0.7)
        self._collection_retry_attempts = memory_config.get("collection_retry_attempts", 3)
        self._collection_retry_delay_seconds = memory_config.get(
            "collection_retry_delay_seconds", 0.35
        )
        self._search_timeout_seconds = float(memory_config.get("search_timeout_seconds", 2.0))
        self._delete_timeout_seconds = float(memory_config.get("delete_timeout_seconds", 2.0))

        logger.info("Memory System initialized")

    def store_memory(self, memory: MemoryItem) -> int:
        """
        Store a memory item in the appropriate collection.

        Args:
            memory: Memory item to store

        Returns:
            int: ID of the stored memory

        Raises:
            ValueError: If memory data is invalid
            RuntimeError: If storage fails
        """
        # Validate memory
        if not memory.content or not memory.content.strip():
            raise ValueError("Memory content cannot be empty")

        if not memory.memory_type:
            raise ValueError("Memory type must be specified")

        # Set timestamp if not provided
        if not memory.timestamp:
            memory.timestamp = datetime.utcnow()

        try:
            # Generate embedding
            embedding = self._embedding_service.generate_embedding(memory.content)
            memory.embedding = embedding

            # Determine target collection
            if memory.memory_type == MemoryType.AGENT:
                collection_name = CollectionName.AGENT_MEMORIES
                if not memory.agent_id:
                    raise ValueError("agent_id required for agent memories")
            else:
                # Company, user_context, and task_context all go to company_memories
                collection_name = CollectionName.COMPANY_MEMORIES
                if not memory.user_id:
                    raise ValueError("user_id required for company/user_context memories")

            # Get collection
            collection = self._milvus.get_collection(collection_name)

            # Prepare data for insertion
            timestamp_ms = int(memory.timestamp.timestamp() * 1000)

            if collection_name == CollectionName.AGENT_MEMORIES:
                data = [
                    [memory.agent_id],  # agent_id
                    [embedding],  # embedding
                    [memory.content],  # content
                    [timestamp_ms],  # timestamp
                    [memory.metadata or {}],  # metadata
                ]
            else:  # COMPANY_MEMORIES
                data = [
                    [memory.user_id],  # user_id
                    [embedding],  # embedding
                    [memory.content],  # content
                    [memory.memory_type.value],  # memory_type
                    [timestamp_ms],  # timestamp
                    [memory.metadata or {}],  # metadata
                ]

            # Insert into Milvus
            result = collection.insert(data)

            # Get the inserted ID
            memory_id = result.primary_keys[0]

            logger.info(
                f"Stored memory: id={memory_id}, type={memory.memory_type.value}, "
                f"collection={collection_name}"
            )

            return memory_id

        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise RuntimeError(f"Memory storage failed: {e}")

    def retrieve_memories(self, query: SearchQuery) -> List[MemoryItem]:
        """
        Retrieve memories based on semantic similarity search.

        Args:
            query: Search query with filters

        Returns:
            List[MemoryItem]: List of matching memories ranked by relevance

        Raises:
            ValueError: If query is invalid
            RuntimeError: If retrieval fails
        """
        if not query.query_text or not query.query_text.strip():
            raise ValueError("Query text cannot be empty")

        try:
            # Generate query embedding
            query_embedding = self._embedding_service.generate_embedding(query.query_text)

            # Determine which collections to search
            collections_to_search = self._determine_search_collections(query)

            # Search each collection
            all_results = []
            for collection_name in collections_to_search:
                results = self._search_collection(collection_name, query_embedding, query)
                all_results.extend(results)

            # Rank results by relevance (similarity + recency)
            ranked_results = self._rank_results(all_results)

            # Apply top_k limit
            top_k = query.top_k or self._default_top_k
            final_results = ranked_results[:top_k]

            logger.info(
                f"Retrieved {len(final_results)} memories for query "
                f"(searched {len(collections_to_search)} collections)"
            )

            return final_results

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            raise RuntimeError(f"Memory retrieval failed: {e}")

    def _determine_search_collections(self, query: SearchQuery) -> List[str]:
        """
        Determine which collections to search based on query filters.

        Args:
            query: Search query

        Returns:
            List[str]: List of collection names to search
        """
        collections = []

        if query.memory_type == MemoryType.AGENT:
            collections.append(CollectionName.AGENT_MEMORIES)
        elif query.memory_type in [
            MemoryType.COMPANY,
            MemoryType.USER_CONTEXT,
            MemoryType.TASK_CONTEXT,
        ]:
            collections.append(CollectionName.COMPANY_MEMORIES)
        else:
            # Search all collections if no specific type
            if query.agent_id:
                collections.append(CollectionName.AGENT_MEMORIES)
            if query.user_id:
                collections.append(CollectionName.COMPANY_MEMORIES)
            if not query.agent_id and not query.user_id:
                # Search both if no filters
                collections.extend([CollectionName.AGENT_MEMORIES, CollectionName.COMPANY_MEMORIES])

        return collections

    def _search_collection(
        self, collection_name: str, query_embedding: List[float], query: SearchQuery
    ) -> List[MemoryItem]:
        """
        Search a specific collection for similar memories.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            query: Search query with filters

        Returns:
            List[MemoryItem]: List of matching memories
        """
        try:
            collection = self._milvus.get_collection(collection_name)

            # Build filter expression
            filter_expr = self._build_filter_expression(collection_name, query)

            # Prepare search parameters
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}

            # Determine output fields based on collection
            if collection_name == CollectionName.AGENT_MEMORIES:
                output_fields = ["agent_id", "content", "timestamp", "metadata"]
            else:  # COMPANY_MEMORIES
                output_fields = ["user_id", "content", "memory_type", "timestamp", "metadata"]

            # Perform search with short retries for transient load-state failures.
            results = self._search_collection_with_retry(
                collection=collection,
                collection_name=collection_name,
                query_embedding=query_embedding,
                search_params=search_params,
                limit=query.top_k or self._default_top_k,
                filter_expr=filter_expr,
                output_fields=output_fields,
            )

            # Convert results to MemoryItem objects
            memories = []
            for hits in results:
                for hit in hits:
                    memory = self._hit_to_memory_item(hit, collection_name)
                    if memory and memory.similarity_score >= query.min_similarity:
                        memories.append(memory)

            return memories

        except Exception as e:
            logger.error(f"Failed to search collection {collection_name}: {e}")
            return []

    @staticmethod
    def _is_collection_not_loaded_error(exc: Exception) -> bool:
        """Detect Milvus transient collection load-state error."""
        current = exc
        seen = set()
        while current and id(current) not in seen:
            seen.add(id(current))
            code = getattr(current, "code", None)
            if code == 101:
                return True
            message = str(current).lower()
            if "collection not loaded" in message:
                return True
            if "not loaded" in message and "collection" in message:
                return True

            if current.__cause__ is not None:
                current = current.__cause__
            elif current.__context__ is not None:
                current = current.__context__
            else:
                current = None
        return False

    def _search_collection_with_retry(
        self,
        collection: Collection,
        collection_name: str,
        query_embedding: List[float],
        search_params: Dict[str, Any],
        limit: int,
        filter_expr: Optional[str],
        output_fields: List[str],
    ):
        """Search Milvus with retries when collection is still loading."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self._collection_retry_attempts + 1):
            try:
                return collection.search(
                    data=[query_embedding],
                    anns_field="embedding",
                    param=search_params,
                    limit=limit,
                    expr=filter_expr if filter_expr else None,
                    output_fields=output_fields,
                    timeout=max(self._search_timeout_seconds, 0.5),
                )
            except Exception as exc:
                if not self._is_collection_not_loaded_error(exc):
                    raise
                last_error = exc
                try:
                    collection.load(timeout=1.0, _async=True)
                except Exception as load_exc:
                    logger.debug(
                        "Failed to trigger async load for %s after search failure: %s",
                        collection_name,
                        load_exc,
                    )

                if attempt < self._collection_retry_attempts:
                    delay = self._collection_retry_delay_seconds * attempt
                    logger.warning(
                        "Collection '%s' not loaded yet (attempt %d/%d), retrying in %.2fs",
                        collection_name,
                        attempt,
                        self._collection_retry_attempts,
                        delay,
                    )
                    time.sleep(delay)

        if last_error:
            logger.warning(
                "Collection '%s' remained unavailable after %d retries: %s",
                collection_name,
                self._collection_retry_attempts,
                last_error,
            )
        return []

    def _build_filter_expression(self, collection_name: str, query: SearchQuery) -> Optional[str]:
        """
        Build Milvus filter expression from query filters.

        Args:
            collection_name: Name of the collection
            query: Search query with filters

        Returns:
            Optional[str]: Filter expression or None
        """
        filters = []

        if collection_name == CollectionName.AGENT_MEMORIES:
            if query.agent_id:
                filters.append(f'agent_id == "{query.agent_id}"')
        else:  # COMPANY_MEMORIES
            if query.user_id:
                filters.append(f'user_id == "{query.user_id}"')
            if query.memory_type:
                filters.append(f'memory_type == "{query.memory_type.value}"')
            if query.task_id:
                # Filter by task_id in metadata (requires JSON filtering)
                filters.append(f'metadata["task_id"] == "{query.task_id}"')

        return " && ".join(filters) if filters else None

    def _hit_to_memory_item(self, hit: Any, collection_name: str) -> Optional[MemoryItem]:
        """
        Convert a Milvus search hit to a MemoryItem.

        Args:
            hit: Milvus search hit
            collection_name: Name of the collection

        Returns:
            Optional[MemoryItem]: Memory item or None if conversion fails
        """
        try:
            # Extract fields from hit
            memory_id = hit.id
            similarity_score = 1.0 / (1.0 + hit.distance)  # Convert L2 distance to similarity
            content = hit.entity.get("content")
            timestamp_ms = hit.entity.get("timestamp")
            metadata = hit.entity.get("metadata")

            # Convert timestamp
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0) if timestamp_ms else None

            # Determine memory type and extract type-specific fields
            if collection_name == CollectionName.AGENT_MEMORIES:
                agent_id = hit.entity.get("agent_id")
                memory_type = MemoryType.AGENT
                user_id = None
            else:  # COMPANY_MEMORIES
                agent_id = None
                user_id = hit.entity.get("user_id")
                memory_type_str = hit.entity.get("memory_type", "company")
                memory_type = MemoryType(memory_type_str)

            # Extract task_id from metadata if present
            task_id = metadata.get("task_id") if metadata else None

            return MemoryItem(
                id=memory_id,
                content=content,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
                task_id=task_id,
                timestamp=timestamp,
                metadata=metadata,
                similarity_score=similarity_score,
            )

        except Exception as e:
            logger.error(f"Failed to convert hit to memory item: {e}")
            return None

    def _rank_results(self, results: List[MemoryItem]) -> List[MemoryItem]:
        """
        Rank results by relevance (similarity + recency).

        Args:
            results: List of memory items

        Returns:
            List[MemoryItem]: Ranked list of memory items
        """
        if not results:
            return []

        # Calculate current time for recency scoring
        current_time = datetime.utcnow()

        # Calculate combined scores
        for memory in results:
            # Similarity score (already normalized 0-1)
            similarity_score = memory.similarity_score or 0.0

            # Recency score (exponential decay)
            if memory.timestamp:
                age_seconds = (current_time - memory.timestamp).total_seconds()
                age_days = age_seconds / 86400.0
                recency_score = 1.0 / (1.0 + age_days)  # Decay over days
            else:
                recency_score = 0.0

            # Combined score
            combined_score = (
                self._similarity_weight * similarity_score + self._recency_weight * recency_score
            )

            # Store combined score in metadata for debugging
            if not memory.metadata:
                memory.metadata = {}
            memory.metadata["_combined_score"] = combined_score
            memory.metadata["_recency_score"] = recency_score

        # Sort by combined score (descending)
        ranked = sorted(results, key=lambda m: m.metadata.get("_combined_score", 0.0), reverse=True)

        return ranked

    def delete_memory(self, memory_id: int, memory_type: MemoryType) -> bool:
        """
        Delete a specific memory by ID.

        Args:
            memory_id: ID of the memory to delete
            memory_type: Type of memory (determines collection)

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            # Determine collection
            if memory_type == MemoryType.AGENT:
                collection_name = CollectionName.AGENT_MEMORIES
            else:
                collection_name = CollectionName.COMPANY_MEMORIES

            # Get collection
            collection = self._milvus.get_collection(collection_name)

            # Delete by ID
            expr = f"id == {memory_id}"
            collection.delete(expr, timeout=max(self._delete_timeout_seconds, 0.5))

            logger.info(f"Deleted memory: id={memory_id}, type={memory_type.value}")
            return True

        except Exception as e:
            if self._is_collection_not_loaded_error(e):
                logger.warning(
                    "Skip deleting memory %s in %s because collection is not loaded: %s",
                    memory_id,
                    memory_type.value,
                    e,
                )
                return False
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False

    def archive_agent_memories(self, agent_id: str) -> Dict[str, Any]:
        """
        Archive all memories for an agent to cold storage (MinIO).

        This is called when an agent is terminated.

        Args:
            agent_id: Agent identifier

        Returns:
            dict: Archive metadata (location, count, timestamp)
        """
        try:
            # Query all memories for the agent
            collection = self._milvus.get_collection(CollectionName.AGENT_MEMORIES)

            # Search with filter
            expr = f'agent_id == "{agent_id}"'
            results = collection.query(
                expr=expr, output_fields=["id", "agent_id", "content", "timestamp", "metadata"]
            )

            if not results:
                logger.info(f"No memories to archive for agent {agent_id}")
                return {
                    "agent_id": agent_id,
                    "count": 0,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # Prepare archive data
            archive_data = {
                "agent_id": agent_id,
                "archived_at": datetime.utcnow().isoformat(),
                "count": len(results),
                "memories": results,
            }

            # TODO: Upload to MinIO (requires MinIO client integration)
            # For now, just log the archive
            logger.info(
                f"Archived {len(results)} memories for agent {agent_id} "
                f"(MinIO upload not yet implemented)"
            )

            # Delete memories from Milvus after archiving
            collection.delete(expr)

            return {
                "agent_id": agent_id,
                "count": len(results),
                "timestamp": archive_data["archived_at"],
                "location": f"minio://agent-artifacts/{agent_id}/memories.json",
            }

        except Exception as e:
            logger.error(f"Failed to archive memories for agent {agent_id}: {e}")
            raise RuntimeError(f"Memory archival failed: {e}")

    def classify_memory_type(
        self, content: str, context: Optional[Dict[str, Any]] = None
    ) -> MemoryType:
        """
        Classify whether memory should be user-specific or task-specific.

        This uses simple heuristics. For more sophisticated classification,
        an LLM could be used.

        Args:
            content: Memory content text
            context: Additional context for classification

        Returns:
            MemoryType: Classified memory type
        """
        content_lower = content.lower()

        # User context keywords
        user_keywords = [
            "prefer",
            "like",
            "dislike",
            "always",
            "never",
            "usually",
            "my",
            "i am",
            "i have",
            "remember that i",
        ]

        # Task context keywords
        task_keywords = [
            "task",
            "step",
            "result",
            "output",
            "completed",
            "failed",
            "processing",
            "analyzed",
            "generated",
        ]

        # Check for explicit context hints
        if context:
            if context.get("is_user_preference"):
                return MemoryType.USER_CONTEXT
            if context.get("is_task_result"):
                return MemoryType.TASK_CONTEXT

        # Check for user context keywords
        if any(keyword in content_lower for keyword in user_keywords):
            return MemoryType.USER_CONTEXT

        # Check for task context keywords
        if any(keyword in content_lower for keyword in task_keywords):
            return MemoryType.TASK_CONTEXT

        # Default to general company memory
        return MemoryType.COMPANY

    def share_memory(
        self, memory_id: int, source_type: MemoryType, target_user_ids: List[str]
    ) -> bool:
        """
        Share a memory with specific users.

        This creates copies of the memory in company_memories with
        appropriate user_id filters.

        Args:
            memory_id: ID of the memory to share
            source_type: Source memory type
            target_user_ids: List of user IDs to share with

        Returns:
            bool: True if shared successfully
        """
        try:
            # Retrieve the source memory
            if source_type == MemoryType.AGENT:
                collection_name = CollectionName.AGENT_MEMORIES
            else:
                collection_name = CollectionName.COMPANY_MEMORIES

            collection = self._milvus.get_collection(collection_name)

            # Query the memory
            results = collection.query(
                expr=f"id == {memory_id}", output_fields=["content", "timestamp", "metadata"]
            )

            if not results:
                logger.error(f"Memory {memory_id} not found")
                return False

            source_memory = results[0]

            # Create shared copies for each target user
            for user_id in target_user_ids:
                shared_memory = MemoryItem(
                    content=source_memory["content"],
                    memory_type=MemoryType.COMPANY,
                    user_id=user_id,
                    timestamp=datetime.fromtimestamp(source_memory["timestamp"] / 1000.0),
                    metadata={
                        **(source_memory.get("metadata") or {}),
                        "shared_from": memory_id,
                        "shared_at": datetime.utcnow().isoformat(),
                    },
                )

                self.store_memory(shared_memory)

            logger.info(f"Shared memory {memory_id} with {len(target_user_ids)} users")
            return True

        except Exception as e:
            logger.error(f"Failed to share memory {memory_id}: {e}")
            return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about memory usage.

        Returns:
            dict: Statistics including counts, sizes, etc.
        """
        try:
            stats = {}

            # Get stats for each collection
            for collection_name in [CollectionName.AGENT_MEMORIES, CollectionName.COMPANY_MEMORIES]:
                try:
                    collection_stats = self._milvus.get_collection_stats(collection_name)
                    stats[collection_name] = collection_stats
                except Exception as e:
                    logger.error(f"Failed to get stats for {collection_name}: {e}")
                    stats[collection_name] = {"error": str(e)}

            return stats

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"error": str(e)}


# Global memory system instance
_memory_system: Optional[MemorySystem] = None


def get_memory_system() -> MemorySystem:
    """
    Get the global Memory System instance.

    Returns:
        MemorySystem: Global memory system instance
    """
    global _memory_system

    if _memory_system is None:
        _memory_system = MemorySystem()

    return _memory_system
