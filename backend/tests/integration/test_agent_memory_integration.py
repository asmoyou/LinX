"""Integration tests for AgentExecutor memory context wiring."""

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
    memory_interface.retrieve_agent_memory.return_value = [Mock(content="agent memory 1")]
    memory_interface.retrieve_company_memory.return_value = [Mock(content="company memory 1")]
    memory_interface.memory_system.retrieve_memories.return_value = [Mock(content="user context 1")]
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["agent", "company", "user_context"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="How should we handle onboarding?",
    )

    result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["agent_memories"] == ["agent memory 1"]
    assert execute_context["company_memories"] == ["company memory 1"]
    assert execute_context["user_context_memories"] == ["user context 1"]


def test_executor_continues_when_memory_lookup_fails():
    """Memory retrieval failures should not break agent execution."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.side_effect = RuntimeError("milvus unavailable")
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.memory_system.retrieve_memories.return_value = []
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
    memory_interface.retrieve_agent_memory.return_value = [Mock(content="agent memory 1")]
    memory_interface.retrieve_company_memory.return_value = [Mock(content="company memory 1")]
    memory_interface.memory_system.retrieve_memories.return_value = [Mock(content="user context 1")]
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["agent", "company", "user_context"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Need debug details",
    )

    _, debug_info = executor.build_execution_context_with_debug(agent, context)

    assert debug_info["memory"]["agent"]["hit_count"] == 1
    assert debug_info["memory"]["company"]["hit_count"] == 1
    assert debug_info["memory"]["user_context"]["hit_count"] == 1
    assert debug_info["memory"]["agent"]["hits"][0].startswith("agent memory")


def test_executor_uses_zero_threshold_fallback_when_company_retrieval_is_empty():
    """Fallback retrieval should recover company memories when default filtering returns none."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.memory_system.retrieve_memories.return_value = [
        Mock(content="company fallback memory")
    ]
    memory_interface.store_agent_memory.return_value = "memory-id"

    agent = _build_agent(allowed_memory=["company"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Need company fallback",
    )

    context_data, debug_info = executor.build_execution_context_with_debug(agent, context)

    assert context_data["company_memories"] == ["company fallback memory"]
    assert debug_info["memory"]["company"]["fallback_used"] is True
    assert debug_info["memory"]["company"]["fallback_hit_count"] == 1


def test_executor_stores_successful_response_as_agent_memory():
    """Successful executions should be persisted to agent memory with structured format."""
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
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
    memory_interface.store_agent_memory.assert_called_once()
    call_kwargs = memory_interface.store_agent_memory.call_args.kwargs
    assert call_kwargs["agent_id"] == context.agent_id
    # New structured format uses _format_agent_memory_content
    assert "Task: Summarize Q4 report" in call_kwargs["content"]
    assert "[Agent: Memory Integration Agent]" in call_kwargs["content"]
