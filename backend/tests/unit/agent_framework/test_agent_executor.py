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


def test_is_task_log_memory_detects_executor_task_source():
    executor = _build_executor()
    memory = {
        "content": "Task: 写一篇旅游攻略\nResult: 已完成",
        "metadata": {"source": "agent_executor_task"},
    }

    assert executor._is_task_log_memory(memory) is True
    assert executor._is_interaction_log_memory(memory) is False


def test_prune_interaction_log_memories_respects_history_intent():
    executor = _build_executor()
    memories = [
        {
            "content": "Task: 写一篇福州旅游攻略\nResult: 已完成",
            "metadata": {"source": "agent_executor_task"},
        },
        {
            "content": "[Agent: 小新]\nSession conversation summary (1 turns)\nRound 1 User: 继续\nRound 1 Assistant: 好的",
            "metadata": {"source": "agent_test_session"},
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
    assert pruned_count == 2

    kept_memories, kept_pruned_count = executor._prune_interaction_log_memories(
        memories,
        allow_interaction_logs=True,
    )

    assert len(kept_memories) == 2
    assert kept_pruned_count == 1


def test_format_memory_for_prompt_includes_timestamp_label():
    executor = _build_executor()
    memory = {
        "content": "user.preference.output_format=markdown",
        "timestamp": "2026-02-25T10:30:00+00:00",
    }

    formatted = executor._format_memory_for_prompt(memory)

    assert formatted is not None
    assert formatted.startswith("[memory_time=2026-02-25 10:30 UTC] ")
    assert formatted.endswith("user.preference.output_format=markdown")


def test_structured_user_preference_memory_is_always_relevant():
    executor = _build_executor()
    memory = {
        "content": "user.preference.output_format=markdown",
        "metadata": {"signal_type": "user_preference"},
    }

    assert executor._is_context_memory_relevant(memory, "写一份山西旅游攻略") is True


def test_inactive_user_preference_memory_is_not_forced_relevant():
    executor = _build_executor()
    memory = {
        "content": "user.preference.output_format=markdown",
        "metadata": {"signal_type": "user_preference", "is_active": False},
    }

    assert executor._is_structured_user_preference_memory(memory) is False


def test_prune_interaction_log_memories_drops_unpublished_agent_candidates():
    executor = _build_executor()
    memories = [
        {
            "content": "interaction.sop.topic=写旅游攻略\ninteraction.sop.steps=1.收集资料|2.整理路线|3.输出文档",
            "metadata": {
                "signal_type": "agent_memory_candidate",
                "review_status": "pending",
            },
        },
        {
            "content": "interaction.sop.topic=写旅游攻略\ninteraction.sop.steps=1.收集资料|2.整理路线|3.输出文档",
            "metadata": {
                "signal_type": "agent_memory_candidate",
                "review_status": "published",
            },
        },
    ]

    kept, pruned = executor._prune_interaction_log_memories(
        memories,
        allow_interaction_logs=True,
    )

    assert pruned == 1
    assert len(kept) == 1
    assert kept[0]["metadata"]["review_status"] == "published"


def test_execute_does_not_persist_task_memory_for_debug_chat_profile():
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


def test_execute_does_not_persist_task_memory_for_non_debug_profile():
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
    memory_interface.store_agent_memory.assert_not_called()
