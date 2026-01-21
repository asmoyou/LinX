"""Unit tests for ABAC (Attribute-Based Access Control) engine.

References:
- Requirements 14: User-Based Access Control
- Design Section 8.2: Authorization Models (ABAC)
- Task 2.2.5: Create ABAC attribute evaluation engine
"""

from datetime import datetime

import pytest

from access_control.abac import (
    ABACEvaluationEngine,
    ABACPolicy,
    Condition,
    ConditionGroup,
    ConditionOperator,
    LogicalOperator,
    PolicyEffect,
    create_business_hours_policy,
    create_clearance_level_policy,
    create_department_access_policy,
    evaluate_abac_access,
    get_abac_engine,
)


class TestCondition:
    """Test Condition class."""

    def test_condition_equals(self):
        """Test EQUALS operator."""
        condition = Condition("user.department", ConditionOperator.EQUALS, "engineering")
        context = {"user": {"department": "engineering"}}
        assert condition.evaluate(context) is True

        context = {"user": {"department": "sales"}}
        assert condition.evaluate(context) is False

    def test_condition_not_equals(self):
        """Test NOT_EQUALS operator."""
        condition = Condition("user.role", ConditionOperator.NOT_EQUALS, "guest")
        context = {"user": {"role": "admin"}}
        assert condition.evaluate(context) is True

        context = {"user": {"role": "guest"}}
        assert condition.evaluate(context) is False

    def test_condition_greater_than(self):
        """Test GREATER_THAN operator."""
        condition = Condition("user.clearance_level", ConditionOperator.GREATER_THAN, 2)
        context = {"user": {"clearance_level": 3}}
        assert condition.evaluate(context) is True

        context = {"user": {"clearance_level": 2}}
        assert condition.evaluate(context) is False

    def test_condition_greater_than_or_equal(self):
        """Test GREATER_THAN_OR_EQUAL operator."""
        condition = Condition("user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 3)
        context = {"user": {"clearance_level": 3}}
        assert condition.evaluate(context) is True

        context = {"user": {"clearance_level": 4}}
        assert condition.evaluate(context) is True

        context = {"user": {"clearance_level": 2}}
        assert condition.evaluate(context) is False

    def test_condition_less_than(self):
        """Test LESS_THAN operator."""
        condition = Condition("resource.required_clearance", ConditionOperator.LESS_THAN, 5)
        context = {"resource": {"required_clearance": 3}}
        assert condition.evaluate(context) is True

        context = {"resource": {"required_clearance": 5}}
        assert condition.evaluate(context) is False

    def test_condition_in(self):
        """Test IN operator."""
        condition = Condition("user.department", ConditionOperator.IN, ["engineering", "research"])
        context = {"user": {"department": "engineering"}}
        assert condition.evaluate(context) is True

        context = {"user": {"department": "sales"}}
        assert condition.evaluate(context) is False

    def test_condition_contains(self):
        """Test CONTAINS operator."""
        condition = Condition("user.projects", ConditionOperator.CONTAINS, "project-x")
        context = {"user": {"projects": ["project-x", "project-y"]}}
        assert condition.evaluate(context) is True

        context = {"user": {"projects": ["project-y", "project-z"]}}
        assert condition.evaluate(context) is False

    def test_condition_nested_attribute(self):
        """Test nested attribute access."""
        condition = Condition("user.profile.location", ConditionOperator.EQUALS, "US")
        context = {"user": {"profile": {"location": "US"}}}
        assert condition.evaluate(context) is True

    def test_condition_missing_attribute(self):
        """Test missing attribute returns False."""
        condition = Condition("user.nonexistent", ConditionOperator.EQUALS, "value")
        context = {"user": {"department": "engineering"}}
        assert condition.evaluate(context) is False


class TestConditionGroup:
    """Test ConditionGroup class."""

    def test_condition_group_and_all_true(self):
        """Test AND operator with all conditions true."""
        group = ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                Condition("user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 3),
            ],
        )
        context = {"user": {"department": "engineering", "clearance_level": 3}}
        assert group.evaluate(context) is True

    def test_condition_group_and_one_false(self):
        """Test AND operator with one condition false."""
        group = ConditionGroup(
            operator=LogicalOperator.AND,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                Condition("user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 5),
            ],
        )
        context = {"user": {"department": "engineering", "clearance_level": 3}}
        assert group.evaluate(context) is False

    def test_condition_group_or_one_true(self):
        """Test OR operator with one condition true."""
        group = ConditionGroup(
            operator=LogicalOperator.OR,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                Condition("user.department", ConditionOperator.EQUALS, "research"),
            ],
        )
        context = {"user": {"department": "engineering"}}
        assert group.evaluate(context) is True

    def test_condition_group_or_all_false(self):
        """Test OR operator with all conditions false."""
        group = ConditionGroup(
            operator=LogicalOperator.OR,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                Condition("user.department", ConditionOperator.EQUALS, "research"),
            ],
        )
        context = {"user": {"department": "sales"}}
        assert group.evaluate(context) is False

    def test_condition_group_not(self):
        """Test NOT operator."""
        group = ConditionGroup(
            operator=LogicalOperator.NOT,
            conditions=[
                Condition("user.department", ConditionOperator.EQUALS, "guest"),
            ],
        )
        context = {"user": {"department": "engineering"}}
        assert group.evaluate(context) is True

        context = {"user": {"department": "guest"}}
        assert group.evaluate(context) is False

    def test_condition_group_nested(self):
        """Test nested condition groups."""
        # (dept == engineering AND clearance >= 3) OR (dept == research AND clearance >= 2)
        group = ConditionGroup(
            operator=LogicalOperator.OR,
            conditions=[
                ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=[
                        Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                        Condition(
                            "user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 3
                        ),
                    ],
                ),
                ConditionGroup(
                    operator=LogicalOperator.AND,
                    conditions=[
                        Condition("user.department", ConditionOperator.EQUALS, "research"),
                        Condition(
                            "user.clearance_level", ConditionOperator.GREATER_THAN_OR_EQUAL, 2
                        ),
                    ],
                ),
            ],
        )

        # Should match first group
        context = {"user": {"department": "engineering", "clearance_level": 3}}
        assert group.evaluate(context) is True

        # Should match second group
        context = {"user": {"department": "research", "clearance_level": 2}}
        assert group.evaluate(context) is True

        # Should not match either group
        context = {"user": {"department": "sales", "clearance_level": 5}}
        assert group.evaluate(context) is False


