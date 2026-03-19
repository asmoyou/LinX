"""Integration tests for AgentExecutor runtime context wiring."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from agent_framework.agent_executor import AgentExecutor, ExecutionContext


def _build_agent(*, access_level: str = "team", allowed_memory=None, allowed_knowledge=None):
    agent = Mock()
    agent.config.name = "Context Integration Agent"
    agent.config.access_level = access_level
    agent.config.allowed_memory = allowed_memory if allowed_memory is not None else []
    agent.config.allowed_knowledge = allowed_knowledge if allowed_knowledge is not None else []
    agent.execute_task.return_value = {"success": True, "output": "ok"}
    return agent


def test_executor_injects_user_memory_and_skills_into_agent_execution():
    context_service = Mock()
    context_service.retrieve_skills.return_value = [
        SimpleNamespace(content="onboarding skill 1", similarity_score=0.91)
    ]
    context_service.retrieve_user_memory.return_value = [
        SimpleNamespace(content="user prefers concise markdown", similarity_score=0.93)
    ]

    agent = _build_agent(allowed_memory=["skills", "user_memory"])
    executor = AgentExecutor(context_service=context_service)
    executor._filter_context_memories = lambda memories, _task: (memories, 0)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="How should we handle onboarding?",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["skills"] == ["onboarding skill 1"]
    assert execute_context["user_memory"] == ["user prefers concise markdown"]


def test_executor_continues_when_skill_lookup_fails():
    context_service = Mock()
    context_service.retrieve_skills.side_effect = RuntimeError("milvus unavailable")
    context_service.retrieve_user_memory.return_value = []

    agent = _build_agent(allowed_memory=["skills", "user_memory"])
    executor = AgentExecutor(context_service=context_service)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Continue even if memory fails",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["skills"] == []


def test_executor_exposes_context_debug_details():
    context_service = Mock()
    context_service.retrieve_skills.return_value = [
        SimpleNamespace(content="debug skill 1", similarity_score=0.91)
    ]
    context_service.retrieve_user_memory.return_value = [
        SimpleNamespace(content="debug user memory 1", similarity_score=0.92)
    ]

    agent = _build_agent(allowed_memory=["skills", "user_memory"])
    executor = AgentExecutor(context_service=context_service)
    executor._filter_context_memories = lambda memories, _task: (memories, 0)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Need debug details",
    )

    _, debug_info = executor.build_execution_context_with_debug(agent, context)

    assert debug_info["memory"]["skills"]["hit_count"] == 1
    assert debug_info["memory"]["user_memory"]["hit_count"] == 1
    assert debug_info["memory"]["skills"]["hits"][0].startswith("debug skill")


def test_executor_uses_default_runtime_scopes_even_with_legacy_allowed_memory_values():
    context_service = Mock()
    context_service.retrieve_skills.return_value = []
    context_service.retrieve_user_memory.return_value = []

    agent = _build_agent(allowed_memory=["company", "task_context"])
    executor = AgentExecutor(context_service=context_service)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_id=uuid4(),
        task_description="Legacy scopes should not inject memory",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    context_service.retrieve_skills.assert_called_once()
    context_service.retrieve_user_memory.assert_called_once()
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["skills"] == []
    assert execute_context["user_memory"] == []


def test_executor_does_not_store_task_completion_as_skill_memory():
    context_service = Mock()
    context_service.retrieve_skills.return_value = []
    context_service.retrieve_user_memory.return_value = []

    agent = _build_agent(allowed_memory=["skills"])
    executor = AgentExecutor(context_service=context_service)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_id=uuid4(),
        task_description="Summarize Q4 report",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    context_service.retrieve_skills.assert_called_once()
