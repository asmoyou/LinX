"""Unit tests for mission orchestrator safety guards."""

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List
from uuid import uuid4

import pytest

from agent_framework.runtime_policy import ExecutionProfile
from mission_system.exceptions import MissionError
from mission_system.orchestrator import MissionOrchestrator


def test_extract_binary_verdict_prefers_explicit_fail():
    text = "Summary: mostly good.\nFinal Verdict: FAIL"
    assert MissionOrchestrator._extract_binary_verdict(text) == "FAIL"


def test_extract_binary_verdict_defaults_to_fail_when_ambiguous():
    text = "No explicit verdict in this output."
    assert MissionOrchestrator._extract_binary_verdict(text) == "FAIL"


def test_extract_binary_verdict_handles_leading_pass_with_long_body():
    body_lines = "\n".join([f"Detail line {i}" for i in range(1, 30)])
    text = f"PASS\n\n{body_lines}"
    assert MissionOrchestrator._extract_binary_verdict(text) == "PASS"


def test_extract_binary_verdict_ignores_instruction_noise():
    text = (
        "Respond with PASS or FAIL followed by your reasoning.\n"
        "If FAIL, provide specific actionable feedback.\n"
        "No explicit verdict in this output."
    )
    assert MissionOrchestrator._extract_binary_verdict(text) == "FAIL"


def test_extract_structured_binary_verdict_prefers_json_verdict():
    text = """
Respond with PASS or FAIL followed by your reasoning.
```json
{
  "verdict": "PASS",
  "summary": "All acceptance criteria are satisfied."
}
```
"""
    assert MissionOrchestrator._extract_structured_binary_verdict(text) == "PASS"


def test_extract_structured_binary_verdict_supports_nested_audit_report():
    text = """
```json
{
  "audit_report": {
    "verdict": "FAILED",
    "summary": "Critical acceptance criteria are missing."
  }
}
```
"""
    assert MissionOrchestrator._extract_structured_binary_verdict(text) == "FAIL"


def test_extract_qa_audit_details_parses_summary_and_issues():
    text = """
Summary: Deliverable has format mismatch.
- Issue: Missing required heading.
- 风险: 文档末尾缺少结论段。
Final Verdict: FAIL
"""
    details = MissionOrchestrator._extract_qa_audit_details(text)
    assert "format mismatch" in details["summary"]
    assert details["issues_count"] >= 2
    assert any("Missing required heading" in issue for issue in details["issues"])


def test_extract_qa_audit_details_handles_pass_json_payload():
    text = """
```json
{
  "summary": "All deliverables meet requirements.",
  "details": "No critical issues found.",
  "verdict": "PASS"
}
```
"""
    details = MissionOrchestrator._extract_qa_audit_details(text, verdict="PASS")
    assert details["summary"] == "All deliverables meet requirements."
    assert details["issues_count"] == 0
    assert details["issues"] == []


def test_extract_qa_audit_details_handles_issue_object_payload():
    text = """
```json
{
  "summary": "```json",
  "issues": [
    {"issue": "Missing required output filename."},
    {"description": "Body line spacing does not match 1.5x requirement."}
  ],
  "verdict": "FAIL"
}
```
"""
    details = MissionOrchestrator._extract_qa_audit_details(text, verdict="FAIL")
    assert details["issues_count"] == 2
    assert any("Missing required output filename" in issue for issue in details["issues"])
    assert any("line spacing" in issue for issue in details["issues"])
    assert details["summary"] != "```json"


def test_extract_qa_audit_details_handles_nested_audit_report_payload():
    text = """
```json
{
  "audit_report": {
    "verdict": "FAIL",
    "findings": [
      {"category": "Correctness", "issue": "Output filename does not match requirement."},
      {"category": "Quality", "issue": "Poem meter has tone-pattern violations."}
    ],
    "recommendations": ["Rename the file to the required filename."]
  }
}
```
"""
    details = MissionOrchestrator._extract_qa_audit_details(text, verdict="FAIL")
    assert details["report_format"] == "audit_report_json"
    assert details["issues_count"] == 2
    assert any("filename" in issue for issue in details["issues"])
    assert any("tone-pattern" in issue for issue in details["issues"])
    assert details["summary"] != '"audit_report": {'
    assert details["recommendations"] == ["Rename the file to the required filename."]


def test_build_qa_verdict_event_data_has_stable_schema():
    payload = MissionOrchestrator._build_qa_verdict_event_data(
        verdict="fail",
        qa_details={
            "summary": "Deliverable does not satisfy naming requirement.",
            "issues": ["Filename mismatch."],
            "issues_count": 1,
            "recommendations": ["Rename output file."],
            "report_format": "audit_report_json",
        },
    )
    assert payload["schema_version"] == "qa_verdict.v2"
    assert payload["verdict"] == "FAIL"
    assert payload["summary"] == "Deliverable does not satisfy naming requirement."
    assert payload["issues_count"] == 1
    assert payload["issues"] == ["Filename mismatch."]
    assert payload["recommendations"] == ["Rename output file."]
    assert payload["report_format"] == "audit_report_json"


def test_build_qa_rework_feedback_contains_findings_and_recommendations():
    feedback = MissionOrchestrator._build_qa_rework_feedback(
        {
            "summary": "QA found critical output mismatches.",
            "issues": ["Filename mismatch.", "Poem meter violation."],
            "recommendations": [
                "Rename the output file.",
                "Regenerate the poem with corrected tone.",
            ],
        }
    )
    assert "QA audit failed." in feedback
    assert "Summary: QA found critical output mismatches." in feedback
    assert "1. Filename mismatch." in feedback
    assert "2. Poem meter violation." in feedback
    assert "Recommended fixes:" in feedback


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


def test_build_system_time_context_contains_utc_and_local_timestamps():
    context = MissionOrchestrator._build_system_time_context()
    assert context["utc_now"].endswith("Z")
    assert context["local_timezone"]
    assert len(context["local_date"]) == 10
    datetime.fromisoformat(context["utc_now"].replace("Z", "+00:00"))
    datetime.fromisoformat(context["local_now"])


def test_render_system_time_prompt_block_contains_authoritative_hint():
    prompt_block = MissionOrchestrator._render_system_time_prompt_block(
        {
            "utc_now": "2026-02-25T12:34:56Z",
            "local_now": "2026-02-25T20:34:56+08:00",
            "local_timezone": "CST",
            "local_date": "2026-02-25",
        }
    )
    assert "## System Time Context" in prompt_block
    assert "UTC now: 2026-02-25T12:34:56Z" in prompt_block
    assert "Local timezone: CST" in prompt_block
    assert "authoritative current time" in prompt_block