class TestABACPolicy:
    """Test ABACPolicy class."""

    def test_policy_creation(self):
        """Test policy creation."""
        policy = ABACPolicy(
            policy_id="test-policy-001",
            name="Test Policy",
            description="Test policy description",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                ],
            ),
            priority=100,
        )

        assert policy.policy_id == "test-policy-001"
        assert policy.name == "Test Policy"
        assert policy.effect == PolicyEffect.ALLOW
        assert policy.enabled is True

    def test_policy_evaluate_allow(self):
        """Test policy evaluation with ALLOW effect."""
        policy = ABACPolicy(
            policy_id="test-policy-002",
            name="Engineering Access",
            description="Allow engineering to read internal knowledge",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                    Condition("resource.classification", ConditionOperator.EQUALS, "internal"),
                ],
            ),
            priority=100,
        )

        user_attrs = {"department": "engineering"}
        resource_attrs = {"classification": "internal"}
        env_attrs = {}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result == PolicyEffect.ALLOW

    def test_policy_evaluate_deny(self):
        """Test policy evaluation with DENY effect."""
        policy = ABACPolicy(
            policy_id="test-policy-003",
            name="After Hours Restriction",
            description="Deny access after hours",
            effect=PolicyEffect.DENY,
            resource_type="knowledge",
            actions=["read", "write"],
            conditions=ConditionGroup(
                operator=LogicalOperator.OR,
                conditions=[
                    Condition("environment.time.hour", ConditionOperator.LESS_THAN, 9),
                    Condition("environment.time.hour", ConditionOperator.GREATER_THAN_OR_EQUAL, 17),
                ],
            ),
            priority=200,
        )

        user_attrs = {}
        resource_attrs = {}
        env_attrs = {"time": {"hour": 20}}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result == PolicyEffect.DENY

    def test_policy_evaluate_no_match_action(self):
        """Test policy evaluation when action doesn't match."""
        policy = ABACPolicy(
            policy_id="test-policy-004",
            name="Read Only",
            description="Allow read only",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                ],
            ),
            priority=100,
        )

        user_attrs = {"department": "engineering"}
        resource_attrs = {}
        env_attrs = {}

        # Action doesn't match
        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "write")
        assert result is None

    def test_policy_evaluate_disabled(self):
        """Test disabled policy returns None."""
        policy = ABACPolicy(
            policy_id="test-policy-005",
            name="Disabled Policy",
            description="This policy is disabled",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                ],
            ),
            priority=100,
            enabled=False,
        )

        user_attrs = {"department": "engineering"}
        resource_attrs = {}
        env_attrs = {}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result is None


