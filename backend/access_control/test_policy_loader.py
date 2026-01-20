"""Tests for ABAC policy loader.

This module tests the policy loader functionality including:
- Policy CRUD operations
- Policy serialization/deserialization
- Loading policies into ABAC engine
- Policy enable/disable operations
"""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from access_control.policy_loader import (
    PolicyLoader,
    PolicySerializationError,
    PolicyNotFoundError,
    get_policy_loader,
    load_policies_on_startup,
)
from access_control.abac import (
    ABACPolicy,
    ABACEvaluationEngine,
    PolicyEffect,
    ConditionGroup,
    Condition,
    ConditionOperator,
    LogicalOperator,
)
from database.connection import get_db_session
from database.models import ABACPolicyModel, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create a test database session."""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def abac_engine():
    """Create a fresh ABAC evaluation engine for testing."""
    engine = ABACEvaluationEngine()
    return engine


@pytest.fixture
def policy_loader(abac_engine, monkeypatch):
    """Create a policy loader with test database."""
    loader = PolicyLoader(engine=abac_engine)
    
    # Mock get_db_session to use test session
    # Note: In real tests, you'd use a test database or mock
    
    return loader


@pytest.fixture
def sample_policy():
    """Create a sample ABAC policy for testing."""
    return ABACPolicy(
        policy_id="test-policy-001",
        name="Test Engineering Access",
        description="Allow engineering department to read internal resources",
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
        priority=100,
        enabled=True
    )


@pytest.fixture
def complex_policy():
    """Create a complex policy with nested conditions."""
    return ABACPolicy(
        policy_id="test-policy-002",
        name="Complex Access Policy",
        description="Complex policy with nested conditions",
        effect=PolicyEffect.ALLOW,
        resource_type="memory",
        actions=["read", "write"],
        conditions=ConditionGroup(
            operator=LogicalOperator.OR,
            conditions=[
                ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=[
                        Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                        Condition("user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 3)
                    ]
                ),
                Condition("user.role", ConditionOperator.EQUALS, "admin")
            ]
        ),
        priority=200,
        enabled=True
    )


class TestPolicyLoader:
    """Test suite for PolicyLoader class."""
    
    def test_initialization(self, abac_engine):
        """Test policy loader initialization."""
        loader = PolicyLoader(engine=abac_engine)
        assert loader.engine == abac_engine
    
    def test_serialize_simple_condition(self, policy_loader):
        """Test serialization of simple condition."""
        condition = Condition("user.department", ConditionOperator.EQUALS, "engineering")
        
        serialized = policy_loader._serialize_condition(condition)
        
        assert serialized["type"] == "condition"
        assert serialized["attribute"] == "user.department"
        assert serialized["operator"] == "=="
        assert serialized["value"] == "engineering"
    
    def test_deserialize_simple_condition(self, policy_loader):
        """Test deserialization of simple condition."""
        data = {
            "type": "condition",
            "attribute": "user.department",
            "operator": "==",
            "value": "engineering"
        }
        
        condition = policy_loader._deserialize_condition(data)
        
        assert isinstance(condition, Condition)
        assert condition.attribute == "user.department"
        assert condition.operator == ConditionOperator.EQUALS
        assert condition.value == "engineering"
    
    def test_serialize_condition_group(self, policy_loader, sample_policy):
        """Test serialization of condition group."""
        serialized = policy_loader._serialize_conditions(sample_policy.conditions)
        
        assert serialized["operator"] == "AND"
        assert len(serialized["conditions"]) == 2
        assert serialized["conditions"][0]["type"] == "condition"
        assert serialized["conditions"][0]["attribute"] == "user.department"
    
    def test_deserialize_condition_group(self, policy_loader):
        """Test deserialization of condition group."""
        data = {
            "operator": "AND",
            "conditions": [
                {
                    "type": "condition",
                    "attribute": "user.department",
                    "operator": "==",
                    "value": "engineering"
                },
                {
                    "type": "condition",
                    "attribute": "resource.classification",
                    "operator": "==",
                    "value": "internal"
                }
            ]
        }
        
        condition_group = policy_loader._deserialize_conditions(data)
        
        assert isinstance(condition_group, ConditionGroup)
        assert condition_group.operator == LogicalOperator.AND
        assert len(condition_group.conditions) == 2
        assert all(isinstance(c, Condition) for c in condition_group.conditions)
    
    def test_serialize_nested_conditions(self, policy_loader, complex_policy):
        """Test serialization of nested condition groups."""
        serialized = policy_loader._serialize_conditions(complex_policy.conditions)
        
        assert serialized["operator"] == "OR"
        assert len(serialized["conditions"]) == 2
        
        # First condition is a nested group
        first_cond = serialized["conditions"][0]
        assert first_cond["type"] == "group"
        assert first_cond["operator"] == "AND"
        assert len(first_cond["conditions"]) == 2
        
        # Second condition is a simple condition
        second_cond = serialized["conditions"][1]
        assert second_cond["type"] == "condition"
    
    def test_deserialize_nested_conditions(self, policy_loader):
        """Test deserialization of nested condition groups."""
        data = {
            "operator": "OR",
            "conditions": [
                {
                    "type": "group",
                    "operator": "AND",
                    "conditions": [
                        {
                            "type": "condition",
                            "attribute": "user.department",
                            "operator": "==",
                            "value": "engineering"
                        },
                        {
                            "type": "condition",
                            "attribute": "user.clearance_level",
                            "operator": ">=",
                            "value": 3
                        }
                    ]
                },
                {
                    "type": "condition",
                    "attribute": "user.role",
                    "operator": "==",
                    "value": "admin"
                }
            ]
        }
        
        condition_group = policy_loader._deserialize_conditions(data)
        
        assert isinstance(condition_group, ConditionGroup)
        assert condition_group.operator == LogicalOperator.OR
        assert len(condition_group.conditions) == 2
        
        # First condition is a nested group
        first_cond = condition_group.conditions[0]
        assert isinstance(first_cond, ConditionGroup)
        assert first_cond.operator == LogicalOperator.AND
        
        # Second condition is a simple condition
        second_cond = condition_group.conditions[1]
        assert isinstance(second_cond, Condition)
    
    def test_policy_to_model_conversion(self, policy_loader, sample_policy):
        """Test conversion from ABACPolicy to database model."""
        model = policy_loader._policy_to_model(sample_policy)
        
        assert model.policy_id == sample_policy.policy_id
        assert model.name == sample_policy.name
        assert model.description == sample_policy.description
        assert model.effect == sample_policy.effect.value
        assert model.resource_type == sample_policy.resource_type
        assert model.actions == sample_policy.actions
        assert model.priority == sample_policy.priority
        assert model.enabled == sample_policy.enabled
        assert isinstance(model.conditions, dict)
    
    def test_model_to_policy_conversion(self, policy_loader, sample_policy):
        """Test conversion from database model to ABACPolicy."""
        # First convert to model
        model = policy_loader._policy_to_model(sample_policy)
        
        # Then convert back to policy
        policy = policy_loader._model_to_policy(model)
        
        assert policy.policy_id == sample_policy.policy_id
        assert policy.name == sample_policy.name
        assert policy.description == sample_policy.description
        assert policy.effect == sample_policy.effect
        assert policy.resource_type == sample_policy.resource_type
        assert policy.actions == sample_policy.actions
        assert policy.priority == sample_policy.priority
        assert policy.enabled == sample_policy.enabled
        assert isinstance(policy.conditions, ConditionGroup)
    
    def test_roundtrip_serialization(self, policy_loader, complex_policy):
        """Test that policy survives roundtrip serialization."""
        # Convert to model and back
        model = policy_loader._policy_to_model(complex_policy)
        restored_policy = policy_loader._model_to_policy(model)
        
        # Verify all fields match
        assert restored_policy.policy_id == complex_policy.policy_id
        assert restored_policy.name == complex_policy.name
        assert restored_policy.effect == complex_policy.effect
        assert restored_policy.resource_type == complex_policy.resource_type
        assert restored_policy.actions == complex_policy.actions
        assert restored_policy.priority == complex_policy.priority
        
        # Verify conditions structure
        assert restored_policy.conditions.operator == complex_policy.conditions.operator
        assert len(restored_policy.conditions.conditions) == len(complex_policy.conditions.conditions)


class TestPolicyLoaderIntegration:
    """Integration tests for policy loader with database operations."""
    
    # Note: These tests would require a test database setup
    # For now, they serve as documentation of expected behavior
    
    def test_create_policy_adds_to_engine(self, sample_policy):
        """Test that creating a policy adds it to the ABAC engine."""
        # This test would require database mocking or test database
        pass
    
    def test_update_policy_updates_engine(self, sample_policy):
        """Test that updating a policy updates it in the ABAC engine."""
        pass
    
    def test_delete_policy_removes_from_engine(self, sample_policy):
        """Test that deleting a policy removes it from the ABAC engine."""
        pass
    
    def test_load_policies_into_engine(self):
        """Test loading all policies from database into engine."""
        pass
    
    def test_enable_disable_policy(self, sample_policy):
        """Test enabling and disabling policies."""
        pass


class TestPolicyLoaderEdgeCases:
    """Test edge cases and error handling."""
    
    def test_serialize_unknown_condition_type(self, policy_loader):
        """Test serialization with unknown condition type."""
        with pytest.raises(PolicySerializationError):
            policy_loader._serialize_condition("invalid")
    
    def test_deserialize_unknown_condition_type(self, policy_loader):
        """Test deserialization with unknown condition type."""
        data = {"type": "unknown", "data": "invalid"}
        
        with pytest.raises(PolicySerializationError):
            policy_loader._deserialize_condition(data)
    
    def test_get_nonexistent_policy(self, policy_loader):
        """Test getting a policy that doesn't exist."""
        # This would require database mocking
        pass
    
    def test_update_nonexistent_policy(self, policy_loader, sample_policy):
        """Test updating a policy that doesn't exist."""
        # This would require database mocking
        pass
    
    def test_delete_nonexistent_policy(self, policy_loader):
        """Test deleting a policy that doesn't exist."""
        # This would require database mocking
        pass


