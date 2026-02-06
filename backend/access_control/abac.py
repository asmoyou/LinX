"""ABAC (Attribute-Based Access Control) attribute evaluation engine.

This module implements fine-grained permission evaluation based on user attributes,
resource attributes, and environmental conditions.

References:
- Requirements 14: User-Based Access Control (Acceptance Criteria 8)
- Design Section 8.2: Authorization Models (ABAC)
- Task 2.2.5: Create ABAC attribute evaluation engine
"""

import logging
import operator
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class PolicyEffect(str, Enum):
    """Policy evaluation result."""

    ALLOW = "allow"
    DENY = "deny"


class ConditionOperator(str, Enum):
    """Operators for attribute comparison."""

    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class LogicalOperator(str, Enum):
    """Logical operators for combining conditions."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


@dataclass
class Condition:
    """Represents a single attribute condition.

    Attributes:
        attribute: Attribute path (e.g., "user.department", "resource.classification")
        operator: Comparison operator
        value: Value to compare against

    Example:
        Condition("user.department", ConditionOperator.EQUALS, "engineering")
        Condition("user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 3)
    """

    attribute: str
    operator: ConditionOperator
    value: Any

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate this condition against a context.

        Args:
            context: Dictionary containing user, resource, and environment attributes

        Returns:
            True if condition is satisfied, False otherwise
        """
        try:
            # Extract attribute value from context
            attr_value = self._get_attribute_value(context, self.attribute)

            # Handle None values
            if attr_value is None:
                logger.debug(f"Attribute {self.attribute} not found in context")
                return False

            # Evaluate based on operator
            return self._compare(attr_value, self.operator, self.value)

        except Exception as e:
            logger.warning(
                f"Error evaluating condition {self.attribute} {self.operator} {self.value}: {e}"
            )
            return False

    def _get_attribute_value(self, context: Dict[str, Any], attribute_path: str) -> Any:
        """Extract attribute value from nested context using dot notation.

        Args:
            context: Context dictionary
            attribute_path: Dot-separated path (e.g., "user.department")

        Returns:
            Attribute value or None if not found
        """
        parts = attribute_path.split(".")
        current = context

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None

            if current is None:
                return None

        return current

    def _compare(self, attr_value: Any, op: ConditionOperator, compare_value: Any) -> bool:
        """Compare attribute value with comparison value using operator.

        Args:
            attr_value: Actual attribute value
            op: Comparison operator
            compare_value: Value to compare against

        Returns:
            Comparison result
        """
        try:
            if op == ConditionOperator.EQUALS:
                return attr_value == compare_value
            elif op == ConditionOperator.NOT_EQUALS:
                return attr_value != compare_value
            elif op == ConditionOperator.GREATER_THAN:
                return attr_value > compare_value
            elif op == ConditionOperator.GREATER_THAN_OR_EQUAL:
                return attr_value >= compare_value
            elif op == ConditionOperator.LESS_THAN:
                return attr_value < compare_value
            elif op == ConditionOperator.LESS_THAN_OR_EQUAL:
                return attr_value <= compare_value
            elif op == ConditionOperator.IN:
                return attr_value in compare_value
            elif op == ConditionOperator.NOT_IN:
                return attr_value not in compare_value
            elif op == ConditionOperator.CONTAINS:
                return compare_value in attr_value
            elif op == ConditionOperator.STARTS_WITH:
                return str(attr_value).startswith(str(compare_value))
            elif op == ConditionOperator.ENDS_WITH:
                return str(attr_value).endswith(str(compare_value))
            else:
                logger.warning(f"Unknown operator: {op}")
                return False
        except Exception as e:
            logger.warning(f"Comparison error: {e}")
            return False


@dataclass
class ConditionGroup:
    """Group of conditions combined with logical operators.

    Attributes:
        operator: Logical operator (AND, OR, NOT)
        conditions: List of conditions or nested condition groups

    Example:
        # user.department == "engineering" AND user.clearance_level >= 3
        ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                Condition("user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 3)
            ]
        )
    """

    operator: LogicalOperator
    conditions: List[Union[Condition, "ConditionGroup"]] = field(default_factory=list)

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate this condition group against a context.

        Args:
            context: Dictionary containing user, resource, and environment attributes

        Returns:
            True if condition group is satisfied, False otherwise
        """
        if not self.conditions:
            return True

        results = [cond.evaluate(context) for cond in self.conditions]

        if self.operator == LogicalOperator.AND:
            return all(results)
        elif self.operator == LogicalOperator.OR:
            return any(results)
        elif self.operator == LogicalOperator.NOT:
            # NOT operator should have exactly one condition
            return not results[0] if results else False
        else:
            logger.warning(f"Unknown logical operator: {self.operator}")
            return False


@dataclass
class ABACPolicy:
    """ABAC policy definition.

    Attributes:
        policy_id: Unique policy identifier
        name: Human-readable policy name
        description: Policy description
        effect: Policy effect (ALLOW or DENY)
        resource_type: Type of resource this policy applies to
        actions: List of actions this policy applies to
        conditions: Condition group that must be satisfied
        priority: Policy priority (higher number = higher priority)
        enabled: Whether policy is active

    Example:
        # Allow engineering department to access internal resources
        ABACPolicy(
            policy_id="policy-001",
            name="Engineering Internal Access",
            description="Allow engineering to access internal resources",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                    Condition("resource.classification", ConditionOperator.EQUALS, "internal")
                ]
            ),
            priority=100
        )
    """

    policy_id: str
    name: str
    description: str
    effect: PolicyEffect
    resource_type: str
    actions: List[str]
    conditions: ConditionGroup
    priority: int = 0
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def evaluate(
        self,
        user_attributes: Dict[str, Any],
        resource_attributes: Dict[str, Any],
        environment_attributes: Dict[str, Any],
        action: str,
    ) -> Optional[PolicyEffect]:
        """Evaluate policy against given attributes.

        Args:
            user_attributes: User attributes
            resource_attributes: Resource attributes
            environment_attributes: Environmental attributes (time, location, etc.)
            action: Action being performed

        Returns:
            PolicyEffect if policy applies, None if policy doesn't apply
        """
        # Check if policy is enabled
        if not self.enabled:
            return None

        # Check if action matches
        if action not in self.actions and "*" not in self.actions:
            return None

        # Build evaluation context
        context = {
            "user": user_attributes,
            "resource": resource_attributes,
            "environment": environment_attributes,
        }

        # Evaluate conditions
        if self.conditions.evaluate(context):
            logger.debug(
                f"Policy {self.policy_id} ({self.name}) matched with effect {self.effect}",
                extra={
                    "policy_id": self.policy_id,
                    "effect": self.effect,
                    "action": action,
                },
            )
            return self.effect

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert policy to dictionary representation."""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "effect": self.effect.value,
            "resource_type": self.resource_type,
            "actions": self.actions,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ABACEvaluationEngine:
    """ABAC policy evaluation engine.

    This engine evaluates ABAC policies to determine access decisions based on
    user attributes, resource attributes, and environmental conditions.
    """

    def __init__(self):
        """Initialize ABAC evaluation engine."""
        self.policies: Dict[str, ABACPolicy] = {}
        logger.info("ABAC evaluation engine initialized")

    def add_policy(self, policy: ABACPolicy) -> None:
        """Add a policy to the engine.

        Args:
            policy: ABAC policy to add
        """
        self.policies[policy.policy_id] = policy
        logger.info(
            f"Added ABAC policy: {policy.name}",
            extra={"policy_id": policy.policy_id, "effect": policy.effect},
        )

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy from the engine.

        Args:
            policy_id: ID of policy to remove

        Returns:
            True if policy was removed, False if not found
        """
        if policy_id in self.policies:
            policy = self.policies.pop(policy_id)
            logger.info(f"Removed ABAC policy: {policy.name}", extra={"policy_id": policy_id})
            return True
        return False

    def get_policy(self, policy_id: str) -> Optional[ABACPolicy]:
        """Get a policy by ID.

        Args:
            policy_id: Policy ID

        Returns:
            ABACPolicy if found, None otherwise
        """
        return self.policies.get(policy_id)

    def list_policies(
        self, resource_type: Optional[str] = None, enabled_only: bool = True
    ) -> List[ABACPolicy]:
        """List all policies, optionally filtered.

        Args:
            resource_type: Filter by resource type
            enabled_only: Only return enabled policies

        Returns:
            List of policies
        """
        policies = list(self.policies.values())

        if resource_type:
            policies = [p for p in policies if p.resource_type == resource_type]

        if enabled_only:
            policies = [p for p in policies if p.enabled]

        # Sort by priority (descending)
        policies.sort(key=lambda p: p.priority, reverse=True)

        return policies

    def evaluate(
        self,
        user_attributes: Dict[str, Any],
        resource_type: str,
        resource_attributes: Dict[str, Any],
        action: str,
        environment_attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate access decision based on ABAC policies.

        This method evaluates all applicable policies and returns the final decision.

        Decision logic:
        1. Evaluate all policies that match resource_type and action
        2. Sort by priority (highest first)
        3. If any DENY policy matches, deny access
        4. If any ALLOW policy matches, allow access
        5. If no policies match, deny access (default deny)

        Args:
            user_attributes: User attributes (from User.attributes JSONB field)
            resource_type: Type of resource being accessed
            resource_attributes: Resource attributes
            action: Action being performed
            environment_attributes: Environmental conditions (time, location, etc.)

        Returns:
            True if access is allowed, False if denied

        Example:
            engine = ABACEvaluationEngine()

            # Add policy
            engine.add_policy(ABACPolicy(...))

            # Evaluate access
            allowed = engine.evaluate(
                user_attributes={"department": "engineering", "clearance_level": 3},
                resource_type="knowledge",
                resource_attributes={"classification": "internal"},
                action="read",
                environment_attributes={"time": {"hour": 14}}
            )
        """
        if environment_attributes is None:
            environment_attributes = self._get_default_environment()

        # Get applicable policies
        applicable_policies = [
            p for p in self.list_policies(resource_type=resource_type, enabled_only=True)
        ]

        if not applicable_policies:
            logger.debug(
                f"No ABAC policies found for {resource_type}:{action}, denying by default",
                extra={
                    "resource_type": resource_type,
                    "action": action,
                },
            )
            return False

        # Evaluate policies in priority order
        deny_matched = False
        allow_matched = False

        for policy in applicable_policies:
            effect = policy.evaluate(
                user_attributes, resource_attributes, environment_attributes, action
            )

            if effect == PolicyEffect.DENY:
                deny_matched = True
                logger.info(
                    f"ABAC policy {policy.name} denied access",
                    extra={
                        "policy_id": policy.policy_id,
                        "resource_type": resource_type,
                        "action": action,
                    },
                )
                # Deny takes precedence, return immediately
                return False
            elif effect == PolicyEffect.ALLOW:
                allow_matched = True
                logger.debug(
                    f"ABAC policy {policy.name} allowed access",
                    extra={
                        "policy_id": policy.policy_id,
                        "resource_type": resource_type,
                        "action": action,
                    },
                )

        # If any ALLOW matched and no DENY matched, allow
        if allow_matched:
            return True

        # Default deny
        logger.debug(
            f"No ABAC policies matched for {resource_type}:{action}, denying by default",
            extra={
                "resource_type": resource_type,
                "action": action,
            },
        )
        return False

    def _get_default_environment(self) -> Dict[str, Any]:
        """Get default environment attributes.

        Returns:
            Dictionary with current time and other environmental attributes
        """
        now = datetime.utcnow()
        return {
            "time": {
                "hour": now.hour,
                "day_of_week": now.weekday(),  # 0=Monday, 6=Sunday
                "timestamp": now.isoformat(),
            }
        }

    def clear_policies(self) -> None:
        """Remove all policies from the engine."""
        count = len(self.policies)
        self.policies.clear()
        logger.info(f"Cleared {count} ABAC policies")