class TestABACEvaluationEngine:
    """Test ABACEvaluationEngine class."""

    def test_engine_initialization(self):
        """Test engine initialization."""
        engine = ABACEvaluationEngine()
        assert len(engine.policies) == 0

    def test_add_policy(self):
        """Test adding policy to engine."""
        engine = ABACEvaluationEngine()
        policy = ABACPolicy(
            policy_id="test-policy-006",
            name="Test Policy",
            description="Test",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(operator=LogicalOperator.AND, conditions=[]),
            priority=100,
        )

        engine.add_policy(policy)
        assert len(engine.policies) == 1
        assert engine.get_policy("test-policy-006") == policy

    def test_remove_policy(self):
        """Test removing policy from engine."""
        engine = ABACEvaluationEngine()
        policy = ABACPolicy(
            policy_id="test-policy-007",
            name="Test Policy",
            description="Test",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(operator=LogicalOperator.AND, conditions=[]),
            priority=100,
        )

        engine.add_policy(policy)
        assert len(engine.policies) == 1

        result = engine.remove_policy("test-policy-007")
        assert result is True
        assert len(engine.policies) == 0

        # Try removing non-existent policy
        result = engine.remove_policy("non-existent")
        assert result is False

    def test_list_policies(self):
        """Test listing policies with filters."""
        engine = ABACEvaluationEngine()

        policy1 = ABACPolicy(
            policy_id="policy-1",
            name="Policy 1",
            description="Test",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(operator=LogicalOperator.AND, conditions=[]),
            priority=100,
        )

        policy2 = ABACPolicy(
            policy_id="policy-2",
            name="Policy 2",
            description="Test",
            effect=PolicyEffect.ALLOW,
            resource_type="agents",
            actions=["read"],
            conditions=ConditionGroup(operator=LogicalOperator.AND, conditions=[]),
            priority=200,
            enabled=False,
        )

        engine.add_policy(policy1)
        engine.add_policy(policy2)

        # List all enabled policies
        policies = engine.list_policies(enabled_only=True)
        assert len(policies) == 1
        assert policies[0].policy_id == "policy-1"

        # List all policies
        policies = engine.list_policies(enabled_only=False)
        assert len(policies) == 2

        # Filter by resource type
        policies = engine.list_policies(resource_type="knowledge", enabled_only=False)
        assert len(policies) == 1
        assert policies[0].policy_id == "policy-1"

    def test_evaluate_allow(self):
        """Test evaluation with ALLOW policy."""
        engine = ABACEvaluationEngine()

        policy = ABACPolicy(
            policy_id="allow-policy",
            name="Allow Engineering",
            description="Allow engineering to read internal knowledge",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                    Condition("resource.classification", ConditionOperator.EQUALS, "internal"),
                ],
            ),
            priority=100,
        )

        engine.add_policy(policy)

        result = engine.evaluate(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={"classification": "internal"},
            action="read",
        )

        assert result is True

    def test_evaluate_deny(self):
        """Test evaluation with DENY policy."""
        engine = ABACEvaluationEngine()

        # Add ALLOW policy
        allow_policy = ABACPolicy(
            policy_id="allow-policy",
            name="Allow Engineering",
            description="Allow engineering to read knowledge",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                ],
            ),
            priority=100,
        )

        # Add DENY policy with higher priority
        deny_policy = ABACPolicy(
            policy_id="deny-policy",
            name="Deny Restricted",
            description="Deny access to restricted resources",
            effect=PolicyEffect.DENY,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("resource.classification", ConditionOperator.EQUALS, "restricted"),
                ],
            ),
            priority=200,
        )

        engine.add_policy(allow_policy)
        engine.add_policy(deny_policy)

        # DENY should take precedence
        result = engine.evaluate(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={"classification": "restricted"},
            action="read",
        )

        assert result is False

    def test_evaluate_default_deny(self):
        """Test default deny when no policies match."""
        engine = ABACEvaluationEngine()

        policy = ABACPolicy(
            policy_id="policy",
            name="Engineering Only",
            description="Allow engineering only",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                ],
            ),
            priority=100,
        )

        engine.add_policy(policy)

        # User from different department
        result = engine.evaluate(
            user_attributes={"department": "sales"},
            resource_type="knowledge",
            resource_attributes={},
            action="read",
        )

        assert result is False

    def test_evaluate_no_policies(self):
        """Test evaluation with no policies returns False."""
        engine = ABACEvaluationEngine()

        result = engine.evaluate(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={},
            action="read",
        )

        assert result is False

    def test_evaluate_with_environment(self):
        """Test evaluation with environmental conditions."""
        engine = ABACEvaluationEngine()

        policy = ABACPolicy(
            policy_id="business-hours",
            name="Business Hours Only",
            description="Deny access outside business hours",
            effect=PolicyEffect.DENY,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.OR,
                conditions=[
                    Condition("environment.time.hour", ConditionOperator.LESS_THAN, 9),
                    Condition("environment.time.hour", ConditionOperator.GREATER_THAN_OR_EQUAL, 17),
                ],
            ),
            priority=200,
        )

        engine.add_policy(policy)

        # During business hours (10 AM)
        result = engine.evaluate(
            user_attributes={},
            resource_type="knowledge",
            resource_attributes={},
            action="read",
            environment_attributes={"time": {"hour": 10}},
        )

        # No ALLOW policy, so default deny
        assert result is False

        # After business hours (8 PM)
        result = engine.evaluate(
            user_attributes={},
            resource_type="knowledge",
            resource_attributes={},
            action="read",
            environment_attributes={"time": {"hour": 20}},
        )

        # DENY policy matches
        assert result is False