def test_render_execution_plan_markdown_includes_planning_time_context():
    markdown = MissionOrchestrator._render_execution_plan_markdown(
        mission=SimpleNamespace(title="Demo Mission"),
        task_plan_rows=[],
        role_assignments={},
        assignment_summary={
            "assigned_existing": 0,
            "temporary_fallback_pending": 0,
            "unassigned": 0,
        },
        planning_time_context={
            "utc_now": "2026-02-25T12:34:56Z",
            "local_now": "2026-02-25T20:34:56+08:00",
            "local_timezone": "CST",
            "local_date": "2026-02-25",
        },
    )
    assert "- Planner system time (UTC): 2026-02-25T12:34:56Z" in markdown
    assert "- Planner system timezone: CST" in markdown
    assert "- Planner local date: 2026-02-25" in markdown


def test_build_text_signature_is_stable_for_equivalent_content():
    a = MissionOrchestrator._build_text_signature("hello\nworld")
    b = MissionOrchestrator._build_text_signature("hello\nworld")
    c = MissionOrchestrator._build_text_signature("hello world")
    assert a == b
    assert a != c


def test_extract_agent_output_prefers_reason_field_when_error_missing():
    with pytest.raises(RuntimeError) as exc_info:
        MissionOrchestrator._extract_agent_output(
            {"success": False, "reason": "model declined request"},
            "Task execution failed",
        )

    assert "model declined request" in str(exc_info.value)


def test_extract_agent_output_reports_payload_keys_when_error_details_absent():
    with pytest.raises(RuntimeError) as exc_info:
        MissionOrchestrator._extract_agent_output(
            {"success": False, "foo": "bar"},
            "Task execution failed",
        )

    assert "payload keys" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_agent_task_without_container_uses_basic_call():
    class _FakeAgent:
        def __init__(self):
            self.calls = []

        def execute_task(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"success": True, "output": "ok"}

    agent = _FakeAgent()
    result = await MissionOrchestrator._execute_agent_task(agent, "ping")

    assert result["success"] is True
    assert len(agent.calls) == 1
    args, kwargs = agent.calls[0]
    assert args == ()
    assert kwargs["task_description"] == "ping"
    assert kwargs["execution_profile"] == ExecutionProfile.MISSION_CONTROL


@pytest.mark.asyncio
async def test_execute_agent_task_with_container_enables_streaming_mode():
    class _FakeAgent:
        def __init__(self):
            self.calls = []

        def execute_task(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"success": True, "output": "ok"}

    agent = _FakeAgent()
    result = await MissionOrchestrator._execute_agent_task(
        agent,
        "ping",
        container_id="container-123",
    )

    assert result["success"] is True
    assert len(agent.calls) == 1
    args, kwargs = agent.calls[0]
    assert args == ()
    assert kwargs["task_description"] == "ping"
    assert kwargs["container_id"] == "container-123"
    assert kwargs["execution_profile"] == ExecutionProfile.MISSION_CONTROL
    assert "stream_callback" not in kwargs


@pytest.mark.asyncio
async def test_execute_agent_task_without_container_passes_execution_context():
    class _FakeAgent:
        def __init__(self):
            self.calls = []

        def execute_task(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"success": True, "output": "ok"}

    agent = _FakeAgent()
    exec_context = {"agent_memories": ["prior context"]}
    result = await MissionOrchestrator._execute_agent_task(
        agent,
        "ping",
        execution_context=exec_context,
    )

    assert result["success"] is True
    assert len(agent.calls) == 1
    args, kwargs = agent.calls[0]
    assert args == ()
    assert kwargs["task_description"] == "ping"
    assert kwargs["context"] == {
        "agent_memories": ["prior context"],
        "execution_context_tag": "mission_run",
    }
    assert exec_context == {"agent_memories": ["prior context"]}
    assert kwargs["execution_profile"] == ExecutionProfile.MISSION_CONTROL


@pytest.mark.asyncio
async def test_execute_agent_task_passes_session_workdir():
    class _FakeAgent:
        def __init__(self):
            self.calls = []

        def execute_task(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"success": True, "output": "ok"}

    agent = _FakeAgent()
    workdir = Path("/tmp/mission-workspace-test")
    result = await MissionOrchestrator._execute_agent_task(
        agent,
        "ping",
        session_workdir=workdir,
    )

    assert result["success"] is True
    assert len(agent.calls) == 1
    args, kwargs = agent.calls[0]
    assert args == ()
    assert kwargs["task_description"] == "ping"
    assert kwargs["session_workdir"] == workdir
    assert kwargs["execution_profile"] == ExecutionProfile.MISSION_CONTROL


@pytest.mark.asyncio
async def test_execute_agent_task_legacy_fallback_uses_stream_callback(monkeypatch):
    class _FakeAgent:
        def __init__(self):
            self.calls = []

        def execute_task(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"success": True, "output": "ok"}

    monkeypatch.setenv("MISSION_TASK_UNIFIED_RUNTIME_ENABLED", "false")

    agent = _FakeAgent()
    result = await MissionOrchestrator._execute_agent_task(
        agent,
        "ping",
        container_id="container-legacy",
    )

    assert result["success"] is True
    assert len(agent.calls) == 1
    args, kwargs = agent.calls[0]
    assert args == ()
    assert kwargs["task_description"] == "ping"
    assert kwargs["container_id"] == "container-legacy"
    assert callable(kwargs["stream_callback"])


@pytest.mark.asyncio
async def test_execute_phase_prompt_with_retry_recreates_errored_agent():
    class _FakeStatus:
        def __init__(self, value: str):
            self.value = value

    class _FakeAgent:
        def __init__(self, name: str):
            self.name = name
            self.status = _FakeStatus("active")

    emitted_events = []
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    initial_agent = _FakeAgent("initial-supervisor")
    replacement_agent = _FakeAgent("replacement-supervisor")
    execute_calls = {"count": 0}

    async def _fake_execute_agent_task(agent, _prompt, **kwargs):
        execute_calls["count"] += 1
        assert kwargs.get("execution_profile") == ExecutionProfile.MISSION_CONTROL
        if execute_calls["count"] == 1:
            agent.status = _FakeStatus("error")
            raise RuntimeError("No generations found in stream.")
        assert agent is replacement_agent
        return {"success": True, "output": "PASS: review ok"}

    orchestrator._execute_agent_task = _fake_execute_agent_task

    factory_calls = {"count": 0}

    async def _build_replacement_agent():
        factory_calls["count"] += 1
        replacement_agent.status = _FakeStatus("active")
        return replacement_agent

    mission = SimpleNamespace(mission_config={"execution_config": {"max_retries": 2}})
    output = await MissionOrchestrator._execute_phase_prompt_with_retry(
        orchestrator,
        mission_id=uuid4(),
        mission=mission,
        phase="reviewing",
        step="review_task:test",
        agent=initial_agent,
        prompt="review prompt",
        error_context="Supervisor review failed",
        agent_factory=_build_replacement_agent,
    )

    assert output == "PASS: review ok"
    assert factory_calls["count"] == 1
    assert execute_calls["count"] == 2
    assert any(
        event.get("event_type") == "PHASE_ATTEMPT_FAILED"
        and event.get("data", {}).get("agent_recreated") is True
        and event.get("data", {}).get("agent_status") == "error"
        for event in emitted_events
    )


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


