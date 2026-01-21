"""Physical task type definitions.

References:
- Requirements 10: Robot Integration Preparation
- Design Section 17.2: Physical Task Types
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class PhysicalTaskType(Enum):
    """Types of physical tasks robots can perform."""
    
    # Navigation tasks
    NAVIGATE_TO_LOCATION = "navigate_to_location"
    FOLLOW_PATH = "follow_path"
    PATROL_AREA = "patrol_area"
    
    # Manipulation tasks
    PICK_OBJECT = "pick_object"
    PLACE_OBJECT = "place_object"
    MOVE_OBJECT = "move_object"
    ASSEMBLE_PARTS = "assemble_parts"
    
    # Inspection tasks
    VISUAL_INSPECTION = "visual_inspection"
    MEASURE_DIMENSION = "measure_dimension"
    SCAN_BARCODE = "scan_barcode"
    TAKE_PHOTO = "take_photo"
    
    # Delivery tasks
    DELIVER_ITEM = "deliver_item"
    COLLECT_ITEM = "collect_item"
    TRANSPORT_LOAD = "transport_load"
    
    # Maintenance tasks
    CLEAN_SURFACE = "clean_surface"
    APPLY_COATING = "apply_coating"
    WELD_JOINT = "weld_joint"
    TIGHTEN_FASTENER = "tighten_fastener"
    
    # Interaction tasks
    OPEN_DOOR = "open_door"
    PRESS_BUTTON = "press_button"
    OPERATE_SWITCH = "operate_switch"


@dataclass
class TaskLocation:
    """Physical location for task execution."""
    
    x: float  # meters
    y: float  # meters
    z: float  # meters
    
    # Orientation (quaternion)
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0
    
    # Reference frame
    frame_id: str = "world"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "position": {"x": self.x, "y": self.y, "z": self.z},
            "orientation": {"x": self.qx, "y": self.qy, "z": self.qz, "w": self.qw},
            "frame_id": self.frame_id,
        }


@dataclass
class TaskConstraints:
    """Constraints for physical task execution."""
    
    # Time constraints
    max_duration_seconds: Optional[float] = None
    deadline_timestamp: Optional[float] = None
    
    # Safety constraints
    max_force_newtons: Optional[float] = None
    max_velocity_ms: Optional[float] = None
    safety_zone_radius_m: float = 1.0
    
    # Quality constraints
    position_tolerance_m: float = 0.01
    orientation_tolerance_rad: float = 0.05
    
    # Environmental constraints
    min_temperature_c: Optional[float] = None
    max_temperature_c: Optional[float] = None
    max_humidity_percent: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "time": {
                "max_duration_seconds": self.max_duration_seconds,
                "deadline_timestamp": self.deadline_timestamp,
            },
            "safety": {
                "max_force_newtons": self.max_force_newtons,
                "max_velocity_ms": self.max_velocity_ms,
                "safety_zone_radius_m": self.safety_zone_radius_m,
            },
            "quality": {
                "position_tolerance_m": self.position_tolerance_m,
                "orientation_tolerance_rad": self.orientation_tolerance_rad,
            },
            "environmental": {
                "min_temperature_c": self.min_temperature_c,
                "max_temperature_c": self.max_temperature_c,
                "max_humidity_percent": self.max_humidity_percent,
            },
        }


@dataclass
class PhysicalTask:
    """Physical task definition."""
    
    task_id: UUID
    task_type: PhysicalTaskType
    description: str
    
    # Task parameters
    target_location: Optional[TaskLocation] = None
    target_object_id: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    
    # Constraints
    constraints: Optional[TaskConstraints] = None
    
    # Dependencies
    prerequisite_tasks: List[UUID] = None
    
    # Status
    status: str = "pending"  # pending, executing, completed, failed
    
    def __post_init__(self):
        """Initialize default values."""
        if self.parameters is None:
            self.parameters = {}
        if self.prerequisite_tasks is None:
            self.prerequisite_tasks = []
        if self.constraints is None:
            self.constraints = TaskConstraints()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "task_id": str(self.task_id),
            "task_type": self.task_type.value,
            "description": self.description,
            "target_location": self.target_location.to_dict() if self.target_location else None,
            "target_object_id": self.target_object_id,
            "parameters": self.parameters,
            "constraints": self.constraints.to_dict() if self.constraints else None,
            "prerequisite_tasks": [str(tid) for tid in self.prerequisite_tasks],
            "status": self.status,
        }
    
    @classmethod
    def create_navigation_task(
        cls,
        target_location: TaskLocation,
        description: str = "Navigate to location",
    ) -> "PhysicalTask":
        """Create a navigation task.
        
        Args:
            target_location: Target location
            description: Task description
            
        Returns:
            PhysicalTask instance
        """
        return cls(
            task_id=uuid4(),
            task_type=PhysicalTaskType.NAVIGATE_TO_LOCATION,
            description=description,
            target_location=target_location,
        )
    
    @classmethod
    def create_manipulation_task(
        cls,
        task_type: PhysicalTaskType,
        target_object_id: str,
        target_location: Optional[TaskLocation] = None,
        description: str = "Manipulate object",
    ) -> "PhysicalTask":
        """Create a manipulation task.
        
        Args:
            task_type: Type of manipulation task
            target_object_id: ID of target object
            target_location: Optional target location
            description: Task description
            
        Returns:
            PhysicalTask instance
        """
        return cls(
            task_id=uuid4(),
            task_type=task_type,
            description=description,
            target_object_id=target_object_id,
            target_location=target_location,
        )
    
    @classmethod
    def create_inspection_task(
        cls,
        task_type: PhysicalTaskType,
        target_location: TaskLocation,
        parameters: Optional[Dict[str, Any]] = None,
        description: str = "Perform inspection",
    ) -> "PhysicalTask":
        """Create an inspection task.
        
        Args:
            task_type: Type of inspection task
            target_location: Location to inspect
            parameters: Optional task parameters
            description: Task description
            
        Returns:
            PhysicalTask instance
        """
        return cls(
            task_id=uuid4(),
            task_type=task_type,
            description=description,
            target_location=target_location,
            parameters=parameters or {},
        )


class PhysicalTaskValidator:
    """Validate physical tasks before execution."""
    
    @staticmethod
    def validate_task(task: PhysicalTask) -> tuple[bool, Optional[str]]:
        """Validate a physical task.
        
        Args:
            task: Physical task to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields based on task type
        if task.task_type in [
            PhysicalTaskType.NAVIGATE_TO_LOCATION,
            PhysicalTaskType.FOLLOW_PATH,
        ]:
            if not task.target_location:
                return False, "Navigation task requires target_location"
        
        elif task.task_type in [
            PhysicalTaskType.PICK_OBJECT,
            PhysicalTaskType.PLACE_OBJECT,
            PhysicalTaskType.MOVE_OBJECT,
        ]:
            if not task.target_object_id:
                return False, "Manipulation task requires target_object_id"
        
        # Validate constraints
        if task.constraints:
            if task.constraints.max_force_newtons and task.constraints.max_force_newtons < 0:
                return False, "max_force_newtons must be positive"
            
            if task.constraints.max_velocity_ms and task.constraints.max_velocity_ms < 0:
                return False, "max_velocity_ms must be positive"
        
        return True, None
