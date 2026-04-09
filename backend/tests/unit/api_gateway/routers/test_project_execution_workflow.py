"""Workflow tests for the project execution platform skeleton."""

from __future__ import annotations

import base64
import io
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from agent_framework.agent_registry import get_agent_registry
from api_gateway.main import create_app
from database.connection import get_db_session
from database.models import Agent, AgentConversation, PlatformSetting
from database.project_execution_models import (
    ExecutionNode,
    ExternalAgentBinding,
    ExternalAgentDispatch,
    ProjectRun,
    ProjectTask,
)
from project_execution.run_workspace_manager import get_run_workspace_manager
from project_execution.external_runtime_service import (
    CURRENT_EXTERNAL_RUNTIME_VERSION,
    ExternalRuntimeService,
)

pytestmark = [pytest.mark.usefixtures("cleanup_shared_db_test_artifacts")]


@pytest.fixture
def api_client():
    app = create_app()
    with TestClient(app) as client:
        yield client


def _register_auth_headers(api_client: TestClient) -> dict[str, str]:
    unique_id = str(uuid4())[:8]
    user_data = {
        "username": f"testuser_{unique_id}",
        "email": f"test_{unique_id}@example.com",
        "password": "SecurePassword123!",
        "full_name": "Project Execution Tester",
    }

    register_response = api_client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201, register_response.text

    login_response = api_client.post(
        "/api/v1/auth/login",
        json={"username": user_data["username"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200, login_response.text
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def auth_headers(api_client: TestClient):
    return _register_auth_headers(api_client)


@pytest.fixture(autouse=True)
def reset_project_execution_settings() -> None:
    with get_db_session() as session:
        row = (
            session.query(PlatformSetting)
            .filter(PlatformSetting.setting_key == "project_execution")
            .first()
        )
        if row is None:
            row = PlatformSetting(
                setting_key="project_execution",
                setting_value={"default_launch_command_template": ""},
            )
            session.add(row)
        else:
            row.setting_value = {"default_launch_command_template": ""}
        session.commit()


def _set_platform_launch_command(template: str) -> None:
    with get_db_session() as session:
        row = (
            session.query(PlatformSetting)
            .filter(PlatformSetting.setting_key == "project_execution")
            .first()
        )
        if row is None:
            row = PlatformSetting(
                setting_key="project_execution",
                setting_value={"default_launch_command_template": template},
            )
            session.add(row)
        else:
            row.setting_value = {"default_launch_command_template": template}
        session.commit()


def _build_workspace_archive(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for relative_path, content in entries.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=relative_path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _create_project_and_running_task_run(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    project_name: str,
    task_title: str,
) -> tuple[str, str]:
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": project_name,
            "description": "Exercise run reconciliation.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    task_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": task_title,
            "description": "Create a task bound to a run.",
            "status": "planning",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["project_task_id"]

    plan_response = api_client.post(
        "/api/v1/plans",
        json={
            "project_id": project_id,
            "name": f"{task_title} Plan",
            "goal": task_title,
            "status": "generated",
            "version": 1,
            "definition": {"project_task_id": task_id},
        },
        headers=auth_headers,
    )
    assert plan_response.status_code == 201, plan_response.text
    plan_id = plan_response.json()["plan_id"]

    activate_response = api_client.post(
        f"/api/v1/plans/{plan_id}/activate",
        json={"status": "active"},
        headers=auth_headers,
    )
    assert activate_response.status_code == 200, activate_response.text

    run_response = api_client.post(
        "/api/v1/runs",
        json={
            "project_id": project_id,
            "plan_id": plan_id,
            "status": "queued",
            "trigger_source": "manual",
            "runtime_context": {"project_task_id": task_id},
        },
        headers=auth_headers,
    )
    assert run_response.status_code == 201, run_response.text
    run_id = run_response.json()["run_id"]

    patch_task_response = api_client.patch(
        f"/api/v1/project-tasks/{task_id}",
        json={"plan_id": plan_id, "run_id": run_id, "status": "running"},
        headers=auth_headers,
    )
    assert patch_task_response.status_code == 200, patch_task_response.text

    start_response = api_client.post(
        f"/api/v1/runs/{run_id}/start",
        headers=auth_headers,
    )
    assert start_response.status_code == 200, start_response.text

    return task_id, run_id


def _create_attempt_node(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    run_id: str,
    task_id: str,
    name: str,
    status: str = "pending",
    sequence_number: int = 0,
    node_payload: dict | None = None,
) -> dict:
    response = api_client.post(
        f"/api/v1/attempts/{run_id}/nodes",
        json={
            "project_task_id": task_id,
            "name": name,
            "node_type": "task",
            "status": status,
            "sequence_number": sequence_number,
            "node_payload": node_payload or {"project_task_id": task_id},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete_attempt_node(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    run_id: str,
    node_id: str,
    status: str = "completed",
    result_payload: dict | None = None,
) -> dict:
    response = api_client.post(
        f"/api/v1/attempts/{run_id}/nodes/{node_id}/complete",
        json={
            "status": status,
            "result_payload": result_payload or {},
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _get_attempt_node(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    run_id: str,
    node_id: str,
) -> dict:
    response = api_client.get(
        f"/api/v1/attempts/{run_id}/nodes/{node_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_project_execution_workflow_chain(api_client: TestClient, auth_headers: dict[str, str]):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Workflow Project",
            "description": "Exercise the project execution workflow chain.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]

    task_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Initial Task",
            "description": "Create the first task in the project.",
            "status": "planning",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    task_id = task["project_task_id"]

    plan_response = api_client.post(
        "/api/v1/plans",
        json={
            "project_id": project_id,
            "name": "Initial Plan",
            "goal": "Prepare execution plan",
            "status": "generated",
            "version": 1,
            "definition": {"project_task_id": task_id},
        },
        headers=auth_headers,
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    plan_id = plan["plan_id"]

    activate_response = api_client.post(
        f"/api/v1/plans/{plan_id}/activate",
        json={"status": "active"},
        headers=auth_headers,
    )
    assert activate_response.status_code == 200, activate_response.text
    assert activate_response.json()["status"] == "active"

    run_response = api_client.post(
        "/api/v1/runs",
        json={
            "project_id": project_id,
            "plan_id": plan_id,
            "status": "queued",
            "trigger_source": "manual",
            "runtime_context": {"project_task_id": task_id},
        },
        headers=auth_headers,
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    run_id = run["run_id"]

    patch_task_response = api_client.patch(
        f"/api/v1/project-tasks/{task_id}",
        json={"plan_id": plan_id, "run_id": run_id, "status": "running"},
        headers=auth_headers,
    )
    assert patch_task_response.status_code == 200, patch_task_response.text

    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Execute initial task",
        status="pending",
    )
    assert node["runId"] == run_id

    start_response = api_client.post(
        f"/api/v1/runs/{run_id}/start",
        headers=auth_headers,
    )
    assert start_response.status_code == 200, start_response.text
    started_run = start_response.json()
    assert started_run["status"] == "running"
    assert started_run["started_at"] is not None

    runs_list = api_client.get("/api/v1/runs", headers=auth_headers)
    assert runs_list.status_code == 200, runs_list.text
    assert any(item["run_id"] == run_id for item in runs_list.json())


def test_create_project_normalizes_draft_to_planning(
    api_client: TestClient, auth_headers: dict[str, str]
):
    response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Normalize Draft",
            "description": "Draft should no longer be the visible default.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "planning"


def test_project_detail_endpoint_returns_aggregated_view(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Project Detail Aggregate",
        task_title="Aggregate Me",
    )

    task_response = api_client.get(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200, task_response.text
    project_id = task_response.json()["project_id"]

    detail_response = api_client.get(f"/api/v1/projects/{project_id}/detail", headers=auth_headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    assert detail["id"] == project_id
    assert detail["title"] == "Project Detail Aggregate"
    assert isinstance(detail["tasks"], list)
    assert isinstance(detail["runs"], list)
    assert any(item["id"] == task_id for item in detail["tasks"])
    assert any(item["id"] == run_id for item in detail["runs"])
    assert "recentActivity" in detail
    assert "deliverables" in detail


def test_project_task_detail_endpoint_returns_execution_context(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Task Detail Aggregate",
        task_title="Document Task Detail",
    )

    patch_task_response = api_client.patch(
        f"/api/v1/project-tasks/{task_id}",
        json={
            "input_payload": {
                "execution_mode": "project_sandbox",
                "acceptance_criteria": "Publish a concise summary and completion note.",
                "skill_names": ["Technical Writing"],
                "planner_summary": "Summarize the task and publish the note.",
                "planner_source": "fallback_heuristic",
            }
        },
        headers=auth_headers,
    )
    assert patch_task_response.status_code == 200, patch_task_response.text

    _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Write summary",
        status="running",
        node_payload={
            "project_task_id": task_id,
            "suggested_agent_ids": ["agent-1"],
            "parallel_group": "documentation",
        },
    )

    detail_response = api_client.get(
        f"/api/v1/project-tasks/{task_id}/detail",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    assert detail["id"] == task_id
    assert detail["executionMode"] == "project_sandbox"
    assert detail["acceptanceCriteria"] == "Publish a concise summary and completion note."
    assert detail["assignedSkillNames"] == ["Technical Writing"]
    assert detail["plannerSummary"] == "Summarize the task and publish the note."
    assert detail["stepTotal"] >= 1
    assert detail["events"]


def test_project_task_contract_endpoint_compiles_from_markdown_description(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Task Contract Project",
            "description": "Compile task contract from description.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    task_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Compile contract",
            "description": (
                "## 任务目标\n- 补齐任务合同接口\n\n"
                "## 交付物\n- backend/project_execution/task_contracts.py\n- tests/unit/api_gateway/routers/test_project_execution_workflow.py\n\n"
                "## 验收标准\n- [ ] 可以读取结构化合同\n- [ ] 合同包含交付物与验收条目\n"
            ),
            "status": "planning",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["project_task_id"]

    contract_response = api_client.get(
        f"/api/v1/project-tasks/{task_id}/contract",
        headers=auth_headers,
    )
    assert contract_response.status_code == 200, contract_response.text
    contract = contract_response.json()

    assert contract["taskId"] == task_id
    assert contract["goal"] == "补齐任务合同接口"
    assert "backend/project_execution/task_contracts.py" in contract["deliverables"]
    assert "可以读取结构化合同" in contract["acceptanceCriteria"]


def test_project_task_dependency_endpoints_update_readiness(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Task Dependency Project",
            "description": "Replace dependency edges.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    upstream_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Upstream task",
            "description": "Complete first.",
            "status": "in_review",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert upstream_response.status_code == 201, upstream_response.text
    upstream_task_id = upstream_response.json()["project_task_id"]

    blocked_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Blocked task",
            "description": "Wait on upstream.",
            "status": "planning",
            "priority": "normal",
            "sort_order": 1,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert blocked_response.status_code == 201, blocked_response.text
    blocked_task_id = blocked_response.json()["project_task_id"]

    replace_response = api_client.put(
        f"/api/v1/project-tasks/{blocked_task_id}/dependencies",
        json={
            "dependencies": [
                {
                    "dependsOnTaskId": upstream_task_id,
                    "requiredState": "completed",
                    "dependencyType": "hard",
                }
            ]
        },
        headers=auth_headers,
    )
    assert replace_response.status_code == 200, replace_response.text
    dependencies = replace_response.json()
    assert len(dependencies) == 1
    assert dependencies[0]["dependsOnTaskId"] == upstream_task_id
    assert dependencies[0]["satisfied"] is False

    blocked_detail_response = api_client.get(
        f"/api/v1/project-tasks/{blocked_task_id}/detail",
        headers=auth_headers,
    )
    assert blocked_detail_response.status_code == 200, blocked_detail_response.text
    blocked_detail = blocked_detail_response.json()
    assert blocked_detail["ready"] is False
    assert blocked_detail["blockingDependencyCount"] == 1
    assert blocked_detail["dependencies"][0]["satisfied"] is False

    upstream_complete_response = api_client.patch(
        f"/api/v1/project-tasks/{upstream_task_id}",
        json={"status": "completed"},
        headers=auth_headers,
    )
    assert upstream_complete_response.status_code == 200, upstream_complete_response.text

    refreshed_detail_response = api_client.get(
        f"/api/v1/project-tasks/{blocked_task_id}/detail",
        headers=auth_headers,
    )
    assert refreshed_detail_response.status_code == 200, refreshed_detail_response.text
    refreshed_detail = refreshed_detail_response.json()
    assert refreshed_detail["ready"] is True
    assert refreshed_detail["blockingDependencyCount"] == 0
    assert refreshed_detail["dependencies"][0]["satisfied"] is True


def test_launch_existing_project_task_rejects_unsatisfied_dependencies(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Launch Blocked Project",
            "description": "Launch should be blocked by dependencies.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    upstream_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Upstream task",
            "description": "Not done yet.",
            "status": "reviewing",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert upstream_response.status_code == 201, upstream_response.text
    upstream_task_id = upstream_response.json()["project_task_id"]

    blocked_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Blocked task",
            "description": "Should not launch until upstream completes.",
            "status": "planning",
            "priority": "normal",
            "sort_order": 1,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert blocked_response.status_code == 201, blocked_response.text
    blocked_task_id = blocked_response.json()["project_task_id"]

    replace_response = api_client.put(
        f"/api/v1/project-tasks/{blocked_task_id}/dependencies",
        json={
            "dependencies": [
                {
                    "dependsOnTaskId": upstream_task_id,
                    "requiredState": "completed",
                    "dependencyType": "hard",
                }
            ]
        },
        headers=auth_headers,
    )
    assert replace_response.status_code == 200, replace_response.text

    launch_response = api_client.post(
        f"/api/v1/project-tasks/{blocked_task_id}/launch",
        json={
            "project_id": project_id,
            "title": "Blocked task",
            "description": "Should not launch until upstream completes.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert launch_response.status_code == 409, launch_response.text
    assert "Waiting on" in launch_response.text


def test_schedule_and_start_run_reject_unsatisfied_dependencies(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Schedule Blocked Project",
            "description": "Run scheduling should be blocked by dependencies.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    upstream_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Upstream task",
            "description": "Not done yet.",
            "status": "reviewing",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert upstream_response.status_code == 201, upstream_response.text
    upstream_task_id = upstream_response.json()["project_task_id"]

    bundle_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Primary task",
            "description": "Create attempt first, then block reschedule/start.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert bundle_response.status_code == 201, bundle_response.text
    payload = bundle_response.json()
    task_id = payload["task"]["project_task_id"]
    run_id = payload["run"]["run_id"]

    replace_response = api_client.put(
        f"/api/v1/project-tasks/{task_id}/dependencies",
        json={
            "dependencies": [
                {
                    "dependsOnTaskId": upstream_task_id,
                    "requiredState": "completed",
                    "dependencyType": "hard",
                }
            ]
        },
        headers=auth_headers,
    )
    assert replace_response.status_code == 200, replace_response.text

    schedule_response = api_client.post(f"/api/v1/runs/{run_id}/schedule", headers=auth_headers)
    assert schedule_response.status_code == 409, schedule_response.text

    start_response = api_client.post(f"/api/v1/runs/{run_id}/start", headers=auth_headers)
    assert start_response.status_code == 409, start_response.text


def test_project_task_delivery_records_round_trip_into_detail(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Delivery Records Project",
        task_title="Review this delivery",
    )
    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Review delivery evidence",
        status="running",
        node_payload={"project_task_id": task_id},
    )

    bundle_response = api_client.post(
        f"/api/v1/project-tasks/{task_id}/change-bundles",
        json={
            "runId": run_id,
            "nodeId": node["id"],
            "bundleKind": "patchset",
            "status": "submitted",
            "baseRef": "abc1234",
            "headRef": "def5678",
            "summary": "Initial delivery bundle",
            "commitCount": 2,
            "changedFiles": [
                {"path": "frontend/src/pages/ProjectTaskDetail.tsx", "status": "M"},
                {"path": "backend/project_execution/read_models.py", "status": "M"},
            ],
            "artifactManifest": {"deliverables": ["frontend/src/pages/ProjectTaskDetail.tsx"]},
        },
        headers=auth_headers,
    )
    assert bundle_response.status_code == 201, bundle_response.text
    bundle = bundle_response.json()
    assert bundle["nodeId"] == node["id"]

    evidence_response = api_client.post(
        f"/api/v1/project-tasks/{task_id}/evidence-bundles",
        json={
            "runId": run_id,
            "nodeId": node["id"],
            "summary": "Smoke evidence attached",
            "status": "collected",
            "bundle": {
                "acceptanceChecks": [{"item": "Task detail renders contract", "status": "pass"}],
                "testResults": ["frontend npm run type-check"],
            },
        },
        headers=auth_headers,
    )
    assert evidence_response.status_code == 201, evidence_response.text
    evidence = evidence_response.json()
    assert evidence["nodeId"] == node["id"]

    handoff_response = api_client.post(
        f"/api/v1/project-tasks/{task_id}/handoffs",
        json={
            "runId": run_id,
            "nodeId": node["id"],
            "stage": "dev_to_review",
            "fromActor": "developer",
            "toActor": "reviewer",
            "statusFrom": "in_progress",
            "statusTo": "in_review",
            "title": "Ready for review",
            "summary": "Please review the structured delivery",
            "payload": {"bundleId": bundle["id"], "evidenceBundleId": evidence["id"]},
        },
        headers=auth_headers,
    )
    assert handoff_response.status_code == 201, handoff_response.text
    handoff = handoff_response.json()
    assert handoff["nodeId"] == node["id"]

    issue_response = api_client.post(
        f"/api/v1/project-tasks/{task_id}/review-issues",
        json={
            "changeBundleId": bundle["id"],
            "evidenceBundleId": evidence["id"],
            "handoffId": handoff["id"],
            "issueKey": "ISS-1",
            "severity": "high",
            "category": "coverage",
            "acceptanceRef": "A1",
            "summary": "Missing regression evidence for dependency blocking state",
            "suggestion": "Add a regression assertion for blockingDependencyCount.",
            "status": "open",
        },
        headers=auth_headers,
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    issue_update_response = api_client.patch(
        f"/api/v1/project-tasks/{task_id}/review-issues/{issue['id']}",
        json={"status": "resolved"},
        headers=auth_headers,
    )
    assert issue_update_response.status_code == 200, issue_update_response.text
    assert issue_update_response.json()["status"] == "resolved"

    detail_response = api_client.get(
        f"/api/v1/project-tasks/{task_id}/detail",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    assert detail["latestChangeBundle"]["id"] == bundle["id"]
    assert detail["latestEvidenceBundle"]["id"] == evidence["id"]
    assert detail["handoffs"][0]["id"] == handoff["id"]
    assert detail["reviewIssues"][0]["id"] == issue["id"]
    assert detail["openIssueCount"] == 0


def test_project_task_attempts_endpoint_lists_related_runs(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Task Attempts Project",
        task_title="Attempted Task",
    )

    _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Attempt node",
        status="running",
    )

    attempts_response = api_client.get(
        f"/api/v1/project-tasks/{task_id}/attempts",
        headers=auth_headers,
    )
    assert attempts_response.status_code == 200, attempts_response.text
    attempts = attempts_response.json()
    assert len(attempts) >= 1
    assert attempts[0]["id"] == run_id
    assert attempts[0]["taskId"] == task_id
    assert attempts[0]["totalNodes"] >= 1


def test_attempt_alias_routes_return_run_semantics(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Attempt Alias Project",
        task_title="Alias Task",
    )

    attempts_response = api_client.get("/api/v1/attempts", headers=auth_headers)
    assert attempts_response.status_code == 200, attempts_response.text
    assert any(item["run_id"] == run_id for item in attempts_response.json())

    detail_response = api_client.get(f"/api/v1/attempts/{run_id}", headers=auth_headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["id"] == run_id
    assert detail["taskId"] == task_id


def test_run_nodes_and_runtime_sessions_endpoints(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Run Nodes Project",
        task_title="Node Task",
    )

    patch_run_response = api_client.patch(
        f"/api/v1/runs/{run_id}",
        json={
            "runtime_context": {
                "run_workspace": {"root_path": "/workspace/runs/node-task"},
                "execution_mode": "project_sandbox",
            }
        },
        headers=auth_headers,
    )
    assert patch_run_response.status_code == 200, patch_run_response.text

    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Node A",
        status="running",
        node_payload={
          "project_task_id": task_id,
          "execution_mode": "project_sandbox",
          "executor_kind": "agent",
          "runtime_type": "project_sandbox",
          "suggested_agent_ids": ["agent-a"],
        },
    )
    node_id = node["id"]

    with get_db_session() as session:
        task = session.query(ProjectTask).filter(ProjectTask.project_task_id == UUID(task_id)).first()
        assert task is not None
        registry = get_agent_registry()
        agent_info = registry.register_agent(
            name="Runtime Session Agent",
            agent_type="host_action_agent",
            owner_user_id=task.created_by_user_id,
            capabilities=["ops", "shell", "host_execution"],
            llm_provider=None,
            llm_model=None,
            access_level="private",
        )
        binding = ExternalAgentBinding(
            agent_id=agent_info.agent_id,
            machine_token_hash="hash",
            machine_token_prefix="pref",
            status="online",
        )
        session.add(binding)
        session.flush()
        dispatch = ExternalAgentDispatch(
            agent_id=agent_info.agent_id,
            binding_id=binding.binding_id,
            project_id=task.project_id,
            run_id=UUID(run_id),
            node_id=UUID(node_id),
            source_type="execution_node",
            source_id=node_id,
            runtime_type="external_worktree",
            request_payload={"run_workspace_root": "/workspace/runs/node-task"},
            result_payload={},
            status="running",
        )
        session.add(dispatch)
        session.commit()

    nodes_response = api_client.get(f"/api/v1/runs/{run_id}/nodes", headers=auth_headers)
    assert nodes_response.status_code == 200, nodes_response.text
    nodes = nodes_response.json()
    assert len(nodes) >= 1
    assert nodes[0]["runId"] == run_id
    assert nodes[0]["name"] == "Node A"

    sessions_response = api_client.get(
        f"/api/v1/runs/{run_id}/runtime-sessions",
        headers=auth_headers,
    )
    assert sessions_response.status_code == 200, sessions_response.text
    sessions = sessions_response.json()
    assert any(item["sessionType"] == "run_workspace" for item in sessions)
    assert any(item["sessionType"] == "external_dispatch" for item in sessions)


def test_execution_nodes_dual_write_from_run_steps(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Execution Nodes Dual Write",
        task_title="Mirror Step State",
    )

    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Mirror node",
        status="pending",
        node_payload={"project_task_id": task_id, "execution_mode": "project_sandbox"},
    )
    node_id = node["id"]

    with get_db_session() as session:
        stored_node = session.query(ExecutionNode).filter(ExecutionNode.node_id == UUID(node_id)).first()
        assert stored_node is not None
        assert stored_node.status == "pending"
        assert stored_node.name == "Mirror node"

    _complete_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=node_id,
        result_payload={"result": "ok"},
    )

    with get_db_session() as session:
        stored_node = session.query(ExecutionNode).filter(ExecutionNode.node_id == UUID(node_id)).first()
        assert stored_node is not None
        assert stored_node.status == "completed"
        assert stored_node.result_payload.get("result") == "ok"


def test_attempt_node_write_routes_sync_back_to_run_steps(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Attempt Node Write Routes",
        task_title="Node-first updates",
    )

    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Writable node",
        status="pending",
        node_payload={"project_task_id": task_id},
    )
    node_id = node["id"]

    update_response = api_client.patch(
        f"/api/v1/attempts/{run_id}/nodes/{node_id}",
        json={"status": "assigned", "name": "Writable node assigned"},
        headers=auth_headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["status"] == "assigned"
    assert update_response.json()["name"] == "Writable node assigned"

    with get_db_session() as session:
        step = session.query(ProjectTask).filter(ProjectTask.project_task_id == UUID(task_id)).first()
        assert step is not None
        run_step = session.query(ExecutionNode).filter(ExecutionNode.node_id == UUID(node_id)).first()
        assert run_step is not None

    node_detail = _get_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=node_id,
    )
    assert node_detail["status"] == "assigned"
    assert node_detail["name"] == "Writable node assigned"

    complete_response = api_client.post(
        f"/api/v1/attempts/{run_id}/nodes/{node_id}/complete",
        json={"status": "completed", "result_payload": {"outcome": "done"}},
        headers=auth_headers,
    )
    assert complete_response.status_code == 200, complete_response.text
    assert complete_response.json()["status"] == "completed"

    node_detail = _get_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=node_id,
    )
    assert node_detail["status"] == "completed"
    assert node_detail["resultPayload"]["outcome"] == "done"


def test_run_detail_endpoint_returns_timeline_and_deliverables(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Run Detail Aggregate",
        task_title="Publish Deliverable",
    )

    patch_run_response = api_client.patch(
        f"/api/v1/runs/{run_id}",
        json={
            "runtime_context": {
                "project_task_id": task_id,
                "task_title": "Publish Deliverable",
                "execution_mode": "project_sandbox",
                "planner_summary": "Create and publish a release note.",
                "planner_source": "fallback_heuristic",
                "agent_assignment": {
                    "executor_kind": "agent",
                    "agent_id": str(uuid4()),
                    "selection_reason": "Selected by test scheduler",
                    "provisioned_agent": False,
                    "runtime_type": "project_sandbox",
                },
                "run_workspace": {
                    "root_path": "/workspace/runs/test-run",
                },
            }
        },
        headers=auth_headers,
    )
    assert patch_run_response.status_code == 200, patch_run_response.text

    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Publish release note",
        status="running",
        node_payload={"project_task_id": task_id},
    )

    _complete_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=node["id"],
        result_payload={
            "artifacts": [
                {
                    "path": "/workspace/output/release-note.md",
                    "name": "release-note.md",
                }
            ]
        },
    )

    detail_response = api_client.get(f"/api/v1/runs/{run_id}/detail", headers=auth_headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    assert detail["id"] == run_id
    assert detail["projectId"]
    assert detail["plannerSummary"] == "Create and publish a release note."
    assert detail["timeline"]
    assert detail["deliverables"]
    assert detail["deliverables"][0]["path"] == "/workspace/output/release-note.md"
    assert detail["runWorkspaceRoot"] == "/workspace/runs/test-run"
    assert detail["executorAssignment"]["selectionReason"] == "Selected by test scheduler"
    assert detail["nodes"]
    assert detail["runtimeSessions"]


def test_create_project_task_and_launch_run_atomically(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Atomic Workflow Project",
            "description": "Exercise atomic task creation and launch.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Atomic Task",
            "description": "Create and start in one transaction.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()

    task = payload["task"]
    plan = payload["plan"]
    run = payload["run"]
    node = payload["node"]
    assignment = payload["executor_assignment"]
    workspace = payload["run_workspace"]

    assert task["project_id"] == project_id
    assert task["status"] == "assigned"
    assert task["plan_id"] == plan["plan_id"]
    assert task["run_id"] == run["run_id"]

    assert plan["project_id"] == project_id
    assert plan["status"] == "active"
    assert plan["definition"]["project_task_id"] == task["project_task_id"]

    assert run["project_id"] == project_id
    assert run["plan_id"] == plan["plan_id"]
    assert run["status"] == "scheduled"
    assert run["runtime_context"]["project_task_id"] == task["project_task_id"]
    assert run["started_at"] is None

    assert node["runId"] == run["run_id"]
    assert node["taskId"] == task["project_task_id"]
    assert node["status"] == "assigned"
    assert assignment["executor_kind"] == "agent"
    assert assignment["agent_id"] is not None
    assert assignment["node_id"] == node["id"]
    assert workspace["workspace_id"] == run["run_id"]

    get_task_response = api_client.get(
        f"/api/v1/project-tasks/{task['project_task_id']}",
        headers=auth_headers,
    )
    assert get_task_response.status_code == 200, get_task_response.text
    assert get_task_response.json()["run_id"] == run["run_id"]

    runs_list = api_client.get("/api/v1/runs", headers=auth_headers)
    assert runs_list.status_code == 200, runs_list.text
    assert any(item["run_id"] == run["run_id"] for item in runs_list.json())


def test_list_runs_reconciles_started_run_without_tasks(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Orphan Run Project",
            "description": "Run starts without any tasks.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    run_response = api_client.post(
        "/api/v1/runs",
        json={
            "project_id": project_id,
            "status": "queued",
            "trigger_source": "manual",
            "runtime_context": {},
        },
        headers=auth_headers,
    )
    assert run_response.status_code == 201, run_response.text
    run_id = run_response.json()["run_id"]

    start_response = api_client.post(f"/api/v1/runs/{run_id}/start", headers=auth_headers)
    assert start_response.status_code == 200, start_response.text
    assert start_response.json()["status"] == "running"

    runs_response = api_client.get("/api/v1/runs", headers=auth_headers)
    assert runs_response.status_code == 200, runs_response.text
    reconciled_run = next(item for item in runs_response.json() if item["run_id"] == run_id)
    assert reconciled_run["status"] == "completed"
    assert reconciled_run["completed_at"] is not None

    with get_db_session() as session:
        stored_run = session.query(ProjectRun).filter(ProjectRun.run_id == UUID(run_id)).first()
        assert stored_run is not None
        assert stored_run.status == "completed"
        assert stored_run.completed_at is not None


def test_delete_project_task_reconciles_associated_run(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Delete Reconcile Project",
        task_title="Only Task",
    )

    delete_response = api_client.delete(
        f"/api/v1/project-tasks/{task_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "completed"
    assert run_response.json()["completed_at"] is not None

    with get_db_session() as session:
        stored_run = session.query(ProjectRun).filter(ProjectRun.run_id == UUID(run_id)).first()
        assert stored_run is not None
        assert stored_run.status == "completed"
        assert stored_run.completed_at is not None


def test_complete_run_step_reconciles_task_run_and_project(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Single Step Completion Project",
        task_title="Finalize Release Notes",
    )

    task_response = api_client.get(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200, task_response.text
    project_id = task_response.json()["project_id"]

    node = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Finalize Release Notes",
        status="running",
        node_payload={"project_task_id": task_id},
    )

    _complete_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=node["id"],
        result_payload={
            "artifacts": [{"path": "/workspace/output/release-notes.md", "name": "release-notes.md"}]
        },
    )

    task_response = api_client.get(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200, task_response.text
    assert task_response.json()["status"] == "completed"

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "completed"

    project_response = api_client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert project_response.status_code == 200, project_response.text
    assert project_response.json()["status"] == "completed"


def test_project_status_prefers_latest_success_over_historical_failure(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Recovered Status Project",
            "description": "Latest success should drive project status.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    failed_task_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Old failed task",
            "description": "Historical failure",
            "status": "failed",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert failed_task_response.status_code == 201, failed_task_response.text

    completed_task_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Latest successful task",
            "description": "Recovery succeeded",
            "status": "completed",
            "priority": "normal",
            "sort_order": 1,
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert completed_task_response.status_code == 201, completed_task_response.text

    current_project_response = api_client.get(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert current_project_response.status_code == 200, current_project_response.text
    assert current_project_response.json()["status"] == "completed"


def test_complete_first_run_step_keeps_task_open_until_all_steps_finish(
    api_client: TestClient, auth_headers: dict[str, str]
):
    task_id, run_id = _create_project_and_running_task_run(
        api_client,
        auth_headers,
        project_name="Multi Step Internal Project",
        task_title="Ship Launch Checklist",
    )

    task_response = api_client.get(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200, task_response.text
    project_id = task_response.json()["project_id"]

    first_step = _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Research: Ship Launch Checklist",
        status="running",
        sequence_number=0,
        node_payload={"project_task_id": task_id, "step_kind": "research"},
    )

    _create_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        task_id=task_id,
        name="Review: Ship Launch Checklist",
        status="pending",
        sequence_number=1,
        node_payload={"project_task_id": task_id, "step_kind": "review"},
    )

    _complete_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=first_step["id"],
        result_payload={},
    )

    task_response = api_client.get(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200, task_response.text
    assert task_response.json()["status"] == "queued"

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "running"

    project_response = api_client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert project_response.status_code == 200, project_response.text
    assert project_response.json()["status"] == "running"


def test_terminal_run_retires_ephemeral_current_run_agents(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Ephemeral Cleanup Project",
            "description": "Ensure temporary run agents are retired.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]
    owner_user_id = project_response.json()["created_by_user_id"]

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Failing Task",
            "description": "Fail and retire ephemeral agent.",
            "priority": "normal",
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    task_id = payload["task"]["project_task_id"]
    run_id = payload["run"]["run_id"]

    registry = get_agent_registry()
    agent_info = registry.register_agent(
        name="Ephemeral Run Agent",
        agent_type="project_temp_agent",
        owner_user_id=UUID(owner_user_id),
        capabilities=["implementation"],
        access_level="private",
        runtime_preference="project_sandbox",
        project_scope_id=UUID(project_id),
        is_ephemeral=True,
        lifecycle_scope="current_run",
    )
    registry.update_agent(agent_id=agent_info.agent_id, status="idle")

    with get_db_session() as session:
        task = session.query(ProjectTask).filter(ProjectTask.project_task_id == UUID(task_id)).first()
        run = session.query(ProjectRun).filter(ProjectRun.run_id == UUID(run_id)).first()
        assert task is not None
        assert run is not None
        task.assignee_agent_id = agent_info.agent_id
        task.status = "failed"
        task.error_message = "External agent is not online"
        run.status = "failed"
        run.error_message = "External agent is not online"
        run.completed_at = datetime.now(timezone.utc)
        run.runtime_context = {
            **(run.runtime_context or {}),
            "agent_assignment": {
                "agent_id": str(agent_info.agent_id),
                "selection_reason": "Provisioned temporary internal implementation agent for this run",
                "provisioned_agent": True,
                "runtime_type": "project_sandbox",
            },
        }
        session.commit()

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "failed"

    with get_db_session() as session:
        stored_agent = session.query(Agent).filter(Agent.agent_id == agent_info.agent_id).first()
        assert stored_agent is not None
        assert stored_agent.retired_at is not None

    agents_response = api_client.get("/api/v1/agents", headers=auth_headers)
    assert agents_response.status_code == 200, agents_response.text
    returned_ids = {item["id"] for item in agents_response.json()}
    assert str(agent_info.agent_id) not in returned_ids


def _provision_bound_external_agent(
    api_client: TestClient,
    auth_headers: dict[str, str],
    *,
    project_id: str,
    owner_user_id: str,
    name: str,
    current_version: str = CURRENT_EXTERNAL_RUNTIME_VERSION,
) -> tuple[str, str]:
    registry = get_agent_registry()
    agent_info = registry.register_agent(
        name=name,
        agent_type="host_action_agent",
        owner_user_id=UUID(owner_user_id),
        capabilities=["ops", "shell", "host_execution"],
        llm_provider=None,
        llm_model=None,
        access_level="private",
        runtime_preference="external_worktree",
        project_scope_id=UUID(project_id),
    )
    registry.update_agent(agent_id=agent_info.agent_id, status="idle")

    binding_response = api_client.post(
        f"/api/v1/projects/{project_id}/agent-bindings",
        json={
            "agent_id": str(agent_info.agent_id),
            "role_hint": "host executor",
            "priority": 100,
            "status": "active",
            "allowed_step_kinds": ["host_action"],
            "preferred_skills": ["ops", "shell", "host_execution"],
            "preferred_runtime_types": ["external_worktree"],
        },
        headers=auth_headers,
    )
    assert binding_response.status_code == 201, binding_response.text

    install_command_response = api_client.post(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/install-command",
        json={"target_os": "linux"},
        headers=auth_headers,
    )
    assert install_command_response.status_code == 200, install_command_response.text
    command = install_command_response.json()["command"]
    install_code = command.split("code=", 1)[1].split()[0].split("|")[0].strip("'\"")

    bootstrap_response = api_client.post(
        "/api/v1/external-runtime/bootstrap",
        json={
            "agent_id": str(agent_info.agent_id),
            "install_code": install_code,
            "host_name": "test-host",
            "host_os": "linux",
            "host_arch": "amd64",
            "host_fingerprint": f"fingerprint-{agent_info.agent_id}",
            "current_version": current_version,
            "metadata": {},
        },
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    machine_token = bootstrap_response.json()["machine_token"]
    return str(agent_info.agent_id), machine_token


def test_external_runtime_conversation_workspace_upload_and_download_roundtrip(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Conversation Workspace Project",
            "description": "Roundtrip Runtime Host workspace snapshots.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project["project_id"],
        owner_user_id=project["created_by_user_id"],
        name="Runtime Conversation Workspace Agent",
    )

    with get_db_session() as session:
        conversation = AgentConversation(
            agent_id=UUID(agent_id),
            owner_user_id=UUID(project["created_by_user_id"]),
            title="Runtime Host Conversation",
            status="active",
            source="web",
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        conversation_id = str(conversation.conversation_id)

    archive_bytes = _build_workspace_archive({"output/result.txt": "hello from runtime"})
    host_headers = {"Authorization": f"Bearer {machine_token}"}
    upload_response = api_client.post(
        f"/api/v1/external-runtime/conversations/{conversation_id}/workspace/upload",
        json={
            "archive_base64": base64.b64encode(archive_bytes).decode("utf-8"),
            "workspace_bytes_estimate": 18,
            "workspace_file_count_estimate": 1,
            "snapshot_status": "ready",
        },
        headers=host_headers,
    )
    assert upload_response.status_code == 200, upload_response.text
    assert upload_response.json()["generation"] == 1

    download_response = api_client.get(
        f"/api/v1/external-runtime/conversations/{conversation_id}/workspace/download",
        headers=host_headers,
    )
    assert download_response.status_code == 200, download_response.text
    payload = download_response.json()
    assert payload["generation"] == 1
    restored_bytes = base64.b64decode(payload["archive_base64"].encode("utf-8"))
    assert restored_bytes


def test_external_runtime_run_workspace_upload_and_download_roundtrip(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Run Workspace Project",
            "description": "Roundtrip project run workspace through Runtime Host.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    _agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Runtime Run Workspace Agent",
    )

    run_id = None
    with get_db_session() as session:
        run = ProjectRun(
            project_id=UUID(project_id),
            status="scheduled",
            trigger_source="manual",
            runtime_context={},
            requested_by_user_id=UUID(owner_user_id),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        get_run_workspace_manager().create_run_workspace(UUID(project_id), run.run_id)
        ExternalRuntimeService(session).create_dispatch(
            agent_id=UUID(_agent_id),
            source_type="project_run_step",
            source_id=str(run.run_id),
            runtime_type="external_worktree",
            project_id=UUID(project_id),
            run_id=run.run_id,
            request_payload={
                "run_id": str(run.run_id),
                "step_kind": "host_action",
                "execution_prompt": "Prepare the host workspace.",
            },
        )
        run_id = str(run.run_id)
    assert run_id

    host_headers = {"Authorization": f"Bearer {machine_token}"}
    host_download_response = api_client.get(
        f"/api/v1/external-runtime/runs/{run_id}/workspace/download",
        headers=host_headers,
    )
    assert host_download_response.status_code == 200, host_download_response.text
    assert host_download_response.json()["archive_base64"]

    archive_bytes = _build_workspace_archive({"output/runtime-result.txt": "hello run workspace"})
    host_upload_response = api_client.post(
        f"/api/v1/external-runtime/runs/{run_id}/workspace/upload",
        json={
            "archive_base64": base64.b64encode(archive_bytes).decode("utf-8"),
            "workspace_bytes_estimate": 19,
            "workspace_file_count_estimate": 1,
            "snapshot_status": "ready",
        },
        headers=host_headers,
    )
    assert host_upload_response.status_code == 200, host_upload_response.text

    user_download_response = api_client.get(
        f"/api/v1/runs/{run_id}/workspace/download",
        params={"path": "output/runtime-result.txt"},
        headers=auth_headers,
    )
    assert user_download_response.status_code == 200, user_download_response.text
    assert "hello run workspace" in user_download_response.text


def test_external_runtime_installer_scripts_render_real_service_setup(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Installer Script Project",
            "description": "Exercise runtime installer scripts.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    registry = get_agent_registry()
    agent_info = registry.register_agent(
        name="Installer Script External Agent",
        agent_type="host_action_agent",
        owner_user_id=UUID(project["created_by_user_id"]),
        capabilities=["ops", "shell", "host_execution"],
        llm_provider=None,
        llm_model=None,
        access_level="private",
        runtime_preference="external_worktree",
        project_scope_id=UUID(project["project_id"]),
    )
    registry.update_agent(agent_id=agent_info.agent_id, status="idle")
    with get_db_session() as session:
        ExternalRuntimeService(session).update_profile(
            agent_id=agent_info.agent_id,
        )

    install_command_response = api_client.post(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/install-command",
        json={"target_os": "linux"},
        headers=auth_headers,
    )
    assert install_command_response.status_code == 200, install_command_response.text
    install_command = install_command_response.json()["command"]
    install_url = urlsplit(
        install_command.replace("curl -fsSL ", "", 1).split(" | ", 1)[0].strip("'")
    )
    install_script_response = api_client.get(f"{install_url.path}?{install_url.query}")
    assert install_script_response.status_code == 200, install_script_response.text
    install_script = install_script_response.text
    assert "systemctl --user enable --now" in install_script
    assert "launchctl kickstart -k" in install_script
    assert "api/v1/external-runtime/bootstrap" in install_script
    assert "linx_external_runtime.py" in install_script

    update_command_response = api_client.post(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/update-command",
        json={"target_os": "linux"},
        headers=auth_headers,
    )
    assert update_command_response.status_code == 200, update_command_response.text
    update_command = update_command_response.json()["command"]
    update_url = urlsplit(
        update_command.replace("curl -fsSL ", "", 1).split(" | ", 1)[0].strip("'")
    )
    update_script_response = api_client.get(f"{update_url.path}?{update_url.query}")
    assert update_script_response.status_code == 200, update_script_response.text
    assert "systemctl --user restart" in update_script_response.text

    install_ps1_response = api_client.get(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/install.ps1?target=windows&code=demo-code"
    )
    assert install_ps1_response.status_code == 200, install_ps1_response.text
    assert "Register-ScheduledTask" in install_ps1_response.text
    assert "linx_external_runtime.py" in install_ps1_response.text

    update_ps1_response = api_client.get(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/update.ps1?target=windows"
    )
    assert update_ps1_response.status_code == 200, update_ps1_response.text
    assert "Start-ScheduledTask" in update_ps1_response.text

    uninstall_command_response = api_client.post(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/uninstall-command",
        json={"target_os": "linux"},
        headers=auth_headers,
    )
    assert uninstall_command_response.status_code == 200, uninstall_command_response.text
    uninstall_command = uninstall_command_response.json()["command"]
    uninstall_url = urlsplit(
        uninstall_command.replace("curl -fsSL ", "", 1).split(" | ", 1)[0].strip("'")
    )
    uninstall_script_response = api_client.get(f"{uninstall_url.path}?{uninstall_url.query}")
    assert uninstall_script_response.status_code == 200, uninstall_script_response.text
    uninstall_script = uninstall_script_response.text
    assert "/api/v1/external-runtime/self-unregister" in uninstall_script
    assert "systemctl --user disable --now" in uninstall_script

    uninstall_ps1_response = api_client.get(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/uninstall.ps1?target=windows"
    )
    assert uninstall_ps1_response.status_code == 200, uninstall_ps1_response.text
    assert "Unregister-ScheduledTask" in uninstall_ps1_response.text
    assert "/api/v1/external-runtime/self-unregister" in uninstall_ps1_response.text


def test_external_runtime_overview_includes_local_status_metadata(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Local Status Project",
            "description": "Expose local runtime status metadata.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project["project_id"],
        owner_user_id=project["created_by_user_id"],
        name="Runtime Local Status Agent",
    )

    heartbeat_response = api_client.post(
        "/api/v1/external-runtime/heartbeat",
        json={
            "host_name": "test-host",
            "host_os": "linux",
            "host_arch": "amd64",
            "host_fingerprint": f"fingerprint-{agent_id}",
            "current_version": "0.1.0",
            "status": "online",
            "metadata": {
                "local_status_url": "http://127.0.0.1:45123/",
                "local_status_port": 45123,
                "last_dispatch_action": "update_runtime",
                "last_dispatch_status": "completed",
                "last_dispatch_error_message": "",
            },
        },
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert heartbeat_response.status_code == 200, heartbeat_response.text

    overview_response = api_client.get(
        f"/api/v1/agents/{agent_id}/external-runtime",
        headers=auth_headers,
    )
    assert overview_response.status_code == 200, overview_response.text
    overview = overview_response.json()
    assert overview["state"]["localStatusUrl"] == "http://127.0.0.1:45123/"
    assert overview["state"]["localStatusPort"] == 45123
    assert overview["state"]["lastDispatchAction"] == "update_runtime"
    assert overview["state"]["lastDispatchStatus"] == "completed"


def test_request_runtime_update_creates_maintenance_dispatch(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Update Dispatch Project",
            "description": "Create a maintenance dispatch for runtime update.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project["project_id"],
        owner_user_id=project["created_by_user_id"],
        name="Runtime Update Dispatch Agent",
    )

    response = api_client.post(
        f"/api/v1/agents/{agent_id}/external-runtime/request-update",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_type"] == "maintenance"
    assert payload["source_id"] == "update_runtime"
    assert payload["request_payload"]["control_action"] == "update_runtime"

    dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch = dispatch_response.json()
    assert dispatch["dispatch_id"] == payload["dispatch_id"]
    assert dispatch["request_payload"]["control_action"] == "update_runtime"


def test_request_runtime_uninstall_creates_maintenance_dispatch(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Uninstall Dispatch Project",
            "description": "Create a maintenance dispatch for runtime uninstall.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project["project_id"],
        owner_user_id=project["created_by_user_id"],
        name="Runtime Uninstall Dispatch Agent",
    )

    response = api_client.post(
        f"/api/v1/agents/{agent_id}/external-runtime/request-uninstall",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_type"] == "maintenance"
    assert payload["source_id"] == "uninstall_runtime"
    assert payload["request_payload"]["control_action"] == "uninstall_runtime"

    dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch = dispatch_response.json()
    assert dispatch["dispatch_id"] == payload["dispatch_id"]
    assert dispatch["request_payload"]["control_action"] == "uninstall_runtime"


def test_request_runtime_uninstall_revokes_binding_and_rejects_future_heartbeats(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Uninstall Completion Project",
            "description": "Complete runtime uninstall flow and reject future heartbeats.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project["project_id"],
        owner_user_id=project["created_by_user_id"],
        name="Runtime Uninstall Completion Agent",
    )
    host_headers = {"Authorization": f"Bearer {machine_token}"}

    request_response = api_client.post(
        f"/api/v1/agents/{agent_id}/external-runtime/request-uninstall",
        headers=auth_headers,
    )
    assert request_response.status_code == 200, request_response.text
    dispatch_id = request_response.json()["dispatch_id"]

    next_dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers=host_headers,
    )
    assert next_dispatch_response.status_code == 200, next_dispatch_response.text
    assert next_dispatch_response.json()["dispatch_id"] == dispatch_id

    ack_response = api_client.post(
        f"/api/v1/external-runtime/dispatches/{dispatch_id}/ack",
        json={"status": "running", "result_payload": {"maintenance": True}},
        headers=host_headers,
    )
    assert ack_response.status_code == 200, ack_response.text

    complete_response = api_client.post(
        f"/api/v1/external-runtime/dispatches/{dispatch_id}/complete",
        json={
            "status": "completed",
            "result_payload": {"mode": "uninstall_runtime", "cleanup_required": True},
        },
        headers=host_headers,
    )
    assert complete_response.status_code == 200, complete_response.text

    unregister_response = api_client.post(
        "/api/v1/external-runtime/self-unregister",
        headers=host_headers,
    )
    assert unregister_response.status_code == 200, unregister_response.text

    heartbeat_response = api_client.post(
        "/api/v1/external-runtime/heartbeat",
        json={
            "host_name": "test-host",
            "host_os": "linux",
            "host_arch": "amd64",
            "host_fingerprint": f"fingerprint-{agent_id}",
            "current_version": "0.1.0",
            "status": "online",
            "metadata": {},
        },
        headers=host_headers,
    )
    assert heartbeat_response.status_code == 401, heartbeat_response.text
    heartbeat_payload = heartbeat_response.json()
    heartbeat_detail = heartbeat_payload.get("detail") or heartbeat_payload.get("message")
    assert heartbeat_detail in {
        "external_agent_binding_revoked",
        "external_agent_machine_token_invalid",
    }

    overview_response = api_client.get(
        f"/api/v1/agents/{agent_id}/external-runtime",
        headers=auth_headers,
    )
    assert overview_response.status_code == 200, overview_response.text
    overview = overview_response.json()
    assert overview["state"]["status"] == "uninstalled"
    assert overview["state"]["bound"] is False


def test_external_runtime_can_reinstall_after_revoked_binding(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Runtime Reinstall Project",
            "description": "Allow reinstall after a previous binding was revoked.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project["project_id"],
        owner_user_id=project["created_by_user_id"],
        name="Runtime Reinstall Agent",
    )
    host_headers = {"Authorization": f"Bearer {machine_token}"}

    unregister_response = api_client.post(
        "/api/v1/external-runtime/self-unregister",
        headers=host_headers,
    )
    assert unregister_response.status_code == 200, unregister_response.text

    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        row, code = service.create_install_token(
            agent_id=UUID(agent_id),
            created_by_user_id=UUID(project["created_by_user_id"]),
        )
        session.commit()
        assert row.status == "active"

    bootstrap_response = api_client.post(
        "/api/v1/external-runtime/bootstrap",
        json={
            "agent_id": agent_id,
            "install_code": code,
            "host_name": "reinstall-host",
            "host_os": "darwin",
            "host_arch": "arm64",
            "host_fingerprint": f"reinstall-{agent_id}",
            "current_version": CURRENT_EXTERNAL_RUNTIME_VERSION,
            "metadata": {},
        },
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    assert bootstrap_response.json()["machine_token"].startswith("lxem_")


def test_host_action_dispatch_uses_native_executor_payload(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Native External Dispatch",
            "description": "Use the native external runtime executor payload.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Platform Default Agent",
    )

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy app to host with platform default",
            "description": "SSH to host and deploy the app with the native runtime executor.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text

    dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch = dispatch_response.json()
    assert dispatch["agent_id"] == agent_id
    assert dispatch["source_type"] == "execution_node"
    assert dispatch["request_payload"]["node_id"]
    assert dispatch["request_payload"]["step_kind"] == "host_action"
    assert "launch_command_template" not in dispatch["request_payload"]
    assert "launch_command_source" not in dispatch["request_payload"]
    assert dispatch["request_payload"]["execution_prompt"]


def test_host_action_dispatch_blocks_when_runtime_upgrade_is_required(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Outdated Runtime Host",
            "description": "Block host action dispatch when the Runtime Host is outdated.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    _agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Agent Override Agent",
        current_version="0.1.0",
    )

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy host assets with outdated runtime",
            "description": "Deploy files to the remote host even though the Runtime Host needs an upgrade.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text

    dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert dispatch_response.status_code == 404, dispatch_response.text
    payload = create_and_launch_response.json()
    assert payload["agent_assignment"]["dispatch_id"] is None
    assert "upgrade" in payload["agent_assignment"]["selection_reason"].lower()
    assert payload["node"]["status"] == "blocked"
    assert payload["run"]["status"] == "blocked"


def test_host_action_task_without_external_runtime_blocks_clearly(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Host Action Without External Runtime",
            "description": "Ensure host-action requires explicit external runtime.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy app to host",
            "description": "SSH to host and deploy the app.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    assert payload["run"]["status"] == "blocked"
    assert (
        payload["run"]["error_message"]
        == "No external runtime is configured for this host-action step. Bind an external agent in the Project Agent Pool and configure its launch command."
    )
    assert payload["agent_assignment"]["agent_id"] is None

    with get_db_session() as session:
        ephemeral_agents = (
            session.query(Agent)
            .filter(Agent.project_scope_id == UUID(project_id))
            .filter(Agent.is_ephemeral.is_(True))
            .all()
        )
        assert ephemeral_agents == []


def test_project_sandbox_execution_mode_overrides_host_keyword_inference(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Forced Sandbox Project",
            "description": "Force project sandbox even with deploy keywords.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy app to host",
            "description": "SSH to server and deploy the app.",
            "priority": "normal",
            "input_payload": {
                "execution_mode": "project_sandbox",
            },
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    assert payload["task"]["input_payload"]["execution_mode"] == "project_sandbox"
    assert payload["node"]["executionMode"] == "project_sandbox"
    assert payload["node"]["nodePayload"]["step_kind"] == "implementation"
    assert payload["agent_assignment"]["runtime_type"] == "project_sandbox"
    assert payload["run"]["status"] == "scheduled"
    assert payload["run"]["error_message"] is None


def test_host_action_task_creates_external_dispatch(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Host Action Project",
            "description": "Exercise external dispatch flow.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Bound External Agent 1",
    )

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy app to host",
            "description": "SSH to host and deploy the app.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    assert payload["agent_assignment"]["executor_kind"] == "agent"
    assert payload["agent_assignment"]["agent_id"] == agent_id
    assert payload["agent_assignment"]["dispatch_id"] is not None
    assert payload["agent_assignment"]["node_id"] is not None
    assert payload["agent_assignment"]["runtime_type"] == "external_worktree"
    assert payload["external_dispatch"]["status"] == "pending"
    assert payload["external_dispatch"]["node_id"] == payload["agent_assignment"]["node_id"]
    assert payload["node"]["id"] == payload["agent_assignment"]["node_id"]
    assert payload["node"]["status"] == "queued"
    assert payload["run"]["status"] == "scheduled"

    dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch = dispatch_response.json()
    assert dispatch["dispatch_id"] == payload["external_dispatch"]["dispatch_id"]
    assert dispatch["node_id"] == payload["agent_assignment"]["node_id"]
    assert dispatch["node_id"] == payload["node"]["id"]


def test_external_dispatch_completion_updates_run_state(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Dispatch Completion Project",
            "description": "Exercise external dispatch completion flow.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    agent_id, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Bound External Agent 2",
    )
    assert agent_id

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy host assets",
            "description": "Deploy files to remote host.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    run_id = payload["run"]["run_id"]
    node_id = payload["node"]["id"]
    dispatch_id = payload["external_dispatch"]["dispatch_id"]
    host_headers = {"Authorization": f"Bearer {machine_token}"}

    ack_response = api_client.post(
        f"/api/v1/external-runtime/dispatches/{dispatch_id}/ack",
        json={"status": "running", "result_payload": {}},
        headers=host_headers,
    )
    assert ack_response.status_code == 200, ack_response.text

    complete_response = api_client.post(
        f"/api/v1/external-runtime/dispatches/{dispatch_id}/complete",
        json={"status": "completed", "result_payload": {"stdout": "done"}},
        headers=host_headers,
    )
    assert complete_response.status_code == 200, complete_response.text
    assert complete_response.json()["status"] == "completed"

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "completed"

    node_response = _get_attempt_node(
        api_client,
        auth_headers,
        run_id=run_id,
        node_id=node_id,
    )
    assert node_response["status"] == "completed"


def test_external_dispatch_completion_keeps_task_open_with_pending_followup_step(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Dispatch Multi Step Project",
            "description": "Ensure external completion does not close multi-step tasks early.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    _, machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Bound External Agent Multi Step",
    )

    task_response = api_client.post(
        "/api/v1/project-tasks",
        json={
            "project_id": project_id,
            "title": "Deploy host assets",
            "description": "Ship assets in multiple external phases.",
            "status": "queued",
            "priority": "normal",
            "sort_order": 0,
            "input_payload": {"execution_mode": "external_runtime"},
            "execution_mode": "external_runtime",
        },
        headers=auth_headers,
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["project_task_id"]

    run_response = api_client.post(
        "/api/v1/runs",
        json={
            "project_id": project_id,
            "status": "queued",
            "trigger_source": "manual",
            "runtime_context": {
                "project_task_id": task_id,
                "task_title": "Deploy host assets",
                "execution_mode": "external_runtime",
            },
        },
        headers=auth_headers,
    )
    assert run_response.status_code == 201, run_response.text
    run_id = run_response.json()["run_id"]

    patch_task_response = api_client.patch(
        f"/api/v1/project-tasks/{task_id}",
        json={
            "run_id": run_id,
            "status": "queued",
            "input_payload": {"execution_mode": "external_runtime"},
        },
        headers=auth_headers,
    )
    assert patch_task_response.status_code == 200, patch_task_response.text

    for sequence_number, step_name in enumerate(
        ["Upload host assets", "Verify host assets"],
    ):
        _create_attempt_node(
            api_client,
            auth_headers,
            run_id=run_id,
            task_id=task_id,
            name=step_name,
            status="pending",
            sequence_number=sequence_number,
            node_payload={
                "project_task_id": task_id,
                "step_kind": "host_action",
                "executor_kind": "execution_node",
                "execution_mode": "external_runtime",
            },
        )

    schedule_response = api_client.post(
        f"/api/v1/runs/{run_id}/schedule",
        headers=auth_headers,
    )
    assert schedule_response.status_code == 200, schedule_response.text
    dispatch_id = schedule_response.json()["external_dispatch"]["dispatch_id"]
    host_headers = {"Authorization": f"Bearer {machine_token}"}

    complete_response = api_client.post(
        f"/api/v1/external-runtime/dispatches/{dispatch_id}/complete",
        json={"status": "completed", "result_payload": {"stdout": "phase one done"}},
        headers=host_headers,
    )
    assert complete_response.status_code == 200, complete_response.text

    task_response = api_client.get(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200, task_response.text
    assert task_response.json()["status"] == "queued"

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "scheduled"


def test_project_and_run_workspace_endpoints_list_download_and_reject_invalid_access(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Workspace Browser Project",
            "description": "Expose project and run workspace files.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Prepare workspace output",
            "description": "Generate files for workspace browsing.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    run_id = payload["run"]["run_id"]
    run_workspace_root = Path(payload["run_workspace"]["root_path"])

    project_space_response = api_client.get(
        f"/api/v1/project-space/{project_id}",
        headers=auth_headers,
    )
    assert project_space_response.status_code == 200, project_space_response.text
    project_workspace_root = Path(project_space_response.json()["root_path"])

    (project_workspace_root / "output").mkdir(parents=True, exist_ok=True)
    (project_workspace_root / "output" / "final-report.md").write_text(
        "# Final report\n", encoding="utf-8"
    )
    (project_workspace_root / ".linx").mkdir(parents=True, exist_ok=True)
    (project_workspace_root / ".linx" / "secret.txt").write_text("hidden", encoding="utf-8")

    (run_workspace_root / "output").mkdir(parents=True, exist_ok=True)
    (run_workspace_root / "output" / "draft-report.md").write_text(
        "# Draft report\n", encoding="utf-8"
    )
    (run_workspace_root / ".linx").mkdir(parents=True, exist_ok=True)
    (run_workspace_root / ".linx" / "secret.txt").write_text("hidden", encoding="utf-8")

    list_project_files_response = api_client.get(
        f"/api/v1/project-space/{project_id}/files",
        params={"recursive": True},
        headers=auth_headers,
    )
    assert list_project_files_response.status_code == 200, list_project_files_response.text
    project_paths = {item["path"] for item in list_project_files_response.json()}
    assert "output/final-report.md" in project_paths
    assert ".linx/secret.txt" not in project_paths

    download_project_file_response = api_client.get(
        f"/api/v1/project-space/{project_id}/download",
        params={"path": "output/final-report.md"},
        headers=auth_headers,
    )
    assert download_project_file_response.status_code == 200, download_project_file_response.text
    assert "# Final report" in download_project_file_response.text

    invalid_project_download_response = api_client.get(
        f"/api/v1/project-space/{project_id}/download",
        params={"path": "../outside.txt"},
        headers=auth_headers,
    )
    assert invalid_project_download_response.status_code == 400

    list_run_files_response = api_client.get(
        f"/api/v1/runs/{run_id}/workspace/files",
        params={"recursive": True},
        headers=auth_headers,
    )
    assert list_run_files_response.status_code == 200, list_run_files_response.text
    run_paths = {item["path"] for item in list_run_files_response.json()}
    assert "output/draft-report.md" in run_paths
    assert ".linx/secret.txt" not in run_paths

    download_run_file_response = api_client.get(
        f"/api/v1/runs/{run_id}/workspace/download",
        params={"path": "output/draft-report.md"},
        headers=auth_headers,
    )
    assert download_run_file_response.status_code == 200, download_run_file_response.text
    assert "# Draft report" in download_run_file_response.text

    invalid_run_download_response = api_client.get(
        f"/api/v1/runs/{run_id}/workspace/download",
        params={"path": "../outside.txt"},
        headers=auth_headers,
    )
    assert invalid_run_download_response.status_code == 400

    other_headers = _register_auth_headers(api_client)
    forbidden_project_response = api_client.get(
        f"/api/v1/project-space/{project_id}/files",
        params={"recursive": True},
        headers=other_headers,
    )
    assert forbidden_project_response.status_code == 404

    forbidden_run_response = api_client.get(
        f"/api/v1/runs/{run_id}/workspace/files",
        params={"recursive": True},
        headers=other_headers,
    )
    assert forbidden_run_response.status_code == 404