# Global ABAC engine instance
_abac_engine: Optional[ABACEvaluationEngine] = None


def get_abac_engine() -> ABACEvaluationEngine:
    """Get the global ABAC evaluation engine instance.

    Returns:
        ABACEvaluationEngine singleton instance
    """
    global _abac_engine
    if _abac_engine is None:
        _abac_engine = ABACEvaluationEngine()
    return _abac_engine


def evaluate_abac_access(
    user_attributes: Dict[str, Any],
    resource_type: str,
    resource_attributes: Dict[str, Any],
    action: str,
    environment_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """Convenience function to evaluate ABAC access using global engine.

    Args:
        user_attributes: User attributes
        resource_type: Type of resource
        resource_attributes: Resource attributes
        action: Action being performed
        environment_attributes: Optional environmental attributes

    Returns:
        True if access allowed, False if denied
    """
    engine = get_abac_engine()
    return engine.evaluate(
        user_attributes, resource_type, resource_attributes, action, environment_attributes
    )


# Example policy definitions for common use cases


def create_department_access_policy(
    policy_id: str, department: str, resource_type: str, actions: List[str], priority: int = 100
) -> ABACPolicy:
    """Create a policy that grants access based on department.

    Args:
        policy_id: Unique policy ID
        department: Department name
        resource_type: Resource type
        actions: List of allowed actions
        priority: Policy priority

    Returns:
        ABACPolicy instance
    """
    return ABACPolicy(
        policy_id=policy_id,
        name=f"{department.title()} Department Access",
        description=f"Allow {department} department to {', '.join(actions)} {resource_type}",
        effect=PolicyEffect.ALLOW,
        resource_type=resource_type,
        actions=actions,
        conditions=ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, department),
                Condition("resource.classification", ConditionOperator.IN, ["public", "internal"]),
            ],
        ),
        priority=priority,
    )