def test_get_llm_config_temporary_worker_prefers_explicit_role_model():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    mission = SimpleNamespace(
        mission_config={
            "leader_config": {
                "llm_provider": "llm-pool",
                "llm_model": "leader-model",
                "temperature": 0.4,
                "max_tokens": 6000,
            },
            "temporary_worker_config": {
                "llm_provider": "llm-pool",
                "llm_model": "worker-model",
                "temperature": 0.2,
                "max_tokens": 4096,
            },
        }
    )

    cfg = MissionOrchestrator._get_llm_config(orchestrator, mission, "temporary_worker")

    assert cfg["llm_provider"] == "llm-pool"
    assert cfg["llm_model"] == "worker-model"
    assert cfg["temperature"] == 0.2
    assert cfg["max_tokens"] == 4096


def test_get_llm_config_temporary_worker_legacy_model_key_overrides_leader():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    mission = SimpleNamespace(
        mission_config={
            "leader_config": {
                "llm_provider": "openai",
                "llm_model": "gpt-4.1",
                "temperature": 0.4,
                "max_tokens": 6000,
            },
            "temporary_worker_config": {
                "provider": "llm-pool",
                "model": "legacy-worker-model",
            },
        }
    )

    cfg = MissionOrchestrator._get_llm_config(orchestrator, mission, "temporary_worker")
    assert cfg["llm_provider"] == "llm-pool"
    assert cfg["llm_model"] == "legacy-worker-model"
    assert cfg["temperature"] == 0.4
    assert cfg["max_tokens"] == 6000


def test_get_llm_config_temporary_worker_falls_back_to_nested_execution_config():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    mission = SimpleNamespace(
        mission_config={
            "leader_config": {
                "llm_provider": "openai",
                "llm_model": "gpt-4.1",
                "temperature": 0.4,
                "max_tokens": 6000,
            },
            "execution_config": {
                "temporary_worker_config": {
                    "llm_provider": "llm-pool",
                    "llm_model": "nested-worker-model",
                    "temperature": 0.3,
                    "max_tokens": 4096,
                }
            },
        }
    )

    cfg = MissionOrchestrator._get_llm_config(orchestrator, mission, "temporary_worker")
    assert cfg["llm_provider"] == "llm-pool"
    assert cfg["llm_model"] == "nested-worker-model"
    assert cfg["temperature"] == 0.3
    assert cfg["max_tokens"] == 4096


def test_build_temporary_worker_system_prompt_is_task_specific():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    mission = SimpleNamespace(
        title="Fuzhou Travel Guide",
        instructions="Create a practical five-day travel plan for first-time visitors.",
    )
    task_a = SimpleNamespace(
        task_id=uuid4(),
        goal_text="Draft itinerary structure.",
        acceptance_criteria="Outline each day with morning/afternoon/evening.",
        task_metadata={"title": "Draft itinerary structure"},
    )
    task_b = SimpleNamespace(
        task_id=uuid4(),
        goal_text="Write local food section.",
        acceptance_criteria="Include at least 8 dishes with context.",
        task_metadata={"title": "Write local food section"},
    )

    prompt_a = MissionOrchestrator._build_temporary_worker_system_prompt(
        orchestrator,
        mission,
        task_a,
    )
    prompt_b = MissionOrchestrator._build_temporary_worker_system_prompt(
        orchestrator,
        mission,
        task_b,
    )

    assert str(task_a.task_id) in prompt_a
    assert "Task Title: Draft itinerary structure" in prompt_a
    assert str(task_b.task_id) in prompt_b
    assert "Task Title: Write local food section" in prompt_b
    assert prompt_a != prompt_b


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


def test_merge_deliverable_records_deduplicates_by_path():
    existing = [
        {
            "filename": "output/final.md",
            "path": "artifacts/m1/final.md",
            "size": 128,
            "is_target": True,
        }
    ]
    current = [
        {
            "filename": "shared/qa_report.md",
            "path": "artifacts/m1/qa_report.md",
            "size": 64,
            "is_target": False,
        },
        {
            "filename": "output/final.md",
            "path": "artifacts/m1/final.md",
            "size": 128,
            "is_target": True,
        },
    ]

    merged = MissionOrchestrator._merge_deliverable_records(existing, current)

    assert len(merged) == 2
    assert merged[0]["path"] == "artifacts/m1/final.md"
    assert merged[1]["path"] == "artifacts/m1/qa_report.md"


@pytest.mark.asyncio
async def test_phase_complete_partial_retry_reuses_existing_target_deliverables(monkeypatch):
    mission_id = uuid4()
    existing_final = {
        "filename": "output/fuzhou_guide.md",
        "path": "artifacts/f705132c/fuzhou_guide.md",
        "size": 4096,
        "download_url": None,
        "is_target": True,
        "source_scope": "output",
        "artifact_kind": "final",
    }
    mission = SimpleNamespace(
        mission_id=mission_id,
        total_tasks=9,
        result={"deliverables": [existing_final]},
    )

    emitted_events = []
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))
    orchestrator._workspace = SimpleNamespace(
        collect_deliverables=lambda _mission_id: [
            SimpleNamespace(
                filename="shared/qa_report.md",
                path="artifacts/f705132c/qa_report.md",
                size=512,
                download_url=None,
                is_target=False,
                source_scope="shared",
                artifact_kind="intermediate",
            )
        ]
    )
    orchestrator._get_task_status_counts = lambda _mission_id: {"completed": 9}

    mission_updates = {}
    mission_statuses = []

    monkeypatch.setattr("mission_system.orchestrator.get_mission", lambda _mission_id: mission)
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_fields",
        lambda _mission_id, **kwargs: mission_updates.update(kwargs),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_status",
        lambda _mission_id, status, **kwargs: mission_statuses.append(status),
    )

    await MissionOrchestrator._phase_complete(
        orchestrator,
        mission_id,
        preserve_existing_deliverables=True,
    )

    merged_deliverables = mission_updates["result"]["deliverables"]
    merged_paths = [item.get("path") for item in merged_deliverables]
    assert "artifacts/f705132c/fuzhou_guide.md" in merged_paths
    assert "artifacts/f705132c/qa_report.md" in merged_paths
    assert mission_statuses == ["completed"]
    assert any(event.get("event_type") == "MISSION_DELIVERABLES_REUSED" for event in emitted_events)
    assert any(
        event.get("event_type") == "MISSION_COMPLETED"
        and event.get("data", {}).get("target_deliverable_count") == 1
        for event in emitted_events
    )