class TestPolicyHelpers:
    """Test policy helper functions."""

    def test_create_department_access_policy(self):
        """Test department access policy creation."""
        policy = create_department_access_policy(
            policy_id="dept-policy",
            department="engineering",
            resource_type="knowledge",
            actions=["read", "write"],
            priority=100,
        )

        assert policy.policy_id == "dept-policy"
        assert policy.effect == PolicyEffect.ALLOW
        assert "read" in policy.actions
        assert "write" in policy.actions

        # Test evaluation
        user_attrs = {"department": "engineering"}
        resource_attrs = {"classification": "internal"}
        env_attrs = {}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result == PolicyEffect.ALLOW

    def test_create_clearance_level_policy(self):
        """Test clearance level policy creation."""
        policy = create_clearance_level_policy(
            policy_id="clearance-policy",
            required_clearance=3,
            resource_type="knowledge",
            actions=["read"],
            priority=200,
        )

        assert policy.policy_id == "clearance-policy"
        assert policy.effect == PolicyEffect.ALLOW

        # Test evaluation - user has sufficient clearance
        user_attrs = {"clearance_level": 3}
        resource_attrs = {"required_clearance": 3}
        env_attrs = {}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result == PolicyEffect.ALLOW

        # Test evaluation - user lacks clearance
        user_attrs = {"clearance_level": 2}
        resource_attrs = {"required_clearance": 3}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result is None

    def test_create_business_hours_policy(self):
        """Test business hours policy creation."""
        policy = create_business_hours_policy(
            policy_id="hours-policy",
            resource_type="knowledge",
            actions=["read", "write"],
            start_hour=9,
            end_hour=17,
            priority=50,
        )

        assert policy.policy_id == "hours-policy"
        assert policy.effect == PolicyEffect.DENY

        # Test evaluation - outside business hours
        user_attrs = {}
        resource_attrs = {}
        env_attrs = {"time": {"hour": 20}}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result == PolicyEffect.DENY

        # Test evaluation - during business hours
        env_attrs = {"time": {"hour": 14}}

        result = policy.evaluate(user_attrs, resource_attrs, env_attrs, "read")
        assert result is None


