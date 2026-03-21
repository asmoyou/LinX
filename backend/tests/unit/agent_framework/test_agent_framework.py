"""Tests for Agent Framework.

References:
- Requirements 2, 12: Agent Framework and Lifecycle Management
- Design Section 4: Agent Framework Design
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import Tool
from langgraph.errors import GraphRecursionError

from agent_framework.agent_executor import AgentExecutor, ExecutionContext
from agent_framework.agent_lifecycle import AgentLifecycleManager, LifecyclePhase
from agent_framework.agent_registry import AgentInfo, AgentRegistry
from agent_framework.agent_status import AgentStatusTracker, StatusUpdate
from agent_framework.agent_tools import AgentToolkit, create_langchain_tools
from agent_framework.runtime_context_service import RuntimeContextService
from agent_framework.base_agent import (
    AgentConfig,
    AgentStatus,
    BaseAgent,
    ConversationState,
    ToolCall,
    ToolResult,
)
from agent_framework.capability_matcher import CapabilityMatch, CapabilityMatcher
from agent_framework.runtime_policy import (
    ExecutionProfile,
    FileDeliveryGuardMode,
    LoopMode,
    RuntimePolicy,
)


class TestBaseAgent:
    """Test BaseAgent class."""

    def test_agent_initialization(self):
        """Test agent initialization."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2"],
        )

        agent = BaseAgent(config=config)

        assert agent.config.name == "Test Agent"
        assert agent.status == AgentStatus.INITIALIZING
        assert len(agent.config.capabilities) == 2

    def test_agent_get_capabilities(self):
        """Test getting agent capabilities."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2", "skill3"],
        )

        agent = BaseAgent(config=config)
        capabilities = agent.get_capabilities()

        assert len(capabilities) == 3
        assert "skill1" in capabilities

    def test_sync_skill_package_files_scopes_into_hidden_skills_dir(self, tmp_path):
        """Loaded skill package files should be copied under workspace .skills namespace."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.skill_manager = SimpleNamespace(
            get_agent_skill_docs=lambda: [
                SimpleNamespace(
                    name="Weather Skill",
                    package_files={
                        "weather/SKILL.md": "# Weather Skill",
                        "weather/scripts/run.py": "print('ok')",
                        "weather/requirements.txt": "requests",
                    },
                    skill_md_content="# Weather Skill",
                )
            ]
        )

        copied = agent._sync_skill_package_files_to_workdir(tmp_path)

        assert copied == 3
        assert (tmp_path / ".skills" / "Weather_Skill" / "scripts" / "run.py").exists()
        assert (tmp_path / ".skills" / "Weather_Skill" / "requirements.txt").exists()
        assert (tmp_path / ".skills" / "Weather_Skill" / "SKILL.md").exists()
        assert not (tmp_path / "weather" / "scripts" / "run.py").exists()

    def test_sync_skill_package_files_avoids_duplicate_skill_root(self, tmp_path):
        """Skill package root matching skill name should not create duplicate nested directory."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.skill_manager = SimpleNamespace(
            get_agent_skill_docs=lambda: [
                SimpleNamespace(
                    name="weather-forcast",
                    package_files={
                        "weather-forcast/SKILL.md": "# Weather Skill",
                        "weather-forcast/scripts/run.py": "print('ok')",
                    },
                    skill_md_content="# Weather Skill",
                )
            ]
        )

        copied = agent._sync_skill_package_files_to_workdir(tmp_path)

        assert copied == 2
        assert (tmp_path / ".skills" / "weather-forcast" / "scripts" / "run.py").exists()
        assert (tmp_path / ".skills" / "weather-forcast" / "SKILL.md").exists()
        assert not (
            tmp_path / ".skills" / "weather-forcast" / "weather-forcast" / "scripts" / "run.py"
        ).exists()

    def test_execute_task_streaming_includes_conversation_history(self):
        """Streaming execution should prepend provided conversation history."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()  # initialize guard

        captured_messages = {}

        def _fake_stream(messages):
            captured_messages["messages"] = messages
            yield SimpleNamespace(content="I remember your previous request.", additional_kwargs={})

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.tools = []
        agent.tools_by_name = {}

        history = [
            {"role": "user", "content": "Please calculate 2 + 2."},
            {"role": "assistant", "content": "The answer is 4."},
        ]

        result = agent.execute_task(
            task_description="What did I ask just now?",
            conversation_history=history,
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        sent_messages = captured_messages["messages"]
        assert isinstance(sent_messages[0], SystemMessage)
        assert isinstance(sent_messages[1], HumanMessage)
        assert isinstance(sent_messages[2], AIMessage)
        assert isinstance(sent_messages[3], HumanMessage)
        assert sent_messages[1].content == "Please calculate 2 + 2."
        assert sent_messages[2].content == "The answer is 4."
        assert sent_messages[3].content == "What did I ask just now?"

    def test_execute_task_non_streaming_includes_conversation_history(self):
        """Non-streaming execution should prepend provided conversation history."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.llm = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        captured_messages = {}

        class _FakeGraph:
            def invoke(self, payload):
                captured_messages["messages"] = payload["messages"]
                return {"messages": [AIMessage(content="I remember.")]}

        agent.agent = _FakeGraph()

        history = [
            {"role": "user", "content": "Translate 'hello' to Chinese."},
            {"role": "assistant", "content": "It is 你好."},
        ]

        result = agent.execute_task(
            task_description="What did I ask before this?",
            conversation_history=history,
        )

        assert result["success"] is True
        sent_messages = captured_messages["messages"]
        assert isinstance(sent_messages[0], SystemMessage)
        assert isinstance(sent_messages[1], HumanMessage)
        assert isinstance(sent_messages[2], AIMessage)
        assert isinstance(sent_messages[3], HumanMessage)
        assert sent_messages[1].content == "Translate 'hello' to Chinese."
        assert sent_messages[2].content == "It is 你好."
        assert sent_messages[3].content == "What did I ask before this?"

    def test_build_messages_with_file_delivery_policy_blocks_full_content_dumps(self):
        """Whenever a task is delivered as a file, prompt should require concise summaries only."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)

        messages = agent._build_messages_with_history(
            human_content="把报告发给我",
        )

        assert isinstance(messages[0], SystemMessage)
        assert "Do NOT paste the full file contents" in messages[0].content
        assert "report the exact saved file path(s) and keep the summary concise" in messages[0].content

    def test_assess_autonomous_completion_rejects_inline_file_dump_after_file_delivery(
        self,
    ):
        """Delivered files should not be reprinted inline as the final answer."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        decision = agent._assess_autonomous_completion(
            task_intent_text="把福州攻略整理成 md 文档给我",
            latest_output=(
                "✅ 福州旅游攻略已为你准备好！\n\n"
                "## 文件位置\n"
                "/workspace/output/fuzhou-travel-guide.md\n\n"
                "## 文档内容预览\n"
                "### 福州简介\n"
                "### 必游景点\n"
                "### 美食攻略\n"
                "### 行程推荐\n"
                "### 实用信息\n"
            ),
            tool_call_records=[
                {
                    "tool_name": "write_file",
                    "status": "success",
                    "round_number": 1,
                    "arguments": {"file_path": "/workspace/output/fuzhou-travel-guide.md"},
                    "result": "Saved to /workspace/output/fuzhou-travel-guide.md",
                }
            ],
            round_number=2,
            max_rounds=6,
            file_delivery_required=True,
            requested_file_formats={"md"},
        )

        assert decision["should_stop"] is False
        assert "不要粘贴文件原文" in decision["feedback_prompt"]

    def test_execute_task_cancellation_releases_busy_status_and_skips_fallback(self):
        """Cancellation during streaming should exit as cancelled without fallback invoke."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        def _fake_stream(_messages):
            yield SimpleNamespace(content="partial answer", additional_kwargs={})
            agent.request_cancellation("client stream cancelled")
            raise RuntimeError("stream cancelled by caller")

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(side_effect=AssertionError("fallback invoke should not run"))

        result = agent.execute_task(
            task_description="hello",
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is False
        assert result["cancelled"] is True
        assert agent.status == AgentStatus.ACTIVE
        agent.llm.invoke.assert_not_called()

    def test_execute_task_profile_driven_recovery_without_stream_callback(self):
        """Mission profile should enter recovery loop without requiring stream callback."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.llm = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        captured = {}

        async def _fake_recovery(*_args, **kwargs):
            captured["kwargs"] = kwargs
            return {"success": True, "output": "Recovered", "messages": []}

        agent.execute_task_with_recovery = _fake_recovery  # type: ignore[method-assign]

        result = agent.execute_task(
            task_description="Handle this mission task",
            execution_profile=ExecutionProfile.MISSION_TASK,
        )

        assert result["success"] is True
        runtime_policy = captured["kwargs"]["runtime_policy"]
        assert captured["kwargs"]["execution_profile"] == ExecutionProfile.MISSION_TASK
        assert runtime_policy.loop_mode == LoopMode.RECOVERY_MULTI_TURN
        assert captured["kwargs"]["stream_callback"] is None
        assert captured["kwargs"]["task_intent_text"] == "Handle this mission task"

    def test_normalize_conversation_history_filters_invalid_entries(self):
        """History normalization should keep only valid user/assistant text messages."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        normalized = agent._normalize_conversation_history(
            [
                {"role": "user", "content": "first"},
                {"role": "system", "content": "ignore"},
                {"role": "assistant", "content": [{"text": "second"}]},
                {"role": "user", "content": ""},
                {"role": "assistant", "content": None},
                "invalid-entry",
            ]
        )

        assert normalized == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]

    def test_normalize_conversation_history_preserves_multimodal_image_items(self):
        """History normalization should retain multimodal image_url content for follow-up turns."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        normalized = agent._normalize_conversation_history(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "能看到什么"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                        },
                    ],
                }
            ]
        )

        assert normalized == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "能看到什么"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                    },
                ],
            }
        ]

    def test_create_system_prompt_enforces_write_file_for_file_deliverables(self):
        """Workspace prompt should require write_file when user asks for file outputs."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        prompt = agent._create_system_prompt()

        assert "When users ask for deliverables as files/documents" in prompt
        assert "MUST use `write_file`" in prompt
        assert "**append_file**" in prompt
        assert "report the exact saved file path" in prompt
        assert "prefer `/workspace/output/...`" in prompt
        assert "Default behavior" in prompt
        assert "Use file tools when the user asks for deliverable files" in prompt

    def test_create_system_prompt_renders_runtime_environment_block(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        prompt = agent._create_system_prompt(
            runtime_capabilities={
                "sandbox_enabled": True,
                "sandbox_backend": "docker_enhanced",
                "network_access": False,
                "workspace_root_virtual": "/workspace",
                "writable_roots": ["/workspace"],
                "ui_mode": "none",
                "session_persistent": True,
                "host_fallback_allowed": False,
            }
        )

        assert "## Runtime Environment (Authoritative)" in prompt
        assert "- Sandbox: enabled (docker_enhanced)" in prompt
        assert "- UI mode: none" in prompt
        assert "- Code execution network access: disabled" in prompt
        assert "- Host fallback: blocked" in prompt

    def test_resolve_runtime_capabilities_uses_authoritative_runtime_flags(self):
        resolved = BaseAgent._resolve_runtime_capabilities(
            context={
                "runtime_capabilities": {
                    "sandbox_enabled": True,
                    "sandbox_backend": "firecracker",
                    "network_access": False,
                }
            },
            session_workdir=None,
            container_id=None,
            code_execution_network_access=True,
        )

        assert resolved["sandbox_enabled"] is False
        assert resolved["sandbox_backend"] == "host_subprocess"
        assert resolved["network_access"] is True
        assert resolved["workspace_root_virtual"] == "/workspace"

    def test_build_system_time_context_contains_utc_and_local_timestamps(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        context = agent._build_system_time_context()
        assert context["utc_now"].endswith("Z")
        assert context["local_timezone"]
        assert len(context["local_date"]) == 10
        datetime.fromisoformat(context["utc_now"].replace("Z", "+00:00"))
        datetime.fromisoformat(context["local_now"])

    def test_build_messages_with_history_includes_system_time_context(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        messages = agent._build_messages_with_history(human_content="请告诉我今天是几号")

        assert isinstance(messages[0], SystemMessage)
        assert "## System Time Context" in messages[0].content
        assert "UTC now:" in messages[0].content
        assert "authoritative current time" in messages[0].content

    def test_build_messages_with_history_prepends_extra_system_messages(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        messages = agent._build_messages_with_history(
            human_content="查询今天的国内金价",
            extra_system_messages=["这是一次已触发的定时任务，请直接执行，不要把它当成刚收到的新消息。"],
        )

        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], SystemMessage)
        assert messages[1].content == "这是一次已触发的定时任务，请直接执行，不要把它当成刚收到的新消息。"
        assert isinstance(messages[2], HumanMessage)
        assert messages[2].content == "查询今天的国内金价"

    def test_requires_file_delivery_detects_explicit_file_intent(self):
        """File-delivery guard should only trigger when prompt explicitly asks for file output."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        assert agent._requires_file_delivery("写一篇福州旅游攻略，整理成md文档给我") is True
        assert agent._requires_file_delivery("写一篇福州5天旅游攻略，交付md文档给我") is True
        assert agent._requires_file_delivery("写一篇北京的5天旅游攻略，然后生成md文档给我") is True
        assert agent._requires_file_delivery("请生成PDF文件给我") is True
        assert agent._requires_file_delivery("写一份天津的旅游攻略，给我pdf文档") is True
        assert agent._requires_file_delivery("把以上题目整到excel文件给我") is True
        assert agent._requires_file_delivery("出100道题，整理出excel给我") is True
        assert agent._requires_file_delivery("把这个文档转成pdf给我") is True
        assert agent._requires_file_delivery("请转换为docx文件") is True
        assert agent._requires_file_delivery("Please save this guide as a markdown file.") is True
        assert agent._requires_file_delivery("Generate this as a markdown document.") is True
        assert agent._requires_file_delivery("Deliver this as a markdown document.") is True
        assert (
            agent._requires_file_delivery("请写一篇福州旅游攻略，使用 markdown 格式输出") is False
        )
        assert agent._requires_file_delivery("请直接回复，不要保存文件。") is False
        assert agent._requires_file_delivery("No need to save a file, respond in chat.") is False

    def test_requested_file_formats_and_delivery_match(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        requested = agent._extract_requested_file_formats("写一份天津旅游攻略，给我pdf文档")
        assert requested == {"pdf"}

        md_records = [
            {
                "tool_name": "write_file",
                "status": "success",
                "args": {"file_path": "/workspace/output/tianjin.md"},
                "result": "Successfully wrote /workspace/output/tianjin.md",
            }
        ]
        assert agent._has_successful_requested_format_call(md_records, {"md"}) is True
        assert agent._has_successful_requested_format_call(md_records, {"pdf"}) is False

        pdf_records = [
            {
                "tool_name": "code_execution",
                "status": "success",
                "args": {"code": "print('/workspace/output/tianjin.pdf')"},
                "result": "Code executed successfully:\n/workspace/output/tianjin.pdf",
            }
        ]
        assert agent._has_successful_requested_format_call(pdf_records, {"pdf"}) is True

    def test_recovery_json_format_reply_does_not_force_file_write(self):
        """JSON text-format replies should not trigger file-delivery guard without explicit file intent."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        stream_call_count = {"count": 0}

        def _fake_stream(_messages):
            stream_call_count["count"] += 1
            if stream_call_count["count"] > 1:
                raise AssertionError("unexpected extra round")
            yield SimpleNamespace(
                content="已完成分析。按 JSON 格式字段返回：score=96，risk_level=low。",
                additional_kwargs={},
            )

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(side_effect=AssertionError("llm.invoke should not be called"))

        result = agent.execute_task(
            task_description="请分析这组数据，并以 JSON 格式直接回复，不要保存文件。",
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert stream_call_count["count"] == 1
        assert "score=96" in result["output"]

    def test_assess_autonomous_completion_file_guard_soft_mode_advises_only(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        decision = agent._assess_autonomous_completion(
            task_intent_text="写一篇攻略并交付 md 文件",
            latest_output="这是攻略正文。",
            tool_call_records=[],
            round_number=1,
            max_rounds=5,
            file_delivery_required=True,
            file_delivery_guard_mode=FileDeliveryGuardMode.SOFT,
            requested_file_formats={"md"},
            finish_reason="",
        )

        assert decision["should_stop"] is True
        assert "advisory_message" in decision
        assert "soft" in str(decision.get("reason", "")).lower()

    def test_assess_autonomous_completion_file_guard_strict_forces_followup(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        decision = agent._assess_autonomous_completion(
            task_intent_text="写一篇攻略并交付 md 文件",
            latest_output="这是攻略正文。",
            tool_call_records=[],
            round_number=1,
            max_rounds=5,
            file_delivery_required=True,
            file_delivery_guard_mode=FileDeliveryGuardMode.STRICT,
            requested_file_formats={"md"},
            finish_reason="",
        )

        assert decision["should_stop"] is False
        assert "file deliverable" in str(decision.get("reason", "")).lower()

    def test_assess_autonomous_completion_does_not_misclassify_polite_followup(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        decision = agent._assess_autonomous_completion(
            task_intent_text="查询天气",
            latest_output="福州今天多云，气温 18-25°C。若你需要，我可以继续查询未来三天天气。",
            tool_call_records=[],
            round_number=3,
            max_rounds=6,
            finish_reason="",
        )

        assert decision["should_stop"] is True

    def test_assess_autonomous_completion_does_not_continue_on_polite_chat_invite(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        decision = agent._assess_autonomous_completion(
            task_intent_text="你能听到我在说话吗",
            latest_output=(
                "所以，请继续用文字和我聊天吧！\n"
                "有什么问题尽管问，我会认真回答的！"
            ),
            tool_call_records=[],
            round_number=1,
            max_rounds=6,
            finish_reason="",
        )

        assert decision["should_stop"] is True

    def test_assess_autonomous_completion_detects_explicit_wait_and_continue_signal(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        decision = agent._assess_autonomous_completion(
            task_intent_text="查询天气",
            latest_output="请稍等，我继续查询最新天气数据。",
            tool_call_records=[],
            round_number=1,
            max_rounds=6,
            finish_reason="",
        )

        assert decision["should_stop"] is False
        assert "incomplete" in str(decision.get("reason", "")).lower()

    def test_assess_autonomous_completion_detects_explicit_incomplete_signal(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        decision = agent._assess_autonomous_completion(
            task_intent_text="查询天气",
            latest_output="任务还未完成，我需要继续调用工具获取剩余信息。",
            tool_call_records=[],
            round_number=3,
            max_rounds=6,
            finish_reason="",
        )

        assert decision["should_stop"] is False
        assert "incomplete" in str(decision.get("reason", "")).lower()

    def test_runtime_tool_registry_keeps_file_tools_available(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.tools_by_name = {
            "write_file": Mock(),
            "append_file": Mock(),
            "read_file": Mock(),
        }

        runtime_registry = agent._build_runtime_tool_registry()

        assert set(runtime_registry.keys()) == {"write_file", "append_file", "read_file"}

    def test_extract_native_tool_calls_from_ai_message(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.tools_by_name = {"write_file": Mock()}

        message = SimpleNamespace(
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {
                        "file_path": "/workspace/output/result.md",
                        "content": "# Title",
                    },
                }
            ]
        )

        tool_calls = agent._extract_native_tool_calls(message)

        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "write_file"
        assert tool_calls[0].arguments["file_path"] == "/workspace/output/result.md"

    def test_parse_tool_calls_supports_nested_braces_in_string_arguments(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.tools_by_name = {"write_file": Mock()}

        llm_output = (
            '{"tool":"write_file","file_path":"/workspace/output/tianjin_travel_guide.md",'
            '"content":"# 天津攻略\\n\\n示例内容包含花括号 {a:1} 与表格 |A|B|"}'
        )

        tool_calls, parse_errors = agent._parse_tool_calls(llm_output)

        assert len(tool_calls) == 1
        assert not parse_errors
        assert tool_calls[0].tool_name == "write_file"
        assert "花括号 {a:1}" in tool_calls[0].arguments["content"]

    def test_parse_tool_calls_ignores_unknown_tool_examples_without_explicit_intent(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.tools_by_name = {"write_file": Mock()}

        llm_output = (
            '这是格式示例，不需要执行：{"tool":"unknown_tool","foo":"bar"}。'
            "我接下来会直接给出答案。"
        )

        tool_calls, parse_errors = agent._parse_tool_calls(llm_output)

        assert not tool_calls
        assert not parse_errors

    def test_extract_tool_runtime_error_detects_error_like_outputs(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        assert agent._extract_tool_runtime_error("Error: File not found")
        assert agent._extract_tool_runtime_error("Error reading file: workspace root missing")
        assert agent._extract_tool_runtime_error("Code execution failed:\nboom")
        assert agent._extract_tool_runtime_error("❌ Command failed (exit code 1)")
        assert agent._extract_tool_runtime_error({"success": False, "error": "boom"})
        assert (
            agent._extract_tool_runtime_error("Successfully wrote /workspace/output/a.md") is None
        )

    def test_summarize_tool_arguments_for_stream_file_write(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        summary = agent._summarize_tool_arguments_for_stream(
            "write_file",
            {"file_path": "/workspace/output/fuzhou.md", "content": "hello"},
        )

        assert "file_path=/workspace/output/fuzhou.md" in summary
        assert "content_chars=5" in summary

    def test_summarize_tool_arguments_for_stream_bash_positional_command(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        summary = agent._summarize_tool_arguments_for_stream(
            "bash",
            {"__arg1": "pip install openpyxl -q"},
        )

        assert "command=pip install openpyxl -q" in summary

    def test_summarize_tool_result_for_stream_truncates_large_text(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        summary = agent._summarize_tool_result_for_stream("code_execution", "x" * 600)

        assert len(summary) <= 220
        assert summary.endswith("...")

    def test_summarize_tool_result_for_stream_bash_empty_output(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)

        summary = agent._summarize_tool_result_for_stream("bash", "")

        assert summary == "命令执行成功（无标准输出）"

    def test_handle_execution_failures_returns_execution_feedback(self):
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        state = ConversationState(round_number=1)
        state.retry_counts["tool_write_file"] = 1

        feedback = agent._handle_execution_failures(
            [
                ToolResult(
                    tool_name="write_file",
                    status="error",
                    error="write failed",
                    error_type="execution_error",
                    retry_count=1,
                )
            ],
            state,
        )

        assert feedback is not None
        assert feedback.error_type == "Execution Error"

    def test_recovery_bash_timeout_injected_for_single_input_tool(self):
        """Bash timeout cap should be applied without breaking single-input Tool invocation."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
            tool_timeout_seconds=3.0,
        )
        agent = BaseAgent(config=config)
        state = ConversationState(round_number=1)

        def bash_execute(
            command: str,
            pty: bool = False,
            workdir: str | None = None,
            background: bool = False,
            timeout: int | None = None,
        ) -> str:
            return (
                f"command={command};pty={pty};workdir={workdir};"
                f"background={background};timeout={timeout}"
            )

        bash_tool = Tool(
            name="bash",
            description="test bash tool",
            func=bash_execute,
        )
        agent.tools_by_name = {"bash": bash_tool}

        with asyncio.Runner() as runner:
            results = runner.run(
                agent._execute_tools_with_recovery(
                    [
                        ToolCall(
                            tool_name="bash",
                            arguments={"command": "python3 -m http.server 8080"},
                            raw_json="{}",
                        )
                    ],
                    state,
                )
            )

        assert results[0].status == "success"
        assert "timeout=3" in str(results[0].result)
        assert state.tool_calls_made[0].arguments["timeout"] == 3

    def test_recovery_bash_arg1_is_normalized_to_command_for_single_input_tool(self):
        """When parser emits __arg1 for bash, recovery should normalize it to command."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
            tool_timeout_seconds=3.0,
        )
        agent = BaseAgent(config=config)
        state = ConversationState(round_number=1)

        def bash_execute(
            command: str,
            pty: bool = False,
            workdir: str | None = None,
            background: bool = False,
            timeout: int | None = None,
        ) -> str:
            return (
                f"command={command};pty={pty};workdir={workdir};"
                f"background={background};timeout={timeout}"
            )

        bash_tool = Tool(
            name="bash",
            description="test bash tool",
            func=bash_execute,
        )
        agent.tools_by_name = {"bash": bash_tool}

        with asyncio.Runner() as runner:
            results = runner.run(
                agent._execute_tools_with_recovery(
                    [
                        ToolCall(
                            tool_name="bash",
                            arguments={"__arg1": "python3 -m http.server 8080"},
                            raw_json="{}",
                        )
                    ],
                    state,
                )
            )

        assert results[0].status == "success"
        assert "command=python3 -m http.server 8080" in str(results[0].result)
        assert "timeout=3" in str(results[0].result)
        assert state.tool_calls_made[0].arguments["command"] == "python3 -m http.server 8080"
        assert "__arg1" not in state.tool_calls_made[0].arguments
        assert state.tool_calls_made[0].arguments["timeout"] == 3

    def test_recovery_file_delivery_guard_triggers_extra_write_round(self):
        """When file intent exists and no file write occurred, recovery loop should add one save round."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()  # initialize guard
        agent.tools = []

        write_tool = Mock()
        write_tool.ainvoke = AsyncMock(
            return_value="Successfully wrote /workspace/output/fuzhou.md"
        )
        agent.tools_by_name = {"write_file": write_tool}

        stream_call_count = {"count": 0}

        def _fake_stream(_messages):
            stream_call_count["count"] += 1
            current_round = stream_call_count["count"]
            if current_round == 1:
                yield SimpleNamespace(content="这是福州旅游攻略正文。", additional_kwargs={})
            elif current_round == 2:
                yield SimpleNamespace(
                    content=(
                        '{"tool":"write_file","file_path":"/workspace/output/fuzhou.md",'
                        '"content":"# 福州旅游攻略\\n\\n第一天..."}'
                    ),
                    additional_kwargs={},
                )
            else:
                yield SimpleNamespace(
                    content="已保存到 /workspace/output/fuzhou.md",
                    additional_kwargs={},
                )

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(
            side_effect=[
                SimpleNamespace(
                    content='{"is_complete": false, "confidence": 0.2, "reason": "文件尚未落盘", "next_action": "调用工具写入文件"}'
                ),
                SimpleNamespace(
                    content='{"is_complete": true, "confidence": 0.95, "reason": "文件已保存", "next_action": ""}'
                ),
            ]
        )
        strict_policy = RuntimePolicy(
            profile=ExecutionProfile.DEBUG_CHAT,
            loop_mode=LoopMode.RECOVERY_MULTI_TURN,
            max_rounds=20,
            enable_error_recovery=True,
            file_delivery_guard_mode=FileDeliveryGuardMode.STRICT,
        )

        result = agent.execute_task(
            task_description="写一篇福州旅游攻略，整理成md文档给我",
            runtime_policy=strict_policy,
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert stream_call_count["count"] == 3
        write_tool.ainvoke.assert_awaited_once()
        assert "/workspace/output/fuzhou.md" in result["output"]

    def test_recovery_tool_failure_guard_forces_followup_retry_round(self):
        """If last round failed tool execution, next no-tool response should not terminate immediately."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.tools = []

        bash_tool = Mock()
        bash_tool.ainvoke = AsyncMock(
            side_effect=[
                "❌ Command failed (exit code 127)\n\nError:\n/bin/sh: apt-get: command not found",
                "ok",
            ]
        )
        agent.tools_by_name = {"bash": bash_tool}

        stream_call_count = {"count": 0}

        def _fake_stream(_messages):
            stream_call_count["count"] += 1
            current_round = stream_call_count["count"]
            if current_round == 1:
                yield SimpleNamespace(
                    content='{"tool":"bash","command":"apt-get install -y texlive"}',
                    additional_kwargs={},
                )
            elif current_round == 2:
                yield SimpleNamespace(content="我无法继续执行。", additional_kwargs={})
            elif current_round == 3:
                yield SimpleNamespace(
                    content='{"tool":"bash","command":"python3 -m pip install -q fpdf2"}',
                    additional_kwargs={},
                )
            else:
                yield SimpleNamespace(content="已完成处理。", additional_kwargs={})

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(
            side_effect=[
                SimpleNamespace(
                    content='{"is_complete": false, "confidence": 0.1, "reason": "仍需执行修复步骤", "next_action": "继续调用工具"}'
                ),
                SimpleNamespace(
                    content='{"is_complete": true, "confidence": 0.9, "reason": "步骤已完成", "next_action": ""}'
                ),
            ]
        )

        result = agent.execute_task(
            task_description="请完成环境修复并汇报处理结果",
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert stream_call_count["count"] == 4
        assert bash_tool.ainvoke.await_count == 2

    def test_recovery_no_tool_completion_does_not_trigger_secondary_llm_eval_call(self):
        """No-tool completion should stop via deterministic state machine, without extra llm.invoke."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        stream_call_count = {"count": 0}

        def _fake_stream(_messages):
            stream_call_count["count"] += 1
            yield SimpleNamespace(content="处理已完成。", additional_kwargs={})

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(side_effect=AssertionError("llm.invoke should not be called"))

        result = agent.execute_task(
            task_description="请直接给出总结结果",
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert result["output"] == "处理已完成。"
        assert stream_call_count["count"] == 1

    def test_recovery_finish_reason_length_forces_followup_round(self):
        """When provider reports finish_reason=length, loop should continue to next round."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        stream_call_count = {"count": 0}

        def _fake_stream(_messages):
            stream_call_count["count"] += 1
            if stream_call_count["count"] == 1:
                yield SimpleNamespace(
                    content="这是被截断的输出片段。",
                    additional_kwargs={},
                    response_metadata={"finish_reason": "length"},
                )
            else:
                yield SimpleNamespace(content="这是补全后的最终结果。", additional_kwargs={})

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(side_effect=AssertionError("llm.invoke should not be called"))

        result = agent.execute_task(
            task_description="输出完整报告",
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert result["output"] == "这是补全后的最终结果。"
        assert stream_call_count["count"] == 2

    def test_auto_multi_turn_file_delivery_guard_uses_task_intent_text(self):
        """Attachment context should not trigger file-delivery guard when user didn't request file output."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.tools = []

        stream_call_count = {"count": 0}

        def _fake_stream(_messages):
            stream_call_count["count"] += 1
            yield SimpleNamespace(content="这是文档总结。", additional_kwargs={})

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.llm.invoke = Mock(
            return_value=SimpleNamespace(
                content='{"is_complete": true, "confidence": 0.92, "reason": "总结已完成", "next_action": ""}'
            )
        )

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.MISSION_CONTROL,
            loop_mode=LoopMode.AUTO_MULTI_TURN,
            max_rounds=5,
            enable_error_recovery=False,
            stream_output=True,
        )
        polluted_task_description = (
            "请总结这份方案。\n\n"
            "Attached files context:\n"
            "[Document: sample.pdf]\n"
            "该方案会自动生成健康评估报告。\n\n"
            "Attached files are available in workspace:\n"
            "- sample.pdf: /workspace/input/sample.pdf"
        )

        result = agent.execute_task(
            task_description=polluted_task_description,
            context={"task_intent_text": "请总结这份方案。"},
            runtime_policy=runtime_policy,
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert stream_call_count["count"] == 1
        assert result["output"] == "这是文档总结。"

    def test_should_use_native_tool_fast_path_with_mixed_skills_for_direct_expression(self):
        """Direct calculator-like prompts should prefer native tool-calling even with agent skills loaded."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.native_tool_calling_enabled = True
        agent.loaded_langchain_tool_skill_count = 2
        agent.loaded_agent_skill_count = 1
        agent.agent_skill_names = {"legal_agent_skill"}

        assert agent._should_use_native_tool_fast_path("23223*23/32=?") is True

    def test_should_not_use_native_tool_fast_path_for_agent_skill_intent(self):
        """Agent skill intent should keep multi-turn behavior."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.native_tool_calling_enabled = True
        agent.loaded_langchain_tool_skill_count = 2
        agent.loaded_agent_skill_count = 1
        agent.agent_skill_names = {"legal_agent_skill"}

        assert (
            agent._should_use_native_tool_fast_path("请按 legal_agent_skill workflow 处理合同风险")
            is False
        )

    def test_execute_task_debug_chat_switches_to_single_turn_for_direct_tool_request(self):
        """DEBUG_CHAT should switch from auto multi-turn to single-turn for direct tool requests."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.agent.invoke.return_value = {"messages": [AIMessage(content="16696.53125")]}
        agent.llm = Mock()
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True
        agent.loaded_langchain_tool_skill_count = 2
        agent.loaded_agent_skill_count = 1
        agent.agent_skill_names = {"legal_agent_skill"}

        chunks = []
        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.DEBUG_CHAT,
            loop_mode=LoopMode.AUTO_MULTI_TURN,
            max_rounds=20,
            enable_error_recovery=True,
            stream_output=True,
        )

        result = agent.execute_task(
            task_description="23223*23/32=?",
            runtime_policy=runtime_policy,
            stream_callback=lambda chunk: chunks.append(chunk),
        )

        assert result["success"] is True
        agent.agent.invoke.assert_called_once()
        assert chunks == [("16696.53125", "content")]

    def test_execute_task_debug_chat_keeps_multi_turn_for_agent_skill_intent(self):
        """DEBUG_CHAT should keep multi-turn path when prompt looks like agent skill workflow."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.agent.invoke.return_value = {"messages": [AIMessage(content="fallback")]}
        agent.llm = Mock()
        agent.llm_with_tools = Mock()
        agent.llm_with_tools.stream.return_value = iter(
            [SimpleNamespace(content="已按技能流程完成。", additional_kwargs={})]
        )
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True
        agent.loaded_langchain_tool_skill_count = 2
        agent.loaded_agent_skill_count = 1
        agent.agent_skill_names = {"legal_agent_skill"}

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.DEBUG_CHAT,
            loop_mode=LoopMode.AUTO_MULTI_TURN,
            max_rounds=20,
            enable_error_recovery=True,
            stream_output=True,
        )

        result = agent.execute_task(
            task_description="请按 legal_agent_skill workflow 处理合同风险",
            runtime_policy=runtime_policy,
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        agent.llm_with_tools.stream.assert_called_once()
        agent.agent.invoke.assert_not_called()
        assert result["output"] == "已按技能流程完成。"

    def test_execute_task_single_turn_native_tools_uses_graph_recursion_limit(self):
        """Single-turn graph invoke should cap recursion when native tool-calling is enabled."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.agent.invoke.return_value = {"messages": [AIMessage(content="ok")]}
        agent.llm = Mock()
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.MISSION_CONTROL,
            loop_mode=LoopMode.SINGLE_TURN,
            max_rounds=1,
            enable_error_recovery=False,
            stream_output=False,
        )

        result = agent.execute_task(
            task_description="hello",
            runtime_policy=runtime_policy,
        )

        assert result["success"] is True
        _, kwargs = agent.agent.invoke.call_args
        assert kwargs["config"]["recursion_limit"] == 12

    def test_execute_task_single_turn_recursion_error_falls_back_to_plain_llm(self):
        """If graph recursion limit is hit, single-turn should fallback to plain LLM invoke."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        agent.agent.invoke.side_effect = GraphRecursionError("loop reached")
        agent.llm = Mock()
        agent.llm.invoke.return_value = AIMessage(content="fallback output")
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.MISSION_CONTROL,
            loop_mode=LoopMode.SINGLE_TURN,
            max_rounds=1,
            enable_error_recovery=False,
            stream_output=False,
        )

        result = agent.execute_task(
            task_description="hello",
            runtime_policy=runtime_policy,
        )

        assert result["success"] is True
        assert result["output"] == "fallback output"
        agent.llm.invoke.assert_called_once()

    def test_execute_task_single_turn_http_400_downgrades_native_tools(self):
        """400/422 from upstream tool payload should downgrade native tool-calling and retry."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(400, request=request)
        agent.agent.invoke.side_effect = [
            httpx.HTTPStatusError("bad request", request=request, response=response),
            {"messages": [AIMessage(content="retry ok")]},
        ]
        agent.llm = Mock()
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True
        agent.llm_with_tools = Mock()

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.MISSION_CONTROL,
            loop_mode=LoopMode.SINGLE_TURN,
            max_rounds=1,
            enable_error_recovery=False,
            stream_output=False,
        )

        result = agent.execute_task(
            task_description="23223*23/32=?",
            runtime_policy=runtime_policy,
        )

        assert result["success"] is True
        assert result["output"] == "retry ok"
        assert agent.native_tool_calling_enabled is False
        assert agent.llm_with_tools is agent.llm
        assert agent.agent.invoke.call_count == 2
        assert agent.agent.invoke.call_args_list[0].kwargs["config"]["recursion_limit"] == 12
        assert "config" not in agent.agent.invoke.call_args_list[1].kwargs

    def test_execute_task_single_turn_fast_path_http_400_reroutes_to_auto_multi_turn(self):
        """Fast-path downgrade should reroute current request to auto multi-turn parser loop."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()

        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(400, request=request)
        agent.agent.invoke.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=request,
            response=response,
        )

        calculator_tool = Mock()
        calculator_tool.invoke.return_value = "16696.53125"
        agent.tools = [calculator_tool]
        agent.tools_by_name = {"calculator": calculator_tool}
        agent.native_tool_calling_enabled = True
        agent.loaded_langchain_tool_skill_count = 2
        agent.loaded_agent_skill_count = 1
        agent.agent_skill_names = {"legal_agent_skill"}

        round_counter = {"count": 0}

        def _plain_stream(_messages):
            round_counter["count"] += 1
            if round_counter["count"] == 1:
                yield SimpleNamespace(
                    content='{"tool":"calculator","expression":"23223*23/32"}',
                    additional_kwargs={},
                )
            else:
                yield SimpleNamespace(content="16696.53125", additional_kwargs={})

        plain_llm = Mock()
        plain_llm.stream = _plain_stream
        plain_llm.invoke = Mock(side_effect=AssertionError("Should not invoke in this path"))
        agent.llm = plain_llm
        agent.llm_with_tools = Mock()

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.DEBUG_CHAT,
            loop_mode=LoopMode.AUTO_MULTI_TURN,
            max_rounds=3,
            enable_error_recovery=True,
            stream_output=True,
        )
        chunks = []

        result = agent.execute_task(
            task_description="23223*23/32=?",
            runtime_policy=runtime_policy,
            stream_callback=lambda chunk: chunks.append(chunk),
        )

        assert result["success"] is True
        assert result["output"] == "16696.53125"
        assert agent.agent.invoke.call_count == 1
        assert round_counter["count"] == 2
        calculator_tool.invoke.assert_called_once_with({"expression": "23223*23/32"})
        assert agent.native_tool_calling_enabled is False
        assert agent.llm_with_tools is plain_llm
        assert ("16696.53125", "content") in chunks

    def test_execute_task_single_turn_fast_path_http_400_reroutes_to_recovery(self):
        """Fast-path downgrade should restore recovery mode when original policy is recovery."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()

        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(400, request=request)
        agent.agent.invoke.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=request,
            response=response,
        )

        agent.execute_task_with_recovery = AsyncMock(  # type: ignore[method-assign]
            return_value={"success": True, "output": "recovery ok", "messages": []}
        )
        agent.llm = Mock()
        agent.llm_with_tools = Mock()
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True
        agent.loaded_langchain_tool_skill_count = 2
        agent.loaded_agent_skill_count = 1
        agent.agent_skill_names = {"legal_agent_skill"}

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.DEBUG_CHAT,
            loop_mode=LoopMode.RECOVERY_MULTI_TURN,
            max_rounds=10,
            enable_error_recovery=True,
            stream_output=True,
        )

        result = agent.execute_task(
            task_description="23223*23/32=?",
            runtime_policy=runtime_policy,
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        assert result["output"] == "recovery ok"
        assert agent.agent.invoke.call_count == 1
        assert agent.native_tool_calling_enabled is False
        agent.execute_task_with_recovery.assert_awaited_once()
        recovery_kwargs = agent.execute_task_with_recovery.await_args.kwargs
        assert recovery_kwargs["task_description"] == "23223*23/32=?"
        assert recovery_kwargs["runtime_policy"].loop_mode == LoopMode.RECOVERY_MULTI_TURN

    def test_execute_task_auto_multi_turn_http_400_downgrades_to_plain_llm(self):
        """AUTO multi-turn stream failure on tool payload should retry with plain llm."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()  # initialize guard
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(400, request=request)

        bound_llm = Mock()
        bound_llm.stream.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=request,
            response=response,
        )
        plain_llm = Mock()
        plain_llm.invoke.return_value = AIMessage(content="final from plain llm")

        agent.llm = plain_llm
        agent.llm_with_tools = bound_llm
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.DEBUG_CHAT,
            loop_mode=LoopMode.AUTO_MULTI_TURN,
            max_rounds=1,
            enable_error_recovery=True,
            stream_output=True,
        )
        chunks = []

        result = agent.execute_task(
            task_description="你好",
            runtime_policy=runtime_policy,
            stream_callback=lambda chunk: chunks.append(chunk),
        )

        assert result["success"] is True
        assert result["output"] == "final from plain llm"
        assert agent.native_tool_calling_enabled is False
        assert agent.llm_with_tools is plain_llm
        plain_llm.invoke.assert_called_once()
        assert ("final from plain llm", "content") in chunks

    def test_execute_task_auto_resets_error_status_and_retries(self):
        """Cached agent in ERROR status should auto-reset for the next request."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ERROR
        agent.agent = Mock()
        agent.agent.invoke.return_value = {"messages": [AIMessage(content="ok after reset")]}
        agent.llm = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        result = agent.execute_task(task_description="ping")

        assert result["success"] is True
        assert result["output"] == "ok after reset"
        assert agent.status == AgentStatus.ACTIVE

    def test_execute_task_recovery_multi_turn_stream_fallback_emits_content(self):
        """Recovery path should still stream content when falling back to non-stream invoke."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )
        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()  # initialize guard
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        response = httpx.Response(400, request=request)

        bound_llm = Mock()
        bound_llm.stream.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=request,
            response=response,
        )
        plain_llm = Mock()
        plain_llm.invoke.return_value = AIMessage(content="recover output")

        agent.llm = plain_llm
        agent.llm_with_tools = bound_llm
        agent.tools = [Mock(name="calculator")]
        agent.tools_by_name = {"calculator": Mock()}
        agent.native_tool_calling_enabled = True

        runtime_policy = RuntimePolicy(
            profile=ExecutionProfile.MISSION_TASK,
            loop_mode=LoopMode.RECOVERY_MULTI_TURN,
            max_rounds=1,
            enable_error_recovery=True,
            stream_output=True,
        )
        chunks = []

        result = agent.execute_task(
            task_description="请回答",
            runtime_policy=runtime_policy,
            stream_callback=lambda chunk: chunks.append(chunk),
        )

        assert result["success"] is True
        assert result["output"] == "recover output"
        assert ("recover output", "content") in chunks
        assert agent.native_tool_calling_enabled is False
        assert agent.llm_with_tools is plain_llm
        plain_llm.invoke.assert_called_once()


class TestAgentRegistry:
    """Test agent registry."""

    @patch("agent_framework.agent_registry.get_db_session")
    def test_register_agent(self, mock_session):
        """Test agent registration."""
        # Mock database session
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        mock_agent = Mock()
        mock_agent.agent_id = uuid4()
        mock_agent.name = "Test Agent"
        mock_agent.agent_type = "test"
        mock_agent.owner_user_id = uuid4()
        mock_agent.capabilities = ["skill1"]
        mock_agent.status = "initializing"
        mock_agent.container_id = None
        mock_agent.created_at = Mock()
        mock_agent.updated_at = Mock()

        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Mock the agent creation
        with patch("agent_framework.agent_registry.Agent", return_value=mock_agent):
            registry = AgentRegistry()
            agent_info = registry.register_agent(
                name="Test Agent",
                agent_type="test",
                owner_user_id=uuid4(),
                capabilities=["skill1"],
            )

        assert agent_info.name == "Test Agent"
        assert mock_db.add.called
        assert mock_db.commit.called


class TestAgentLifecycle:
    """Test agent lifecycle management."""

    @patch("agent_framework.agent_lifecycle.get_agent_registry")
    def test_create_agent(self, mock_registry):
        """Test agent creation."""
        # Mock registry
        mock_agent_info = Mock()
        mock_agent_info.agent_id = uuid4()
        mock_agent_info.name = "Test Agent"
        mock_agent_info.agent_type = "test"
        mock_agent_info.owner_user_id = uuid4()
        mock_agent_info.capabilities = ["skill1"]

        mock_registry.return_value.register_agent.return_value = mock_agent_info

        lifecycle = AgentLifecycleManager(mock_registry.return_value)
        agent = lifecycle.create_agent(
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1"],
        )

        assert isinstance(agent, BaseAgent)
        assert agent.config.name == "Test Agent"


class TestCapabilityMatcher:
    """Test capability matching."""

    def test_calculate_match_score(self):
        """Test match score calculation."""
        matcher = CapabilityMatcher()

        agent_info = AgentInfo(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            avatar=None,
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2", "skill3"],
            status="active",
            container_id=None,
            created_at=Mock(),
            updated_at=Mock(),
        )

        required_capabilities = ["skill1", "skill2"]

        match = matcher._calculate_match(agent_info, required_capabilities)

        assert match.match_score == 1.0
        assert len(match.matched_capabilities) == 2
        assert len(match.missing_capabilities) == 0

    def test_partial_match(self):
        """Test partial capability match."""
        matcher = CapabilityMatcher()

        agent_info = AgentInfo(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            avatar=None,
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2"],
            status="active",
            container_id=None,
            created_at=Mock(),
            updated_at=Mock(),
        )

        required_capabilities = ["skill1", "skill2", "skill3", "skill4"]

        match = matcher._calculate_match(agent_info, required_capabilities)

        assert match.match_score == 0.5  # 2 out of 4
        assert len(match.matched_capabilities) == 2
        assert len(match.missing_capabilities) == 2


class TestAgentTools:
    """Test agent tools."""

    def test_create_default_tools(self):
        """Test creating default tools."""
        tools = create_langchain_tools()

        assert len(tools) > 0
        assert any(tool.name == "calculator" for tool in tools)

    def test_toolkit_add_tool(self):
        """Test adding tool to toolkit."""
        toolkit = AgentToolkit()

        mock_tool = Mock()
        mock_tool.name = "TestTool"

        toolkit.add_tool(mock_tool)

        assert len(toolkit.get_tools()) == 1
        assert toolkit.get_tool_by_name("TestTool") is not None


class TestRuntimeContextService:
    """Test runtime context retrieval against reset-architecture services."""

    @patch("agent_framework.runtime_context_service.get_skill_runtime_registry")
    def test_retrieve_skills_delegates_to_runtime_registry(self, mock_get_registry):
        agent_id = uuid4()
        user_id = uuid4()
        expected = [SimpleNamespace(content="learned.skill.goal=Stable PDF delivery")]
        mock_get_registry.return_value.retrieve_skills.return_value = expected

        service = RuntimeContextService()
        results = service.retrieve_skills(
            agent_id=agent_id,
            user_id=user_id,
            query="How should I deliver a converted PDF reliably?",
            top_k=3,
            min_similarity=0.66,
        )

        assert results == expected
        call_kwargs = mock_get_registry.return_value.retrieve_skills.call_args.kwargs
        assert call_kwargs["agent_id"] == agent_id
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["query"] == "How should I deliver a converted PDF reliably?"
        assert call_kwargs["top_k"] == 3
        assert call_kwargs["min_similarity"] == 0.66

    @patch("agent_framework.runtime_context_service.get_user_memory_retriever")
    def test_retrieve_user_memory_delegates_to_user_memory_retriever(self, mock_get_retriever):
        user_id = uuid4()
        expected = [SimpleNamespace(content="user.preference.response_style=concise")]
        mock_get_retriever.return_value.search_user_memory.return_value = expected

        service = RuntimeContextService()
        results = service.retrieve_user_memory(
            user_id=user_id,
            query="Answer concisely",
            top_k=3,
            min_similarity=0.5,
        )

        assert results == expected
        call_kwargs = mock_get_retriever.return_value.search_user_memory.call_args.kwargs
        assert call_kwargs["user_id"] == str(user_id)
        assert call_kwargs["query_text"] == "Answer concisely"
        assert call_kwargs["limit"] == 3
        assert call_kwargs["min_score"] == 0.5


class TestAgentExecutor:
    """Test agent executor."""

    @patch("agent_framework.agent_executor.get_runtime_context_service")
    def test_execute_agent(self, mock_context_service):
        """Test agent execution."""
        mock_context_service.return_value.retrieve_skills.return_value = [
            Mock(content="Test task agent note", similarity_score=0.91)
        ]
        mock_context_service.return_value.retrieve_user_memory.return_value = [
            Mock(content="Test task user preference", similarity_score=0.93)
        ]

        # Create mock agent
        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
        mock_agent.config.access_level = "team"
        mock_agent.config.allowed_memory = ["skills", "user_memory"]
        mock_agent.config.allowed_knowledge = []
        mock_agent.execute_task.return_value = {
            "success": True,
            "output": "Task completed",
        }

        executor = AgentExecutor(mock_context_service.return_value)
        context = ExecutionContext(
            agent_id=uuid4(),
            user_id=uuid4(),
            task_description="Test task",
        )

        result = executor.execute(mock_agent, context)

        assert result["success"]
        mock_agent.execute_task.assert_called_once()
        mock_context_service.return_value.retrieve_skills.assert_called_once()
        agent_retrieve_kwargs = mock_context_service.return_value.retrieve_skills.call_args.kwargs
        assert agent_retrieve_kwargs["user_id"] == context.user_id
        assert agent_retrieve_kwargs["min_similarity"] is None
        execute_context = mock_agent.execute_task.call_args.kwargs["context"]
        assert execute_context["skills"] == ["Test task agent note"]
        assert execute_context["user_memory"] == ["Test task user preference"]

    @patch("agent_framework.agent_executor.get_runtime_context_service")
    def test_execute_agent_passes_conversation_history(self, mock_context_service):
        """Executor should pass optional conversation history through to BaseAgent."""
        mock_context_service.return_value.retrieve_skills.return_value = []
        mock_context_service.return_value.retrieve_user_memory.return_value = []

        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
        mock_agent.config.access_level = "private"
        mock_agent.config.allowed_memory = []
        mock_agent.config.allowed_knowledge = []
        mock_agent.execute_task.return_value = {
            "success": True,
            "output": "Task completed",
        }

        executor = AgentExecutor(mock_context_service.return_value)
        context = ExecutionContext(
            agent_id=uuid4(),
            user_id=uuid4(),
            task_description="Test task",
        )
        history = [{"role": "user", "content": "Remember this."}]

        result = executor.execute(
            mock_agent,
            context,
            conversation_history=history,
            execution_profile=ExecutionProfile.DEBUG_CHAT,
        )

        assert result["success"] is True
        execute_kwargs = mock_agent.execute_task.call_args.kwargs
        assert execute_kwargs["conversation_history"] == history
        assert execute_kwargs["execution_profile"] == ExecutionProfile.DEBUG_CHAT

    @patch("agent_framework.agent_executor.get_runtime_context_service")
    def test_executor_filters_irrelevant_context_memories_and_applies_min_similarity(
        self, mock_context_service
    ):
        """Executor should drop off-topic memories before prompt injection."""
        mock_context_service.return_value.retrieve_skills.return_value = [
            Mock(
                content="品牌营销活动复盘",
                similarity_score=0.41,
                metadata={"_semantic_score": 0.29},
            ),
            Mock(content="火药相关安全风险讨论", similarity_score=0.86),
        ]
        mock_context_service.return_value.retrieve_user_memory.return_value = []

        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
        mock_agent.config.access_level = "team"
        mock_agent.config.allowed_memory = ["skills", "user_memory"]
        mock_agent.config.allowed_knowledge = []
        mock_agent.execute_task.return_value = {"success": True, "output": "Handled safely"}

        executor = AgentExecutor(mock_context_service.return_value)
        context = ExecutionContext(
            agent_id=uuid4(),
            user_id=uuid4(),
            task_description="化肥和白砂糖能做火药？",
        )

        result = executor.build_execution_context_with_debug(
            mock_agent,
            context,
            top_k=5,
            knowledge_min_relevance_score=0.7,
        )
        exec_context, debug = result

        assert "火药相关安全风险讨论" in exec_context["skills"]
        assert "品牌营销活动复盘" not in exec_context["skills"]
        assert exec_context["user_memory"] == []

        agent_kwargs = mock_context_service.return_value.retrieve_skills.call_args.kwargs
        assert agent_kwargs["min_similarity"] is None
        assert debug["memory"]["skills"]["filtered_out_count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
