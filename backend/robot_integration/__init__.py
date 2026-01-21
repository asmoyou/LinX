"""Robot integration module for future robotic worker support.

This module provides the foundation for integrating physical robots:
- RobotAgent interface extending BaseAgent
- Physical task type definitions
- Sensor data storage in Memory System
- ROS (Robot Operating System) integration
- MQTT communication layer
- Physical world state management
- Safety and compliance framework

References:
- Requirements 10: Robot Integration Preparation
- Design Section 17: Robot Integration Architecture
"""

from robot_integration.robot_agent import (
    RobotAgent,
    RobotConfig,
    RobotStatus,
    RobotCapability,
)

from robot_integration.physical_tasks import (
    PhysicalTaskType,
    PhysicalTask,
    TaskLocation,
    TaskConstraints,
)

from robot_integration.sensor_data import (
    SensorData,
    SensorType,
    SensorDataStore,
)

from robot_integration.ros_interface import (
    ROSInterface,
    ROSNode,
    ROSTopic,
)

from robot_integration.mqtt_client import (
    MQTTClient,
    MQTTConfig,
    MQTTMessage,
)

from robot_integration.world_state import (
    WorldState,
    PhysicalObject,
    RobotPose,
)

from robot_integration.safety_framework import (
    SafetyChecker,
    SafetyRule,
    SafetyLevel,
    SafetyViolation,
    ComplianceValidator,
    ComplianceStandard,
)

__all__ = [
    # Robot agent
    'RobotAgent',
    'RobotConfig',
    'RobotStatus',
    'RobotCapability',
    
    # Physical tasks
    'PhysicalTaskType',
    'PhysicalTask',
    'TaskLocation',
    'TaskConstraints',
    
    # Sensor data
    'SensorData',
    'SensorType',
    'SensorDataStore',
    
    # ROS integration
    'ROSInterface',
    'ROSNode',
    'ROSTopic',
    
    # MQTT communication
    'MQTTClient',
    'MQTTConfig',
    'MQTTMessage',
    
    # World state
    'WorldState',
    'PhysicalObject',
    'RobotPose',
    
    # Safety framework
    'SafetyChecker',
    'SafetyRule',
    'SafetyLevel',
    'SafetyViolation',
    'ComplianceValidator',
    'ComplianceStandard',
]
