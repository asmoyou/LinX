from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from agent_framework.agent_executor import AgentExecutor, ExecutionContext
from agent_framework.runtime_policy import ExecutionProfile


def _build_executor() -> AgentExecutor:
    return AgentExecutor(memory_interface=MagicMock())


def test_query_requests_historical_context_detects_follow_up_cues():
    executor = _build_executor()

    assert executor._query_requests_historical_context("继续上次的任务，把它补全。") is True
    assert executor._query_requests_historical_context("请回顾一下历史对话。") is True
    assert executor._query_requests_historical_context("写一份新疆旅游攻略，生成md文档。") is False


def test_is_interaction_log_memory_detects_executor_task_source():
    executor = _build_executor()
    memory = {
        "content": "Task: 写一篇旅游攻略\nResult: 已完成",
        "metadata": {"source": "agent_executor_task"},
    }

    assert executor._is_interaction_log_memory(memory) is True


def test_prune_interaction_log_memories_respects_history_intent():
    executor = _build_executor()
    memories = [
        {
            "content": "Task: 写一篇福州旅游攻略\nResult: 已完成",
            "metadata": {"source": "agent_executor_task"},
        },
        {
            "content": "User preference: 用户偏好 markdown 输出",
            "metadata": {"source": "conversation"},
        },
    ]

    pruned_memories, pruned_count = executor._prune_interaction_log_memories(
        memories,
        allow_interaction_logs=False,
    )
    assert len(pruned_memories) == 1
    assert pruned_count == 1

    kept_memories, kept_pruned_count = executor._prune_interaction_log_memories(
        memories,
        allow_interaction_logs=True,
    )

    assert len(kept_memories) == 2
    assert kept_pruned_count == 0


def test_execute_skips_task_memory_persistence_for_debug_chat_profile():
    memory_interface = MagicMock()
    executor = AgentExecutor(memory_interface=memory_interface)
    mock_runtime_service = MagicMock()
    mock_runtime_service.execute.return_value = {"success": True, "output": "ok"}

    agent = MagicMock()
    agent.config = SimpleNamespace(name="Test Agent")
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="写一份旅游攻略",
    )

    with patch("agent_framework.agent_executor.get_unified_agent_runtime_service") as get_runtime:
        get_runtime.return_value = mock_runtime_service
        result = executor.execute(
            agent=agent,
            context=context,
            execution_profile=ExecutionProfile.DEBUG_CHAT,
            prebuilt_execution_context={},
        )

    assert result["success"] is True
    memory_interface.store_agent_memory.assert_not_called()


def test_execute_persists_task_memory_for_non_debug_profile():
    memory_interface = MagicMock()
    executor = AgentExecutor(memory_interface=memory_interface)
    mock_runtime_service = MagicMock()
    mock_runtime_service.execute.return_value = {"success": True, "output": "ok"}

    agent = MagicMock()
    agent.config = SimpleNamespace(name="Test Agent")
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="写一份旅游攻略",
    )

    with patch("agent_framework.agent_executor.get_unified_agent_runtime_service") as get_runtime:
        get_runtime.return_value = mock_runtime_service
        result = executor.execute(
            agent=agent,
            context=context,
            execution_profile=ExecutionProfile.MISSION_TASK,
            prebuilt_execution_context={},
        )

    assert result["success"] is True
    memory_interface.store_agent_memory.assert_called_once()
