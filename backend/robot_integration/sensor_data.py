"""Sensor data storage in Memory System.

References:
- Requirements 10: Robot Integration Preparation
- Design Section 17.3: Sensor Data Management
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
import time

logger = logging.getLogger(__name__)


class SensorType(Enum):
    """Types of robot sensors."""
    
    # Vision sensors
    CAMERA_RGB = "camera_rgb"
    CAMERA_DEPTH = "camera_depth"
    LIDAR = "lidar"
    
    # Position sensors
    GPS = "gps"
    IMU = "imu"
    ODOMETRY = "odometry"
    
    # Proximity sensors
    ULTRASONIC = "ultrasonic"
    INFRARED = "infrared"
    LASER_RANGE = "laser_range"
    
    # Force sensors
    FORCE_TORQUE = "force_torque"
    TACTILE = "tactile"
    PRESSURE = "pressure"
    
    # Environmental sensors
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    GAS = "gas"


@dataclass
class SensorData:
    """Sensor data record."""
    
    sensor_id: str
    sensor_type: SensorType
    robot_id: UUID
    timestamp: float
    data: Any
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize defaults."""
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type.value,
            "robot_id": str(self.robot_id),
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }


class SensorDataStore:
    """Store sensor data in Memory System."""
    
    def __init__(self, memory_system=None):
        """Initialize sensor data store."""
        self.memory_system = memory_system
        self._cache: List[SensorData] = []
        logger.info("SensorDataStore initialized")
    
    def store(self, sensor_data: SensorData) -> bool:
        """Store sensor data.
        
        Args:
            sensor_data: Sensor data to store
            
        Returns:
            True if successful
        """
        try:
            # Store in cache
            self._cache.append(sensor_data)
            
            # Store in memory system (placeholder)
            if self.memory_system:
                # In real implementation, store in Milvus
                pass
            
            logger.debug(f"Sensor data stored: {sensor_data.sensor_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store sensor data: {e}")
            return False
    
    def query(
        self,
        robot_id: UUID,
        sensor_type: Optional[SensorType] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[SensorData]:
        """Query sensor data.
        
        Args:
            robot_id: Robot ID
            sensor_type: Optional sensor type filter
            start_time: Optional start timestamp
            end_time: Optional end timestamp
            limit: Maximum number of results
            
        Returns:
            List of sensor data
        """
        results = []
        
        for data in self._cache:
            if data.robot_id != robot_id:
                continue
            
            if sensor_type and data.sensor_type != sensor_type:
                continue
            
            if start_time and data.timestamp < start_time:
                continue
            
            if end_time and data.timestamp > end_time:
                continue
            
            results.append(data)
            
            if len(results) >= limit:
                break
        
        return results