def test_transition_allows_failed_to_executing_for_partial_retry(monkeypatch):
    mission_id = uuid4()
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)

    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(status="failed"),
    )

    updates = []

    def _update_status(_mission_id, status, **kwargs):
        updates.append((_mission_id, status))

    monkeypatch.setattr("mission_system.orchestrator.update_mission_status", _update_status)

    MissionOrchestrator._transition(orchestrator, mission_id, "executing")
    assert updates == [(mission_id, "executing")]


@pytest.mark.asyncio
async def test_retry_failed_parts_emits_event_and_tracks_active_task(monkeypatch):
    mission_id = uuid4()
    user_id = uuid4()
    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._active_missions = {}
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(status="failed"),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.prepare_partial_retry_for_failed_tasks",
        lambda _mission_id: {"retried_tasks": 2, "total_tasks": 4},
    )

    async def _fake_run_partial_retry(_mission_id, _user_id):
        return None

    monkeypatch.setattr(orchestrator, "_run_partial_retry", _fake_run_partial_retry)

    await MissionOrchestrator.retry_failed_parts(orchestrator, mission_id, user_id)

    assert mission_id in orchestrator._active_missions
    await orchestrator._active_missions[mission_id]
    assert any(
        event.get("event_type") == "MISSION_PARTIAL_RETRY_REQUESTED" for event in emitted_events
    )


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

    async def _fake_execute_agent_task(agent, prompt, container_id=None, **kwargs):
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

    async def _fake_execute_agent_task(agent, prompt, container_id=None, **kwargs):
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


@pytest.mark.asyncio
async def test_execute_task_with_retry_prefers_platform_agent_before_temporary(monkeypatch):
    mission_id = uuid4()
    owner_user_id = uuid4()
    matched_agent_id = uuid4()
    task_id = uuid4()

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: None)

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "execution_config": {
                "prefer_existing_agents": True,
                "allow_temporary_workers": True,
            }
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Implement API endpoint",
        acceptance_criteria="API endpoint works",
        task_metadata={
            "title": "Implement API",
            "role_required_capabilities": ["python", "api"],
        },
        assigned_agent_id=None,
    )
    matched_platform_agent = SimpleNamespace(
        agent_id=matched_agent_id,
        name="backend-agent",
        status="idle",
        agent_type="platform",
        capabilities=["python", "api"],
        system_prompt="Backend API specialist",
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
        assigned_agent_id=None,
        task_metadata={},
        result=None,
        completed_at=None,
    )

    async def _fake_create_registered(agent_id, owner_user_id):
        if agent_id == matched_agent_id:
            return SimpleNamespace(agent_id=agent_id, name="backend-agent")
        return None

    async def _fake_execute_agent_task(agent, prompt, container_id=None, **kwargs):
        return {"output": "done"}

    provision_calls = {"count": 0}

    def _fake_provision(self, mission_id, mission, task_obj, llm_cfg):
        provision_calls["count"] += 1
        return uuid4()

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
        lambda mission_id, agent_id, status: None,
    )

    success = await MissionOrchestrator._execute_task_with_retry(
        orchestrator,
        mission_id=mission_id,
        mission=mission,
        task_obj=task_obj,
        max_retries=0,
        available_platform_agents=[matched_platform_agent],
    )

    assert success is True
    assert provision_calls["count"] == 0
    assert db_task.assigned_agent_id == matched_agent_id
    assert task_obj.assigned_agent_id == matched_agent_id
    assert task_obj.task_metadata.get("assignment_source") == "platform_auto_match"


@pytest.mark.asyncio
async def test_execute_task_with_retry_keeps_temporary_plan_when_existing_match_is_weak(
    monkeypatch,
):
    mission_id = uuid4()
    owner_user_id = uuid4()
    matched_agent_id = uuid4()
    temporary_agent_id = uuid4()
    task_id = uuid4()
    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "execution_config": {
                "prefer_existing_agents": True,
                "allow_temporary_workers": True,
            }
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Implement API endpoint",
        acceptance_criteria="Endpoint returns valid response",
        task_metadata={
            "title": "Implement API endpoint",
            "assignment_source": "temporary_fallback_pending",
            "role_required_capabilities": [],
        },
        assigned_agent_id=None,
    )
    weak_platform_agent = SimpleNamespace(
        agent_id=matched_agent_id,
        name="Implement API endpoint specialist",
        status="idle",
        agent_type="platform",
        capabilities=[],
        system_prompt="General helper",
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
        assigned_agent_id=None,
        task_metadata={},
        result=None,
        completed_at=None,
    )

    created_agent_ids: List[UUID] = []

    async def _fake_create_registered(agent_id, owner_user_id):
        created_agent_ids.append(agent_id)
        if agent_id == temporary_agent_id:
            return SimpleNamespace(agent_id=agent_id, name="temp-worker")
        if agent_id == matched_agent_id:
            return SimpleNamespace(agent_id=agent_id, name="weak-platform")
        return None

    async def _fake_execute_agent_task(agent, prompt, container_id=None, **kwargs):
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
        lambda mission_id, agent_id, status: None,
    )

    success = await MissionOrchestrator._execute_task_with_retry(
        orchestrator,
        mission_id=mission_id,
        mission=mission,
        task_obj=task_obj,
        max_retries=0,
        available_platform_agents=[weak_platform_agent],
    )

    assert success is True
    assert provision_calls["count"] == 1
    assert matched_agent_id not in created_agent_ids
    assert temporary_agent_id in created_agent_ids
    emitted_types = [event["event_type"] for event in emitted_events]
    assert "TASK_AGENT_MATCH_REJECTED" in emitted_types


