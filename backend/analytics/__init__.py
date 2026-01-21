"""Advanced analytics module for platform insights.

This module provides comprehensive analytics capabilities:
- Agent performance analytics
- Task completion trend analysis
- Resource utilization forecasting
- Anomaly detection for agent behavior
- Cost tracking and optimization
- User satisfaction metrics

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24: Success Metrics
"""

from analytics.agent_performance import (
    AgentPerformanceAnalytics,
    PerformanceMetrics,
    PerformanceReport,
)
from analytics.anomaly_detection import (
    AnomalyAlert,
    AnomalyDetector,
    AnomalyType,
)
from analytics.cost_tracking import (
    CostMetrics,
    CostOptimizer,
    CostTracker,
)
from analytics.resource_forecasting import (
    ForecastModel,
    ForecastResult,
    ResourceForecaster,
)
from analytics.task_trends import (
    TaskTrendAnalyzer,
    TrendMetrics,
    TrendReport,
)
from analytics.user_satisfaction import (
    SatisfactionMetrics,
    SatisfactionSurvey,
    SatisfactionTracker,
)

__all__ = [
    # Agent performance
    "AgentPerformanceAnalytics",
    "PerformanceMetrics",
    "PerformanceReport",
    # Task trends
    "TaskTrendAnalyzer",
    "TrendMetrics",
    "TrendReport",
    # Resource forecasting
    "ResourceForecaster",
    "ForecastModel",
    "ForecastResult",
    # Anomaly detection
    "AnomalyDetector",
    "AnomalyType",
    "AnomalyAlert",
    # Cost tracking
    "CostTracker",
    "CostMetrics",
    "CostOptimizer",
    # User satisfaction
    "SatisfactionTracker",
    "SatisfactionMetrics",
    "SatisfactionSurvey",
]
