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


def test_get_llm_config_temporary_worker_inherits_leader_by_default():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    mission = SimpleNamespace(
        mission_config={
            "leader_config": {
                "llm_provider": "openai",
                "llm_model": "gpt-4.1",
                "temperature": 0.4,
                "max_tokens": 6000,
            }
        }
    )
    cfg = MissionOrchestrator._get_llm_config(orchestrator, mission, "temporary_worker")
    assert cfg["llm_provider"] == "openai"
    assert cfg["llm_model"] == "gpt-4.1"
    assert cfg["temperature"] == 0.4
    assert cfg["max_tokens"] == 6000


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


@pytest.mark.asyncio
async def test_execute_task_with_retry_falls_back_to_temporary_agent(monkeypatch):
    mission_id = uuid4()
    owner_user_id = uuid4()
    unavailable_agent_id = uuid4()
    temporary_agent_id = uuid4()
    task_id = uuid4()

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: None)

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "leader_config": {
                "llm_provider": "ollama",
                "llm_model": "qwen2.5:14b",
                "temperature": 0.2,
                "max_tokens": 1024,
            }
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Implement endpoint",
        acceptance_criteria="All checks pass",
        task_metadata={"title": "Implement endpoint"},
        assigned_agent_id=unavailable_agent_id,
    )

    class _FakeQuery:
        def __init__(self, task):
            self._task = task

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self._task

    class _FakeSession:
        def __init__(self, task):
            self._task = task

        def query(self, *args, **kwargs):
            return _FakeQuery(self._task)

    class _FakeSessionContext:
        def __init__(self, task):
            self._task = task

        def __enter__(self):
            return _FakeSession(self._task)

        def __exit__(self, exc_type, exc, tb):
            return False

    db_task = SimpleNamespace(
        status="pending",
        assigned_agent_id=unavailable_agent_id,
        result=None,
        completed_at=None,
    )

    status_updates = []

    async def _fake_create_registered(agent_id, owner_user_id):
        if agent_id == temporary_agent_id:
            return SimpleNamespace(agent_id=agent_id, name="temporary-worker")
        return None

    async def _fake_execute_agent_task(agent, prompt):
        return {"output": "done"}

    provision_calls = {"count": 0}

    def _fake_provision(self, mission_id, mission, task_obj, llm_cfg):
        provision_calls["count"] += 1
        task_obj.assigned_agent_id = temporary_agent_id
        return temporary_agent_id

    monkeypatch.setattr(
        "mission_system.orchestrator.create_registered_mission_agent",
        _fake_create_registered,
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_execute_agent_task",
        staticmethod(_fake_execute_agent_task),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_provision_temporary_worker_agent",
        _fake_provision,
    )
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_task),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_agent_status",
        lambda mission_id, agent_id, status: status_updates.append((agent_id, status)),
    )

    success = await MissionOrchestrator._execute_task_with_retry(
        orchestrator,
        mission_id=mission_id,
        mission=mission,
        task_obj=task_obj,
        max_retries=0,
    )

    assert success is True
    assert provision_calls["count"] == 1
    assert db_task.status == "completed"
    assert db_task.assigned_agent_id == temporary_agent_id
    assert status_updates == [
        (temporary_agent_id, "active"),
        (temporary_agent_id, "idle"),
    ]
