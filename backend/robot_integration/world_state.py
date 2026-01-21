"""Physical world state management for robot integration.

References:
- Requirements 10: Robot Integration Preparation
- Design Section 17.3: World State Management
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class PhysicalObject:
    """Representation of a physical object in the world."""

    object_id: UUID = field(default_factory=uuid4)
    name: str = ""
    object_type: str = "unknown"  # e.g., "box", "tool", "obstacle", "workpiece"

    # Position (x, y, z in meters)
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Orientation (quaternion: x, y, z, w)
    orientation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])

    # Dimensions (length, width, height in meters)
    dimensions: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Physical properties
    mass_kg: float = 0.0
    is_movable: bool = True
    is_graspable: bool = True

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


@dataclass
class RobotPose:
    """Robot position and orientation in the world."""

    robot_id: UUID = field(default_factory=uuid4)

    # Position (x, y, z in meters)
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Orientation (quaternion: x, y, z, w)
    orientation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])

    # Joint angles (radians) for articulated robots
    joint_angles: List[float] = field(default_factory=list)

    # Velocity (linear and angular)
    linear_velocity: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    angular_velocity: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Timestamp
    timestamp: float = field(default_factory=time.time)

    # Confidence (0.0 to 1.0)
    confidence: float = 1.0


class WorldState:
    """Manages the physical world state for robot operations.

    WorldState maintains:
    - Physical objects in the environment
    - Robot poses and trajectories
    - Workspace boundaries
    - Collision detection
    - State history for debugging
    """

    def __init__(self):
        """Initialize world state manager."""
        self.objects: Dict[UUID, PhysicalObject] = {}
        self.robot_poses: Dict[UUID, RobotPose] = {}
        self.workspace_bounds: Optional[Dict[str, List[float]]] = None
        self.state_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000

        logger.info("WorldState initialized")

    def set_workspace_bounds(
        self,
        min_bounds: List[float],
        max_bounds: List[float],
    ) -> None:
        """Set workspace boundaries.

        Args:
            min_bounds: Minimum [x, y, z] coordinates
            max_bounds: Maximum [x, y, z] coordinates
        """
        self.workspace_bounds = {
            "min": min_bounds,
            "max": max_bounds,
        }
        logger.info(f"Workspace bounds set: {min_bounds} to {max_bounds}")

    def add_object(self, obj: PhysicalObject) -> None:
        """Add a physical object to the world state.

        Args:
            obj: Physical object to add
        """
        self.objects[obj.object_id] = obj
        self._record_state_change("object_added", {"object_id": str(obj.object_id)})
        logger.debug(f"Object added: {obj.name} ({obj.object_id})")

    def remove_object(self, object_id: UUID) -> bool:
        """Remove a physical object from the world state.

        Args:
            object_id: ID of object to remove

        Returns:
            True if object was removed, False if not found
        """
        if object_id in self.objects:
            del self.objects[object_id]
            self._record_state_change("object_removed", {"object_id": str(object_id)})
            logger.debug(f"Object removed: {object_id}")
            return True
        return False

    def update_object(
        self,
        object_id: UUID,
        position: Optional[List[float]] = None,
        orientation: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update object properties.

        Args:
            object_id: ID of object to update
            position: New position (optional)
            orientation: New orientation (optional)
            metadata: Additional metadata (optional)

        Returns:
            True if object was updated, False if not found
        """
        if object_id not in self.objects:
            return False

        obj = self.objects[object_id]

        if position is not None:
            obj.position = position
        if orientation is not None:
            obj.orientation = orientation
        if metadata is not None:
            obj.metadata.update(metadata)

        obj.last_updated = time.time()
        self._record_state_change("object_updated", {"object_id": str(object_id)})

        return True

    def get_object(self, object_id: UUID) -> Optional[PhysicalObject]:
        """Get object by ID.

        Args:
            object_id: Object ID

        Returns:
            PhysicalObject or None if not found
        """
        return self.objects.get(object_id)

    def get_objects_by_type(self, object_type: str) -> List[PhysicalObject]:
        """Get all objects of a specific type.

        Args:
            object_type: Type of objects to retrieve

        Returns:
            List of matching objects
        """
        return [obj for obj in self.objects.values() if obj.object_type == object_type]

    def update_robot_pose(self, pose: RobotPose) -> None:
        """Update robot pose.

        Args:
            pose: New robot pose
        """
        self.robot_poses[pose.robot_id] = pose
        self._record_state_change("robot_pose_updated", {"robot_id": str(pose.robot_id)})
        logger.debug(f"Robot pose updated: {pose.robot_id}")

    def get_robot_pose(self, robot_id: UUID) -> Optional[RobotPose]:
        """Get current robot pose.

        Args:
            robot_id: Robot ID

        Returns:
            RobotPose or None if not found
        """
        return self.robot_poses.get(robot_id)

    def is_position_in_workspace(self, position: List[float]) -> bool:
        """Check if position is within workspace bounds.

        Args:
            position: [x, y, z] position to check

        Returns:
            True if position is within bounds, False otherwise
        """
        if not self.workspace_bounds:
            # No bounds set, assume all positions are valid
            return True

        min_bounds = self.workspace_bounds["min"]
        max_bounds = self.workspace_bounds["max"]

        for i in range(3):
            if position[i] < min_bounds[i] or position[i] > max_bounds[i]:
                return False

        return True

    def check_collision(
        self,
        position: List[float],
        dimensions: List[float],
    ) -> List[PhysicalObject]:
        """Check for collisions with objects.

        Args:
            position: Center position [x, y, z]
            dimensions: [length, width, height]

        Returns:
            List of objects that would collide
        """
        colliding_objects = []

        for obj in self.objects.values():
            if self._check_box_collision(position, dimensions, obj.position, obj.dimensions):
                colliding_objects.append(obj)

        return colliding_objects

    def _check_box_collision(
        self,
        pos1: List[float],
        dim1: List[float],
        pos2: List[float],
        dim2: List[float],
    ) -> bool:
        """Check if two axis-aligned bounding boxes collide.

        Args:
            pos1: Center position of box 1
            dim1: Dimensions of box 1
            pos2: Center position of box 2
            dim2: Dimensions of box 2

        Returns:
            True if boxes collide, False otherwise
        """
        # Simple AABB collision detection
        for i in range(3):
            if abs(pos1[i] - pos2[i]) > (dim1[i] + dim2[i]) / 2:
                return False
        return True

    def get_nearby_objects(
        self,
        position: List[float],
        radius: float,
    ) -> List[PhysicalObject]:
        """Get objects within radius of position.

        Args:
            position: Center position [x, y, z]
            radius: Search radius in meters

        Returns:
            List of objects within radius
        """
        nearby = []

        for obj in self.objects.values():
            distance = self._calculate_distance(position, obj.position)
            if distance <= radius:
                nearby.append(obj)

        return nearby

    def _calculate_distance(self, pos1: List[float], pos2: List[float]) -> float:
        """Calculate Euclidean distance between two positions.

        Args:
            pos1: First position [x, y, z]
            pos2: Second position [x, y, z]

        Returns:
            Distance in meters
        """
        return sum((a - b) ** 2 for a, b in zip(pos1, pos2)) ** 0.5

    def _record_state_change(self, event_type: str, data: Dict[str, Any]) -> None:
        """Record state change in history.

        Args:
            event_type: Type of state change
            data: Event data
        """
        self.state_history.append(
            {
                "timestamp": time.time(),
                "event_type": event_type,
                "data": data,
            }
        )

        # Limit history size
        if len(self.state_history) > self.max_history_size:
            self.state_history = self.state_history[-self.max_history_size :]

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get complete world state snapshot.

        Returns:
            Dictionary with complete world state
        """
        return {
            "objects": {
                str(obj_id): {
                    "name": obj.name,
                    "type": obj.object_type,
                    "position": obj.position,
                    "orientation": obj.orientation,
                    "dimensions": obj.dimensions,
                }
                for obj_id, obj in self.objects.items()
            },
            "robot_poses": {
                str(robot_id): {
                    "position": pose.position,
                    "orientation": pose.orientation,
                    "joint_angles": pose.joint_angles,
                }
                for robot_id, pose in self.robot_poses.items()
            },
            "workspace_bounds": self.workspace_bounds,
            "timestamp": time.time(),
        }

    def clear(self) -> None:
        """Clear all world state."""
        self.objects.clear()
        self.robot_poses.clear()
        self.state_history.clear()
        logger.info("World state cleared")
