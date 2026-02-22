"""Unit tests for mission orchestrator safety guards."""

from datetime import datetime
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
            "execution_config": {
                "max_retries": 1,
                "max_concurrent_tasks": 2,
                "max_qa_cycles": 1,
                "debug_mode": False,
            },
            "max_retries": 5,
            "max_concurrent_tasks": 7,
            "max_qa_cycles": 3,
            "debug_mode": True,
        }
    )
    cfg = MissionOrchestrator._get_execution_config(mission)
    assert cfg["max_retries"] == 5
    assert cfg["max_concurrent_tasks"] == 7
    assert cfg["max_qa_cycles"] == 3
    assert cfg["debug_mode"] is True


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


@pytest.mark.asyncio
async def test_execute_task_with_retry_marks_unsuccessful_agent_response_as_failed(monkeypatch):
    mission_id = uuid4()
    owner_user_id = uuid4()
    assigned_agent_id = uuid4()
    task_id = uuid4()

    emitted_events = []
    status_updates = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "leader_config": {
                "llm_provider": "ollama",
                "llm_model": "qwen2.5:14b",
                "temperature": 0.2,
                "max_tokens": 1024,
            },
            "execution_config": {"debug_mode": True},
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Generate Word deliverable",
        acceptance_criteria="Create report.docx in workspace",
        task_metadata={"title": "Generate report.docx"},
        assigned_agent_id=assigned_agent_id,
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
        assigned_agent_id=assigned_agent_id,
        result=None,
        completed_at=None,
    )

    async def _fake_create_registered(agent_id, owner_user_id):
        return SimpleNamespace(agent_id=agent_id, name="worker-agent")

    async def _fake_execute_agent_task(agent, prompt):
        return {
            "success": False,
            "error": "python-docx import failed",
            "output": None,
        }

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

    assert success is False
    assert db_task.status == "failed"
    assert isinstance(db_task.result, dict)
    assert db_task.result.get("last_error")
    assert db_task.result.get("attempts")
    assert db_task.result["attempts"][0]["attempt"] == 1
    emitted_types = [event["event_type"] for event in emitted_events]
    assert "TASK_STARTED" in emitted_types
    assert "TASK_ATTEMPT_FAILED" in emitted_types
    assert "TASK_FAILED" in emitted_types
    assert status_updates[-1] == (assigned_agent_id, "failed")


def test_cleanup_deletes_temporary_agents(monkeypatch):
    mission_id = uuid4()
    temporary_agent_id = uuid4()
    persistent_agent_id = uuid4()

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._clarification_events = {mission_id: object()}
    orchestrator._clarification_responses = {mission_id: "ok"}
    workspace_cleanup_calls = []
    orchestrator._workspace = SimpleNamespace(
        cleanup_workspace=lambda _mission_id: workspace_cleanup_calls.append(_mission_id)
    )

    monkeypatch.setattr(
        "mission_system.mission_repository.list_mission_agents",
        lambda _mission_id: [
            SimpleNamespace(agent_id=temporary_agent_id, is_temporary=True),
            SimpleNamespace(agent_id=persistent_agent_id, is_temporary=False),
        ],
    )

    deleted_ids = []

    class _FakeRegistry:
        def delete_agent(self, agent_id):
            deleted_ids.append(agent_id)
            return True

    monkeypatch.setattr("agent_framework.agent_registry.AgentRegistry", _FakeRegistry)

    MissionOrchestrator._cleanup(orchestrator, mission_id)

    assert deleted_ids == [temporary_agent_id]
    assert workspace_cleanup_calls == [mission_id]
    assert mission_id not in orchestrator._clarification_events
    assert mission_id not in orchestrator._clarification_responses


