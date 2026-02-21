"""Unit tests for mission orchestrator safety guards."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from mission_system.exceptions import MissionError
from mission_system.orchestrator import MissionOrchestrator


def test_extract_binary_verdict_prefers_explicit_fail():
    text = "Summary: mostly good.\nFinal Verdict: FAIL"
    assert MissionOrchestrator._extract_binary_verdict(text) == "FAIL"


def test_extract_binary_verdict_defaults_to_fail_when_ambiguous():
    text = "No explicit verdict in this output."
    assert MissionOrchestrator._extract_binary_verdict(text) == "FAIL"


def test_get_execution_config_supports_legacy_top_level_keys():
    mission = SimpleNamespace(
        mission_config={
            "execution_config": {"max_retries": 1, "max_concurrent_tasks": 2},
            "max_retries": 5,
            "max_concurrent_tasks": 7,
        }
    )
    cfg = MissionOrchestrator._get_execution_config(mission)
    assert cfg["max_retries"] == 5
    assert cfg["max_concurrent_tasks"] == 7


def test_get_execution_config_maps_network_enabled_to_network_access():
    mission = SimpleNamespace(mission_config={"network_enabled": False})
    cfg = MissionOrchestrator._get_execution_config(mission)
    assert cfg["network_access"] is False


def test_detect_instruction_language_prefers_chinese_for_cjk_text():
    language = MissionOrchestrator._detect_instruction_language("请帮我实现任务管理页面")
    assert language == "Simplified Chinese"


def test_detect_instruction_language_defaults_to_english():
    language = MissionOrchestrator._detect_instruction_language("Build a mission planner API")
    assert language == "English"


def test_transition_allows_idempotent_target(monkeypatch):
    mission_id = uuid4()
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)

    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(status="executing"),
    )

    update_called = {"count": 0}

    def _update_status(*args, **kwargs):
        update_called["count"] += 1

    monkeypatch.setattr("mission_system.orchestrator.update_mission_status", _update_status)

    MissionOrchestrator._transition(orchestrator, mission_id, "executing")
    assert update_called["count"] == 0


@pytest.mark.asyncio
async def test_phase_complete_rejects_unfinished_tasks(monkeypatch):
    mission_id = uuid4()
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._workspace = SimpleNamespace(collect_deliverables=lambda _mission_id: [])
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: None)

    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(total_tasks=3),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_get_task_status_counts",
        staticmethod(lambda _mission_id: {"completed": 1, "pending": 2}),
    )

    update_calls = {"fields": 0, "status": 0}

    def _update_fields(*args, **kwargs):
        update_calls["fields"] += 1

    def _update_status(*args, **kwargs):
        update_calls["status"] += 1

    monkeypatch.setattr("mission_system.orchestrator.update_mission_fields", _update_fields)
    monkeypatch.setattr("mission_system.orchestrator.update_mission_status", _update_status)

    with pytest.raises(MissionError):
        await MissionOrchestrator._phase_complete(orchestrator, mission_id)

    assert update_calls["fields"] == 0
    assert update_calls["status"] == 0
