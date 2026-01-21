"""Tests for analytics module.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24: Success Metrics
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from analytics.agent_performance import (
    AgentPerformanceAnalytics,
    PerformanceMetrics,
)
from analytics.task_trends import (
    TaskTrendAnalyzer,
    TrendDirection,
)
from analytics.resource_forecasting import (
    ResourceForecaster,
    ForecastModel,
)
from analytics.anomaly_detection import (
    AnomalyDetector,
    AnomalyType,
    AnomalySeverity,
)
from analytics.cost_tracking import (
    CostTracker,
    CostOptimizer,
)
from analytics.user_satisfaction import (
    SatisfactionTracker,
    SatisfactionRating,
)


class TestAgentPerformance:
    """Tests for agent performance analytics."""
    
    def test_collect_agent_metrics(self):
        """Test collecting agent metrics."""
        analytics = AgentPerformanceAnalytics()
        agent_id = uuid4()
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=7)
        
        metrics = analytics.collect_agent_metrics(agent_id, start_time, end_time)
        
        assert metrics.agent_id == agent_id
        assert metrics.tasks_completed > 0
        assert metrics.success_rate > 0
    
    def test_generate_performance_report(self):
        """Test generating performance report."""
        analytics = AgentPerformanceAnalytics()
        agent_ids = [uuid4() for _ in range(5)]
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=7)
        
        report = analytics.generate_performance_report(agent_ids, start_time, end_time)
        
        assert len(report.agent_metrics) == 5
        assert report.total_tasks_completed > 0
        assert len(report.top_agents_by_tasks) > 0
    
    def test_compare_agent_performance(self):
        """Test comparing agent performance."""
        analytics = AgentPerformanceAnalytics()
        agent_id = uuid4()
        
        comparison = analytics.compare_agent_performance(agent_id, comparison_period_days=7)
        
        assert "current_period" in comparison
        assert "previous_period" in comparison
        assert "changes" in comparison


class TestTaskTrends:
    """Tests for task trend analysis."""
    
    def test_analyze_trends(self):
        """Test analyzing task trends."""
        analyzer = TaskTrendAnalyzer()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        report = analyzer.analyze_trends(start_date, end_date)
        
        assert len(report.daily_metrics) > 0
        assert report.overall_trend in [t for t in TrendDirection]
        assert report.avg_daily_tasks > 0
    
    def test_trend_direction_detection(self):
        """Test trend direction detection."""
        analyzer = TaskTrendAnalyzer()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=14)
        
        report = analyzer.analyze_trends(start_date, end_date)
        
        assert report.overall_trend is not None
        assert isinstance(report.overall_trend, TrendDirection)
    
    def test_task_distribution(self):
        """Test getting task distribution."""
        analyzer = TaskTrendAnalyzer()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        distribution = analyzer.get_task_distribution(start_date, end_date)
        
        assert "by_status" in distribution
        assert "by_type" in distribution
        assert "by_priority" in distribution


class TestResourceForecasting:
    """Tests for resource forecasting."""
    
    def test_forecast_resource_usage(self):
        """Test forecasting resource usage."""
        forecaster = ResourceForecaster()
        
        result = forecaster.forecast_resource_usage("cpu", forecast_hours=24)
        
        assert result.resource_type == "cpu"
        assert len(result.forecasted_values) == 24
        assert result.confidence_score >= 0 and result.confidence_score <= 1
    
    def test_different_forecast_models(self):
        """Test different forecasting models."""
        forecaster = ResourceForecaster()
        
        models = [
            ForecastModel.MOVING_AVERAGE,
            ForecastModel.EXPONENTIAL_SMOOTHING,
            ForecastModel.LINEAR_REGRESSION,
        ]
        
        for model in models:
            result = forecaster.forecast_resource_usage("memory", forecast_hours=12, model=model)
            assert result.model_used == model
            assert len(result.forecasted_values) == 12
    
    def test_capacity_warnings(self):
        """Test capacity warning generation."""
        forecaster = ResourceForecaster()
        
        result = forecaster.forecast_resource_usage("cpu", forecast_hours=48)
        
        # Warnings may or may not be present depending on forecast
        assert isinstance(result.capacity_warnings, list)
    
    def test_forecast_agent_capacity(self):
        """Test forecasting agent capacity."""
        forecaster = ResourceForecaster()
        
        capacity = forecaster.forecast_agent_capacity(forecast_hours=24)
        
        assert "current_agents" in capacity
        assert "required_agents" in capacity
        assert "recommendation" in capacity


class TestAnomalyDetection:
    """Tests for anomaly detection."""
    
    def test_detect_anomalies(self):
        """Test detecting anomalies."""
        detector = AnomalyDetector()
        agent_id = uuid4()
        
        alerts = detector.detect_anomalies(agent_id, lookback_hours=24)
        
        # Alerts may or may not be present
        assert isinstance(alerts, list)
        for alert in alerts:
            assert alert.agent_id == agent_id
            assert alert.anomaly_type in [t for t in AnomalyType]
    
    def test_alert_management(self):
        """Test alert acknowledgment and resolution."""
        detector = AnomalyDetector()
        agent_id = uuid4()
        
        # Detect anomalies
        alerts = detector.detect_anomalies(agent_id, lookback_hours=24)
        
        if alerts:
            alert = alerts[0]
            
            # Acknowledge alert
            result = detector.acknowledge_alert(alert.alert_id)
            assert result is True
            assert alert.acknowledged is True
            
            # Resolve alert
            result = detector.resolve_alert(alert.alert_id)
            assert result is True
            assert alert.resolved is True
    
    def test_get_active_alerts(self):
        """Test getting active alerts."""
        detector = AnomalyDetector()
        agent_id = uuid4()
        
        # Generate some alerts
        detector.detect_anomalies(agent_id, lookback_hours=24)
        
        # Get active alerts
        active = detector.get_active_alerts()
        
        assert isinstance(active, list)
    
    def test_anomaly_summary(self):
        """Test getting anomaly summary."""
        detector = AnomalyDetector()
        agent_id = uuid4()
        
        # Generate some alerts
        detector.detect_anomalies(agent_id, lookback_hours=24)
        
        summary = detector.get_anomaly_summary(time_period_hours=24)
        
        assert "total_alerts" in summary
        assert "by_severity" in summary
        assert "by_type" in summary


class TestCostTracking:
    """Tests for cost tracking."""
    
    def test_calculate_costs(self):
        """Test calculating costs."""
        tracker = CostTracker()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        metrics = tracker.calculate_costs(start_date, end_date)
        
        assert metrics.total_cost_usd > 0
        assert metrics.llm_cost_usd >= 0
        assert metrics.compute_cost_usd >= 0
        assert metrics.storage_cost_usd >= 0
    
    def test_cost_breakdown(self):
        """Test getting cost breakdown."""
        tracker = CostTracker()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        breakdown = tracker.get_cost_breakdown(start_date, end_date)
        
        assert "total_cost_usd" in breakdown
        assert "breakdown" in breakdown
        assert "llm" in breakdown["breakdown"]
        assert "compute" in breakdown["breakdown"]
    
    def test_compare_costs(self):
        """Test comparing costs."""
        tracker = CostTracker()
        
        comparison = tracker.compare_costs(current_period_days=30)
        
        assert "current_period" in comparison
        assert "previous_period" in comparison
        assert "change" in comparison


class TestCostOptimization:
    """Tests for cost optimization."""
    
    def test_analyze_optimization_opportunities(self):
        """Test analyzing optimization opportunities."""
        tracker = CostTracker()
        optimizer = CostOptimizer(tracker)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        recommendations = optimizer.analyze_optimization_opportunities(start_date, end_date)
        
        assert isinstance(recommendations, list)
        for rec in recommendations:
            assert rec.potential_savings_usd >= 0
            assert rec.category in ["llm", "compute", "storage", "network"]
    
    def test_optimization_summary(self):
        """Test getting optimization summary."""
        tracker = CostTracker()
        optimizer = CostOptimizer(tracker)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        summary = optimizer.get_optimization_summary(start_date, end_date)
        
        assert "current_cost_usd" in summary
        assert "total_potential_savings_usd" in summary
        assert "recommendations_count" in summary


class TestUserSatisfaction:
    """Tests for user satisfaction tracking."""
    
    def test_submit_survey(self):
        """Test submitting satisfaction survey."""
        tracker = SatisfactionTracker()
        user_id = uuid4()
        
        survey = tracker.submit_survey(
            user_id=user_id,
            overall_rating=SatisfactionRating.SATISFIED,
            ease_of_use=SatisfactionRating.VERY_SATISFIED,
            response_quality=SatisfactionRating.SATISFIED,
            feedback_text="Great experience!",
            would_recommend=True,
        )
        
        assert survey.user_id == user_id
        assert survey.overall_rating == SatisfactionRating.SATISFIED
        assert survey.get_average_rating() > 0
    
    def test_calculate_metrics(self):
        """Test calculating satisfaction metrics."""
        tracker = SatisfactionTracker()
        user_id = uuid4()
        
        # Submit some surveys
        for _ in range(5):
            tracker.submit_survey(
                user_id=user_id,
                overall_rating=SatisfactionRating.SATISFIED,
            )
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        metrics = tracker.calculate_metrics(start_date, end_date)
        
        assert metrics.total_surveys == 5
        assert metrics.avg_overall_rating > 0
        assert metrics.nps_score >= -100 and metrics.nps_score <= 100
    
    def test_satisfaction_report(self):
        """Test getting satisfaction report."""
        tracker = SatisfactionTracker()
        user_id = uuid4()
        
        # Submit surveys
        tracker.submit_survey(user_id=user_id, overall_rating=SatisfactionRating.VERY_SATISFIED)
        tracker.submit_survey(user_id=user_id, overall_rating=SatisfactionRating.SATISFIED)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        report = tracker.get_satisfaction_report(start_date, end_date)
        
        assert "overview" in report
        assert "ratings" in report
        assert "nps" in report
        assert "insights" in report
    
    def test_agent_satisfaction(self):
        """Test getting agent satisfaction."""
        tracker = SatisfactionTracker()
        user_id = uuid4()
        agent_id = uuid4()
        
        # Submit survey for agent
        tracker.submit_survey(
            user_id=user_id,
            overall_rating=SatisfactionRating.VERY_SATISFIED,
            agent_id=agent_id,
        )
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        agent_satisfaction = tracker.get_agent_satisfaction(agent_id, start_date, end_date)
        
        assert agent_satisfaction["agent_id"] == str(agent_id)
        assert agent_satisfaction["surveys_received"] == 1
    
    def test_top_rated_agents(self):
        """Test getting top-rated agents."""
        tracker = SatisfactionTracker()
        user_id = uuid4()
        
        # Submit surveys for different agents
        for _ in range(3):
            agent_id = uuid4()
            tracker.submit_survey(
                user_id=user_id,
                overall_rating=SatisfactionRating.SATISFIED,
                agent_id=agent_id,
            )
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        top_agents = tracker.get_top_rated_agents(start_date, end_date, limit=5)
        
        assert isinstance(top_agents, list)
        assert len(top_agents) <= 5