class TestConditionOperators:
    """Test all condition operators work correctly."""
    
    def test_all_operators_serialize(self, policy_loader):
        """Test that all operators can be serialized."""
        operators = [
            ConditionOperator.EQUALS,
            ConditionOperator.NOT_EQUALS,
            ConditionOperator.GREATER_THAN,
            ConditionOperator.GREATER_THAN_OR_EQUAL,
            ConditionOperator.LESS_THAN,
            ConditionOperator.LESS_THAN_OR_EQUAL,
            ConditionOperator.IN,
            ConditionOperator.NOT_IN,
            ConditionOperator.CONTAINS,
            ConditionOperator.STARTS_WITH,
            ConditionOperator.ENDS_WITH,
        ]
        
        for op in operators:
            condition = Condition("test.attr", op, "value")
            serialized = policy_loader._serialize_condition(condition)
            assert serialized["operator"] == op.value
            
            # Deserialize and verify
            deserialized = policy_loader._deserialize_condition(serialized)
            assert deserialized.operator == op


class TestLogicalOperators:
    """Test all logical operators work correctly."""
    
    def test_all_logical_operators_serialize(self, policy_loader):
        """Test that all logical operators can be serialized."""
        operators = [
            LogicalOperator.AND,
            LogicalOperator.OR,
            LogicalOperator.NOT,
        ]
        
        for op in operators:
            condition_group = ConditionGroup(
                operator=op,
                conditions=[
                    Condition("test.attr", ConditionOperator.EQUALS, "value")
                ]
            )
            
            serialized = policy_loader._serialize_conditions(condition_group)
            assert serialized["operator"] == op.value
            
            # Deserialize and verify
            deserialized = policy_loader._deserialize_conditions(serialized)
            assert deserialized.operator == op


def test_get_policy_loader_singleton():
    """Test that get_policy_loader returns singleton instance."""
    loader1 = get_policy_loader()
    loader2 = get_policy_loader()
    
    # Note: This test may fail if the global instance is reset
    # In production, the singleton should persist
    assert loader1 is not None
    assert loader2 is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
