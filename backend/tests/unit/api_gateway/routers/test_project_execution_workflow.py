"""Workflow tests for the project execution platform skeleton."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from agent_framework.agent_registry import get_agent_registry
from api_gateway.main import create_app
from database.connection import get_db_session
from database.models import Agent, PlatformSetting
from database.project_execution_models import ProjectRun, ProjectTask
from project_execution.external_runtime_service import ExternalRuntimeService

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
    launch_command_template: str | None = "echo launch",
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
    if launch_command_template is not None:
        with get_db_session() as session:
            ExternalRuntimeService(session).update_profile(
                agent_id=agent_info.agent_id,
                launch_command_template=launch_command_template,
            )

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
    install_code = command.split("code=", 1)[1].split()[0].split("|")[0].strip()

    bootstrap_response = api_client.post(
        "/api/v1/external-runtime/bootstrap",
        json={
            "agent_id": str(agent_info.agent_id),
            "install_code": install_code,
            "host_name": "test-host",
            "host_os": "linux",
            "host_arch": "amd64",
            "host_fingerprint": f"fingerprint-{agent_info.agent_id}",
            "current_version": "0.1.0",
            "metadata": {},
        },
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    machine_token = bootstrap_response.json()["machine_token"]
    return str(agent_info.agent_id), machine_token


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
            launch_command_template="echo launch",
        )

    install_command_response = api_client.post(
        f"/api/v1/agents/{agent_info.agent_id}/external-runtime/install-command",
        json={"target_os": "linux"},
        headers=auth_headers,
    )
    assert install_command_response.status_code == 200, install_command_response.text
    install_command = install_command_response.json()["command"]
    install_url = urlsplit(
        install_command.replace("curl -fsSL ", "", 1).split(" | ", 1)[0]
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
        update_command.replace("curl -fsSL ", "", 1).split(" | ", 1)[0]
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
        uninstall_command.replace("curl -fsSL ", "", 1).split(" | ", 1)[0]
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


def test_host_action_dispatch_uses_platform_default_launch_command(
    api_client: TestClient, auth_headers: dict[str, str]
):
    _set_platform_launch_command("echo platform launch")
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Platform Default Launch Command",
            "description": "Use platform default external runtime command.",
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
        launch_command_template=None,
    )

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy app to host with platform default",
            "description": "SSH to host and deploy the app with the platform default runtime command.",
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
    assert dispatch["request_payload"]["launch_command_template"] == "echo platform launch"
    assert dispatch["request_payload"]["launch_command_source"] == "platform"


def test_host_action_dispatch_prefers_agent_launch_command_override(
    api_client: TestClient, auth_headers: dict[str, str]
):
    _set_platform_launch_command("echo platform launch")
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Agent Override Launch Command",
            "description": "Prefer agent-level external runtime command.",
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
        launch_command_template="echo agent launch",
    )

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy host assets with agent override",
            "description": "Deploy files to the remote host using the agent override runtime command.",
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
    assert dispatch["request_payload"]["launch_command_template"] == "echo agent launch"
    assert dispatch["request_payload"]["launch_command_source"] == "agent"


def test_host_action_without_launch_command_blocks_clearly(
    api_client: TestClient, auth_headers: dict[str, str]
):
    _set_platform_launch_command("")
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Missing Launch Command",
            "description": "Block execution when launch command is missing.",
            "status": "draft",
            "configuration": {},
        },
        headers=auth_headers,
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    project_id = project["project_id"]
    owner_user_id = project["created_by_user_id"]

    _agent_id, _machine_token = _provision_bound_external_agent(
        api_client,
        auth_headers,
        project_id=project_id,
        owner_user_id=owner_user_id,
        name="Missing Launch Command Agent",
        launch_command_template=None,
    )

    create_and_launch_response = api_client.post(
        "/api/v1/project-tasks/create-and-launch",
        json={
            "project_id": project_id,
            "title": "Deploy host assets without runtime command",
            "description": "Deploy files to the remote host even though the runtime launch command is missing.",
            "priority": "normal",
            "input_payload": {},
        },
        headers=auth_headers,
    )
    assert create_and_launch_response.status_code == 201, create_and_launch_response.text
    payload = create_and_launch_response.json()
    assert payload["agent_assignment"]["dispatch_id"] is None
    assert "launch command" in payload["agent_assignment"]["selection_reason"].lower()
    assert payload["step"]["status"] == "blocked"
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
    assert payload["step"]["input_payload"]["execution_mode"] == "project_sandbox"
    assert payload["step"]["input_payload"]["step_kind"] == "implementation"
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
    assert payload["agent_assignment"]["runtime_type"] == "external_worktree"
    assert payload["external_dispatch"]["status"] == "pending"
    assert payload["step"]["status"] == "queued"
    assert payload["run"]["status"] == "scheduled"

    dispatch_response = api_client.get(
        "/api/v1/external-runtime/dispatches/next",
        headers={"Authorization": f"Bearer {machine_token}"},
    )
    assert dispatch_response.status_code == 200, dispatch_response.text
    dispatch = dispatch_response.json()
    assert dispatch["dispatch_id"] == payload["external_dispatch"]["dispatch_id"]
    assert dispatch["run_step_id"] == payload["step"]["run_step_id"]


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
    step_id = payload["step"]["run_step_id"]
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

    step_response = api_client.get(f"/api/v1/run-steps/{step_id}", headers=auth_headers)
    assert step_response.status_code == 200, step_response.text
    assert step_response.json()["status"] == "completed"
