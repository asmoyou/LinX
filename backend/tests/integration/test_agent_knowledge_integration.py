"""Integration tests for AgentExecutor knowledge-base context wiring."""

from unittest.mock import Mock, patch
from uuid import uuid4

from agent_framework.agent_executor import AgentExecutor, ExecutionContext


def _build_agent(*, allowed_knowledge=None):
    agent = Mock()
    agent.config.name = "Knowledge Integration Agent"
    agent.config.access_level = "private"
    agent.config.allowed_memory = []
    agent.config.allowed_knowledge = allowed_knowledge if allowed_knowledge is not None else []
    agent.execute_task.return_value = {"success": True, "output": "done"}
    return agent


def _build_memory_interface():
    memory_interface = Mock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.retrieve_user_context_memory.return_value = []
    memory_interface.memory_system.retrieve_memories.return_value = []
    memory_interface.store_agent_memory.return_value = "memory-id"
    return memory_interface


def test_executor_injects_knowledge_snippets_into_execution_context():
    """Knowledge search results should be injected into agent context."""
    memory_interface = _build_memory_interface()
    agent = _build_agent(allowed_knowledge=[])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="How do we handle retention policy?",
    )

    search_service = Mock()
    search_service.search.return_value = [
        {
            "document_id": str(uuid4()),
            "chunk_id": str(uuid4()),
            "content_snippet": "Knowledge snippet A",
            "similarity_score": 0.91,
            "metadata": {
                "title": "Retention Handbook",
                "file_reference": "knowledge/retention-handbook.pdf",
            },
        },
        {
            "document_id": str(uuid4()),
            "chunk_id": str(uuid4()),
            "content_snippet": "Knowledge snippet B",
            "similarity_score": 0.87,
            "metadata": {
                "title": "客服标准流程",
                "file_reference": "knowledge/customer-service-sop.docx",
            },
        },
    ]

    with patch("knowledge_base.knowledge_search.get_knowledge_search", return_value=search_service):
        context_data, debug_info = executor.build_execution_context_with_debug(agent, context)

    assert context_data["knowledge_snippets"] == ["Knowledge snippet A", "Knowledge snippet B"]
    assert context_data["knowledge_hits"][0]["title"] == "Retention Handbook"
    assert context_data["knowledge_hits"][0]["file_reference"] == "knowledge/retention-handbook.pdf"
    assert debug_info["knowledge"]["hit_count"] == 2


def test_executor_skips_knowledge_search_when_allowed_collections_are_invalid():
    """Invalid allowed_knowledge IDs should skip search without failing execution."""
    memory_interface = _build_memory_interface()
    agent = _build_agent(allowed_knowledge=["not-a-uuid"])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Try retrieving filtered knowledge",
    )

    with patch("knowledge_base.knowledge_search.get_knowledge_search") as mock_get_search:
        result = executor.execute(agent, context)

    assert result["success"] is True
    mock_get_search.assert_not_called()
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["knowledge_snippets"] == []


def test_executor_continues_when_knowledge_search_throws():
    """Knowledge-base failures should not block agent execution."""
    memory_interface = _build_memory_interface()
    agent = _build_agent(allowed_knowledge=[])
    executor = AgentExecutor(memory_interface)
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="Knowledge lookup should degrade gracefully",
    )

    with patch(
        "knowledge_base.knowledge_search.get_knowledge_search",
        side_effect=RuntimeError("kb unavailable"),
    ):
        result = executor.execute(agent, context)

    assert result["success"] is True
    execute_context = agent.execute_task.call_args.kwargs["context"]
    assert execute_context["knowledge_snippets"] == []
