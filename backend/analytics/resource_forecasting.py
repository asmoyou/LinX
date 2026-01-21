"""Resource utilization forecasting.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24.1: Performance Metrics
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class ForecastModel(Enum):
    """Forecasting model types."""
    
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    LINEAR_REGRESSION = "linear_regression"
    SEASONAL = "seasonal"


@dataclass
class ResourceUsage:
    """Resource usage data point."""
    
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    disk_gb: float
    network_mbps: float
    active_agents: int
    active_tasks: int


@dataclass
class ForecastResult:
    """Forecast result."""
    
    resource_type: str
    forecast_horizon_hours: int
    model_used: ForecastModel
    
    # Historical data
    historical_values: List[float] = field(default_factory=list)
    historical_timestamps: List[datetime] = field(default_factory=list)
    
    # Forecast data
    forecasted_values: List[float] = field(default_factory=list)
    forecasted_timestamps: List[datetime] = field(default_factory=list)
    
    # Confidence intervals
    lower_bound: List[float] = field(default_factory=list)
    upper_bound: List[float] = field(default_factory=list)
    
    # Metrics
    confidence_score: float = 0.0
    mean_absolute_error: float = 0.0
    
    # Alerts
    capacity_warnings: List[str] = field(default_factory=list)


class ResourceForecaster:
    """Resource utilization forecaster.
    
    Forecasts resource utilization including:
    - CPU usage
    - Memory usage
    - Disk usage
    - Network bandwidth
    - Agent capacity
    """
    
    def __init__(self, metrics_collector=None):
        """Initialize resource forecaster.
        
        Args:
            metrics_collector: Metrics collector for historical data
        """
        self.metrics_collector = metrics_collector
        self.forecast_cache: Dict[str, ForecastResult] = {}
        
        logger.info("ResourceForecaster initialized")
    
    def forecast_resource_usage(
        self,
        resource_type: str,
        forecast_hours: int = 24,
        model: ForecastModel = ForecastModel.MOVING_AVERAGE,
    ) -> ForecastResult:
        """Forecast resource usage.
        
        Args:
            resource_type: Type of resource (cpu, memory, disk, network)
            forecast_hours: Number of hours to forecast
            model: Forecasting model to use
            
        Returns:
            ForecastResult with predictions
        """
        logger.info(f"Forecasting {resource_type} usage for {forecast_hours} hours")
        
        # Collect historical data
        historical_data = self._collect_historical_data(resource_type, lookback_hours=168)  # 7 days
        
        result = ForecastResult(
            resource_type=resource_type,
            forecast_horizon_hours=forecast_hours,
            model_used=model,
        )
        
        # Extract values and timestamps
        result.historical_values = [d.get(resource_type, 0.0) for d in historical_data]
        result.historical_timestamps = [d.get('timestamp') for d in historical_data]
        
        # Generate forecast based on model
        if model == ForecastModel.MOVING_AVERAGE:
            result.forecasted_values = self._moving_average_forecast(
                result.historical_values,
                forecast_hours
            )
        elif model == ForecastModel.EXPONENTIAL_SMOOTHING:
            result.forecasted_values = self._exponential_smoothing_forecast(
                result.historical_values,
                forecast_hours
            )
        elif model == ForecastModel.LINEAR_REGRESSION:
            result.forecasted_values = self._linear_regression_forecast(
                result.historical_values,
                forecast_hours
            )
        else:
            result.forecasted_values = self._moving_average_forecast(
                result.historical_values,
                forecast_hours
            )
        
        # Generate timestamps for forecast
        last_timestamp = result.historical_timestamps[-1] if result.historical_timestamps else datetime.now()
        result.forecasted_timestamps = [
            last_timestamp + timedelta(hours=i+1)
            for i in range(forecast_hours)
        ]
        
        # Calculate confidence intervals
        result.lower_bound, result.upper_bound = self._calculate_confidence_intervals(
            result.historical_values,
            result.forecasted_values
        )
        
        # Calculate confidence score
        result.confidence_score = self._calculate_confidence_score(result.historical_values)
        
        # Generate capacity warnings
        result.capacity_warnings = self._generate_capacity_warnings(
            resource_type,
            result.forecasted_values
        )
        
        # Cache result
        cache_key = f"{resource_type}_{forecast_hours}_{model.value}"
        self.forecast_cache[cache_key] = result
        
        return result
    
    def _collect_historical_data(
        self,
        resource_type: str,
        lookback_hours: int,
    ) -> List[Dict[str, Any]]:
        """Collect historical resource usage data.
        
        Args:
            resource_type: Type of resource
            lookback_hours: Hours of historical data to collect
            
        Returns:
            List of data points
        """
        # Placeholder for actual metrics collection
        # In real implementation, query from metrics database
        
        data = []
        now = datetime.now()
        
        for i in range(lookback_hours):
            timestamp = now - timedelta(hours=lookback_hours - i)
            
            # Simulate data with some pattern
            base_value = 50.0
            variation = 10.0 * (i % 24) / 24  # Daily pattern
            noise = (hash(str(timestamp)) % 10) - 5  # Random noise
            
            data.append({
                'timestamp': timestamp,
                resource_type: base_value + variation + noise,
            })
        
        return data
    
    def _moving_average_forecast(
        self,
        historical_values: List[float],
        forecast_hours: int,
        window_size: int = 24,
    ) -> List[float]:
        """Generate forecast using moving average.
        
        Args:
            historical_values: Historical data
            forecast_hours: Hours to forecast
            window_size: Moving average window size
            
        Returns:
            List of forecasted values
        """
        if len(historical_values) < window_size:
            window_size = len(historical_values)
        
        # Calculate moving average of recent data
        recent_values = historical_values[-window_size:]
        avg_value = statistics.mean(recent_values)
        
        # Simple forecast: repeat average
        return [avg_value] * forecast_hours
    
    def _exponential_smoothing_forecast(
        self,
        historical_values: List[float],
        forecast_hours: int,
        alpha: float = 0.3,
    ) -> List[float]:
        """Generate forecast using exponential smoothing.
        
        Args:
            historical_values: Historical data
            forecast_hours: Hours to forecast
            alpha: Smoothing parameter (0-1)
            
        Returns:
            List of forecasted values
        """
        if not historical_values:
            return [0.0] * forecast_hours
        
        # Calculate smoothed value
        smoothed = historical_values[0]
        for value in historical_values[1:]:
            smoothed = alpha * value + (1 - alpha) * smoothed
        
        # Forecast: use last smoothed value
        return [smoothed] * forecast_hours
    
    def _linear_regression_forecast(
        self,
        historical_values: List[float],
        forecast_hours: int,
    ) -> List[float]:
        """Generate forecast using linear regression.
        
        Args:
            historical_values: Historical data
            forecast_hours: Hours to forecast
            
        Returns:
            List of forecasted values
        """
        if len(historical_values) < 2:
            return [historical_values[0] if historical_values else 0.0] * forecast_hours
        
        # Simple linear regression
        n = len(historical_values)
        x = list(range(n))
        y = historical_values
        
        # Calculate slope and intercept
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return [y_mean] * forecast_hours
        
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        
        # Generate forecast
        forecast = []
        for i in range(forecast_hours):
            x_future = n + i
            y_future = slope * x_future + intercept
            forecast.append(max(0.0, y_future))  # Ensure non-negative
        
        return forecast
    
    def _calculate_confidence_intervals(
        self,
        historical_values: List[float],
        forecasted_values: List[float],
        confidence_level: float = 0.95,
    ) -> tuple[List[float], List[float]]:
        """Calculate confidence intervals for forecast.
        
        Args:
            historical_values: Historical data
            forecasted_values: Forecasted values
            confidence_level: Confidence level (0-1)
            
        Returns:
            Tuple of (lower_bound, upper_bound) lists
        """
        if not historical_values:
            return forecasted_values, forecasted_values
        
        # Calculate standard deviation of historical data
        stdev = statistics.stdev(historical_values) if len(historical_values) > 1 else 0.0
        
        # Z-score for 95% confidence
        z_score = 1.96
        
        margin = z_score * stdev
        
        lower_bound = [max(0.0, v - margin) for v in forecasted_values]
        upper_bound = [v + margin for v in forecasted_values]
        
        return lower_bound, upper_bound
    
    def _calculate_confidence_score(
        self,
        historical_values: List[float],
    ) -> float:
        """Calculate confidence score for forecast.
        
        Args:
            historical_values: Historical data
            
        Returns:
            Confidence score (0-1)
        """
        if len(historical_values) < 2:
            return 0.5
        
        # Calculate coefficient of variation
        mean = statistics.mean(historical_values)
        stdev = statistics.stdev(historical_values)
        
        if mean == 0:
            return 0.5
        
        cv = stdev / mean
        
        # Lower CV = higher confidence
        # CV > 1.0 = low confidence
        # CV < 0.1 = high confidence
        confidence = max(0.0, min(1.0, 1.0 - cv))
        
        return confidence
    
    def _generate_capacity_warnings(
        self,
        resource_type: str,
        forecasted_values: List[float],
        threshold_percent: float = 80.0,
    ) -> List[str]:
        """Generate capacity warnings based on forecast.
        
        Args:
            resource_type: Type of resource
            forecasted_values: Forecasted values
            threshold_percent: Warning threshold
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Check if any forecasted value exceeds threshold
        max_forecast = max(forecasted_values) if forecasted_values else 0.0
        
        if max_forecast > threshold_percent:
            hours_to_threshold = next(
                (i for i, v in enumerate(forecasted_values) if v > threshold_percent),
                None
            )
            
            if hours_to_threshold is not None:
                warnings.append(
                    f"{resource_type.upper()} usage will exceed {threshold_percent}% "
                    f"in approximately {hours_to_threshold} hours"
                )
        
        # Check for rapid growth
        if len(forecasted_values) >= 2:
            growth_rate = (forecasted_values[-1] - forecasted_values[0]) / len(forecasted_values)
            if growth_rate > 5.0:  # More than 5% per hour
                warnings.append(
                    f"{resource_type.upper()} usage is growing rapidly "
                    f"({growth_rate:.1f}% per hour)"
                )
        
        return warnings
    
    def forecast_agent_capacity(
        self,
        forecast_hours: int = 24,
    ) -> Dict[str, Any]:
        """Forecast agent capacity requirements.
        
        Args:
            forecast_hours: Hours to forecast
            
        Returns:
            Dictionary with capacity forecast
        """
        # Forecast task volume
        # Placeholder implementation
        
        current_agents = 10
        avg_tasks_per_agent_per_hour = 5
        forecasted_tasks_per_hour = 60
        
        required_agents = forecasted_tasks_per_hour / avg_tasks_per_agent_per_hour
        
        return {
            "current_agents": current_agents,
            "forecasted_tasks_per_hour": forecasted_tasks_per_hour,
            "required_agents": int(required_agents),
            "additional_agents_needed": max(0, int(required_agents - current_agents)),
            "utilization_percent": (current_agents / required_agents * 100) if required_agents > 0 else 0,
            "recommendation": "Scale up" if required_agents > current_agents * 1.2 else "Current capacity sufficient"
        }
