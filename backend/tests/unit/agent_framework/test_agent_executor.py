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


def test_structured_user_preference_memory_requires_overlap_or_high_confidence():
    executor = _build_executor()
    memory = {
        "content": "user.preference.output_format=markdown",
        "metadata": {"signal_type": "user_preference"},
    }

    assert executor._is_context_memory_relevant(memory, "写一份山西旅游攻略") is False


def test_structured_user_preference_memory_kept_when_query_overlaps():
    executor = _build_executor()
    memory = {
        "content": "user.preference.output_format=markdown",
        "similarity_score": 0.72,
        "metadata": {"signal_type": "user_preference"},
    }

    assert executor._is_context_memory_relevant(memory, "请用markdown输出这份旅游攻略") is True


def test_preference_query_keeps_domain_matched_memory_without_lexical_overlap():
    executor = _build_executor()
    memory = {
        "content": "user.preference.drink_preference_like=可乐",
        "similarity_score": 0.79,
        "metadata": {
            "signal_type": "user_preference",
            "preference_key": "drink_preference_like",
            "is_active": True,
        },
    }

    assert executor._is_context_memory_relevant(memory, "我喜欢什么饮料") is True


def test_inactive_preference_memory_requires_history_cue():
    executor = _build_executor()
    memory = {
        "content": "user.preference.drink_preference_like=可乐",
        "similarity_score": 0.88,
        "metadata": {
            "signal_type": "user_preference",
            "preference_key": "drink_preference_like",
            "is_active": False,
        },
    }

    assert executor._is_context_memory_relevant(memory, "我喜欢什么饮料") is False
    assert executor._is_context_memory_relevant(memory, "我之前喜欢什么饮料") is True


def test_preference_memory_rejects_domain_mismatch():
    executor = _build_executor()
    memory = {
        "content": "user.preference.drink_preference_like=可乐",
        "similarity_score": 0.88,
        "metadata": {
            "signal_type": "user_preference",
            "preference_key": "drink_preference_like",
            "is_active": True,
        },
    }

    assert executor._is_context_memory_relevant(memory, "我喜欢什么食物") is False
    assert executor._is_context_memory_relevant(memory, "我喜欢什么饮料") is True


def test_inactive_user_preference_memory_is_not_forced_relevant():
    executor = _build_executor()
    memory = {
        "content": "user.preference.output_format=markdown",
        "metadata": {"signal_type": "user_preference", "is_active": False},
    }

    assert executor._is_structured_user_preference_memory(memory) is False


def test_history_query_can_recall_inactive_preference_memory():
    executor = _build_executor()
    memory = {
        "content": "user.preference.food_preference_like=黄焖鸡",
        "similarity_score": 0.73,
        "metadata": {
            "signal_type": "user_preference",
            "preference_key": "food_preference_like",
            "is_active": False,
        },
    }

    assert executor._is_context_memory_relevant(memory, "我之前喜欢吃什么") is True
    assert executor._is_context_memory_relevant(memory, "请写一份山西旅游攻略") is False


def test_keyword_fallback_memory_uses_score_floor():
    executor = _build_executor()
    memory = {
        "content": "上次只提到火药，主题其实是营销活动复盘",
        "similarity_score": 0.35,
        "metadata": {"search_method": "keyword"},
    }

    assert executor._is_context_memory_relevant(memory, "火药 安全 注意事项") is False


def test_filter_context_memories_records_source_quality_metrics():
    executor = _build_executor()
    labels_handle = MagicMock()
    counter = MagicMock()
    counter.labels.return_value = labels_handle

    memories = [
        {
            "content": "山西旅游攻略建议先去平遥古城再去五台山",
            "memory_type": "company",
            "similarity_score": 0.82,
            "metadata": {"search_method": "keyword"},
        },
        {
            "content": "上次营销复盘关注了投放ROI",
            "memory_type": "company",
            "similarity_score": 0.35,
            "metadata": {"search_method": "keyword"},
        },
    ]

    with patch("agent_framework.agent_executor.memory_retrieval_source_quality_total", counter):
        kept, filtered = executor._filter_context_memories(memories, "山西旅游攻略 路线")

    assert len(kept) == 1
    assert filtered == 1
    assert counter.labels.call_count == 2
    qualities = [call.kwargs["quality"] for call in counter.labels.call_args_list]
    assert "accepted" in qualities
    assert "rejected" in qualities
    assert labels_handle.inc.call_count == 2


def test_context_relevance_uses_semantic_score_not_blended_business_score():
    executor = _build_executor()
    memory = {
        "content": "上次只提到火药，主题其实是营销活动复盘",
        "similarity_score": 0.93,
        "metadata": {
            "_semantic_score": 0.29,
        },
    }

    assert executor._is_context_memory_relevant(memory, "火药 安全 注意事项") is False


def test_execution_context_uses_explicit_memory_similarity_threshold():
    memory_interface = MagicMock()
    memory_interface.retrieve_agent_memory.return_value = []
    memory_interface.retrieve_company_memory.return_value = []
    memory_interface.memory_system.retrieve_memories.return_value = []
    executor = AgentExecutor(memory_interface=memory_interface)

    agent = MagicMock()
    agent.config = SimpleNamespace(
        name="Test Agent",
        access_level="team",
        allowed_memory=["agent", "company", "user_context"],
        allowed_knowledge=[],
    )
    context = ExecutionContext(
        agent_id=uuid4(),
        user_id=uuid4(),
        task_description="检索记忆阈值测试",
    )

    executor.build_execution_context_with_debug(
        agent=agent,
        context=context,
        top_k=5,
        memory_min_similarity=0.64,
    )

    assert memory_interface.retrieve_agent_memory.call_args.kwargs["min_similarity"] == 0.64
    assert memory_interface.retrieve_company_memory.call_args.kwargs["min_similarity"] == 0.64


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
