"""ABAC policy loader and persistence.

This module provides functionality to load, store, and manage ABAC policies
in the PostgreSQL database. It bridges the gap between the database storage
and the in-memory ABAC evaluation engine.

References:
- Requirements 14: User-Based Access Control (Acceptance Criteria 8, 10, 11)
- Design Section 8.2: Authorization Models (ABAC)
- Task 2.2.6: Implement permission policy loader
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from access_control.abac import (
    ABACEvaluationEngine,
    ABACPolicy,
    Condition,
    ConditionGroup,
    ConditionOperator,
    LogicalOperator,
    PolicyEffect,
    get_abac_engine,
)
from database.connection import get_db_session
from database.models import ABACPolicyModel

logger = logging.getLogger(__name__)


class PolicySerializationError(Exception):
    """Raised when policy serialization/deserialization fails."""

    pass


class PolicyNotFoundError(Exception):
    """Raised when a policy is not found in the database."""

    pass


class PolicyLoader:
    """
    ABAC policy loader and persistence manager.

    This class provides CRUD operations for ABAC policies and manages
    synchronization between database storage and the in-memory ABAC engine.

    Features:
    - Create, read, update, delete policies
    - Load policies from database into ABAC engine
    - Serialize/deserialize policy conditions
    - Bulk policy operations
    - Policy validation

    Example:
        >>> loader = PolicyLoader()
        >>>
        >>> # Create a policy
        >>> policy = ABACPolicy(...)
        >>> loader.create_policy(policy)
        >>>
        >>> # Load all policies into engine
        >>> loader.load_policies_into_engine()
        >>>
        >>> # Update a policy
        >>> policy.enabled = False
        >>> loader.update_policy(policy)
    """

    def __init__(self, engine: Optional[ABACEvaluationEngine] = None):
        """
        Initialize policy loader.

        Args:
            engine: ABAC evaluation engine (uses global engine if not provided)
        """
        self.engine = engine or get_abac_engine()
        logger.info("PolicyLoader initialized")

    def create_policy(self, policy: ABACPolicy) -> ABACPolicy:
        """
        Create a new policy in the database.

        Args:
            policy: ABACPolicy instance to create

        Returns:
            Created ABACPolicy instance

        Raises:
            IntegrityError: If policy_id already exists
            PolicySerializationError: If policy cannot be serialized
        """
        try:
            with get_db_session() as session:
                # Serialize policy to database model
                policy_model = self._policy_to_model(policy)

                # Add to database
                session.add(policy_model)
                session.commit()

                logger.info(
                    f"Created ABAC policy: {policy.name}",
                    extra={
                        "policy_id": policy.policy_id,
                        "effect": policy.effect,
                        "resource_type": policy.resource_type,
                    },
                )

                # Add to engine if enabled
                if policy.enabled:
                    self.engine.add_policy(policy)

                return policy

        except IntegrityError as e:
            logger.error(f"Policy with ID {policy.policy_id} already exists: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create policy: {e}")
            raise PolicySerializationError(f"Failed to create policy: {e}")

    def get_policy(self, policy_id: str) -> Optional[ABACPolicy]:
        """
        Get a policy by ID from the database.

        Args:
            policy_id: Policy ID

        Returns:
            ABACPolicy instance if found, None otherwise
        """
        try:
            with get_db_session() as session:
                policy_model = session.query(ABACPolicyModel).filter_by(policy_id=policy_id).first()

                if policy_model is None:
                    return None

                # Deserialize to ABACPolicy
                policy = self._model_to_policy(policy_model)
                return policy

        except Exception as e:
            logger.error(f"Failed to get policy {policy_id}: {e}")
            return None

    def list_policies(
        self,
        resource_type: Optional[str] = None,
        enabled_only: bool = False,
        effect: Optional[PolicyEffect] = None,
    ) -> List[ABACPolicy]:
        """
        List policies from the database with optional filtering.

        Args:
            resource_type: Filter by resource type
            enabled_only: Only return enabled policies
            effect: Filter by policy effect (ALLOW or DENY)

        Returns:
            List of ABACPolicy instances
        """
        try:
            with get_db_session() as session:
                query = session.query(ABACPolicyModel)

                # Apply filters
                if resource_type:
                    query = query.filter_by(resource_type=resource_type)

                if enabled_only:
                    query = query.filter_by(enabled=True)

                if effect:
                    query = query.filter_by(effect=effect.value)

                # Order by priority (descending)
                query = query.order_by(ABACPolicyModel.priority.desc())

                policy_models = query.all()

                # Deserialize to ABACPolicy instances
                policies = [self._model_to_policy(model) for model in policy_models]

                return policies

        except Exception as e:
            logger.error(f"Failed to list policies: {e}")
            return []

    def update_policy(self, policy: ABACPolicy) -> ABACPolicy:
        """
        Update an existing policy in the database.

        Args:
            policy: ABACPolicy instance with updated values

        Returns:
            Updated ABACPolicy instance

        Raises:
            PolicyNotFoundError: If policy doesn't exist
            PolicySerializationError: If policy cannot be serialized
        """
        try:
            with get_db_session() as session:
                # Find existing policy
                policy_model = (
                    session.query(ABACPolicyModel).filter_by(policy_id=policy.policy_id).first()
                )

                if policy_model is None:
                    raise PolicyNotFoundError(f"Policy {policy.policy_id} not found")

                # Update fields
                policy_model.name = policy.name
                policy_model.description = policy.description
                policy_model.effect = policy.effect.value
                policy_model.resource_type = policy.resource_type
                policy_model.actions = policy.actions
                policy_model.conditions = self._serialize_conditions(policy.conditions)
                policy_model.priority = policy.priority
                policy_model.enabled = policy.enabled
                policy_model.updated_at = datetime.utcnow()

                session.commit()

                logger.info(
                    f"Updated ABAC policy: {policy.name}",
                    extra={
                        "policy_id": policy.policy_id,
                        "enabled": policy.enabled,
                    },
                )

                # Update in engine
                self.engine.remove_policy(policy.policy_id)
                if policy.enabled:
                    self.engine.add_policy(policy)

                return policy

        except PolicyNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to update policy: {e}")
            raise PolicySerializationError(f"Failed to update policy: {e}")

    def delete_policy(self, policy_id: str) -> bool:
        """
        Delete a policy from the database.

        Args:
            policy_id: Policy ID to delete

        Returns:
            True if policy was deleted, False if not found
        """
        try:
            with get_db_session() as session:
                policy_model = session.query(ABACPolicyModel).filter_by(policy_id=policy_id).first()

                if policy_model is None:
                    logger.warning(f"Policy {policy_id} not found for deletion")
                    return False

                session.delete(policy_model)
                session.commit()

                logger.info(
                    f"Deleted ABAC policy: {policy_model.name}", extra={"policy_id": policy_id}
                )

                # Remove from engine
                self.engine.remove_policy(policy_id)

                return True

        except Exception as e:
            logger.error(f"Failed to delete policy {policy_id}: {e}")
            return False

    def load_policies_into_engine(self, clear_existing: bool = True) -> int:
        """
        Load all enabled policies from database into the ABAC engine.

        This method is typically called during application startup to
        initialize the ABAC engine with policies from the database.

        Args:
            clear_existing: Whether to clear existing policies in engine first

        Returns:
            Number of policies loaded
        """
        try:
            if clear_existing:
                self.engine.clear_policies()
                logger.info("Cleared existing policies from ABAC engine")

            # Load all enabled policies
            policies = self.list_policies(enabled_only=True)

            # Add to engine
            for policy in policies:
                self.engine.add_policy(policy)

            logger.info(
                f"Loaded {len(policies)} ABAC policies into engine",
                extra={"policy_count": len(policies)},
            )

            return len(policies)

        except Exception as e:
            logger.error(f"Failed to load policies into engine: {e}")
            return 0

    def reload_policies(self) -> int:
        """
        Reload all policies from database into engine.

        This is a convenience method that clears and reloads all policies.

        Returns:
            Number of policies loaded
        """
        return self.load_policies_into_engine(clear_existing=True)

    def enable_policy(self, policy_id: str) -> bool:
        """
        Enable a policy.

        Args:
            policy_id: Policy ID to enable

        Returns:
            True if successful, False otherwise
        """
        policy = self.get_policy(policy_id)
        if policy is None:
            return False

        policy.enabled = True
        try:
            self.update_policy(policy)
            return True
        except Exception:
            return False

    def disable_policy(self, policy_id: str) -> bool:
        """
        Disable a policy.

        Args:
            policy_id: Policy ID to disable

        Returns:
            True if successful, False otherwise
        """
        policy = self.get_policy(policy_id)
        if policy is None:
            return False

        policy.enabled = False
        try:
            self.update_policy(policy)
            return True
        except Exception:
            return False

    def _policy_to_model(self, policy: ABACPolicy) -> ABACPolicyModel:
        """
        Convert ABACPolicy to database model.

        Args:
            policy: ABACPolicy instance

        Returns:
            ABACPolicyModel instance
        """
        return ABACPolicyModel(
            policy_id=policy.policy_id,
            name=policy.name,
            description=policy.description,
            effect=policy.effect.value,
            resource_type=policy.resource_type,
            actions=policy.actions,
            conditions=self._serialize_conditions(policy.conditions),
            priority=policy.priority,
            enabled=policy.enabled,
            created_at=policy.created_at or datetime.utcnow(),
            updated_at=policy.updated_at or datetime.utcnow(),
        )

    def _model_to_policy(self, model: ABACPolicyModel) -> ABACPolicy:
        """
        Convert database model to ABACPolicy.

        Args:
            model: ABACPolicyModel instance

        Returns:
            ABACPolicy instance
        """
        return ABACPolicy(
            policy_id=model.policy_id,
            name=model.name,
            description=model.description,
            effect=PolicyEffect(model.effect),
            resource_type=model.resource_type,
            actions=model.actions,
            conditions=self._deserialize_conditions(model.conditions),
            priority=model.priority,
            enabled=model.enabled,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _serialize_conditions(self, condition_group: ConditionGroup) -> Dict[str, Any]:
        """
        Serialize ConditionGroup to JSON-compatible dict.

        Args:
            condition_group: ConditionGroup instance

        Returns:
            Dictionary representation
        """
        return {
            "operator": condition_group.operator.value,
            "conditions": [self._serialize_condition(cond) for cond in condition_group.conditions],
        }

    def _serialize_condition(self, condition) -> Dict[str, Any]:
        """
        Serialize a Condition or ConditionGroup to dict.

        Args:
            condition: Condition or ConditionGroup instance

        Returns:
            Dictionary representation
        """
        if isinstance(condition, Condition):
            return {
                "type": "condition",
                "attribute": condition.attribute,
                "operator": condition.operator.value,
                "value": condition.value,
            }
        elif isinstance(condition, ConditionGroup):
            return {
                "type": "group",
                "operator": condition.operator.value,
                "conditions": [self._serialize_condition(c) for c in condition.conditions],
            }
        else:
            raise PolicySerializationError(f"Unknown condition type: {type(condition)}")

    def _deserialize_conditions(self, data: Dict[str, Any]) -> ConditionGroup:
        """
        Deserialize dict to ConditionGroup.

        Args:
            data: Dictionary representation

        Returns:
            ConditionGroup instance
        """
        operator = LogicalOperator(data["operator"])
        conditions = [self._deserialize_condition(cond_data) for cond_data in data["conditions"]]
        return ConditionGroup(operator=operator, conditions=conditions)

    def _deserialize_condition(self, data: Dict[str, Any]):
        """
        Deserialize dict to Condition or ConditionGroup.

        Args:
            data: Dictionary representation

        Returns:
            Condition or ConditionGroup instance
        """
        cond_type = data.get("type", "condition")

        if cond_type == "condition":
            return Condition(
                attribute=data["attribute"],
                operator=ConditionOperator(data["operator"]),
                value=data["value"],
            )
        elif cond_type == "group":
            operator = LogicalOperator(data["operator"])
            conditions = [self._deserialize_condition(c) for c in data["conditions"]]
            return ConditionGroup(operator=operator, conditions=conditions)
        else:
            raise PolicySerializationError(f"Unknown condition type: {cond_type}")


# Global policy loader instance
_policy_loader: Optional[PolicyLoader] = None


def get_policy_loader() -> PolicyLoader:
    """
    Get the global policy loader instance.

    Returns:
        PolicyLoader singleton instance
    """
    global _policy_loader
    if _policy_loader is None:
        _policy_loader = PolicyLoader()
    return _policy_loader


def load_policies_on_startup() -> int:
    """
    Load policies from database into ABAC engine on application startup.

    This function should be called during application initialization.

    Returns:
        Number of policies loaded
    """
    loader = get_policy_loader()
    count = loader.load_policies_into_engine(clear_existing=True)
    logger.info(f"Startup: Loaded {count} ABAC policies")
    return count