def test_provision_temporary_worker_agent_registers_without_default_skills(monkeypatch):
    mission_id = uuid4()
    task_id = uuid4()
    owner_user_id = uuid4()
    temp_agent_id = uuid4()

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: None)

    mission = SimpleNamespace(created_by_user_id=owner_user_id)
    task_obj = SimpleNamespace(
        task_id=task_id,
        task_metadata={"title": "Implement API"},
        assigned_agent_id=None,
    )

    captured_capabilities = {}
    captured_system_prompt = {}

    class _FakeRegistry:
        def register_agent(self, **kwargs):
            captured_capabilities["value"] = kwargs.get("capabilities")
            captured_system_prompt["value"] = kwargs.get("system_prompt")
            return SimpleNamespace(agent_id=temp_agent_id, name="temp-worker")

    monkeypatch.setattr("agent_framework.agent_registry.AgentRegistry", _FakeRegistry)
    monkeypatch.setattr("mission_system.orchestrator.assign_mission_agent", lambda **kwargs: None)

    class _FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return SimpleNamespace(task_metadata={}, assigned_agent_id=None)

    class _FakeSession:
        def query(self, *args, **kwargs):
            return _FakeQuery()

    class _FakeSessionContext:
        def __enter__(self):
            return _FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("database.connection.get_db_session", lambda: _FakeSessionContext())

    llm_cfg = {
        "llm_provider": "ollama",
        "llm_model": "qwen2.5:14b",
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    result_id = MissionOrchestrator._provision_temporary_worker_agent(
        orchestrator,
        mission_id=mission_id,
        mission=mission,
        task_obj=task_obj,
        llm_cfg=llm_cfg,
    )

    assert result_id == temp_agent_id
    assert captured_capabilities["value"] == []
    assert "Task-Specific SOP" in (captured_system_prompt["value"] or "")
    assert "Task Title: Implement API" in (captured_system_prompt["value"] or "")
    assert task_obj.assigned_agent_id == temp_agent_id
    assert task_obj.task_metadata["assigned_agent_temporary"] is True


@pytest.mark.asyncio
async def test_phase_execution_resets_failed_tasks_to_pending(monkeypatch):
    mission_id = uuid4()
    failed_task = SimpleNamespace(
        task_id=uuid4(),
        status="failed",
        completed_at=datetime.utcnow(),
        dependencies=[],
        task_metadata={"title": "Rework task"},
    )
    pending_task = SimpleNamespace(
        task_id=uuid4(),
        status="pending",
        completed_at=None,
        dependencies=[],
        task_metadata={"title": "Pending task"},
    )
    db_tasks = [failed_task, pending_task]

    class _FakeQuery:
        def __init__(self, tasks):
            self._tasks = tasks

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self._tasks

    class _FakeSession:
        def __init__(self, tasks):
            self._tasks = tasks

        def query(self, *args, **kwargs):
            return _FakeQuery(self._tasks)

        def expunge(self, _obj):
            return None

    class _FakeSessionContext:
        def __init__(self, tasks):
            self._tasks = tasks

        def __enter__(self):
            return _FakeSession(self._tasks)

        def __exit__(self, exc_type, exc, tb):
            return False

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: None)

    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(
            total_tasks=2,
            mission_config={"execution_config": {"max_concurrent_tasks": 2}},
        ),
    )
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_tasks),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_topological_sort",
        staticmethod(lambda tasks: []),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_get_task_status_counts",
        staticmethod(lambda _mission_id: {"pending": 2}),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_transition",
        lambda self, _mission_id, _status: None,
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_fields",
        lambda *args, **kwargs: None,
    )

    await MissionOrchestrator._phase_execution(orchestrator, mission_id)

    assert failed_task.status == "pending"
    assert failed_task.completed_at is None
    assert pending_task.status == "pending"


@pytest.mark.asyncio
async def test_execute_task_with_retry_includes_review_feedback_in_prompt(monkeypatch):
    mission_id = uuid4()
    owner_user_id = uuid4()
    assigned_agent_id = uuid4()
    task_id = uuid4()
    captured_prompt = {}

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
        goal_text="Refine output",
        acceptance_criteria="Meet all formatting constraints",
        task_metadata={
            "title": "Refine output",
            "review_cycle_count": 2,
            "review_feedback": "Remove full-width spaces and keep exact newline formatting.",
        },
        assigned_agent_id=assigned_agent_id,
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
        assigned_agent_id=assigned_agent_id,
        result=None,
        completed_at=None,
    )

    async def _fake_create_registered(agent_id, owner_user_id):
        return SimpleNamespace(agent_id=agent_id, name="worker-agent")

    async def _fake_execute_agent_task(agent, prompt):
        captured_prompt["value"] = prompt
        return {"output": "done"}

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
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_task),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_agent_status",
        lambda mission_id, agent_id, status: None,
    )

    success = await MissionOrchestrator._execute_task_with_retry(
        orchestrator,
        mission_id=mission_id,
        mission=mission,
        task_obj=task_obj,
        max_retries=0,
    )

    assert success is True
    prompt = captured_prompt.get("value", "")
    assert "Rework Context" in prompt
    assert "Previous Review Feedback" in prompt
    assert "Remove full-width spaces" in prompt
    assert "rework cycle 2" in prompt
