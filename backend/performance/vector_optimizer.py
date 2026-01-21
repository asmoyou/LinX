"""Vector search optimization.

References:
- Requirements 8: Scalability and Performance
- Design Section 10: Scalability and Performance
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IndexType(Enum):
    """Vector index types."""

    FLAT = "FLAT"  # Brute force, exact search
    IVF_FLAT = "IVF_FLAT"  # Inverted file with flat quantization
    IVF_SQ8 = "IVF_SQ8"  # Inverted file with scalar quantization
    IVF_PQ = "IVF_PQ"  # Inverted file with product quantization
    HNSW = "HNSW"  # Hierarchical navigable small world
    ANNOY = "ANNOY"  # Approximate nearest neighbors oh yeah


@dataclass
class IndexConfig:
    """Vector index configuration."""

    index_type: IndexType
    nlist: int = 1024  # Number of clusters for IVF
    m: int = 8  # Number of subquantizers for PQ
    nbits: int = 8  # Bits per subquantizer
    ef_construction: int = 200  # HNSW construction parameter
    M: int = 16  # HNSW M parameter


@dataclass
class SearchConfig:
    """Vector search configuration."""

    nprobe: int = 10  # Number of clusters to search
    ef: int = 64  # HNSW search parameter
    top_k: int = 10  # Number of results to return


class VectorSearchOptimizer:
    """Vector search optimizer.

    Optimizes vector search performance:
    - Index type selection
    - Index parameter tuning
    - Search parameter optimization
    - Query batching
    - Result caching
    """

    def __init__(self):
        """Initialize vector search optimizer."""
        self.index_configs: Dict[str, IndexConfig] = {}
        self.search_configs: Dict[str, SearchConfig] = {}

        logger.info("VectorSearchOptimizer initialized")

    def recommend_index_type(
        self,
        collection_size: int,
        vector_dim: int,
        accuracy_requirement: float = 0.95,
    ) -> IndexType:
        """Recommend index type based on collection characteristics.

        Args:
            collection_size: Number of vectors
            vector_dim: Vector dimensionality
            accuracy_requirement: Required accuracy (0-1)

        Returns:
            Recommended index type
        """
        # Small collections: use FLAT for exact search
        if collection_size < 10000:
            logger.info("Recommending FLAT index for small collection")
            return IndexType.FLAT

        # Medium collections with high accuracy: use IVF_FLAT
        if collection_size < 1000000 and accuracy_requirement > 0.95:
            logger.info("Recommending IVF_FLAT index for medium collection")
            return IndexType.IVF_FLAT

        # Large collections with high accuracy: use HNSW
        if accuracy_requirement > 0.95:
            logger.info("Recommending HNSW index for large collection")
            return IndexType.HNSW

        # Large collections with moderate accuracy: use IVF_PQ
        logger.info("Recommending IVF_PQ index for large collection")
        return IndexType.IVF_PQ

    def create_index_config(
        self,
        collection_name: str,
        index_type: IndexType,
        collection_size: int,
    ) -> IndexConfig:
        """Create optimized index configuration.

        Args:
            collection_name: Collection name
            index_type: Index type
            collection_size: Number of vectors

        Returns:
            Index configuration
        """
        config = IndexConfig(index_type=index_type)

        if index_type in [IndexType.IVF_FLAT, IndexType.IVF_SQ8, IndexType.IVF_PQ]:
            # nlist should be sqrt(N) to 4*sqrt(N)
            import math

            config.nlist = min(int(4 * math.sqrt(collection_size)), 65536)

        elif index_type == IndexType.HNSW:
            # Larger M for better accuracy, smaller for speed
            config.M = 16
            config.ef_construction = 200

        self.index_configs[collection_name] = config

        logger.info(
            f"Created index config for {collection_name}",
            extra={"index_type": index_type.value, "nlist": config.nlist},
        )

        return config

    def create_search_config(
        self,
        collection_name: str,
        accuracy_requirement: float = 0.95,
    ) -> SearchConfig:
        """Create optimized search configuration.

        Args:
            collection_name: Collection name
            accuracy_requirement: Required accuracy (0-1)

        Returns:
            Search configuration
        """
        index_config = self.index_configs.get(collection_name)

        config = SearchConfig()

        if index_config:
            if index_config.index_type in [IndexType.IVF_FLAT, IndexType.IVF_SQ8, IndexType.IVF_PQ]:
                # nprobe should be 1-20% of nlist
                config.nprobe = max(int(index_config.nlist * 0.05), 10)

            elif index_config.index_type == IndexType.HNSW:
                # Higher ef for better accuracy
                config.ef = int(200 * accuracy_requirement)

        self.search_configs[collection_name] = config

        logger.info(
            f"Created search config for {collection_name}",
            extra={"nprobe": config.nprobe, "ef": config.ef},
        )

        return config

    def optimize_batch_size(
        self,
        num_queries: int,
        vector_dim: int,
    ) -> int:
        """Optimize batch size for vector search.

        Args:
            num_queries: Number of queries
            vector_dim: Vector dimensionality

        Returns:
            Optimal batch size
        """
        # Larger batches for smaller dimensions
        if vector_dim < 128:
            batch_size = 100
        elif vector_dim < 512:
            batch_size = 50
        else:
            batch_size = 20

        # Don't exceed number of queries
        batch_size = min(batch_size, num_queries)

        logger.debug(f"Optimal batch size: {batch_size}")

        return batch_size

    def get_optimization_recommendations(
        self,
        collection_name: str,
        current_qps: float,
        current_latency_ms: float,
        target_latency_ms: float,
    ) -> List[str]:
        """Get optimization recommendations.

        Args:
            collection_name: Collection name
            current_qps: Current queries per second
            current_latency_ms: Current latency in milliseconds
            target_latency_ms: Target latency in milliseconds

        Returns:
            List of recommendations
        """
        recommendations = []

        if current_latency_ms > target_latency_ms * 2:
            recommendations.append(
                "Consider using a faster index type (e.g., HNSW instead of IVF_FLAT)"
            )
            recommendations.append("Reduce nprobe parameter to search fewer clusters")
            recommendations.append("Enable result caching for frequently searched queries")

        if current_qps > 100:
            recommendations.append("Implement query batching to improve throughput")
            recommendations.append("Consider horizontal scaling with multiple Milvus instances")

        index_config = self.index_configs.get(collection_name)
        if index_config and index_config.index_type == IndexType.FLAT:
            recommendations.append("Upgrade from FLAT to IVF_FLAT or HNSW for better performance")

        return recommendations

    def get_performance_report(self) -> Dict[str, Any]:
        """Get performance optimization report.

        Returns:
            Performance report
        """
        return {
            "collections": len(self.index_configs),
            "index_configs": {
                name: {
                    "index_type": config.index_type.value,
                    "nlist": config.nlist,
                }
                for name, config in self.index_configs.items()
            },
            "search_configs": {
                name: {
                    "nprobe": config.nprobe,
                    "ef": config.ef,
                    "top_k": config.top_k,
                }
                for name, config in self.search_configs.items()
            },
        }