@pytest.mark.asyncio
async def test_execute_task_with_retry_fails_when_temp_worker_disabled_and_no_platform_match(
    monkeypatch,
):
    mission_id = uuid4()
    owner_user_id = uuid4()
    task_id = uuid4()
    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "execution_config": {
                "prefer_existing_agents": True,
                "allow_temporary_workers": False,
            }
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Implement API endpoint",
        acceptance_criteria="API endpoint works",
        task_metadata={"title": "Implement API"},
        assigned_agent_id=None,
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
        assigned_agent_id=None,
        task_metadata={},
        result=None,
        completed_at=None,
    )

    async def _fake_create_registered(agent_id, owner_user_id):
        return None

    monkeypatch.setattr(
        "mission_system.orchestrator.create_registered_mission_agent",
        _fake_create_registered,
    )
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_task),
    )

    success = await MissionOrchestrator._execute_task_with_retry(
        orchestrator,
        mission_id=mission_id,
        mission=mission,
        task_obj=task_obj,
        max_retries=0,
        available_platform_agents=[],
    )

    assert success is False
    assert db_task.status == "failed"
    assert isinstance(db_task.result, dict)
    assert "temporary workers are disabled" in (db_task.result.get("error") or "").lower()
    emitted_types = [event["event_type"] for event in emitted_events]
    assert "TASK_FAILED" in emitted_types


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


def test_restore_workspace_snapshot_if_available_uses_latest_history_record():
    mission_id = uuid4()
    emitted_events = []
    restored_paths = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))
    orchestrator._workspace = SimpleNamespace(
        restore_workspace=lambda _mission_id, path: (
            restored_paths.append(path) or {
                "restored_file_count": 4,
                "archive_size": 256,
                "restored_at": "2026-02-25T00:00:00Z",
            }
        )
    )

    mission = SimpleNamespace(
        result={
            "workspace_snapshots": [
                {"path": "artifacts/old_snapshot.tar.gz"},
                {"path": "artifacts/new_snapshot.tar.gz"},
            ]
        }
    )

    MissionOrchestrator._restore_workspace_snapshot_if_available(orchestrator, mission_id, mission)

    assert restored_paths == ["artifacts/new_snapshot.tar.gz"]
    assert any(
        event.get("event_type") == "WORKSPACE_RESTORED" for event in emitted_events
    )


def test_restore_workspace_snapshot_if_available_emits_skip_when_absent():
    mission_id = uuid4()
    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))
    orchestrator._workspace = SimpleNamespace(restore_workspace=lambda *_args, **_kwargs: None)

    mission = SimpleNamespace(result={"deliverables": []})

    MissionOrchestrator._restore_workspace_snapshot_if_available(orchestrator, mission_id, mission)

    assert any(
        event.get("event_type") == "WORKSPACE_RESTORE_SKIPPED" for event in emitted_events
    )


def test_snapshot_deliverables_persists_workspace_snapshot_history(monkeypatch):
    mission_id = uuid4()
    emitted_events = []
    mission_updates = {}

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))
    orchestrator._workspace = SimpleNamespace(
        collect_deliverables=lambda _mission_id: [],
        snapshot_workspace=lambda _mission_id, reason: {
            "path": "artifacts/new_snapshot.tar.gz",
            "size": 321,
            "file_count": 12,
            "reason": reason,
            "created_at": "2026-02-25T00:00:00Z",
        },
    )

    mission = SimpleNamespace(
        result={"workspace_snapshots": [{"path": "artifacts/old_snapshot.tar.gz"}]}
    )

    monkeypatch.setattr("mission_system.orchestrator.get_mission", lambda _mission_id: mission)
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_fields",
        lambda _mission_id, **kwargs: mission_updates.update(kwargs),
    )

    MissionOrchestrator._snapshot_deliverables(orchestrator, mission_id, reason="failed")

    result_payload = mission_updates.get("result")
    assert isinstance(result_payload, dict)
    assert result_payload.get("workspace_snapshot", {}).get("path") == "artifacts/new_snapshot.tar.gz"
    history = result_payload.get("workspace_snapshots", [])
    assert {"path": "artifacts/old_snapshot.tar.gz"} in history
    assert any(item.get("path") == "artifacts/new_snapshot.tar.gz" for item in history)
    assert any(
        event.get("event_type") == "WORKSPACE_SNAPSHOTTED" for event in emitted_events
    )


def test_snapshot_deliverables_deletes_rotated_storage_objects(monkeypatch):
    mission_id = uuid4()
    mission_updates = {}
    deleted_objects = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **_kwargs: None)
    orchestrator._workspace = SimpleNamespace(
        collect_deliverables=lambda _mission_id: [
            SimpleNamespace(
                filename="output/new.md",
                path="artifacts/new_deliverable.md",
                size=123,
                is_target=True,
                source_scope="output",
                artifact_kind="final",
            )
        ],
        snapshot_workspace=lambda _mission_id, reason: {
            "path": "artifacts/ws11.tar.gz",
            "size": 1024,
            "file_count": 8,
            "reason": reason,
            "created_at": "2026-02-25T00:00:00Z",
        },
    )

    mission = SimpleNamespace(
        result={
            "deliverables": [
                {
                    "filename": "output/old.md",
                    "path": "artifacts/old_deliverable.md",
                }
            ],
            "workspace_snapshot": {"path": "artifacts/ws10.tar.gz"},
            "workspace_snapshots": [
                {"path": f"artifacts/ws{i}.tar.gz"} for i in range(1, 11)
            ],
        }
    )

    class _FakeMinio:
        def delete_file(self, bucket_name, object_key):
            deleted_objects.append((bucket_name, object_key))

    monkeypatch.setattr("mission_system.orchestrator.get_mission", lambda _mission_id: mission)
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_fields",
        lambda _mission_id, **kwargs: mission_updates.update(kwargs),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.get_minio_client",
        lambda: _FakeMinio(),
    )

    MissionOrchestrator._snapshot_deliverables(orchestrator, mission_id, reason="failed")

    assert ("artifacts", "old_deliverable.md") in deleted_objects
    assert ("artifacts", "ws1.tar.gz") in deleted_objects

    result_payload = mission_updates.get("result", {})
    history = result_payload.get("workspace_snapshots", [])
    assert len(history) == 10
    assert history[0].get("path") == "artifacts/ws2.tar.gz"
    assert history[-1].get("path") == "artifacts/ws11.tar.gz"


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


def test_extract_json_object_parses_markdown_block():
    payload = """
```json
{"team_blueprint":[{"role_key":"backend"}],"tasks":[{"title":"t1"}]}
```
"""
    parsed = MissionOrchestrator._extract_json_object(payload)
    assert parsed["team_blueprint"][0]["role_key"] == "backend"
    assert parsed["tasks"][0]["title"] == "t1"


