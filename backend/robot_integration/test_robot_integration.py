"""Tests for robot integration module.

References:
- Requirements 10: Robot Integration Preparation
- Design Section 17: Robot Integration Architecture
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, patch, MagicMock
import time

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
    PhysicalTaskValidator,
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
    ComplianceValidator,
    ComplianceStandard,
)


class TestRobotAgent:
    """Tests for RobotAgent class."""
    
    def test_robot_agent_initialization(self):
        """Test robot agent initialization."""
        config = RobotConfig(
            agent_id=uuid4(),
            name="TestRobot",
            agent_type="industrial_robot",
            owner_user_id=uuid4(),
            capabilities=["navigation", "manipulation"],
            robot_model="UR5",
            serial_number="UR5-12345",
            physical_capabilities=[RobotCapability.NAVIGATION, RobotCapability.MANIPULATION],
            max_payload_kg=5.0,
            max_reach_m=0.85,
            max_speed_ms=1.0,
        )
        
        agent = RobotAgent(config)
        
        assert agent.config.name == "TestRobot"
        assert agent.robot_status == RobotStatus.OFFLINE
        assert agent.robot_config.robot_model == "UR5"
        assert len(agent.robot_config.physical_capabilities) == 2
    
    def test_robot_connect_disconnect(self):
        """Test robot connection and disconnection."""
        config = RobotConfig(
            agent_id=uuid4(),
            name="TestRobot",
            agent_type="industrial_robot",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        
        agent = RobotAgent(config)
        
        # Test connection
        result = agent.connect()
        assert result is True
        assert agent.robot_status == RobotStatus.ONLINE
        
        # Test disconnection
        agent.disconnect()
        assert agent.robot_status == RobotStatus.OFFLINE
    
    def test_robot_sensor_data_update(self):
        """Test sensor data updates."""
        config = RobotConfig(
            agent_id=uuid4(),
            name="TestRobot",
            agent_type="industrial_robot",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        
        agent = RobotAgent(config)
        
        # Update sensor data
        agent.update_sensor_data("camera", {"image": "data"})
        agent.update_sensor_data("lidar", {"points": [1, 2, 3]})
        
        assert "camera" in agent.sensor_data
        assert "lidar" in agent.sensor_data
        assert agent.sensor_data["camera"]["data"] == {"image": "data"}
    
    def test_robot_execute_physical_task(self):
        """Test physical task execution."""
        config = RobotConfig(
            agent_id=uuid4(),
            name="TestRobot",
            agent_type="industrial_robot",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        
        agent = RobotAgent(config)
        agent.connect()
        
        # Execute task
        result = agent.execute_physical_task(
            "pick_and_place",
            {"object_id": "box123", "target_position": [1.0, 2.0, 0.5]}
        )
        
        assert result["success"] is True
        assert result["task_type"] == "pick_and_place"
    
    def test_robot_emergency_stop(self):
        """Test emergency stop."""
        config = RobotConfig(
            agent_id=uuid4(),
            name="TestRobot",
            agent_type="industrial_robot",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        
        agent = RobotAgent(config)
        agent.connect()
        
        # Trigger emergency stop
        agent.emergency_stop()
        
        assert agent.robot_status == RobotStatus.EMERGENCY_STOP
    
    def test_robot_get_capabilities(self):
        """Test getting robot capabilities."""
        config = RobotConfig(
            agent_id=uuid4(),
            name="TestRobot",
            agent_type="industrial_robot",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2"],
            physical_capabilities=[RobotCapability.NAVIGATION, RobotCapability.MANIPULATION],
        )
        
        agent = RobotAgent(config)
        capabilities = agent.get_capabilities()
        
        assert "skill1" in capabilities
        assert "skill2" in capabilities
        assert "physical:navigation" in capabilities
        assert "physical:manipulation" in capabilities


class TestPhysicalTasks:
    """Tests for physical task definitions."""
    
    def test_physical_task_creation(self):
        """Test physical task creation."""
        location = TaskLocation(
            x=1.0,
            y=2.0,
            z=0.5,
            qx=0.0,
            qy=0.0,
            qz=0.0,
            qw=1.0,
        )
        
        constraints = TaskConstraints(
            max_time_seconds=60.0,
            max_speed_ms=0.5,
            max_force_n=100.0,
        )
        
        task = PhysicalTask(
            task_type=PhysicalTaskType.PICK_AND_PLACE,
            description="Pick box and place on shelf",
            location=location,
            constraints=constraints,
            parameters={"object_id": "box123"},
        )
        
        assert task.task_type == PhysicalTaskType.PICK_AND_PLACE
        assert task.location.x == 1.0
        assert task.location.y == 2.0
        assert task.location.z == 0.5
        assert task.constraints.max_time_seconds == 60.0
    
    def test_physical_task_factory_methods(self):
        """Test physical task factory methods."""
        # Navigation task
        nav_task = PhysicalTask.create_navigation_task(
            x=1.0,
            y=2.0,
            z=0.0,
            max_speed=0.5,
        )
        assert nav_task.task_type == PhysicalTaskType.NAVIGATE_TO_LOCATION
        
        # Pick and place task
        pick_task = PhysicalTask.create_pick_and_place_task(
            pick_x=1.0,
            pick_y=2.0,
            pick_z=0.5,
            place_x=2.0,
            place_y=3.0,
            place_z=0.5,
            object_id="box123",
        )
        assert pick_task.task_type == PhysicalTaskType.PICK_AND_PLACE
        
        # Inspection task
        inspect_task = PhysicalTask.create_inspection_task(
            x=1.0,
            y=2.0,
            z=1.0,
            inspection_type="visual",
        )
        assert inspect_task.task_type == PhysicalTaskType.VISUAL_INSPECTION
    
    def test_physical_task_validator(self):
        """Test physical task validation."""
        validator = PhysicalTaskValidator()
        
        # Valid task
        valid_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate to position",
            location=TaskLocation(x=1.0, y=2.0, z=0.0),
        )
        
        is_valid, errors = validator.validate(valid_task)
        assert is_valid is True
        assert len(errors) == 0
        
        # Invalid task (no location)
        invalid_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate to position",
        )
        
        is_valid, errors = validator.validate(invalid_task)
        assert is_valid is False
        assert len(errors) > 0


class TestSensorData:
    """Tests for sensor data storage."""
    
    def test_sensor_data_creation(self):
        """Test sensor data creation."""
        sensor_data = SensorData(
            sensor_type=SensorType.CAMERA_RGB,
            data={"image": "base64_data"},
            robot_id=uuid4(),
        )
        
        assert sensor_data.sensor_type == SensorType.CAMERA_RGB
        assert sensor_data.data["image"] == "base64_data"
    
    @patch('memory_system.memory_system.MemorySystem')
    def test_sensor_data_store(self, mock_memory_system):
        """Test sensor data storage."""
        mock_memory = MagicMock()
        mock_memory_system.return_value = mock_memory
        
        store = SensorDataStore(mock_memory)
        robot_id = uuid4()
        
        # Store sensor data
        sensor_data = SensorData(
            sensor_type=SensorType.LIDAR,
            data={"points": [1, 2, 3]},
            robot_id=robot_id,
        )
        
        store.store_sensor_data(sensor_data)
        
        # Verify memory system was called
        mock_memory.store_memory.assert_called_once()
    
    @patch('memory_system.memory_system.MemorySystem')
    def test_sensor_data_retrieval(self, mock_memory_system):
        """Test sensor data retrieval."""
        mock_memory = MagicMock()
        mock_memory_system.return_value = mock_memory
        
        # Mock retrieval
        mock_memory.search_memories.return_value = [
            {"sensor_type": "camera", "data": {"image": "data"}}
        ]
        
        store = SensorDataStore(mock_memory)
        robot_id = uuid4()
        
        # Retrieve sensor data
        results = store.get_sensor_data(robot_id, SensorType.CAMERA_RGB, limit=10)
        
        assert len(results) == 1
        mock_memory.search_memories.assert_called_once()


class TestROSInterface:
    """Tests for ROS integration."""
    
    def test_ros_interface_initialization(self):
        """Test ROS interface initialization."""
        interface = ROSInterface()
        
        assert interface.master_uri == "http://localhost:11311"
        assert interface.connected is False
    
    def test_ros_topic_creation(self):
        """Test ROS topic creation."""
        topic = ROSTopic(
            name="/robot/joint_states",
            message_type="sensor_msgs/JointState",
        )
        
        assert topic.name == "/robot/joint_states"
        assert topic.message_type == "sensor_msgs/JointState"
    
    def test_ros_publish(self):
        """Test ROS message publishing."""
        interface = ROSInterface()
        
        # Publish message (placeholder implementation)
        result = interface.publish("/test_topic", {"data": "test"})
        
        # In placeholder implementation, this returns False
        assert result is False


class TestMQTTClient:
    """Tests for MQTT communication."""
    
    def test_mqtt_config_creation(self):
        """Test MQTT configuration."""
        config = MQTTConfig(
            broker_host="mqtt.example.com",
            broker_port=1883,
            username="robot1",
            password="secret",
        )
        
        assert config.broker_host == "mqtt.example.com"
        assert config.broker_port == 1883
    
    def test_mqtt_client_initialization(self):
        """Test MQTT client initialization."""
        config = MQTTConfig(broker_host="localhost")
        client = MQTTClient(config)
        
        assert client.config.broker_host == "localhost"
        # Note: MQTTClient doesn't have a 'connected' attribute in placeholder implementation
    
    def test_mqtt_message_creation(self):
        """Test MQTT message creation."""
        message = MQTTMessage(
            topic="robot/status",
            payload={"status": "online"},
            qos=1,
        )
        
        assert message.topic == "robot/status"
        assert message.payload["status"] == "online"
        assert message.qos == 1


class TestWorldState:
    """Tests for world state management."""
    
    def test_world_state_initialization(self):
        """Test world state initialization."""
        world_state = WorldState()
        
        assert len(world_state.objects) == 0
        assert len(world_state.robot_poses) == 0
    
    def test_workspace_bounds(self):
        """Test workspace boundary setting."""
        world_state = WorldState()
        
        world_state.set_workspace_bounds(
            min_bounds=[0.0, 0.0, 0.0],
            max_bounds=[5.0, 5.0, 2.0],
        )
        
        assert world_state.workspace_bounds is not None
        assert world_state.workspace_bounds["min"] == [0.0, 0.0, 0.0]
        assert world_state.workspace_bounds["max"] == [5.0, 5.0, 2.0]
    
    def test_add_remove_object(self):
        """Test adding and removing objects."""
        world_state = WorldState()
        
        obj = PhysicalObject(
            name="Box1",
            object_type="box",
            position=[1.0, 2.0, 0.5],
            dimensions=[0.3, 0.3, 0.3],
        )
        
        # Add object
        world_state.add_object(obj)
        assert len(world_state.objects) == 1
        
        # Remove object
        result = world_state.remove_object(obj.object_id)
        assert result is True
        assert len(world_state.objects) == 0
    
    def test_update_object(self):
        """Test updating object properties."""
        world_state = WorldState()
        
        obj = PhysicalObject(
            name="Box1",
            object_type="box",
            position=[1.0, 2.0, 0.5],
        )
        
        world_state.add_object(obj)
        
        # Update position
        result = world_state.update_object(
            obj.object_id,
            position=[2.0, 3.0, 0.5],
        )
        
        assert result is True
        updated_obj = world_state.get_object(obj.object_id)
        assert updated_obj.position == [2.0, 3.0, 0.5]
    
    def test_robot_pose_update(self):
        """Test robot pose updates."""
        world_state = WorldState()
        robot_id = uuid4()
        
        pose = RobotPose(
            robot_id=robot_id,
            position=[1.0, 2.0, 0.0],
            orientation=[0.0, 0.0, 0.0, 1.0],
        )
        
        world_state.update_robot_pose(pose)
        
        retrieved_pose = world_state.get_robot_pose(robot_id)
        assert retrieved_pose is not None
        assert retrieved_pose.position == [1.0, 2.0, 0.0]
    
    def test_position_in_workspace(self):
        """Test workspace boundary checking."""
        world_state = WorldState()
        
        world_state.set_workspace_bounds(
            min_bounds=[0.0, 0.0, 0.0],
            max_bounds=[5.0, 5.0, 2.0],
        )
        
        # Position inside workspace
        assert world_state.is_position_in_workspace([2.5, 2.5, 1.0]) is True
        
        # Position outside workspace
        assert world_state.is_position_in_workspace([6.0, 2.5, 1.0]) is False
        assert world_state.is_position_in_workspace([2.5, 2.5, 3.0]) is False
    
    def test_collision_detection(self):
        """Test collision detection."""
        world_state = WorldState()
        
        # Add object
        obj = PhysicalObject(
            name="Box1",
            object_type="box",
            position=[2.0, 2.0, 0.5],
            dimensions=[0.5, 0.5, 0.5],
        )
        world_state.add_object(obj)
        
        # Check collision (overlapping)
        collisions = world_state.check_collision(
            position=[2.1, 2.1, 0.5],
            dimensions=[0.3, 0.3, 0.3],
        )
        assert len(collisions) > 0
        
        # Check no collision (far away)
        collisions = world_state.check_collision(
            position=[10.0, 10.0, 0.5],
            dimensions=[0.3, 0.3, 0.3],
        )
        assert len(collisions) == 0
    
    def test_nearby_objects(self):
        """Test finding nearby objects."""
        world_state = WorldState()
        
        # Add objects
        obj1 = PhysicalObject(name="Box1", position=[1.0, 1.0, 0.0])
        obj2 = PhysicalObject(name="Box2", position=[1.5, 1.5, 0.0])
        obj3 = PhysicalObject(name="Box3", position=[10.0, 10.0, 0.0])
        
        world_state.add_object(obj1)
        world_state.add_object(obj2)
        world_state.add_object(obj3)
        
        # Find nearby objects
        nearby = world_state.get_nearby_objects([1.0, 1.0, 0.0], radius=1.0)
        
        assert len(nearby) == 2  # obj1 and obj2
    
    def test_state_snapshot(self):
        """Test getting state snapshot."""
        world_state = WorldState()
        
        # Add object and robot pose
        obj = PhysicalObject(name="Box1", position=[1.0, 2.0, 0.5])
        world_state.add_object(obj)
        
        robot_id = uuid4()
        pose = RobotPose(robot_id=robot_id, position=[0.0, 0.0, 0.0])
        world_state.update_robot_pose(pose)
        
        # Get snapshot
        snapshot = world_state.get_state_snapshot()
        
        assert "objects" in snapshot
        assert "robot_poses" in snapshot
        assert len(snapshot["objects"]) == 1
        assert len(snapshot["robot_poses"]) == 1


class TestSafetyFramework:
    """Tests for safety framework."""
    
    def test_safety_checker_initialization(self):
        """Test safety checker initialization."""
        world_state = WorldState()
        checker = SafetyChecker(world_state)
        
        # Should have default rules
        assert len(checker.rules) > 0
    
    def test_add_remove_safety_rule(self):
        """Test adding and removing safety rules."""
        world_state = WorldState()
        checker = SafetyChecker(world_state)
        
        initial_count = len(checker.rules)
        
        # Add rule
        rule = SafetyRule(
            name="Custom Rule",
            description="Test rule",
            rule_type="custom",
        )
        checker.add_rule(rule)
        
        assert len(checker.rules) == initial_count + 1
        
        # Remove rule
        result = checker.remove_rule(rule.rule_id)
        assert result is True
        assert len(checker.rules) == initial_count
    
    def test_workspace_boundary_check(self):
        """Test workspace boundary safety check."""
        world_state = WorldState()
        world_state.set_workspace_bounds(
            min_bounds=[0.0, 0.0, 0.0],
            max_bounds=[5.0, 5.0, 2.0],
        )
        
        checker = SafetyChecker(world_state)
        robot_id = uuid4()
        
        # Task inside workspace (safe)
        safe_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate",
            location=TaskLocation(x=2.5, y=2.5, z=1.0),
        )
        
        is_safe, violations = checker.check_task_safety(safe_task, robot_id)
        assert is_safe is True
        assert len(violations) == 0
        
        # Task outside workspace (unsafe)
        unsafe_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate",
            location=TaskLocation(x=10.0, y=10.0, z=1.0),
        )
        
        is_safe, violations = checker.check_task_safety(unsafe_task, robot_id)
        assert is_safe is False
        assert len(violations) > 0
    
    def test_speed_limit_check(self):
        """Test speed limit safety check."""
        world_state = WorldState()
        checker = SafetyChecker(world_state)
        robot_id = uuid4()
        
        # Task within speed limit (safe)
        safe_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate",
            location=TaskLocation(x=1.0, y=1.0, z=0.0),
            constraints=TaskConstraints(max_speed_ms=1.0),
        )
        
        is_safe, violations = checker.check_task_safety(safe_task, robot_id)
        # May have other violations, but not speed limit
        speed_violations = [v for v in violations if v.rule.rule_type == "speed_limit"]
        assert len(speed_violations) == 0
        
        # Task exceeding speed limit (unsafe)
        unsafe_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate",
            location=TaskLocation(x=1.0, y=1.0, z=0.0),
            constraints=TaskConstraints(max_speed_ms=10.0),
        )
        
        is_safe, violations = checker.check_task_safety(unsafe_task, robot_id)
        speed_violations = [v for v in violations if v.rule.rule_type == "speed_limit"]
        assert len(speed_violations) > 0
    
    def test_violation_resolution(self):
        """Test violation resolution."""
        world_state = WorldState()
        checker = SafetyChecker(world_state)
        robot_id = uuid4()
        
        # Create violation
        unsafe_task = PhysicalTask(
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description="Navigate",
            location=TaskLocation(x=1.0, y=1.0, z=0.0),
            constraints=TaskConstraints(max_speed_ms=10.0),
        )
        
        is_safe, violations = checker.check_task_safety(unsafe_task, robot_id)
        assert len(violations) > 0
        
        # Resolve violation
        violation_id = violations[0].violation_id
        result = checker.resolve_violation(violation_id, "Speed reduced to safe limit")
        
        assert result is True
        
        # Check active violations
        active = checker.get_active_violations(robot_id)
        assert violation_id not in [v.violation_id for v in active]
    
    def test_emergency_stop_check(self):
        """Test emergency stop requirement check."""
        world_state = WorldState()
        checker = SafetyChecker(world_state)
        robot_id = uuid4()
        
        # No emergency initially
        required, reason = checker.check_emergency_stop_required(robot_id)
        assert required is False
        
        # Create emergency violation manually
        from robot_integration.safety_framework import SafetyViolation
        
        emergency_violation = SafetyViolation(
            rule=SafetyRule(name="Emergency", rule_type="emergency"),
            robot_id=robot_id,
            description="Critical safety violation",
            safety_level=SafetyLevel.EMERGENCY,
        )
        checker.violations.append(emergency_violation)
        
        # Check emergency stop required
        required, reason = checker.check_emergency_stop_required(robot_id)
        assert required is True
        assert reason is not None


class TestComplianceValidator:
    """Tests for compliance validation."""
    
    def test_compliance_validator_initialization(self):
        """Test compliance validator initialization."""
        validator = ComplianceValidator()
        
        assert len(validator.required_standards) == 0
        assert len(validator.compliance_records) == 0
    
    def test_set_required_standards(self):
        """Test setting required standards."""
        validator = ComplianceValidator()
        
        standards = [
            ComplianceStandard.ISO_10218,
            ComplianceStandard.ISO_13849,
        ]
        
        validator.set_required_standards(standards)
        
        assert len(validator.required_standards) == 2
        assert ComplianceStandard.ISO_10218 in validator.required_standards
    
    def test_compliance_validation(self):
        """Test compliance validation."""
        world_state = WorldState()
        checker = SafetyChecker(world_state)
        validator = ComplianceValidator()
        
        # Set required standards
        validator.set_required_standards([ComplianceStandard.ISO_10218])
        
        # Validate (should be compliant with default rules)
        is_compliant, missing = validator.validate_compliance(checker)
        
        assert is_compliant is True
        assert len(missing) == 0
    
    def test_compliance_report(self):
        """Test compliance report generation."""
        validator = ComplianceValidator()
        
        validator.set_required_standards([ComplianceStandard.ISO_10218])
        
        # Generate report
        report = validator.generate_compliance_report()
        
        assert "required_standards" in report
        assert "compliance_checks" in report
        assert len(report["required_standards"]) == 1
