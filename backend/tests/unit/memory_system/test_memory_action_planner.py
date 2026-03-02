"""Unit tests for MemoryActionPlanner decision matrix."""

from datetime import datetime

from memory_system.memory_action_planner import MemoryAction, MemoryActionPlanner
from memory_system.memory_interface import MemoryType
from memory_system.memory_repository import MemoryRecordData


def _make_record(record_id: int = 1) -> MemoryRecordData:
    return MemoryRecordData(
        id=record_id,
        memory_type=MemoryType.AGENT,
        content="interaction.task.latest = summarize q4 report",
        user_id="user123",
        agent_id="agent123",
        metadata={},
        timestamp=datetime.utcnow(),
    )


class TestMemoryActionPlanner:
    """Decision coverage for ADD/UPDATE/DELETE/NONE semantics."""

    def test_plan_explicit_none(self):
        planner = MemoryActionPlanner()

        decision = planner.plan(
            requested_action=MemoryAction.NONE,
            explicit_target=None,
            exact_duplicate=None,
            semantic_duplicate=None,
        )

        assert decision.action == MemoryAction.NONE
        assert decision.reason == "explicit_none"

    def test_plan_auto_add_when_no_duplicates(self):
        planner = MemoryActionPlanner()

        decision = planner.plan(
            requested_action=None,
            explicit_target=None,
            exact_duplicate=None,
            semantic_duplicate=None,
        )

        assert decision.action == MemoryAction.ADD
        assert decision.reason == "no_duplicate"

    def test_plan_auto_update_on_exact_duplicate(self):
        planner = MemoryActionPlanner()
        existing = _make_record(record_id=7)

        decision = planner.plan(
            requested_action=None,
            explicit_target=None,
            exact_duplicate=(existing, 1.0, "exact_hash"),
            semantic_duplicate=None,
        )

        assert decision.action == MemoryAction.UPDATE
        assert decision.existing_record is existing
        assert decision.reason == "exact_hash"
        assert decision.merge_reason == "exact_hash"

    def test_plan_explicit_delete_without_target_returns_none(self):
        planner = MemoryActionPlanner()

        decision = planner.plan(
            requested_action=MemoryAction.DELETE,
            explicit_target=None,
            exact_duplicate=None,
            semantic_duplicate=None,
        )

        assert decision.action == MemoryAction.NONE
        assert decision.reason == "explicit_delete_target_missing"

    def test_plan_explicit_delete_with_target(self):
        planner = MemoryActionPlanner()
        existing = _make_record(record_id=9)

        decision = planner.plan(
            requested_action=MemoryAction.DELETE,
            explicit_target=existing,
            exact_duplicate=None,
            semantic_duplicate=None,
        )

        assert decision.action == MemoryAction.DELETE
        assert decision.existing_record is existing
        assert decision.reason == "explicit_delete_target"

    def test_plan_explicit_update_falls_back_to_add_when_target_missing(self):
        planner = MemoryActionPlanner()

        decision = planner.plan(
            requested_action=MemoryAction.UPDATE,
            explicit_target=None,
            exact_duplicate=None,
            semantic_duplicate=None,
        )

        assert decision.action == MemoryAction.ADD
        assert decision.reason == "explicit_update_target_missing"
