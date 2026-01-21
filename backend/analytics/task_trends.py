"""Task completion trend analysis.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24.2: Business Metrics
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Trend direction."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class TrendMetrics:
    """Trend metrics for a time period."""

    period_start: datetime
    period_end: datetime

    # Task counts
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0

    # Completion metrics
    completion_rate: float = 0.0
    avg_completion_time_seconds: float = 0.0

    # Trend indicators
    trend_direction: TrendDirection = TrendDirection.STABLE
    growth_rate: float = 0.0

    def calculate_metrics(self) -> None:
        """Calculate derived metrics."""
        if self.total_tasks > 0:
            self.completion_rate = self.completed_tasks / self.total_tasks


@dataclass
class TrendReport:
    """Trend analysis report."""

    report_id: str
    generated_at: datetime
    analysis_period_days: int

    # Time series data
    daily_metrics: List[TrendMetrics] = field(default_factory=list)
    weekly_metrics: List[TrendMetrics] = field(default_factory=list)
    monthly_metrics: List[TrendMetrics] = field(default_factory=list)

    # Overall trends
    overall_trend: TrendDirection = TrendDirection.STABLE
    avg_daily_tasks: float = 0.0
    peak_day: Optional[datetime] = None
    peak_tasks: int = 0

    # Predictions
    predicted_next_week_tasks: int = 0
    predicted_next_month_tasks: int = 0

    # Insights
    insights: List[str] = field(default_factory=list)


class TaskTrendAnalyzer:
    """Task completion trend analyzer.

    Analyzes task completion trends including:
    - Daily/weekly/monthly patterns
    - Growth rates
    - Seasonal patterns
    - Predictions
    """

    def __init__(self, database=None):
        """Initialize trend analyzer.

        Args:
            database: Database connection for querying task data
        """
        self.database = database
        self.trend_cache: Dict[str, TrendReport] = {}

        logger.info("TaskTrendAnalyzer initialized")

    def analyze_trends(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> TrendReport:
        """Analyze task completion trends.

        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            user_id: Optional user ID to filter by

        Returns:
            TrendReport with analysis results
        """
        logger.info(f"Analyzing trends from {start_date} to {end_date}")

        days = (end_date - start_date).days

        report = TrendReport(
            report_id=f"trend-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            generated_at=datetime.now(),
            analysis_period_days=days,
        )

        # Collect daily metrics
        report.daily_metrics = self._collect_daily_metrics(start_date, end_date, user_id)

        # Collect weekly metrics
        report.weekly_metrics = self._collect_weekly_metrics(start_date, end_date, user_id)

        # Collect monthly metrics if period is long enough
        if days >= 30:
            report.monthly_metrics = self._collect_monthly_metrics(start_date, end_date, user_id)

        # Analyze overall trend
        report.overall_trend = self._determine_trend_direction(report.daily_metrics)

        # Calculate averages
        if report.daily_metrics:
            report.avg_daily_tasks = statistics.mean([m.total_tasks for m in report.daily_metrics])

            # Find peak day
            peak_metric = max(report.daily_metrics, key=lambda m: m.total_tasks)
            report.peak_day = peak_metric.period_start
            report.peak_tasks = peak_metric.total_tasks

        # Generate predictions
        report.predicted_next_week_tasks = self._predict_tasks(report.daily_metrics, days=7)
        report.predicted_next_month_tasks = self._predict_tasks(report.daily_metrics, days=30)

        # Generate insights
        report.insights = self._generate_insights(report)

        # Cache report
        self.trend_cache[report.report_id] = report

        return report

    def _collect_daily_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> List[TrendMetrics]:
        """Collect daily metrics.

        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter

        Returns:
            List of daily TrendMetrics
        """
        daily_metrics = []
        current_date = start_date

        while current_date < end_date:
            next_date = current_date + timedelta(days=1)

            # Placeholder for actual database query
            # In real implementation, query tasks for this day
            metrics = TrendMetrics(
                period_start=current_date,
                period_end=next_date,
                total_tasks=50,  # Simulated data
                completed_tasks=45,
                failed_tasks=3,
                cancelled_tasks=2,
                avg_completion_time_seconds=120.0,
            )
            metrics.calculate_metrics()

            daily_metrics.append(metrics)
            current_date = next_date

        return daily_metrics

    def _collect_weekly_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> List[TrendMetrics]:
        """Collect weekly metrics.

        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter

        Returns:
            List of weekly TrendMetrics
        """
        weekly_metrics = []
        current_date = start_date

        while current_date < end_date:
            next_date = min(current_date + timedelta(days=7), end_date)

            # Aggregate daily metrics for the week
            metrics = TrendMetrics(
                period_start=current_date,
                period_end=next_date,
                total_tasks=350,  # Simulated data
                completed_tasks=315,
                failed_tasks=21,
                cancelled_tasks=14,
                avg_completion_time_seconds=125.0,
            )
            metrics.calculate_metrics()

            weekly_metrics.append(metrics)
            current_date = next_date

        return weekly_metrics

    def _collect_monthly_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> List[TrendMetrics]:
        """Collect monthly metrics.

        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter

        Returns:
            List of monthly TrendMetrics
        """
        monthly_metrics = []
        current_date = start_date

        while current_date < end_date:
            # Move to next month
            if current_date.month == 12:
                next_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
            else:
                next_date = current_date.replace(month=current_date.month + 1, day=1)

            next_date = min(next_date, end_date)

            metrics = TrendMetrics(
                period_start=current_date,
                period_end=next_date,
                total_tasks=1500,  # Simulated data
                completed_tasks=1350,
                failed_tasks=90,
                cancelled_tasks=60,
                avg_completion_time_seconds=130.0,
            )
            metrics.calculate_metrics()

            monthly_metrics.append(metrics)
            current_date = next_date

        return monthly_metrics

    def _determine_trend_direction(
        self,
        metrics_list: List[TrendMetrics],
    ) -> TrendDirection:
        """Determine overall trend direction.

        Args:
            metrics_list: List of metrics

        Returns:
            TrendDirection
        """
        if len(metrics_list) < 2:
            return TrendDirection.STABLE

        # Calculate linear regression slope
        task_counts = [m.total_tasks for m in metrics_list]

        # Simple trend detection
        first_half = task_counts[: len(task_counts) // 2]
        second_half = task_counts[len(task_counts) // 2 :]

        if not first_half or not second_half:
            return TrendDirection.STABLE

        avg_first = statistics.mean(first_half)
        avg_second = statistics.mean(second_half)

        change_percent = ((avg_second - avg_first) / avg_first * 100) if avg_first > 0 else 0

        # Check volatility
        if len(task_counts) > 3:
            stdev = statistics.stdev(task_counts)
            mean = statistics.mean(task_counts)
            cv = (stdev / mean * 100) if mean > 0 else 0

            if cv > 30:  # High coefficient of variation
                return TrendDirection.VOLATILE

        if change_percent > 10:
            return TrendDirection.INCREASING
        elif change_percent < -10:
            return TrendDirection.DECREASING
        else:
            return TrendDirection.STABLE

    def _predict_tasks(
        self,
        historical_metrics: List[TrendMetrics],
        days: int,
    ) -> int:
        """Predict number of tasks for future period.

        Args:
            historical_metrics: Historical metrics
            days: Number of days to predict

        Returns:
            Predicted number of tasks
        """
        if not historical_metrics:
            return 0

        # Simple moving average prediction
        recent_metrics = historical_metrics[-min(7, len(historical_metrics)) :]
        avg_daily_tasks = statistics.mean([m.total_tasks for m in recent_metrics])

        return int(avg_daily_tasks * days)

    def _generate_insights(
        self,
        report: TrendReport,
    ) -> List[str]:
        """Generate insights from trend analysis.

        Args:
            report: Trend report

        Returns:
            List of insight strings
        """
        insights = []

        # Trend direction insight
        if report.overall_trend == TrendDirection.INCREASING:
            insights.append("Task volume is increasing. Consider scaling resources.")
        elif report.overall_trend == TrendDirection.DECREASING:
            insights.append("Task volume is decreasing. Review user engagement.")
        elif report.overall_trend == TrendDirection.VOLATILE:
            insights.append("Task volume is volatile. Investigate causes of fluctuation.")

        # Peak day insight
        if report.peak_day:
            day_name = report.peak_day.strftime("%A")
            insights.append(f"Peak activity occurs on {day_name}s with {report.peak_tasks} tasks.")

        # Completion rate insight
        if report.daily_metrics:
            avg_completion_rate = statistics.mean([m.completion_rate for m in report.daily_metrics])
            if avg_completion_rate < 0.8:
                insights.append(
                    f"Average completion rate is {avg_completion_rate:.1%}. Consider investigating failures."
                )

        # Prediction insight
        if report.predicted_next_week_tasks > report.avg_daily_tasks * 7 * 1.2:
            insights.append(
                "Predicted increase in task volume next week. Prepare additional capacity."
            )

        return insights

    def get_task_distribution(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Get task distribution by type, status, etc.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary with distribution data
        """
        # Placeholder for actual implementation
        return {
            "by_status": {
                "completed": 1350,
                "failed": 90,
                "cancelled": 60,
                "in_progress": 50,
            },
            "by_type": {
                "data_analysis": 500,
                "content_generation": 400,
                "code_review": 300,
                "research": 250,
                "other": 100,
            },
            "by_priority": {
                "high": 300,
                "medium": 800,
                "low": 450,
            },
        }