def test_evaluate_task_plan_relevance_flags_off_topic_tasks():
    task_list = [
        {
            "title": "Implement checkout API",
            "instructions": "Build order submission endpoint",
            "acceptance_criteria": "Order can be created and validated",
            "requirement_refs": ["checkout", "order submission"],
        },
        {
            "title": "Design office party invitation",
            "instructions": "Write celebration poster copy",
            "acceptance_criteria": "Poster text drafted",
            "requirement_refs": ["celebration"],
        },
    ]
    report = MissionOrchestrator._evaluate_task_plan_relevance(
        task_list,
        anchor_text="Build ecommerce checkout and order payment flow",
    )
    assert len(report["scores"]) == 2
    assert report["scores"][0] > report["scores"][1]
    assert report["off_topic_indices"] == [1]


def test_build_task_key_enforces_uniqueness():
    existing = set()
    first = MissionOrchestrator._build_task_key("Build API Contract", 0, existing)
    second = MissionOrchestrator._build_task_key("Build API Contract", 1, existing)
    third = MissionOrchestrator._build_task_key("", 2, existing)
    assert first == "build_api_contract"
    assert second == "build_api_contract_2"
    assert third == "task_3"


def test_resolve_task_dependency_keys_supports_mixed_references():
    resolved = MissionOrchestrator._resolve_task_dependency_keys(
        ["setup_db", "Implement API", "implement-api", "unknown"],
        title_to_key={"Setup DB": "setup_db", "Implement API": "implement_api"},
        normalized_title_to_key={
            "setup_db": "setup_db",
            "implement_api": "implement_api",
        },
        task_keys={"setup_db", "implement_api"},
    )
    assert resolved == ["setup_db", "implement_api"]


def test_compute_dependency_levels_builds_execution_waves():
    levels = MissionOrchestrator._compute_dependency_levels(
        [
            {"task_key": "a", "dependency_keys": []},
            {"task_key": "b", "dependency_keys": ["a"]},
            {"task_key": "c", "dependency_keys": ["a"]},
            {"task_key": "d", "dependency_keys": ["b", "c"]},
        ]
    )
    assert levels["a"] == 0
    assert levels["b"] == 1
    assert levels["c"] == 1
    assert levels["d"] == 2


def test_resolve_temporary_worker_memory_scopes_defaults_and_normalization():
    assert MissionOrchestrator._resolve_temporary_worker_memory_scopes({}) == [
        "agent",
        "company",
        "user_context",
        "task_context",
    ]
    normalized = MissionOrchestrator._resolve_temporary_worker_memory_scopes(
        {
            "temp_worker_memory_scopes": [
                "COMPANY",
                "agent",
                "invalid_scope",
            ]
        }
    )
    assert normalized == ["company", "agent", "task_context"]


def test_resolve_blueprint_role_assignments_prefers_capability_match():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    agent_a = SimpleNamespace(
        agent_id=uuid4(),
        name="backend-agent",
        capabilities=["python", "api"],
    )
    agent_b = SimpleNamespace(
        agent_id=uuid4(),
        name="ui-agent",
        capabilities=["react", "css"],
    )
    role_map = MissionOrchestrator._resolve_blueprint_role_assignments(
        orchestrator,
        team_blueprint=[
            {
                "role_key": "backend_lead",
                "role_name": "Backend Lead",
                "required_capabilities": ["python"],
            }
        ],
        available_agents=[agent_a, agent_b],
    )
    assert role_map["backend_lead"]["assigned_agent_id"] == str(agent_a.agent_id)
    assert role_map["backend_lead"]["assigned_agent_name"] == "backend-agent"


def test_select_temporary_worker_skills_uses_task_overlap(monkeypatch):
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    mission = SimpleNamespace(mission_id=uuid4())
    task_obj = SimpleNamespace(
        task_metadata={"title": "Build REST API"},
        goal_text="Implement Python API endpoints",
        acceptance_criteria="Expose HTTP API routes",
    )

    class _FakeSkill:
        def __init__(self, name, description, skill_type="agent_skill"):
            self.name = name
            self.description = description
            self.skill_type = skill_type

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows

        def query(self, *args, **kwargs):
            return _FakeQuery(self._rows)

    class _FakeSessionContext:
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return _FakeSession(self._rows)

        def __exit__(self, exc_type, exc, tb):
            return False

    rows = [
        _FakeSkill("python_api_helper", "Build python API services"),
        _FakeSkill("ui_styling_pack", "Improve CSS and visual style"),
    ]
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(rows),
    )

    selected = MissionOrchestrator._select_temporary_worker_skills(
        orchestrator,
        mission=mission,
        task_obj=task_obj,
        exec_cfg={"auto_select_temp_skills": True, "temp_worker_skill_limit": 2},
    )
    assert "python_api_helper" in selected
    assert "ui_styling_pack" not in selected


def test_select_platform_agent_for_task_prefers_capability_overlap():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    task_obj = SimpleNamespace(
        task_metadata={"title": "Build API", "role_required_capabilities": ["python", "api"]},
        goal_text="Implement backend API service",
        acceptance_criteria="Expose stable API endpoints",
    )
    matched_agent = SimpleNamespace(
        agent_id=uuid4(),
        name="Backend Specialist",
        agent_type="platform",
        status="idle",
        capabilities=["python", "api", "fastapi"],
        system_prompt="Backend implementation specialist",
    )
    unmatched_agent = SimpleNamespace(
        agent_id=uuid4(),
        name="UI Specialist",
        agent_type="platform",
        status="idle",
        capabilities=["react", "css"],
        system_prompt="Frontend specialist",
    )

    selected = MissionOrchestrator._select_platform_agent_for_task(
        orchestrator,
        task_obj=task_obj,
        available_agents=[unmatched_agent, matched_agent],
    )

    assert selected is not None
    assert selected["agent_id"] == str(matched_agent.agent_id)
    assert selected["agent_name"] == "Backend Specialist"


def test_select_platform_agent_for_task_returns_none_without_overlap():
    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    task_obj = SimpleNamespace(
        task_metadata={"title": "Build API", "role_required_capabilities": ["python"]},
        goal_text="Implement backend API service",
        acceptance_criteria="Expose stable API endpoints",
    )
    candidate = SimpleNamespace(
        agent_id=uuid4(),
        name="Design Specialist",
        agent_type="platform",
        status="idle",
        capabilities=["figma", "illustration"],
        system_prompt="Visual design specialist",
    )

    selected = MissionOrchestrator._select_platform_agent_for_task(
        orchestrator,
        task_obj=task_obj,
        available_agents=[candidate],
    )

    assert selected is None


