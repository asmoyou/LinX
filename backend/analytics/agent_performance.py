"""Agent performance analytics.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24.1: Performance Metrics
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for an agent."""

    agent_id: UUID
    agent_name: str

    # Task metrics
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_in_progress: int = 0

    # Time metrics
    avg_task_duration_seconds: float = 0.0
    min_task_duration_seconds: float = 0.0
    max_task_duration_seconds: float = 0.0

    # Quality metrics
    success_rate: float = 0.0
    error_rate: float = 0.0
    retry_rate: float = 0.0

    # Resource metrics
    avg_cpu_usage_percent: float = 0.0
    avg_memory_usage_mb: float = 0.0
    avg_llm_tokens_per_task: float = 0.0

    # Efficiency metrics
    tasks_per_hour: float = 0.0
    cost_per_task: float = 0.0

    # Time period
    period_start: datetime = field(default_factory=datetime.now)
    period_end: datetime = field(default_factory=datetime.now)

    def calculate_derived_metrics(self) -> None:
        """Calculate derived metrics from raw data."""
        total_tasks = self.tasks_completed + self.tasks_failed

        if total_tasks > 0:
            self.success_rate = self.tasks_completed / total_tasks
            self.error_rate = self.tasks_failed / total_tasks

        # Calculate tasks per hour
        duration_hours = (self.period_end - self.period_start).total_seconds() / 3600
        if duration_hours > 0:
            self.tasks_per_hour = self.tasks_completed / duration_hours


@dataclass
class PerformanceReport:
    """Performance report for multiple agents."""

    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime

    # Agent metrics
    agent_metrics: List[PerformanceMetrics] = field(default_factory=list)

    # Aggregate metrics
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    avg_success_rate: float = 0.0

    # Top performers
    top_agents_by_tasks: List[UUID] = field(default_factory=list)
    top_agents_by_success_rate: List[UUID] = field(default_factory=list)
    top_agents_by_efficiency: List[UUID] = field(default_factory=list)

    # Bottom performers
    agents_needing_attention: List[UUID] = field(default_factory=list)


