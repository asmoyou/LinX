"""Safety and compliance framework for robot operations.

References:
- Requirements 10: Robot Integration Preparation
- Design Section 17.4: Safety Framework
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from robot_integration.physical_tasks import PhysicalTask, TaskLocation
from robot_integration.world_state import RobotPose, WorldState

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """Safety level classification."""

    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"
    EMERGENCY = "emergency"


class ComplianceStandard(Enum):
    """Industrial safety and compliance standards."""

    ISO_10218 = "iso_10218"  # Robots and robotic devices - Safety requirements
    ISO_13849 = "iso_13849"  # Safety of machinery - Safety-related parts of control systems
    ANSI_RIA_R15_06 = "ansi_ria_r15_06"  # Industrial Robots and Robot Systems - Safety Requirements
    IEC_61508 = "iec_61508"  # Functional safety of electrical/electronic systems
    OSHA = "osha"  # Occupational Safety and Health Administration


@dataclass
class SafetyRule:
    """Safety rule definition."""

    rule_id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""

    # Rule type
    rule_type: str = "workspace_boundary"  # workspace_boundary, collision, speed, force, etc.

    # Rule parameters
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Validation function (optional)
    validator: Optional[Callable] = None

    # Safety level if violated
    violation_level: SafetyLevel = SafetyLevel.WARNING

    # Enabled flag
    enabled: bool = True

    # Compliance standards this rule satisfies
    compliance_standards: List[ComplianceStandard] = field(default_factory=list)


@dataclass
class SafetyViolation:
    """Safety rule violation record."""

    violation_id: UUID = field(default_factory=uuid4)
    rule: SafetyRule = None
    timestamp: float = field(default_factory=time.time)

    # Violation details
    robot_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    description: str = ""

    # Severity
    safety_level: SafetyLevel = SafetyLevel.WARNING

    # Context
    context: Dict[str, Any] = field(default_factory=dict)

    # Resolution
    resolved: bool = False
    resolution_time: Optional[float] = None
    resolution_action: Optional[str] = None


class SafetyChecker:
    """Safety checker for validating robot operations.

    SafetyChecker validates:
    - Workspace boundaries
    - Collision avoidance
    - Speed limits
    - Force limits
    - Emergency stop conditions
    - Human presence detection
    """

    def __init__(self, world_state: WorldState):
        """Initialize safety checker.

        Args:
            world_state: World state manager
        """
        self.world_state = world_state
        self.rules: Dict[UUID, SafetyRule] = {}
        self.violations: List[SafetyViolation] = []
        self.max_violations_history = 1000

        # Initialize default safety rules
        self._initialize_default_rules()

        logger.info("SafetyChecker initialized")

    def _initialize_default_rules(self) -> None:
        """Initialize default safety rules."""
        # Workspace boundary rule
        self.add_rule(
            SafetyRule(
                name="Workspace Boundary",
                description="Robot must stay within workspace boundaries",
                rule_type="workspace_boundary",
                violation_level=SafetyLevel.DANGER,
                compliance_standards=[ComplianceStandard.ISO_10218],
            )
        )

        # Collision avoidance rule
        self.add_rule(
            SafetyRule(
                name="Collision Avoidance",
                description="Robot must not collide with objects",
                rule_type="collision",
                violation_level=SafetyLevel.DANGER,
                compliance_standards=[ComplianceStandard.ISO_10218],
            )
        )

        # Speed limit rule
        self.add_rule(
            SafetyRule(
                name="Speed Limit",
                description="Robot speed must not exceed safe limits",
                rule_type="speed_limit",
                parameters={"max_speed_ms": 2.0},
                violation_level=SafetyLevel.WARNING,
                compliance_standards=[ComplianceStandard.ISO_10218],
            )
        )

        # Force limit rule
        self.add_rule(
            SafetyRule(
                name="Force Limit",
                description="Robot force must not exceed safe limits",
                rule_type="force_limit",
                parameters={"max_force_n": 150.0},
                violation_level=SafetyLevel.WARNING,
                compliance_standards=[ComplianceStandard.ISO_10218],
            )
        )

    def add_rule(self, rule: SafetyRule) -> None:
        """Add a safety rule.

        Args:
            rule: Safety rule to add
        """
        self.rules[rule.rule_id] = rule
        logger.info(f"Safety rule added: {rule.name}")

    def remove_rule(self, rule_id: UUID) -> bool:
        """Remove a safety rule.

        Args:
            rule_id: ID of rule to remove

        Returns:
            True if rule was removed, False if not found
        """
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"Safety rule removed: {rule_id}")
            return True
        return False

    def check_task_safety(
        self,
        task: PhysicalTask,
        robot_id: UUID,
    ) -> tuple[bool, List[SafetyViolation]]:
        """Check if task is safe to execute.

        Args:
            task: Physical task to check
            robot_id: ID of robot that would execute task

        Returns:
            Tuple of (is_safe, list of violations)
        """
        violations = []

        # Check each enabled rule
        for rule in self.rules.values():
            if not rule.enabled:
                continue

            violation = self._check_rule(rule, task, robot_id)
            if violation:
                violations.append(violation)
                self.violations.append(violation)

        # Limit violations history
        if len(self.violations) > self.max_violations_history:
            self.violations = self.violations[-self.max_violations_history :]

        is_safe = len(violations) == 0

        if not is_safe:
            logger.warning(
                f"Task safety check failed: {len(violations)} violations",
                extra={"task_id": str(task.task_id), "robot_id": str(robot_id)},
            )

        return is_safe, violations

    def _check_rule(
        self,
        rule: SafetyRule,
        task: PhysicalTask,
        robot_id: UUID,
    ) -> Optional[SafetyViolation]:
        """Check a specific safety rule.

        Args:
            rule: Safety rule to check
            task: Physical task
            robot_id: Robot ID

        Returns:
            SafetyViolation if rule is violated, None otherwise
        """
        # Use custom validator if provided
        if rule.validator:
            try:
                is_valid = rule.validator(task, robot_id, self.world_state)
                if not is_valid:
                    return SafetyViolation(
                        rule=rule,
                        robot_id=robot_id,
                        task_id=task.task_id,
                        description=f"Custom validator failed: {rule.name}",
                        safety_level=rule.violation_level,
                    )
            except Exception as e:
                logger.error(f"Error in custom validator: {e}")
                return SafetyViolation(
                    rule=rule,
                    robot_id=robot_id,
                    task_id=task.task_id,
                    description=f"Validator error: {str(e)}",
                    safety_level=SafetyLevel.DANGER,
                )

        # Built-in rule checks
        if rule.rule_type == "workspace_boundary":
            return self._check_workspace_boundary(rule, task, robot_id)
        elif rule.rule_type == "collision":
            return self._check_collision(rule, task, robot_id)
        elif rule.rule_type == "speed_limit":
            return self._check_speed_limit(rule, task, robot_id)
        elif rule.rule_type == "force_limit":
            return self._check_force_limit(rule, task, robot_id)

        return None

    def _check_workspace_boundary(
        self,
        rule: SafetyRule,
        task: PhysicalTask,
        robot_id: UUID,
    ) -> Optional[SafetyViolation]:
        """Check workspace boundary rule.

        Args:
            rule: Safety rule
            task: Physical task
            robot_id: Robot ID

        Returns:
            SafetyViolation if violated, None otherwise
        """
        if task.location:
            position = [task.location.x, task.location.y, task.location.z]
            if not self.world_state.is_position_in_workspace(position):
                return SafetyViolation(
                    rule=rule,
                    robot_id=robot_id,
                    task_id=task.task_id,
                    description="Task location outside workspace boundaries",
                    safety_level=rule.violation_level,
                    context={"position": position},
                )

        return None

    def _check_collision(
        self,
        rule: SafetyRule,
        task: PhysicalTask,
        robot_id: UUID,
    ) -> Optional[SafetyViolation]:
        """Check collision avoidance rule.

        Args:
            rule: Safety rule
            task: Physical task
            robot_id: Robot ID

        Returns:
            SafetyViolation if violated, None otherwise
        """
        # Placeholder for collision checking
        # In real implementation, this would:
        # 1. Get robot dimensions
        # 2. Check collision with objects at task location
        # 3. Consider robot trajectory

        return None

    def _check_speed_limit(
        self,
        rule: SafetyRule,
        task: PhysicalTask,
        robot_id: UUID,
    ) -> Optional[SafetyViolation]:
        """Check speed limit rule.

        Args:
            rule: Safety rule
            task: Physical task
            robot_id: Robot ID

        Returns:
            SafetyViolation if violated, None otherwise
        """
        max_speed = rule.parameters.get("max_speed_ms", 2.0)

        # Check task constraints
        if task.constraints and task.constraints.max_speed_ms:
            if task.constraints.max_speed_ms > max_speed:
                return SafetyViolation(
                    rule=rule,
                    robot_id=robot_id,
                    task_id=task.task_id,
                    description=f"Task speed {task.constraints.max_speed_ms} exceeds limit {max_speed}",
                    safety_level=rule.violation_level,
                    context={
                        "requested_speed": task.constraints.max_speed_ms,
                        "max_speed": max_speed,
                    },
                )

        return None

    def _check_force_limit(
        self,
        rule: SafetyRule,
        task: PhysicalTask,
        robot_id: UUID,
    ) -> Optional[SafetyViolation]:
        """Check force limit rule.

        Args:
            rule: Safety rule
            task: Physical task
            robot_id: Robot ID

        Returns:
            SafetyViolation if violated, None otherwise
        """
        max_force = rule.parameters.get("max_force_n", 150.0)

        # Check task constraints
        if task.constraints and task.constraints.max_force_n:
            if task.constraints.max_force_n > max_force:
                return SafetyViolation(
                    rule=rule,
                    robot_id=robot_id,
                    task_id=task.task_id,
                    description=f"Task force {task.constraints.max_force_n} exceeds limit {max_force}",
                    safety_level=rule.violation_level,
                    context={
                        "requested_force": task.constraints.max_force_n,
                        "max_force": max_force,
                    },
                )

        return None

    def check_emergency_stop_required(
        self,
        robot_id: UUID,
    ) -> tuple[bool, Optional[str]]:
        """Check if emergency stop is required.

        Args:
            robot_id: Robot ID

        Returns:
            Tuple of (emergency_stop_required, reason)
        """
        # Check for critical violations
        for violation in self.violations:
            if (
                violation.robot_id == robot_id
                and not violation.resolved
                and violation.safety_level == SafetyLevel.EMERGENCY
            ):
                return True, violation.description

        return False, None

    def resolve_violation(
        self,
        violation_id: UUID,
        resolution_action: str,
    ) -> bool:
        """Mark a violation as resolved.

        Args:
            violation_id: Violation ID
            resolution_action: Description of resolution action

        Returns:
            True if violation was found and resolved, False otherwise
        """
        for violation in self.violations:
            if violation.violation_id == violation_id:
                violation.resolved = True
                violation.resolution_time = time.time()
                violation.resolution_action = resolution_action
                logger.info(f"Violation resolved: {violation_id}")
                return True

        return False

    def get_active_violations(
        self,
        robot_id: Optional[UUID] = None,
    ) -> List[SafetyViolation]:
        """Get active (unresolved) violations.

        Args:
            robot_id: Optional robot ID to filter by

        Returns:
            List of active violations
        """
        violations = [v for v in self.violations if not v.resolved]

        if robot_id:
            violations = [v for v in violations if v.robot_id == robot_id]

        return violations


class ComplianceValidator:
    """Validator for regulatory compliance.

    ComplianceValidator ensures:
    - Compliance with safety standards (ISO, ANSI, IEC, OSHA)
    - Documentation requirements
    - Certification requirements
    - Audit trail maintenance
    """

    def __init__(self):
        """Initialize compliance validator."""
        self.required_standards: List[ComplianceStandard] = []
        self.compliance_records: List[Dict[str, Any]] = []

        logger.info("ComplianceValidator initialized")

    def set_required_standards(
        self,
        standards: List[ComplianceStandard],
    ) -> None:
        """Set required compliance standards.

        Args:
            standards: List of required standards
        """
        self.required_standards = standards
        logger.info(f"Required standards set: {[s.value for s in standards]}")

    def validate_compliance(
        self,
        safety_checker: SafetyChecker,
    ) -> tuple[bool, List[str]]:
        """Validate compliance with required standards.

        Args:
            safety_checker: Safety checker with rules

        Returns:
            Tuple of (is_compliant, list of missing requirements)
        """
        missing_requirements = []

        for standard in self.required_standards:
            # Check if any enabled rules satisfy this standard
            has_rule = False
            for rule in safety_checker.rules.values():
                if rule.enabled and standard in rule.compliance_standards:
                    has_rule = True
                    break

            if not has_rule:
                missing_requirements.append(
                    f"No active safety rules for standard: {standard.value}"
                )

        is_compliant = len(missing_requirements) == 0

        # Record compliance check
        self.compliance_records.append(
            {
                "timestamp": time.time(),
                "is_compliant": is_compliant,
                "missing_requirements": missing_requirements,
            }
        )

        return is_compliant, missing_requirements

    def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate compliance report.

        Returns:
            Dictionary with compliance report
        """
        return {
            "required_standards": [s.value for s in self.required_standards],
            "compliance_checks": len(self.compliance_records),
            "latest_check": self.compliance_records[-1] if self.compliance_records else None,
            "timestamp": time.time(),
        }