@pytest.mark.asyncio
async def test_execute_task_with_retry_escalates_rework_to_temporary_for_non_temp_assignment(
    monkeypatch,
):
    mission_id = uuid4()
    owner_user_id = uuid4()
    assigned_agent_id = uuid4()
    temporary_agent_id = uuid4()
    task_id = uuid4()

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: None)

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "execution_config": {
                "allow_temporary_workers": True,
                "prefer_existing_agents": True,
            }
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Refine deliverable",
        acceptance_criteria="All review feedback addressed",
        task_metadata={
            "title": "Refine deliverable",
            "review_cycle_count": 1,
            "review_feedback": "Fix formatting issues.",
            "assignment_source": "leader_assigned",
            "assigned_agent_temporary": False,
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
        task_metadata={},
        result=None,
        completed_at=None,
    )

    create_calls = []

    async def _fake_create_registered(agent_id, owner_user_id):
        create_calls.append(agent_id)
        if agent_id == temporary_agent_id:
            return SimpleNamespace(agent_id=agent_id, name="temp-worker")
        return None

    async def _fake_execute_agent_task(agent, prompt, container_id=None, **kwargs):
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
    assert provision_calls["count"] == 1
    assert create_calls == [temporary_agent_id]
    assert task_obj.assigned_agent_id == temporary_agent_id


@pytest.mark.asyncio
async def test_phase_review_reuses_cached_pass_for_unchanged_output(monkeypatch):
    mission_id = uuid4()
    task_id = uuid4()
    task_output = "stable deliverable output"
    task_metadata = {
        "title": "Stable Task",
        "review_status": "approved",
        "review_output_signature": MissionOrchestrator._build_text_signature(task_output),
    }
    db_task = SimpleNamespace(
        task_id=task_id,
        status="completed",
        goal_text="Do work",
        acceptance_criteria="All done",
        result={"output": task_output},
        task_metadata=task_metadata,
        dependencies=[],
        completed_at=datetime.utcnow(),
    )

    class _FakeQuery:
        def __init__(self, task):
            self._task = task

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return [self._task]

        def first(self):
            return self._task

    class _FakeSession:
        def __init__(self, task):
            self._task = task

        def query(self, *args, **kwargs):
            return _FakeQuery(self._task)

        def expunge(self, _obj):
            return None

    class _FakeSessionContext:
        def __init__(self, task):
            self._task = task

        def __enter__(self):
            return _FakeSession(self._task)

        def __exit__(self, exc_type, exc, tb):
            return False

    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    monkeypatch.setattr(
        MissionOrchestrator,
        "_transition",
        lambda self, _mission_id, _status: None,
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(
            created_by_user_id=uuid4(),
            mission_config={},
            total_tasks=1,
        ),
    )

    async def _fake_create_mission_agent(*args, **kwargs):
        return SimpleNamespace(name="supervisor")

    monkeypatch.setattr(
        "mission_system.orchestrator.create_mission_agent",
        _fake_create_mission_agent,
    )

    async def _should_not_be_called(*args, **kwargs):
        raise AssertionError("Model review should be skipped for unchanged approved output")

    monkeypatch.setattr(
        MissionOrchestrator,
        "_execute_phase_prompt_with_retry",
        _should_not_be_called,
    )
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_task),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_topological_sort",
        staticmethod(lambda tasks: tasks),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_get_task_status_counts",
        staticmethod(lambda _mission_id: {"completed": 1}),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_fields",
        lambda *args, **kwargs: None,
    )

    await MissionOrchestrator._phase_review(orchestrator, mission_id)

    cached_review_event = next(
        (
            event
            for event in emitted_events
            if event.get("event_type") == "TASK_REVIEWED" and event.get("task_id") == task_id
        ),
        None,
    )
    assert cached_review_event is not None
    assert cached_review_event.get("data", {}).get("reason") == "reuse_previous_pass"
    assert cached_review_event.get("data", {}).get("verdict") == "PASS"