def create_clearance_level_policy(
    policy_id: str,
    required_clearance: int,
    resource_type: str,
    actions: List[str],
    priority: int = 200,
) -> ABACPolicy:
    """Create a policy that grants access based on clearance level.

    Args:
        policy_id: Unique policy ID
        required_clearance: Minimum clearance level required
        resource_type: Resource type
        actions: List of allowed actions
        priority: Policy priority

    Returns:
        ABACPolicy instance
    """
    return ABACPolicy(
        policy_id=policy_id,
        name=f"Clearance Level {required_clearance}+ Access",
        description=f"Allow users with clearance level {required_clearance}+ to {', '.join(actions)} {resource_type}",
        effect=PolicyEffect.ALLOW,
        resource_type=resource_type,
        actions=actions,
        conditions=ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[
                Condition(
                    "user.clearance_level",
                    ConditionOperator.GREATER_THAN_OR_EQUAL,
                    required_clearance,
                ),
                Condition(
                    "resource.required_clearance",
                    ConditionOperator.LESS_THAN_OR_EQUAL,
                    required_clearance,
                ),
            ],
        ),
        priority=priority,
    )


def build_user_attributes(user) -> Dict[str, Any]:
    """Build user attributes for ABAC evaluation, merging FK-derived department info.

    This ensures existing ABAC policies using `user.department` continue to work
    after migration from attributes JSONB to department_id FK.

    Args:
        user: User SQLAlchemy model instance

    Returns:
        Merged attributes dict with department derived from FK relationship
    """
    attrs = dict(user.attributes or {})

    # Override department from FK relationship if available
    if hasattr(user, "department") and user.department:
        attrs["department"] = user.department.code
        attrs["department_id"] = str(user.department.department_id)
        attrs["department_name"] = user.department.name

    return attrs


def create_business_hours_policy(
    policy_id: str,
    resource_type: str,
    actions: List[str],
    start_hour: int = 9,
    end_hour: int = 17,
    priority: int = 50,
) -> ABACPolicy:
    """Create a policy that restricts access to business hours.

    Args:
        policy_id: Unique policy ID
        resource_type: Resource type
        actions: List of actions to restrict
        start_hour: Business hours start (0-23)
        end_hour: Business hours end (0-23)
        priority: Policy priority

    Returns:
        ABACPolicy instance
    """
    return ABACPolicy(
        policy_id=policy_id,
        name="Business Hours Only",
        description=f"Deny access to {resource_type} outside business hours ({start_hour}:00-{end_hour}:00)",
        effect=PolicyEffect.DENY,
        resource_type=resource_type,
        actions=actions,
        conditions=ConditionGroup(
            operator=LogicalOperator.OR,
            conditions=[
                Condition("environment.time.hour", ConditionOperator.LESS_THAN, start_hour),
                Condition(
                    "environment.time.hour", ConditionOperator.GREATER_THAN_OR_EQUAL, end_hour
                ),
            ],
        ),
        priority=priority,
    )
