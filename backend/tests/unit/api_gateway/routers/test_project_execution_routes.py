"""Route registration tests for project execution routers."""

from api_gateway.main import create_app


def test_project_execution_routes_are_registered():
    app = create_app()
    registered_paths = {route.path for route in app.routes}

    expected_paths = {
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/project-tasks",
        "/api/v1/project-tasks/{project_task_id}/transition",
        "/api/v1/plans/{plan_id}/activate",
        "/api/v1/runs/{run_id}/start",
        "/api/v1/run-steps/{run_step_id}/complete",
        "/api/v1/project-space/{project_id}/sync",
        "/api/v1/execution-nodes/{node_id}/heartbeat",
        "/api/v1/extensions/{extension_package_id}/enable",
        "/api/v1/skills/import",
        "/api/v1/skills/imports/{skill_package_id}/test",
    }

    assert expected_paths.issubset(registered_paths)