@pytest.mark.asyncio
async def test_phase_review_keeps_dependency_blocked_tasks_pending(monkeypatch):
    mission_id = uuid4()
    root_task_id = uuid4()
    child_task_id = uuid4()
    emitted_events = []

    root_task = SimpleNamespace(
        task_id=root_task_id,
        status="failed",
        goal_text="Collect facts",
        acceptance_criteria="Facts collected",
        result={"last_error": "worker crashed"},
        task_metadata={"title": "Root task"},
        dependencies=[],
        completed_at=None,
    )
    child_task = SimpleNamespace(
        task_id=child_task_id,
        status="pending",
        goal_text="Write summary",
        acceptance_criteria="Summary completed",
        result={},
        task_metadata={"title": "Child task"},
        dependencies=[str(root_task_id)],
        completed_at=None,
    )
    tasks_by_id = {
        str(root_task_id): root_task,
        str(child_task_id): child_task,
    }
    first_results = [root_task, child_task, root_task]

    class _FakeQuery:
        def __init__(self, tasks, first_values):
            self._tasks = tasks
            self._first_values = first_values

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return list(self._tasks.values())

        def first(self):
            if self._first_values:
                return self._first_values.pop(0)
            return next(iter(self._tasks.values()))

    class _FakeSession:
        def __init__(self, tasks, first_values):
            self._tasks = tasks
            self._first_values = first_values

        def query(self, *args, **kwargs):
            return _FakeQuery(self._tasks, self._first_values)

        def expunge(self, _obj):
            return None

    class _FakeSessionContext:
        def __init__(self, tasks, first_values):
            self._tasks = tasks
            self._first_values = first_values

        def __enter__(self):
            return _FakeSession(self._tasks, self._first_values)

        def __exit__(self, exc_type, exc, tb):
            return False

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    monkeypatch.setattr(
        MissionOrchestrator,
        "_transition",
        lambda self, _mission_id, _status: None,
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.get_mission",
        lambda _mission_id: SimpleNamespace(
            created_by_user_id=uuid4(),
            mission_config={"execution_config": {"max_rework_cycles": 0}},
            total_tasks=2,
        ),
    )

    async def _fake_create_mission_agent(*args, **kwargs):
        return SimpleNamespace(name="supervisor")

    monkeypatch.setattr(
        "mission_system.orchestrator.create_mission_agent",
        _fake_create_mission_agent,
    )
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(tasks_by_id, first_results),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_topological_sort",
        staticmethod(lambda tasks: [root_task, child_task]),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_get_task_status_counts",
        staticmethod(lambda _mission_id: {"failed": 1, "pending": 1}),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_fields",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(MissionError, match="Review failed after"):
        await MissionOrchestrator._phase_review(orchestrator, mission_id)

    assert root_task.status == "failed"
    assert root_task.task_metadata["review_status"] == "rework_required"
    assert root_task.task_metadata["review_feedback"] == "worker crashed"
    assert child_task.status == "pending"
    assert child_task.task_metadata["review_status"] == "blocked_by_dependency"
    assert child_task.task_metadata["blocked_by_failed_dependencies"] == [str(root_task_id)]
    assert any(
        event.get("event_type") == "TASK_REVIEWED"
        and event.get("task_id") == child_task_id
        and event.get("data", {}).get("verdict") == "BLOCKED"
        for event in emitted_events
    )


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
            created_by_user_id=uuid4(),
            mission_config={"execution_config": {"max_concurrent_tasks": 2}},
        ),
    )
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_tasks),
    )
    monkeypatch.setattr(
        "agent_framework.agent_registry.AgentRegistry",
        lambda: SimpleNamespace(list_agents=lambda **kwargs: []),
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

    async def _fake_execute_agent_task(agent, prompt, container_id=None, **kwargs):
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


@pytest.mark.asyncio
async def test_execute_task_with_retry_respects_task_timeout(monkeypatch):
    mission_id = uuid4()
    owner_user_id = uuid4()
    assigned_agent_id = uuid4()
    task_id = uuid4()
    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    mission = SimpleNamespace(
        created_by_user_id=owner_user_id,
        mission_config={
            "execution_config": {"task_timeout_s": 1, "max_retries": 0},
            "leader_config": {
                "llm_provider": "ollama",
                "llm_model": "qwen2.5:14b",
                "temperature": 0.2,
                "max_tokens": 1024,
            },
        },
    )
    task_obj = SimpleNamespace(
        task_id=task_id,
        goal_text="Generate output",
        acceptance_criteria="Must finish quickly",
        task_metadata={"title": "Timeout candidate"},
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

    async def _fake_execute_agent_task(*args, **kwargs):
        return {"output": "should-not-complete"}

    async def _fake_wait_for(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        "mission_system.orchestrator.create_registered_mission_agent",
        _fake_create_registered,
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_execute_agent_task",
        staticmethod(_fake_execute_agent_task),
    )
    monkeypatch.setattr("mission_system.orchestrator.asyncio.wait_for", _fake_wait_for)
    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(db_task),
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_agent_status",
        lambda mission_id, agent_id, status: None,
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_safe_sync_mission_task_counters",
        lambda self, mission_id, fallback_total=0: {},
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
    assert "timeout" in str((db_task.result or {}).get("last_error", "")).lower()
    assert any(
        event.get("event_type") == "TASK_FAILED"
        and event.get("data", {}).get("error_type") == "TaskTimeoutError"
        for event in emitted_events
    )


@pytest.mark.asyncio
async def test_review_task_for_dependency_gate_marks_failed_task(monkeypatch):
    mission_id = uuid4()
    dependency_task_id = uuid4()
    emitted_events = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    dependency_task = SimpleNamespace(
        task_id=dependency_task_id,
        status="completed",
        goal_text="Collect source facts",
        acceptance_criteria="Facts must be accurate",
        result={"output": "raw output"},
        task_metadata={"title": "Collect facts", "review_status": "pending"},
        completed_at=datetime.utcnow(),
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

    async def _fake_review(*args, **kwargs):
        return "FAIL: Missing reliable citations."

    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext(dependency_task),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_execute_phase_prompt_with_retry",
        _fake_review,
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_safe_sync_mission_task_counters",
        lambda self, mission_id, fallback_total=0: {"failed_tasks": 1},
    )

    verdict = await MissionOrchestrator._review_task_for_dependency_gate(
        orchestrator,
        mission_id=mission_id,
        mission=SimpleNamespace(created_by_user_id=uuid4()),
        dependency_task_id=dependency_task_id,
        supervisor=SimpleNamespace(name="supervisor"),
        fallback_total_tasks=1,
    )

    assert verdict is False
    assert dependency_task.status == "failed"
    assert dependency_task.task_metadata["review_status"] == "rework_required"
    assert "review_feedback" in dependency_task.task_metadata
    assert any(event.get("event_type") == "TASK_REVIEWED" for event in emitted_events)
    assert any(event.get("event_type") == "TASK_FAILED" for event in emitted_events)


@pytest.mark.asyncio
async def test_recover_stale_missions_after_restart_marks_orphaned_tasks(monkeypatch):
    mission_id = uuid4()
    emitted_events = []
    status_updates = []

    orchestrator = MissionOrchestrator.__new__(MissionOrchestrator)
    orchestrator._active_missions = {}
    orchestrator._emitter = SimpleNamespace(emit=lambda **kwargs: emitted_events.append(kwargs))

    mission_row = SimpleNamespace(mission_id=mission_id, status="executing", total_tasks=2)
    task_row = SimpleNamespace(
        mission_id=mission_id,
        status="in_progress",
        completed_at=datetime.utcnow(),
        result={},
    )

    class _FakeQuery:
        def __init__(self, model, missions, tasks):
            self._model = model
            self._missions = missions
            self._tasks = tasks

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            if getattr(self._model, "__name__", "") == "Mission":
                return self._missions
            return self._tasks

    class _FakeSession:
        def __init__(self, missions, tasks):
            self._missions = missions
            self._tasks = tasks

        def query(self, model):
            return _FakeQuery(model, self._missions, self._tasks)

    class _FakeSessionContext:
        def __init__(self, missions, tasks):
            self._missions = missions
            self._tasks = tasks

        def __enter__(self):
            return _FakeSession(self._missions, self._tasks)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "database.connection.get_db_session",
        lambda: _FakeSessionContext([mission_row], [task_row]),
    )
    monkeypatch.setattr(
        MissionOrchestrator,
        "_safe_sync_mission_task_counters",
        lambda self, mission_id, fallback_total=0: {
            "total_tasks": max(2, fallback_total),
            "completed_tasks": 0,
            "failed_tasks": 1,
        },
    )
    monkeypatch.setattr(
        "mission_system.orchestrator.update_mission_status",
        lambda mission_id, status, error_message=None: status_updates.append(
            (mission_id, status, error_message)
        ),
    )

    summary = await MissionOrchestrator.recover_stale_missions_after_restart(orchestrator)

    assert summary["candidates"] == 1
    assert summary["recovered"] == 1
    assert summary["failed"] == 0
    assert task_row.status == "failed"
    assert task_row.result["last_error_type"] == "ServiceRestartRecovery"
    assert status_updates and status_updates[0][1] == "failed"
    assert any(
        event.get("event_type") == "MISSION_RECOVERED_FROM_STALE_STATE"
        and event.get("mission_id") == mission_id
        for event in emitted_events
    )