class TestGlobalEngine:
    """Test global engine functions."""

    def test_get_abac_engine_singleton(self):
        """Test global engine is singleton."""
        engine1 = get_abac_engine()
        engine2 = get_abac_engine()

        assert engine1 is engine2

    def test_evaluate_abac_access(self):
        """Test convenience function for evaluation."""
        engine = get_abac_engine()
        engine.clear_policies()

        policy = ABACPolicy(
            policy_id="test-global",
            name="Test Global",
            description="Test",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                ],
            ),
            priority=100,
        )

        engine.add_policy(policy)

        result = evaluate_abac_access(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={},
            action="read",
        )

        assert result is True


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_multi_policy_evaluation(self):
        """Test evaluation with multiple policies."""
        engine = ABACEvaluationEngine()

        # Policy 1: Allow engineering to read internal resources
        policy1 = ABACPolicy(
            policy_id="eng-internal",
            name="Engineering Internal Access",
            description="Allow engineering to read internal resources",
            effect=PolicyEffect.ALLOW,
            resource_type="knowledge",
            actions=["read"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("user.department", ConditionOperator.EQUALS, "engineering"),
                    Condition(
                        "resource.classification", ConditionOperator.IN, ["public", "internal"]
                    ),
                ],
            ),
            priority=100,
        )

        # Policy 2: Deny access to restricted resources
        policy2 = ABACPolicy(
            policy_id="deny-restricted",
            name="Deny Restricted",
            description="Deny access to restricted resources",
            effect=PolicyEffect.DENY,
            resource_type="knowledge",
            actions=["read", "write"],
            conditions=ConditionGroup(
                operator=LogicalOperator.AND,
                conditions=[
                    Condition("resource.classification", ConditionOperator.EQUALS, "restricted"),
                ],
            ),
            priority=200,
        )

        # Policy 3: Deny access outside business hours
        policy3 = ABACPolicy(
            policy_id="business-hours",
            name="Business Hours",
            description="Deny access outside business hours",
            effect=PolicyEffect.DENY,
            resource_type="knowledge",
            actions=["read", "write"],
            conditions=ConditionGroup(
                operator=LogicalOperator.OR,
                conditions=[
                    Condition("environment.time.hour", ConditionOperator.LESS_THAN, 9),
                    Condition("environment.time.hour", ConditionOperator.GREATER_THAN_OR_EQUAL, 17),
                ],
            ),
            priority=150,
        )

        engine.add_policy(policy1)
        engine.add_policy(policy2)
        engine.add_policy(policy3)

        # Scenario 1: Engineering user, internal resource, business hours - ALLOW
        result = engine.evaluate(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={"classification": "internal"},
            action="read",
            environment_attributes={"time": {"hour": 14}},
        )
        assert result is True

        # Scenario 2: Engineering user, restricted resource - DENY
        result = engine.evaluate(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={"classification": "restricted"},
            action="read",
            environment_attributes={"time": {"hour": 14}},
        )
        assert result is False

        # Scenario 3: Engineering user, internal resource, after hours - DENY
        result = engine.evaluate(
            user_attributes={"department": "engineering"},
            resource_type="knowledge",
            resource_attributes={"classification": "internal"},
            action="read",
            environment_attributes={"time": {"hour": 20}},
        )
        assert result is False

        # Scenario 4: Sales user, internal resource - DENY (no matching ALLOW policy)
        result = engine.evaluate(
            user_attributes={"department": "sales"},
            resource_type="knowledge",
            resource_attributes={"classification": "internal"},
            action="read",
            environment_attributes={"time": {"hour": 14}},
        )
        assert result is False
