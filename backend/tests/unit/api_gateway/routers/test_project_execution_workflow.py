"""Workflow tests for the project execution platform skeleton."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api_gateway.main import create_app
from database.connection import get_db_session
from database.project_execution_models import ProjectRun

pytestmark = [pytest.mark.usefixtures("cleanup_shared_db_test_artifacts")]


@pytest.fixture
def api_client():
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers(api_client: TestClient):
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

    step_response = api_client.post(
        "/api/v1/run-steps",
        json={
            "run_id": run_id,
            "project_task_id": task_id,
            "name": "Execute initial task",
            "step_type": "task",
            "status": "pending",
            "sequence_number": 0,
            "input_payload": {"project_task_id": task_id},
        },
        headers=auth_headers,
    )
    assert step_response.status_code == 201, step_response.text
    step = step_response.json()
    assert step["run_id"] == run_id

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
    step = payload["step"]
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

    assert step["run_id"] == run["run_id"]
    assert assignment["executor_kind"] == "agent"
    assert assignment["agent_id"] is not None
    assert workspace["workspace_id"] == run["run_id"]
    assert step["project_task_id"] == task["project_task_id"]
    assert step["status"] == "assigned"

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

    delete_response = api_client.delete(f"/api/v1/project-tasks/{task_id}", headers=auth_headers)
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


def test_host_action_task_creates_execution_lease(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Host Action Project",
            "description": "Exercise external execution node dispatch.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    node_response = api_client.post(
        "/api/v1/execution-nodes/register",
        json={
            "project_id": project_id,
            "name": "Host Node 1",
            "node_type": "external_cli",
            "capabilities": ["host_execution", "ops", "shell"],
            "config": {"paths": ["/tmp"]},
        },
        headers=auth_headers,
    )
    assert node_response.status_code == 201, node_response.text
    node_id = node_response.json()["node_id"]

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
    assert payload["agent_assignment"]["agent_id"] is not None
    assert payload["agent_assignment"]["node_id"] == node_id
    assert payload["agent_assignment"]["runtime_type"] == "external_worktree"
    assert payload["runtime_binding"]["execution_node_id"] == node_id
    assert payload["external_session"]["execution_node_id"] == node_id
    assert payload["external_session"]["status"] == "pending"
    assert payload["step"]["status"] == "leased"
    assert payload["run"]["status"] == "scheduled"

    leases_response = api_client.get(f"/api/v1/execution-nodes/{node_id}/leases", headers=auth_headers)
    assert leases_response.status_code == 200, leases_response.text
    leases = leases_response.json()
    assert len(leases) == 1
    assert leases[0]["run_step_id"] == payload["step"]["run_step_id"]


def test_execution_lease_completion_updates_run_state(
    api_client: TestClient, auth_headers: dict[str, str]
):
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Lease Completion Project",
            "description": "Exercise lease completion flow.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    node_response = api_client.post(
        "/api/v1/execution-nodes/register",
        json={
            "project_id": project_id,
            "name": "Host Node 2",
            "node_type": "external_cli",
            "capabilities": ["host_execution", "ops", "shell"],
            "config": {},
        },
        headers=auth_headers,
    )
    assert node_response.status_code == 201, node_response.text
    node_id = node_response.json()["node_id"]

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
    step_id = payload["step"]["run_step_id"]

    leases_response = api_client.get(f"/api/v1/execution-nodes/{node_id}/leases", headers=auth_headers)
    assert leases_response.status_code == 200, leases_response.text
    lease_id = leases_response.json()[0]["lease_id"]

    ack_response = api_client.post(
        f"/api/v1/execution-nodes/{node_id}/leases/{lease_id}/ack",
        json={"status": "running", "result_payload": {}},
        headers=auth_headers,
    )
    assert ack_response.status_code == 200, ack_response.text

    complete_response = api_client.post(
        f"/api/v1/execution-nodes/{node_id}/leases/{lease_id}/complete",
        json={"status": "completed", "result_payload": {"stdout": "done"}},
        headers=auth_headers,
    )
    assert complete_response.status_code == 200, complete_response.text
    assert complete_response.json()["status"] == "completed"

    external_sessions_response = api_client.get(f"/api/v1/runs/{run_id}/external-sessions", headers=auth_headers)
    assert external_sessions_response.status_code == 200, external_sessions_response.text
    external_sessions = external_sessions_response.json()
    assert len(external_sessions) == 1
    assert external_sessions[0]["status"] == "completed"
    assert external_sessions[0]["lease_id"] == lease_id

    run_response = api_client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "completed"

    step_response = api_client.get(f"/api/v1/run-steps/{step_id}", headers=auth_headers)
    assert step_response.status_code == 200, step_response.text
    assert step_response.json()["status"] == "completed"