class AgentPerformanceAnalytics:
    """Agent performance analytics engine.

    Analyzes agent performance metrics including:
    - Task completion rates
    - Success/failure rates
    - Resource utilization
    - Efficiency metrics
    - Performance trends
    """

    def __init__(self, database=None, metrics_collector=None):
        """Initialize performance analytics.

        Args:
            database: Database connection for querying metrics
            metrics_collector: Metrics collector for real-time data
        """
        self.database = database
        self.metrics_collector = metrics_collector
        self.performance_cache: Dict[UUID, PerformanceMetrics] = {}

        logger.info("AgentPerformanceAnalytics initialized")

    def collect_agent_metrics(
        self,
        agent_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> PerformanceMetrics:
        """Collect performance metrics for an agent.

        Args:
            agent_id: Agent ID
            start_time: Start of time period
            end_time: End of time period

        Returns:
            PerformanceMetrics for the agent
        """
        logger.info(f"Collecting metrics for agent {agent_id}")

        # Placeholder for actual database queries
        # In real implementation, this would:
        # 1. Query task completion data
        # 2. Query resource usage data
        # 3. Query error logs
        # 4. Calculate metrics

        metrics = PerformanceMetrics(
            agent_id=agent_id,
            agent_name=f"Agent-{agent_id}",
            period_start=start_time,
            period_end=end_time,
        )

        # Simulate data collection
        metrics.tasks_completed = 100
        metrics.tasks_failed = 5
        metrics.avg_task_duration_seconds = 45.0
        metrics.avg_cpu_usage_percent = 35.0
        metrics.avg_memory_usage_mb = 512.0

        metrics.calculate_derived_metrics()

        # Cache metrics
        self.performance_cache[agent_id] = metrics

        return metrics

    def generate_performance_report(
        self,
        agent_ids: List[UUID],
        start_time: datetime,
        end_time: datetime,
    ) -> PerformanceReport:
        """Generate performance report for multiple agents.

        Args:
            agent_ids: List of agent IDs
            start_time: Start of time period
            end_time: End of time period

        Returns:
            PerformanceReport
        """
        logger.info(f"Generating performance report for {len(agent_ids)} agents")

        report = PerformanceReport(
            report_id=f"perf-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            generated_at=datetime.now(),
            period_start=start_time,
            period_end=end_time,
        )

        # Collect metrics for each agent
        for agent_id in agent_ids:
            metrics = self.collect_agent_metrics(agent_id, start_time, end_time)
            report.agent_metrics.append(metrics)

        # Calculate aggregate metrics
        if report.agent_metrics:
            report.total_tasks_completed = sum(m.tasks_completed for m in report.agent_metrics)
            report.total_tasks_failed = sum(m.tasks_failed for m in report.agent_metrics)

            success_rates = [m.success_rate for m in report.agent_metrics if m.success_rate > 0]
            if success_rates:
                report.avg_success_rate = statistics.mean(success_rates)

        # Identify top performers
        report.top_agents_by_tasks = self._rank_agents_by_tasks(report.agent_metrics)
        report.top_agents_by_success_rate = self._rank_agents_by_success_rate(report.agent_metrics)
        report.top_agents_by_efficiency = self._rank_agents_by_efficiency(report.agent_metrics)

        # Identify agents needing attention
        report.agents_needing_attention = self._identify_underperformers(report.agent_metrics)

        return report

    def _rank_agents_by_tasks(
        self,
        metrics_list: List[PerformanceMetrics],
    ) -> List[UUID]:
        """Rank agents by number of tasks completed.

        Args:
            metrics_list: List of performance metrics

        Returns:
            List of agent IDs ranked by tasks completed
        """
        sorted_metrics = sorted(metrics_list, key=lambda m: m.tasks_completed, reverse=True)
        return [m.agent_id for m in sorted_metrics[:10]]

    def _rank_agents_by_success_rate(
        self,
        metrics_list: List[PerformanceMetrics],
    ) -> List[UUID]:
        """Rank agents by success rate.

        Args:
            metrics_list: List of performance metrics

        Returns:
            List of agent IDs ranked by success rate
        """
        sorted_metrics = sorted(metrics_list, key=lambda m: m.success_rate, reverse=True)
        return [m.agent_id for m in sorted_metrics[:10]]

    def _rank_agents_by_efficiency(
        self,
        metrics_list: List[PerformanceMetrics],
    ) -> List[UUID]:
        """Rank agents by efficiency (tasks per hour).

        Args:
            metrics_list: List of performance metrics

        Returns:
            List of agent IDs ranked by efficiency
        """
        sorted_metrics = sorted(metrics_list, key=lambda m: m.tasks_per_hour, reverse=True)
        return [m.agent_id for m in sorted_metrics[:10]]

    def _identify_underperformers(
        self,
        metrics_list: List[PerformanceMetrics],
        success_rate_threshold: float = 0.8,
        error_rate_threshold: float = 0.2,
    ) -> List[UUID]:
        """Identify agents that need attention.

        Args:
            metrics_list: List of performance metrics
            success_rate_threshold: Minimum acceptable success rate
            error_rate_threshold: Maximum acceptable error rate

        Returns:
            List of agent IDs needing attention
        """
        underperformers = []

        for metrics in metrics_list:
            if (
                metrics.success_rate < success_rate_threshold
                or metrics.error_rate > error_rate_threshold
            ):
                underperformers.append(metrics.agent_id)

        return underperformers

    def compare_agent_performance(
        self,
        agent_id: UUID,
        comparison_period_days: int = 7,
    ) -> Dict[str, Any]:
        """Compare agent performance across time periods.

        Args:
            agent_id: Agent ID
            comparison_period_days: Number of days to compare

        Returns:
            Dictionary with comparison results
        """
        now = datetime.now()

        # Current period
        current_start = now - timedelta(days=comparison_period_days)
        current_metrics = self.collect_agent_metrics(agent_id, current_start, now)

        # Previous period
        previous_end = current_start
        previous_start = previous_end - timedelta(days=comparison_period_days)
        previous_metrics = self.collect_agent_metrics(agent_id, previous_start, previous_end)

        # Calculate changes
        comparison = {
            "agent_id": str(agent_id),
            "current_period": {
                "start": current_start.isoformat(),
                "end": now.isoformat(),
                "metrics": {
                    "tasks_completed": current_metrics.tasks_completed,
                    "success_rate": current_metrics.success_rate,
                    "tasks_per_hour": current_metrics.tasks_per_hour,
                },
            },
            "previous_period": {
                "start": previous_start.isoformat(),
                "end": previous_end.isoformat(),
                "metrics": {
                    "tasks_completed": previous_metrics.tasks_completed,
                    "success_rate": previous_metrics.success_rate,
                    "tasks_per_hour": previous_metrics.tasks_per_hour,
                },
            },
            "changes": {
                "tasks_completed": current_metrics.tasks_completed
                - previous_metrics.tasks_completed,
                "success_rate": current_metrics.success_rate - previous_metrics.success_rate,
                "tasks_per_hour": current_metrics.tasks_per_hour - previous_metrics.tasks_per_hour,
            },
        }

        return comparison

    def get_performance_summary(
        self,
        agent_id: UUID,
    ) -> Dict[str, Any]:
        """Get performance summary for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with performance summary
        """
        # Get cached metrics or collect new ones
        if agent_id in self.performance_cache:
            metrics = self.performance_cache[agent_id]
        else:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)
            metrics = self.collect_agent_metrics(agent_id, start_time, end_time)

        return {
            "agent_id": str(agent_id),
            "agent_name": metrics.agent_name,
            "tasks_completed": metrics.tasks_completed,
            "tasks_failed": metrics.tasks_failed,
            "success_rate": metrics.success_rate,
            "avg_task_duration": metrics.avg_task_duration_seconds,
            "tasks_per_hour": metrics.tasks_per_hour,
            "resource_usage": {
                "cpu_percent": metrics.avg_cpu_usage_percent,
                "memory_mb": metrics.avg_memory_usage_mb,
            },
        }
