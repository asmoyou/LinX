"""Anomaly detection for agent behavior.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24.1: Performance Metrics
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
from uuid import UUID
import statistics

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of anomalies."""
    
    PERFORMANCE_DEGRADATION = "performance_degradation"
    UNUSUAL_ERROR_RATE = "unusual_error_rate"
    RESOURCE_SPIKE = "resource_spike"
    TASK_DURATION_ANOMALY = "task_duration_anomaly"
    BEHAVIOR_CHANGE = "behavior_change"
    SECURITY_ANOMALY = "security_anomaly"


class AnomalySeverity(Enum):
    """Anomaly severity levels."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AnomalyAlert:
    """Anomaly alert."""
    
    alert_id: str
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    detected_at: datetime
    
    # Subject
    agent_id: Optional[UUID] = None
    agent_name: Optional[str] = None
    
    # Details
    description: str = ""
    metric_name: str = ""
    current_value: float = 0.0
    expected_value: float = 0.0
    deviation_percent: float = 0.0
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Status
    acknowledged: bool = False
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    
    # Actions
    recommended_actions: List[str] = field(default_factory=list)


class AnomalyDetector:
    """Anomaly detector for agent behavior.
    
    Detects anomalies using:
    - Statistical methods (z-score, IQR)
    - Threshold-based detection
    - Pattern recognition
    - Machine learning (placeholder)
    """
    
    def __init__(self, metrics_collector=None):
        """Initialize anomaly detector.
        
        Args:
            metrics_collector: Metrics collector for data
        """
        self.metrics_collector = metrics_collector
        self.alerts: List[AnomalyAlert] = []
        self.baseline_metrics: Dict[UUID, Dict[str, float]] = {}
        
        logger.info("AnomalyDetector initialized")
    
    def detect_anomalies(
        self,
        agent_id: UUID,
        lookback_hours: int = 24,
    ) -> List[AnomalyAlert]:
        """Detect anomalies for an agent.
        
        Args:
            agent_id: Agent ID
            lookback_hours: Hours of data to analyze
            
        Returns:
            List of detected anomalies
        """
        logger.info(f"Detecting anomalies for agent {agent_id}")
        
        alerts = []
        
        # Collect recent metrics
        metrics = self._collect_metrics(agent_id, lookback_hours)
        
        # Get or establish baseline
        baseline = self._get_baseline(agent_id)
        
        # Check for performance degradation
        perf_alerts = self._detect_performance_degradation(agent_id, metrics, baseline)
        alerts.extend(perf_alerts)
        
        # Check for unusual error rates
        error_alerts = self._detect_error_rate_anomalies(agent_id, metrics, baseline)
        alerts.extend(error_alerts)
        
        # Check for resource spikes
        resource_alerts = self._detect_resource_spikes(agent_id, metrics, baseline)
        alerts.extend(resource_alerts)
        
        # Check for task duration anomalies
        duration_alerts = self._detect_task_duration_anomalies(agent_id, metrics, baseline)
        alerts.extend(duration_alerts)
        
        # Store alerts
        self.alerts.extend(alerts)
        
        return alerts
    
    def _collect_metrics(
        self,
        agent_id: UUID,
        lookback_hours: int,
    ) -> Dict[str, List[float]]:
        """Collect metrics for analysis.
        
        Args:
            agent_id: Agent ID
            lookback_hours: Hours to look back
            
        Returns:
            Dictionary of metric time series
        """
        # Placeholder for actual metrics collection
        # In real implementation, query from metrics database
        
        return {
            "task_completion_time": [45.0, 47.0, 46.0, 120.0, 48.0],  # Spike at index 3
            "error_rate": [0.02, 0.03, 0.02, 0.15, 0.03],  # Spike at index 3
            "cpu_usage": [35.0, 36.0, 34.0, 85.0, 37.0],  # Spike at index 3
            "memory_usage": [512.0, 520.0, 515.0, 890.0, 518.0],  # Spike at index 3
            "tasks_per_hour": [10.0, 11.0, 10.0, 5.0, 10.0],  # Drop at index 3
        }
    
    def _get_baseline(
        self,
        agent_id: UUID,
    ) -> Dict[str, float]:
        """Get baseline metrics for agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Dictionary of baseline values
        """
        if agent_id in self.baseline_metrics:
            return self.baseline_metrics[agent_id]
        
        # Establish baseline from historical data
        baseline = {
            "task_completion_time": 46.0,
            "error_rate": 0.025,
            "cpu_usage": 35.0,
            "memory_usage": 515.0,
            "tasks_per_hour": 10.0,
        }
        
        self.baseline_metrics[agent_id] = baseline
        return baseline
    
    def _detect_performance_degradation(
        self,
        agent_id: UUID,
        metrics: Dict[str, List[float]],
        baseline: Dict[str, float],
    ) -> List[AnomalyAlert]:
        """Detect performance degradation.
        
        Args:
            agent_id: Agent ID
            metrics: Current metrics
            baseline: Baseline metrics
            
        Returns:
            List of anomaly alerts
        """
        alerts = []
        
        # Check tasks per hour
        if "tasks_per_hour" in metrics and "tasks_per_hour" in baseline:
            recent_values = metrics["tasks_per_hour"][-5:]  # Last 5 data points
            avg_recent = statistics.mean(recent_values)
            baseline_value = baseline["tasks_per_hour"]
            
            deviation = ((baseline_value - avg_recent) / baseline_value * 100) if baseline_value > 0 else 0
            
            if deviation > 30:  # 30% drop in throughput
                alert = AnomalyAlert(
                    alert_id=f"anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    anomaly_type=AnomalyType.PERFORMANCE_DEGRADATION,
                    severity=AnomalySeverity.HIGH if deviation > 50 else AnomalySeverity.MEDIUM,
                    detected_at=datetime.now(),
                    agent_id=agent_id,
                    description=f"Agent throughput dropped by {deviation:.1f}%",
                    metric_name="tasks_per_hour",
                    current_value=avg_recent,
                    expected_value=baseline_value,
                    deviation_percent=deviation,
                    recommended_actions=[
                        "Check agent logs for errors",
                        "Review recent task assignments",
                        "Consider restarting agent",
                    ]
                )
                alerts.append(alert)
        
        return alerts
    
    def _detect_error_rate_anomalies(
        self,
        agent_id: UUID,
        metrics: Dict[str, List[float]],
        baseline: Dict[str, float],
    ) -> List[AnomalyAlert]:
        """Detect unusual error rates.
        
        Args:
            agent_id: Agent ID
            metrics: Current metrics
            baseline: Baseline metrics
            
        Returns:
            List of anomaly alerts
        """
        alerts = []
        
        if "error_rate" in metrics and "error_rate" in baseline:
            recent_values = metrics["error_rate"]
            baseline_value = baseline["error_rate"]
            
            # Use z-score for anomaly detection
            if len(recent_values) > 1:
                mean = statistics.mean(recent_values)
                stdev = statistics.stdev(recent_values)
                
                for value in recent_values[-3:]:  # Check last 3 values
                    if stdev > 0:
                        z_score = abs((value - mean) / stdev)
                        
                        if z_score > 2.5 and value > baseline_value * 2:  # Significant spike
                            alert = AnomalyAlert(
                                alert_id=f"anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                anomaly_type=AnomalyType.UNUSUAL_ERROR_RATE,
                                severity=AnomalySeverity.HIGH,
                                detected_at=datetime.now(),
                                agent_id=agent_id,
                                description=f"Error rate spiked to {value:.1%}",
                                metric_name="error_rate",
                                current_value=value,
                                expected_value=baseline_value,
                                deviation_percent=((value - baseline_value) / baseline_value * 100) if baseline_value > 0 else 0,
                                recommended_actions=[
                                    "Review error logs",
                                    "Check for recent code changes",
                                    "Verify external dependencies",
                                ]
                            )
                            alerts.append(alert)
                            break  # Only one alert per metric
        
        return alerts
    
    def _detect_resource_spikes(
        self,
        agent_id: UUID,
        metrics: Dict[str, List[float]],
        baseline: Dict[str, float],
    ) -> List[AnomalyAlert]:
        """Detect resource usage spikes.
        
        Args:
            agent_id: Agent ID
            metrics: Current metrics
            baseline: Baseline metrics
            
        Returns:
            List of anomaly alerts
        """
        alerts = []
        
        # Check CPU usage
        if "cpu_usage" in metrics and "cpu_usage" in baseline:
            recent_values = metrics["cpu_usage"]
            baseline_value = baseline["cpu_usage"]
            max_value = max(recent_values)
            
            if max_value > baseline_value * 2 and max_value > 80:  # 2x baseline and >80%
                alert = AnomalyAlert(
                    alert_id=f"anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    anomaly_type=AnomalyType.RESOURCE_SPIKE,
                    severity=AnomalySeverity.MEDIUM,
                    detected_at=datetime.now(),
                    agent_id=agent_id,
                    description=f"CPU usage spiked to {max_value:.1f}%",
                    metric_name="cpu_usage",
                    current_value=max_value,
                    expected_value=baseline_value,
                    deviation_percent=((max_value - baseline_value) / baseline_value * 100) if baseline_value > 0 else 0,
                    recommended_actions=[
                        "Check for resource-intensive tasks",
                        "Review agent workload",
                        "Consider scaling resources",
                    ]
                )
                alerts.append(alert)
        
        # Check memory usage
        if "memory_usage" in metrics and "memory_usage" in baseline:
            recent_values = metrics["memory_usage"]
            baseline_value = baseline["memory_usage"]
            max_value = max(recent_values)
            
            if max_value > baseline_value * 1.5:  # 50% increase
                alert = AnomalyAlert(
                    alert_id=f"anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    anomaly_type=AnomalyType.RESOURCE_SPIKE,
                    severity=AnomalySeverity.MEDIUM,
                    detected_at=datetime.now(),
                    agent_id=agent_id,
                    description=f"Memory usage increased to {max_value:.0f} MB",
                    metric_name="memory_usage",
                    current_value=max_value,
                    expected_value=baseline_value,
                    deviation_percent=((max_value - baseline_value) / baseline_value * 100) if baseline_value > 0 else 0,
                    recommended_actions=[
                        "Check for memory leaks",
                        "Review data caching strategy",
                        "Monitor for continued growth",
                    ]
                )
                alerts.append(alert)
        
        return alerts
    
    def _detect_task_duration_anomalies(
        self,
        agent_id: UUID,
        metrics: Dict[str, List[float]],
        baseline: Dict[str, float],
    ) -> List[AnomalyAlert]:
        """Detect task duration anomalies.
        
        Args:
            agent_id: Agent ID
            metrics: Current metrics
            baseline: Baseline metrics
            
        Returns:
            List of anomaly alerts
        """
        alerts = []
        
        if "task_completion_time" in metrics and "task_completion_time" in baseline:
            recent_values = metrics["task_completion_time"]
            baseline_value = baseline["task_completion_time"]
            
            # Check for outliers using IQR method
            if len(recent_values) >= 4:
                sorted_values = sorted(recent_values)
                q1 = sorted_values[len(sorted_values) // 4]
                q3 = sorted_values[3 * len(sorted_values) // 4]
                iqr = q3 - q1
                
                upper_bound = q3 + 1.5 * iqr
                
                outliers = [v for v in recent_values if v > upper_bound]
                
                if outliers:
                    max_outlier = max(outliers)
                    alert = AnomalyAlert(
                        alert_id=f"anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        anomaly_type=AnomalyType.TASK_DURATION_ANOMALY,
                        severity=AnomalySeverity.MEDIUM,
                        detected_at=datetime.now(),
                        agent_id=agent_id,
                        description=f"Task duration anomaly detected: {max_outlier:.1f}s",
                        metric_name="task_completion_time",
                        current_value=max_outlier,
                        expected_value=baseline_value,
                        deviation_percent=((max_outlier - baseline_value) / baseline_value * 100) if baseline_value > 0 else 0,
                        recommended_actions=[
                            "Review slow tasks",
                            "Check for blocking operations",
                            "Optimize task execution",
                        ]
                    )
                    alerts.append(alert)
        
        return alerts
    
    def get_active_alerts(
        self,
        agent_id: Optional[UUID] = None,
        severity: Optional[AnomalySeverity] = None,
    ) -> List[AnomalyAlert]:
        """Get active (unresolved) alerts.
        
        Args:
            agent_id: Optional agent ID filter
            severity: Optional severity filter
            
        Returns:
            List of active alerts
        """
        alerts = [a for a in self.alerts if not a.resolved]
        
        if agent_id:
            alerts = [a for a in alerts if a.agent_id == agent_id]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        return alerts
    
    def acknowledge_alert(
        self,
        alert_id: str,
    ) -> bool:
        """Acknowledge an alert.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            True if alert was found and acknowledged
        """
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                logger.info(f"Alert acknowledged: {alert_id}")
                return True
        
        return False
    
    def resolve_alert(
        self,
        alert_id: str,
    ) -> bool:
        """Resolve an alert.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            True if alert was found and resolved
        """
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolution_time = datetime.now()
                logger.info(f"Alert resolved: {alert_id}")
                return True
        
        return False
    
    def get_anomaly_summary(
        self,
        time_period_hours: int = 24,
    ) -> Dict[str, Any]:
        """Get summary of anomalies.
        
        Args:
            time_period_hours: Time period to summarize
            
        Returns:
            Dictionary with anomaly summary
        """
        cutoff_time = datetime.now() - timedelta(hours=time_period_hours)
        recent_alerts = [a for a in self.alerts if a.detected_at >= cutoff_time]
        
        return {
            "total_alerts": len(recent_alerts),
            "active_alerts": len([a for a in recent_alerts if not a.resolved]),
            "by_severity": {
                "critical": len([a for a in recent_alerts if a.severity == AnomalySeverity.CRITICAL]),
                "high": len([a for a in recent_alerts if a.severity == AnomalySeverity.HIGH]),
                "medium": len([a for a in recent_alerts if a.severity == AnomalySeverity.MEDIUM]),
                "low": len([a for a in recent_alerts if a.severity == AnomalySeverity.LOW]),
            },
            "by_type": {
                anomaly_type.value: len([a for a in recent_alerts if a.anomaly_type == anomaly_type])
                for anomaly_type in AnomalyType
            },
            "most_affected_agents": self._get_most_affected_agents(recent_alerts),
        }
    
    def _get_most_affected_agents(
        self,
        alerts: List[AnomalyAlert],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get agents with most anomalies.
        
        Args:
            alerts: List of alerts
            limit: Maximum number of agents to return
            
        Returns:
            List of agent summaries
        """
        agent_counts: Dict[UUID, int] = {}
        
        for alert in alerts:
            if alert.agent_id:
                agent_counts[alert.agent_id] = agent_counts.get(alert.agent_id, 0) + 1
        
        sorted_agents = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {"agent_id": str(agent_id), "anomaly_count": count}
            for agent_id, count in sorted_agents[:limit]
        ]
