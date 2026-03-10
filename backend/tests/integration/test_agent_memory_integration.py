"""Integration tests for AgentExecutor memory context wiring."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from agent_framework.agent_executor import AgentExecutor, ExecutionContext


def _build_agent(*, access_level: str = "team", allowed_memory=None, allowed_knowledge=None):
    """Create a minimal mock agent compatible with AgentExecutor."""
    agent = Mock()
    agent.config.name = "Memory Integration Agent"
    agent.config.access_level = access_level
    agent.config.allowed_memory = allowed_memory if allowed_memory is not None else []
    agent.config.allowed_knowledge = allowed_knowledge if allowed_knowledge is not None else []
    agent.execute_task.return_value = {"success": True, "output": "ok"}
    return agent


def test_executor_injects_memory_context_into_agent_execution():
    """AgentExecutor should pass retrieved memory content into execution context."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = [
        SimpleNamespace(content="onboarding agent memory 1", similarity_score=0.91)
    ]
    memory_interface.retrieve_company_memory.return_value = [
        SimpleNamespace(content="onboarding company memory 1", similarity_score=0.88)
    ]
    memory_interface.retrieve_user_context_memory.return_value = [
        SimpleNamespace(content="onboarding user context 1", similarity_score=0.93)
    ]
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["agent", "company", "user_context"])
    executor = AgentExecutor(memory_interface)
    executor._filter_context_memories = lambda memories, _task: (memories, 0)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="How should we handle onboarding?",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["agent_memories"] == ["onboarding agent memory 1"]
    assert execute_context["company_memories"] == ["onboarding company memory 1"]
    assert execute_context["user_context_memories"] == ["onboarding user context 1"]


def test_executor_continues_when_memory_lookup_fails():
    """Memory retrieval failures should not break agent execution."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.side_effect = RuntimeError("milvus unavailable")
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.retrieve_user_context_memory.return_value = []
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["agent", "company", "user_context"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Continue even if memory fails",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["agent_memories"] == []


def test_executor_exposes_memory_debug_details():
    """Context builder should expose memory retrieval debug information."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = [
        SimpleNamespace(content="debug agent memory 1", similarity_score=0.91)
    ]
    memory_interface.retrieve_company_memory.return_value = [
        SimpleNamespace(content="debug company memory 1", similarity_score=0.89)
    ]
    memory_interface.retrieve_user_context_memory.return_value = [
        SimpleNamespace(content="debug user context 1", similarity_score=0.92)
    ]
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["agent", "company", "user_context"])
    executor = AgentExecutor(memory_interface)
    executor._filter_context_memories = lambda memories, _task: (memories, 0)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Need debug details",
    )

    _, debug_info = executor.build_execution_context_with_debug(agent, context)

    assert debug_info["memory"]["agent"]["hit_count"] == 1
    assert debug_info["memory"]["company"]["hit_count"] == 1
    assert debug_info["memory"]["user_context"]["hit_count"] == 1
    assert debug_info["memory"]["agent"]["hits"][0].startswith("debug agent")


def test_executor_does_not_force_zero_threshold_fallback_for_company_memory():
    """Company memory lookup should not bypass configured similarity threshold."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.retrieve_user_context_memory.return_value = []
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["company"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Need company fallback",
    )

    context_data, debug_info = executor.build_execution_context_with_debug(agent, context)

    assert context_data["company_memories"] == []
    assert debug_info["memory"]["company"]["fallback_used"] is False
    assert debug_info["memory"]["company"]["fallback_hit_count"] == 0
    memory_interface.memory_system.retrieve_memories.assert_not_called()


def test_executor_injects_task_context_memories_when_task_scope_enabled():
    """Task context memories should be queried and injected when scope + task_id are present."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.retrieve_user_context_memory.return_value = [
        SimpleNamespace(content="continue previous user context 1", similarity_score=0.92)
    ]

    def _retrieve_memories(query):
        memory_type = str(getattr(query.memory_type, "value", query.memory_type))
        if memory_type == "task_context":
            return [
                SimpleNamespace(content="continue previous task context 1", similarity_score=0.9)
            ]
        return []

    memory_interface.memory_system.retrieve_memories.side_effect = _retrieve_memories
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["user_context", "task_context"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_id=uuid4(),
        task_description="Continue previous task plan",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["user_context_memories"] == ["continue previous user context 1"]
    assert execute_context["task_context_memories"] == ["continue previous task context 1"]


def test_executor_does_not_store_task_completion_as_agent_memory():
    """Task completion should not create task-log style agent memory records."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.retrieve_user_context_memory.return_value = []
    memory_interface.memory_system.retrieve_memories.return_value = []
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["agent"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_id=uuid4(),
        task_description="Summarize Q4 report",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    memory_interface.store_agent_memory.assert_not_called()
