from __future__ import annotations

from types import SimpleNamespace

import pytest

from project_execution.model_planner import ProjectExecutionPlanner


class _FakeRouter:
    def __init__(self, content: str):
        self._content = content

    async def generate(self, **_: object):
        return SimpleNamespace(content=self._content)


@pytest.mark.asyncio
async def test_model_planner_parses_multi_step_response(monkeypatch: pytest.MonkeyPatch) -> None:
    planner = ProjectExecutionPlanner(allow_model_calls_in_tests=True)
    monkeypatch.setattr(
        planner,
        "_resolve_planner_target",
        lambda: ("ollama", "qwen3-vl:30b", 0.2, 4000),
    )
    monkeypatch.setattr(
        "project_execution.model_planner.get_llm_provider",
        lambda: _FakeRouter(
            """
            {
              "summary": "Plan the rollout and implement the changes.",
              "needs_clarification": false,
              "clarification_questions": [],
              "steps": [
                {
                  "id": "research",
                  "name": "Research the rollout constraints",
                  "step_kind": "research",
                  "executor_kind": "agent",
                  "execution_mode": "project_sandbox",
                  "required_capabilities": ["research"],
                  "suggested_agent_ids": ["agent-1"],
                  "acceptance": "Known constraints are documented.",
                  "depends_on": [],
                  "parallel_group": null
                },
                {
                  "id": "implement",
                  "name": "Implement the changes",
                  "step_kind": "implementation",
                  "executor_kind": "agent",
                  "execution_mode": "project_sandbox",
                  "required_capabilities": ["implementation"],
                  "suggested_agent_ids": ["agent-2"],
                  "acceptance": "Code changes are ready for review.",
                  "depends_on": ["research"],
                  "parallel_group": null
                }
              ]
            }
            """
        ),
    )

    result = await planner.plan(
        title="Ship rollout",
        description="Research constraints and implement the changes.",
        execution_mode="auto",
        project_context={"project_name": "Test"},
        available_agents=[
          {"id": "agent-1", "name": "Researcher"},
          {"id": "agent-2", "name": "Builder"},
        ],
    )

    assert result.planner_source == "model"
    assert len(result.steps) == 2
    assert result.steps[1].depends_on == ["research"]
    assert result.steps[0].suggested_agent_ids == ["agent-1"]


@pytest.mark.asyncio
async def test_model_planner_falls_back_when_response_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    planner = ProjectExecutionPlanner(allow_model_calls_in_tests=True)
    monkeypatch.setattr(
        planner,
        "_resolve_planner_target",
        lambda: ("ollama", "qwen3-vl:30b", 0.2, 4000),
    )
    monkeypatch.setattr(
        "project_execution.model_planner.get_llm_provider",
        lambda: _FakeRouter("not-json"),
    )

    result = await planner.plan(
        title="Fix onboarding modal",
        description="Adjust validation and copy.",
        execution_mode="auto",
        project_context={},
        available_agents=[],
    )

    assert result.planner_source == "fallback_heuristic"
    assert len(result.steps) == 1
    assert result.steps[0].step_kind == "implementation"


@pytest.mark.asyncio
async def test_model_planner_normalizes_external_steps_in_project_sandbox_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner = ProjectExecutionPlanner(allow_model_calls_in_tests=True)
    monkeypatch.setattr(
        planner,
        "_resolve_planner_target",
        lambda: ("ollama", "qwen3-vl:30b", 0.2, 4000),
    )
    monkeypatch.setattr(
        "project_execution.model_planner.get_llm_provider",
        lambda: _FakeRouter(
            """
            {
              "summary": "Do the deploy work in the sandbox.",
              "needs_clarification": false,
              "clarification_questions": [],
              "steps": [
                {
                  "id": "deploy",
                  "name": "Deploy app to host",
                  "step_kind": "host_action",
                  "executor_kind": "execution_node",
                  "execution_mode": "external_runtime",
                  "required_capabilities": ["ops"],
                  "suggested_agent_ids": [],
                  "acceptance": "Deployment finished.",
                  "depends_on": [],
                  "parallel_group": null
                }
              ]
            }
            """
        ),
    )

    result = await planner.plan(
        title="Deploy app",
        description="SSH to host and deploy.",
        execution_mode="project_sandbox",
        project_context={},
        available_agents=[],
    )

    assert result.steps[0].execution_mode == "project_sandbox"
    assert result.steps[0].step_kind == "implementation"
    assert result.steps[0].executor_kind == "agent"
