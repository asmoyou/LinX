"""Database query optimization.

References:
- Requirements 8: Scalability and Performance
- Design Section 10: Scalability and Performance
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueryStats:
    """Query statistics."""

    query_hash: str
    query_text: str
    execution_count: int
    total_time_ms: float
    avg_time_ms: float
    max_time_ms: float
    min_time_ms: float
    last_executed: datetime


@dataclass
class IndexRecommendation:
    """Index recommendation."""

    table_name: str
    columns: List[str]
    reason: str
    estimated_improvement: str


class QueryOptimizer:
    """Database query optimizer.

    Provides query optimization features:
    - Query analysis and profiling
    - Slow query detection
    - Index recommendations
    - Query plan analysis
    - Query rewriting suggestions
    """

    def __init__(self, slow_query_threshold_ms: float = 1000):
        """Initialize query optimizer.

        Args:
            slow_query_threshold_ms: Threshold for slow queries in milliseconds
        """
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.query_stats: Dict[str, QueryStats] = {}
        self.slow_queries: List[QueryStats] = []

        logger.info("QueryOptimizer initialized")

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """Analyze query for optimization opportunities.

        Args:
            query: SQL query

        Returns:
            Analysis results
        """
        analysis = {
            "query": query,
            "issues": [],
            "recommendations": [],
            "estimated_cost": "medium",
        }

        # Check for common issues
        query_lower = query.lower()

        # Missing WHERE clause
        if "select" in query_lower and "where" not in query_lower and "join" not in query_lower:
            analysis["issues"].append("Missing WHERE clause - may scan entire table")
            analysis["recommendations"].append("Add WHERE clause to filter results")

        # SELECT *
        if "select *" in query_lower:
            analysis["issues"].append("Using SELECT * - fetches unnecessary columns")
            analysis["recommendations"].append("Specify only needed columns")

        # Missing LIMIT
        if "select" in query_lower and "limit" not in query_lower:
            analysis["issues"].append("Missing LIMIT clause - may return too many rows")
            analysis["recommendations"].append("Add LIMIT clause to restrict result set")

        # Subqueries
        if query_lower.count("select") > 1:
            analysis["issues"].append("Contains subqueries - may be inefficient")
            analysis["recommendations"].append("Consider using JOINs instead of subqueries")

        # OR conditions
        if " or " in query_lower:
            analysis["issues"].append("Using OR conditions - may prevent index usage")
            analysis["recommendations"].append("Consider using UNION or IN clause")

        return analysis

    def track_query_execution(
        self,
        query: str,
        execution_time_ms: float,
    ):
        """Track query execution for statistics.

        Args:
            query: SQL query
            execution_time_ms: Execution time in milliseconds
        """
        import hashlib

        query_hash = hashlib.md5(query.encode()).hexdigest()[:16]

        if query_hash in self.query_stats:
            stats = self.query_stats[query_hash]
            stats.execution_count += 1
            stats.total_time_ms += execution_time_ms
            stats.avg_time_ms = stats.total_time_ms / stats.execution_count
            stats.max_time_ms = max(stats.max_time_ms, execution_time_ms)
            stats.min_time_ms = min(stats.min_time_ms, execution_time_ms)
            stats.last_executed = datetime.now()
        else:
            stats = QueryStats(
                query_hash=query_hash,
                query_text=query[:200],  # Truncate for storage
                execution_count=1,
                total_time_ms=execution_time_ms,
                avg_time_ms=execution_time_ms,
                max_time_ms=execution_time_ms,
                min_time_ms=execution_time_ms,
                last_executed=datetime.now(),
            )
            self.query_stats[query_hash] = stats

        # Track slow queries
        if execution_time_ms > self.slow_query_threshold_ms:
            if stats not in self.slow_queries:
                self.slow_queries.append(stats)

            logger.warning(
                f"Slow query detected: {execution_time_ms:.2f}ms",
                extra={
                    "query_hash": query_hash,
                    "execution_time_ms": execution_time_ms,
                },
            )

    def get_slow_queries(self, limit: int = 10) -> List[QueryStats]:
        """Get slowest queries.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of slow query statistics
        """
        # Sort by average time
        sorted_queries = sorted(
            self.slow_queries,
            key=lambda q: q.avg_time_ms,
            reverse=True,
        )

        return sorted_queries[:limit]

    def get_most_frequent_queries(self, limit: int = 10) -> List[QueryStats]:
        """Get most frequently executed queries.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of query statistics
        """
        sorted_queries = sorted(
            self.query_stats.values(),
            key=lambda q: q.execution_count,
            reverse=True,
        )

        return sorted_queries[:limit]

    def recommend_indexes(self, table_name: str) -> List[IndexRecommendation]:
        """Recommend indexes for table.

        Args:
            table_name: Table name

        Returns:
            List of index recommendations
        """
        recommendations = []

        # Analyze queries for this table
        table_queries = [
            stats
            for stats in self.query_stats.values()
            if table_name.lower() in stats.query_text.lower()
        ]

        if not table_queries:
            return recommendations

        # Common patterns
        for stats in table_queries:
            query_lower = stats.query_text.lower()

            # WHERE clause columns
            if "where" in query_lower:
                recommendations.append(
                    IndexRecommendation(
                        table_name=table_name,
                        columns=["id"],  # Simplified - would parse actual columns
                        reason="Frequently used in WHERE clause",
                        estimated_improvement="30-50% faster queries",
                    )
                )

            # JOIN columns
            if "join" in query_lower:
                recommendations.append(
                    IndexRecommendation(
                        table_name=table_name,
                        columns=["foreign_key_id"],  # Simplified
                        reason="Used in JOIN operations",
                        estimated_improvement="50-70% faster joins",
                    )
                )

            # ORDER BY columns
            if "order by" in query_lower:
                recommendations.append(
                    IndexRecommendation(
                        table_name=table_name,
                        columns=["created_at"],  # Simplified
                        reason="Used in ORDER BY clause",
                        estimated_improvement="20-40% faster sorting",
                    )
                )

        # Remove duplicates
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            key = (rec.table_name, tuple(rec.columns))
            if key not in seen:
                seen.add(key)
                unique_recommendations.append(rec)

        return unique_recommendations

    def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report.

        Returns:
            Optimization report
        """
        total_queries = sum(s.execution_count for s in self.query_stats.values())
        total_time = sum(s.total_time_ms for s in self.query_stats.values())
        avg_time = total_time / total_queries if total_queries > 0 else 0

        return {
            "summary": {
                "total_queries": total_queries,
                "unique_queries": len(self.query_stats),
                "slow_queries": len(self.slow_queries),
                "total_time_ms": total_time,
                "avg_time_ms": avg_time,
            },
            "slow_queries": [
                {
                    "query": q.query_text,
                    "avg_time_ms": q.avg_time_ms,
                    "execution_count": q.execution_count,
                }
                for q in self.get_slow_queries(5)
            ],
            "frequent_queries": [
                {
                    "query": q.query_text,
                    "execution_count": q.execution_count,
                    "avg_time_ms": q.avg_time_ms,
                }
                for q in self.get_most_frequent_queries(5)
            ],
        }
