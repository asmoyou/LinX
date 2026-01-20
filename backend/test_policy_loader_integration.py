#!/usr/bin/env python
"""Integration test for policy loader functionality.

This script tests the policy loader without requiring a full database setup.
"""

import sys
sys.path.insert(0, '.')

from access_control.policy_loader import PolicyLoader
from access_control.abac import (
    ABACPolicy,
    ABACEvaluationEngine,
    PolicyEffect,
    ConditionGroup,
    Condition,
    ConditionOperator,
    LogicalOperator,
)


def test_serialization():
    """Test policy serialization and deserialization."""
    print("Testing policy serialization...")
    
    # Create a test policy
    policy = ABACPolicy(
        policy_id="test-001",
        name="Test Policy",
        description="Test policy for serialization",
        effect=PolicyEffect.ALLOW,
        resource_type="knowledge",
        actions=["read", "write"],
        conditions=ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                Condition("resource.classification", ConditionOperator.IN, ["public", "internal"])
            ]
        ),
        priority=100,
        enabled=True
    )
    
    # Create policy loader
    engine = ABACEvaluationEngine()
    loader = PolicyLoader(engine=engine)
    
    # Test serialization
    print("  - Converting policy to model...")
    model = loader._policy_to_model(policy)
    assert model.policy_id == policy.policy_id
    assert model.name == policy.name
    assert model.effect == policy.effect.value
    assert isinstance(model.conditions, dict)
    print("    ✓ Policy to model conversion successful")
    
    # Test deserialization
    print("  - Converting model back to policy...")
    restored_policy = loader._model_to_policy(model)
    assert restored_policy.policy_id == policy.policy_id
    assert restored_policy.name == policy.name
    assert restored_policy.effect == policy.effect
    assert restored_policy.resource_type == policy.resource_type
    assert len(restored_policy.actions) == len(policy.actions)
    assert restored_policy.priority == policy.priority
    print("    ✓ Model to policy conversion successful")
    
    # Test condition structure
    print("  - Verifying condition structure...")
    assert isinstance(restored_policy.conditions, ConditionGroup)
    assert restored_policy.conditions.operator == LogicalOperator.AND
    assert len(restored_policy.conditions.conditions) == 2
    
    cond1 = restored_policy.conditions.conditions[0]
    assert isinstance(cond1, Condition)
    assert cond1.attribute == "user.department"
    assert cond1.operator == ConditionOperator.EQUALS
    assert cond1.value == "engineering"
    
    cond2 = restored_policy.conditions.conditions[1]
    assert isinstance(cond2, Condition)
    assert cond2.attribute == "resource.classification"
    assert cond2.operator == ConditionOperator.IN
    assert cond2.value == ["public", "internal"]
    print("    ✓ Condition structure verified")
    
    print("✓ Serialization tests passed!\n")


def test_nested_conditions():
    """Test serialization of nested condition groups."""
    print("Testing nested condition serialization...")
    
    # Create a policy with nested conditions
    policy = ABACPolicy(
        policy_id="test-002",
        name="Complex Policy",
        description="Policy with nested conditions",
        effect=PolicyEffect.ALLOW,
        resource_type="memory",
        actions=["read"],
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
    
    engine = ABACEvaluationEngine()
    loader = PolicyLoader(engine=engine)
    
    # Serialize and deserialize
    print("  - Serializing nested conditions...")
    model = loader._policy_to_model(policy)
    restored_policy = loader._model_to_policy(model)
    
    # Verify structure
    print("  - Verifying nested structure...")
    assert restored_policy.conditions.operator == LogicalOperator.OR
    assert len(restored_policy.conditions.conditions) == 2
    
    # First condition is a nested group
    first_cond = restored_policy.conditions.conditions[0]
    assert isinstance(first_cond, ConditionGroup)
    assert first_cond.operator == LogicalOperator.AND
    assert len(first_cond.conditions) == 2
    
    # Second condition is a simple condition
    second_cond = restored_policy.conditions.conditions[1]
    assert isinstance(second_cond, Condition)
    assert second_cond.attribute == "user.role"
    
    print("    ✓ Nested condition structure verified")
    print("✓ Nested condition tests passed!\n")


def test_all_operators():
    """Test that all operators serialize correctly."""
    print("Testing all condition operators...")
    
    engine = ABACEvaluationEngine()
    loader = PolicyLoader(engine=engine)
    
    operators = [
        (ConditionOperator.EQUALS, "=="),
        (ConditionOperator.NOT_EQUALS, "!="),
        (ConditionOperator.GREATER_THAN, ">"),
        (ConditionOperator.GREATER_THAN_OR_EQUAL, ">="),
        (ConditionOperator.LESS_THAN, "<"),
        (ConditionOperator.LESS_THAN_OR_EQUAL, "<="),
        (ConditionOperator.IN, "in"),
        (ConditionOperator.NOT_IN, "not_in"),
        (ConditionOperator.CONTAINS, "contains"),
        (ConditionOperator.STARTS_WITH, "starts_with"),
        (ConditionOperator.ENDS_WITH, "ends_with"),
    ]
    
    for op_enum, op_value in operators:
        condition = Condition("test.attr", op_enum, "value")
        serialized = loader._serialize_condition(condition)
        assert serialized["operator"] == op_value
        
        deserialized = loader._deserialize_condition(serialized)
        assert deserialized.operator == op_enum
        print(f"  ✓ {op_value} operator works")
    
    print("✓ All operators tested successfully!\n")


def test_policy_evaluation():
    """Test that deserialized policies can be evaluated."""
    print("Testing policy evaluation after deserialization...")
    
    # Create and serialize a policy
    policy = ABACPolicy(
        policy_id="test-003",
        name="Evaluation Test",
        description="Test policy evaluation",
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
    
    engine = ABACEvaluationEngine()
    loader = PolicyLoader(engine=engine)
    
    # Serialize and deserialize
    model = loader._policy_to_model(policy)
    restored_policy = loader._model_to_policy(model)
    
    # Test evaluation with matching attributes
    print("  - Testing with matching attributes...")
    result = restored_policy.evaluate(
        user_attributes={"department": "engineering"},
        resource_attributes={"classification": "internal"},
        environment_attributes={},
        action="read"
    )
    assert result == PolicyEffect.ALLOW
    print("    ✓ Policy correctly allows access")
    
    # Test evaluation with non-matching attributes
    print("  - Testing with non-matching attributes...")
    result = restored_policy.evaluate(
        user_attributes={"department": "marketing"},
        resource_attributes={"classification": "internal"},
        environment_attributes={},
        action="read"
    )
    assert result is None
    print("    ✓ Policy correctly denies access")
    
    print("✓ Policy evaluation tests passed!\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Policy Loader Integration Tests")
    print("=" * 60)
    print()
    
    try:
        test_serialization()
        test_nested_conditions()
        test_all_operators()
        test_policy_evaluation()
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
