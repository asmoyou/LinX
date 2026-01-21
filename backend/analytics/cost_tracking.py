"""Cost tracking and optimization.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24.2: Business Metrics
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class CostMetrics:
    """Cost metrics for a time period."""

    period_start: datetime
    period_end: datetime

    # LLM costs
    llm_api_calls: int = 0
    llm_tokens_used: int = 0
    llm_cost_usd: float = 0.0

    # Compute costs
    cpu_hours: float = 0.0
    memory_gb_hours: float = 0.0
    compute_cost_usd: float = 0.0

    # Storage costs
    storage_gb: float = 0.0
    storage_cost_usd: float = 0.0

    # Network costs
    network_gb: float = 0.0
    network_cost_usd: float = 0.0

    # Total
    total_cost_usd: float = 0.0

    # Per-unit costs
    cost_per_task: float = 0.0
    cost_per_agent: float = 0.0
    cost_per_user: float = 0.0

    def calculate_total(self) -> None:
        """Calculate total cost."""
        self.total_cost_usd = (
            self.llm_cost_usd
            + self.compute_cost_usd
            + self.storage_cost_usd
            + self.network_cost_usd
        )


@dataclass
class CostOptimization:
    """Cost optimization recommendation."""

    recommendation_id: str
    category: str  # llm, compute, storage, network
    description: str
    potential_savings_usd: float
    implementation_effort: str  # low, medium, high
    priority: str  # low, medium, high

    # Details
    current_cost: float = 0.0
    optimized_cost: float = 0.0
    savings_percent: float = 0.0

    # Actions
    action_items: List[str] = field(default_factory=list)


class CostTracker:
    """Cost tracking system.

    Tracks costs for:
    - LLM API usage
    - Compute resources
    - Storage
    - Network bandwidth
    """

    def __init__(self, database=None, metrics_collector=None):
        """Initialize cost tracker.

        Args:
            database: Database connection
            metrics_collector: Metrics collector
        """
        self.database = database
        self.metrics_collector = metrics_collector

        # Cost rates (USD)
        self.llm_cost_per_1k_tokens = 0.002  # Example rate
        self.compute_cost_per_cpu_hour = 0.05
        self.compute_cost_per_gb_hour = 0.01
        self.storage_cost_per_gb_month = 0.10
        self.network_cost_per_gb = 0.09

        logger.info("CostTracker initialized")

    def calculate_costs(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
    ) -> CostMetrics:
        """Calculate costs for a time period.

        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter
            agent_id: Optional agent ID filter

        Returns:
            CostMetrics
        """
        logger.info(f"Calculating costs from {start_date} to {end_date}")

        metrics = CostMetrics(
            period_start=start_date,
            period_end=end_date,
        )

        # Collect usage data
        usage_data = self._collect_usage_data(start_date, end_date, user_id, agent_id)

        # Calculate LLM costs
        metrics.llm_api_calls = usage_data.get("llm_api_calls", 0)
        metrics.llm_tokens_used = usage_data.get("llm_tokens_used", 0)
        metrics.llm_cost_usd = (metrics.llm_tokens_used / 1000) * self.llm_cost_per_1k_tokens

        # Calculate compute costs
        metrics.cpu_hours = usage_data.get("cpu_hours", 0.0)
        metrics.memory_gb_hours = usage_data.get("memory_gb_hours", 0.0)
        metrics.compute_cost_usd = (
            metrics.cpu_hours * self.compute_cost_per_cpu_hour
            + metrics.memory_gb_hours * self.compute_cost_per_gb_hour
        )

        # Calculate storage costs
        metrics.storage_gb = usage_data.get("storage_gb", 0.0)
        days = (end_date - start_date).days
        months = days / 30.0
        metrics.storage_cost_usd = metrics.storage_gb * self.storage_cost_per_gb_month * months

        # Calculate network costs
        metrics.network_gb = usage_data.get("network_gb", 0.0)
        metrics.network_cost_usd = metrics.network_gb * self.network_cost_per_gb

        # Calculate total
        metrics.calculate_total()

        # Calculate per-unit costs
        tasks_completed = usage_data.get("tasks_completed", 0)
        active_agents = usage_data.get("active_agents", 0)
        active_users = usage_data.get("active_users", 0)

        if tasks_completed > 0:
            metrics.cost_per_task = metrics.total_cost_usd / tasks_completed
        if active_agents > 0:
            metrics.cost_per_agent = metrics.total_cost_usd / active_agents
        if active_users > 0:
            metrics.cost_per_user = metrics.total_cost_usd / active_users

        return metrics

    def _collect_usage_data(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Collect usage data for cost calculation.

        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter
            agent_id: Optional agent ID filter

        Returns:
            Dictionary with usage data
        """
        # Placeholder for actual data collection
        # In real implementation, query from database and metrics

        return {
            "llm_api_calls": 10000,
            "llm_tokens_used": 5000000,  # 5M tokens
            "cpu_hours": 240.0,  # 10 days * 24 hours
            "memory_gb_hours": 12288.0,  # 512GB * 24 hours
            "storage_gb": 100.0,
            "network_gb": 50.0,
            "tasks_completed": 1000,
            "active_agents": 10,
            "active_users": 5,
        }

    def get_cost_breakdown(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Get detailed cost breakdown.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary with cost breakdown
        """
        metrics = self.calculate_costs(start_date, end_date)

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
            "total_cost_usd": metrics.total_cost_usd,
            "breakdown": {
                "llm": {
                    "cost_usd": metrics.llm_cost_usd,
                    "percent": (
                        (metrics.llm_cost_usd / metrics.total_cost_usd * 100)
                        if metrics.total_cost_usd > 0
                        else 0
                    ),
                    "api_calls": metrics.llm_api_calls,
                    "tokens_used": metrics.llm_tokens_used,
                },
                "compute": {
                    "cost_usd": metrics.compute_cost_usd,
                    "percent": (
                        (metrics.compute_cost_usd / metrics.total_cost_usd * 100)
                        if metrics.total_cost_usd > 0
                        else 0
                    ),
                    "cpu_hours": metrics.cpu_hours,
                    "memory_gb_hours": metrics.memory_gb_hours,
                },
                "storage": {
                    "cost_usd": metrics.storage_cost_usd,
                    "percent": (
                        (metrics.storage_cost_usd / metrics.total_cost_usd * 100)
                        if metrics.total_cost_usd > 0
                        else 0
                    ),
                    "storage_gb": metrics.storage_gb,
                },
                "network": {
                    "cost_usd": metrics.network_cost_usd,
                    "percent": (
                        (metrics.network_cost_usd / metrics.total_cost_usd * 100)
                        if metrics.total_cost_usd > 0
                        else 0
                    ),
                    "network_gb": metrics.network_gb,
                },
            },
            "per_unit": {
                "cost_per_task": metrics.cost_per_task,
                "cost_per_agent": metrics.cost_per_agent,
                "cost_per_user": metrics.cost_per_user,
            },
        }

    def compare_costs(
        self,
        current_period_days: int = 30,
    ) -> Dict[str, Any]:
        """Compare costs across time periods.

        Args:
            current_period_days: Days in current period

        Returns:
            Dictionary with cost comparison
        """
        now = datetime.now()

        # Current period
        current_start = now - timedelta(days=current_period_days)
        current_metrics = self.calculate_costs(current_start, now)

        # Previous period
        previous_end = current_start
        previous_start = previous_end - timedelta(days=current_period_days)
        previous_metrics = self.calculate_costs(previous_start, previous_end)

        # Calculate changes
        cost_change = current_metrics.total_cost_usd - previous_metrics.total_cost_usd
        cost_change_percent = (
            (cost_change / previous_metrics.total_cost_usd * 100)
            if previous_metrics.total_cost_usd > 0
            else 0
        )

        return {
            "current_period": {
                "start": current_start.isoformat(),
                "end": now.isoformat(),
                "total_cost_usd": current_metrics.total_cost_usd,
            },
            "previous_period": {
                "start": previous_start.isoformat(),
                "end": previous_end.isoformat(),
                "total_cost_usd": previous_metrics.total_cost_usd,
            },
            "change": {
                "absolute_usd": cost_change,
                "percent": cost_change_percent,
                "trend": (
                    "increasing"
                    if cost_change > 0
                    else "decreasing" if cost_change < 0 else "stable"
                ),
            },
        }


class CostOptimizer:
    """Cost optimization analyzer.

    Analyzes costs and provides optimization recommendations.
    """

    def __init__(self, cost_tracker: CostTracker):
        """Initialize cost optimizer.

        Args:
            cost_tracker: Cost tracker instance
        """
        self.cost_tracker = cost_tracker

        logger.info("CostOptimizer initialized")

    def analyze_optimization_opportunities(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> List[CostOptimization]:
        """Analyze cost optimization opportunities.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of optimization recommendations
        """
        logger.info("Analyzing cost optimization opportunities")

        recommendations = []

        # Get current costs
        metrics = self.cost_tracker.calculate_costs(start_date, end_date)

        # Analyze LLM costs
        llm_recs = self._analyze_llm_costs(metrics)
        recommendations.extend(llm_recs)

        # Analyze compute costs
        compute_recs = self._analyze_compute_costs(metrics)
        recommendations.extend(compute_recs)

        # Analyze storage costs
        storage_recs = self._analyze_storage_costs(metrics)
        recommendations.extend(storage_recs)

        # Sort by potential savings
        recommendations.sort(key=lambda r: r.potential_savings_usd, reverse=True)

        return recommendations

    def _analyze_llm_costs(
        self,
        metrics: CostMetrics,
    ) -> List[CostOptimization]:
        """Analyze LLM cost optimization opportunities.

        Args:
            metrics: Cost metrics

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check if LLM costs are high
        if metrics.llm_cost_usd > metrics.total_cost_usd * 0.5:  # >50% of total
            # Recommend caching
            rec = CostOptimization(
                recommendation_id="llm-cache-001",
                category="llm",
                description="Implement response caching for deterministic queries",
                potential_savings_usd=metrics.llm_cost_usd * 0.3,  # 30% savings
                implementation_effort="medium",
                priority="high",
                current_cost=metrics.llm_cost_usd,
                optimized_cost=metrics.llm_cost_usd * 0.7,
                savings_percent=30.0,
                action_items=[
                    "Identify frequently repeated queries",
                    "Implement Redis-based response cache",
                    "Set appropriate TTL for cached responses",
                    "Monitor cache hit rate",
                ],
            )
            recommendations.append(rec)

            # Recommend prompt optimization
            rec = CostOptimization(
                recommendation_id="llm-prompt-001",
                category="llm",
                description="Optimize prompts to reduce token usage",
                potential_savings_usd=metrics.llm_cost_usd * 0.15,  # 15% savings
                implementation_effort="low",
                priority="medium",
                current_cost=metrics.llm_cost_usd,
                optimized_cost=metrics.llm_cost_usd * 0.85,
                savings_percent=15.0,
                action_items=[
                    "Review and shorten system prompts",
                    "Remove unnecessary context",
                    "Use more efficient prompt templates",
                ],
            )
            recommendations.append(rec)

        return recommendations

    def _analyze_compute_costs(
        self,
        metrics: CostMetrics,
    ) -> List[CostOptimization]:
        """Analyze compute cost optimization opportunities.

        Args:
            metrics: Cost metrics

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check for idle resources
        if metrics.compute_cost_usd > 0:
            rec = CostOptimization(
                recommendation_id="compute-idle-001",
                category="compute",
                description="Implement auto-scaling to reduce idle resources",
                potential_savings_usd=metrics.compute_cost_usd * 0.25,  # 25% savings
                implementation_effort="medium",
                priority="high",
                current_cost=metrics.compute_cost_usd,
                optimized_cost=metrics.compute_cost_usd * 0.75,
                savings_percent=25.0,
                action_items=[
                    "Configure horizontal pod autoscaler",
                    "Set appropriate min/max replicas",
                    "Monitor resource utilization",
                    "Implement graceful shutdown",
                ],
            )
            recommendations.append(rec)

        return recommendations

    def _analyze_storage_costs(
        self,
        metrics: CostMetrics,
    ) -> List[CostOptimization]:
        """Analyze storage cost optimization opportunities.

        Args:
            metrics: Cost metrics

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check for old data
        if metrics.storage_cost_usd > 0:
            rec = CostOptimization(
                recommendation_id="storage-archive-001",
                category="storage",
                description="Archive old data to cold storage",
                potential_savings_usd=metrics.storage_cost_usd * 0.40,  # 40% savings
                implementation_effort="low",
                priority="medium",
                current_cost=metrics.storage_cost_usd,
                optimized_cost=metrics.storage_cost_usd * 0.60,
                savings_percent=40.0,
                action_items=[
                    "Identify data older than 90 days",
                    "Move to cold storage tier",
                    "Implement data lifecycle policies",
                    "Set up automated archival",
                ],
            )
            recommendations.append(rec)

        return recommendations

    def get_optimization_summary(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Get optimization summary.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary with optimization summary
        """
        recommendations = self.analyze_optimization_opportunities(start_date, end_date)

        total_potential_savings = sum(r.potential_savings_usd for r in recommendations)
        current_cost = self.cost_tracker.calculate_costs(start_date, end_date).total_cost_usd

        return {
            "current_cost_usd": current_cost,
            "total_potential_savings_usd": total_potential_savings,
            "savings_percent": (
                (total_potential_savings / current_cost * 100) if current_cost > 0 else 0
            ),
            "recommendations_count": len(recommendations),
            "by_priority": {
                "high": len([r for r in recommendations if r.priority == "high"]),
                "medium": len([r for r in recommendations if r.priority == "medium"]),
                "low": len([r for r in recommendations if r.priority == "low"]),
            },
            "by_category": {
                "llm": sum(r.potential_savings_usd for r in recommendations if r.category == "llm"),
                "compute": sum(
                    r.potential_savings_usd for r in recommendations if r.category == "compute"
                ),
                "storage": sum(
                    r.potential_savings_usd for r in recommendations if r.category == "storage"
                ),
                "network": sum(
                    r.potential_savings_usd for r in recommendations if r.category == "network"
                ),
            },
            "top_recommendations": [
                {
                    "id": r.recommendation_id,
                    "description": r.description,
                    "savings_usd": r.potential_savings_usd,
                    "priority": r.priority,
                }
                for r in recommendations[:5]
            ],
        }
