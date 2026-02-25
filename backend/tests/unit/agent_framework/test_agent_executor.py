from unittest.mock import MagicMock

from agent_framework.agent_executor import AgentExecutor


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
