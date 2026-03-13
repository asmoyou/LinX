from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from agent_framework.agent_executor import AgentExecutor, ExecutionContext


def _build_agent(*, allowed_memory=None, allowed_knowledge=None):
    agent = Mock()
    agent.config.name = "Runtime User Memory Agent"
    agent.config.access_level = "team"
    agent.config.allowed_memory = allowed_memory if allowed_memory is not None else []
    agent.config.allowed_knowledge = allowed_knowledge if allowed_knowledge is not None else []
    agent.execute_task.return_value = {"success": True, "output": "ok"}
    return agent


def test_runtime_context_respects_global_source_toggles() -> None:
    context_service = Mock()
    context_service.retrieve_skills.return_value = [
        SimpleNamespace(content="skill memory", similarity_score=0.91)
    ]
    context_service.retrieve_user_memory.return_value = [
        SimpleNamespace(content="user memory", similarity_score=0.92)
    ]

    config = Mock()
    config.get_section.side_effect = lambda name: {
        "user_memory": {"retrieval": {}, "observability": {}},
        "runtime_context": {
            "enable_user_memory": False,
            "enable_skills": True,
            "enable_knowledge_base": False,
        },
    }.get(name, {})

    with patch("agent_framework.agent_executor.get_config", return_value=config):
        executor = AgentExecutor(context_service=context_service)

    agent = _build_agent(allowed_memory=["skills", "user_memory"], allowed_knowledge=[str(uuid4())])
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Use the best available context",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    context_service.retrieve_skills.assert_called_once()
    context_service.retrieve_user_memory.assert_not_called()
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["skills"] == ["skill memory"]
    assert execute_context["user_memory"] == []
