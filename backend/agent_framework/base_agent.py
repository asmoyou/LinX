"""BaseAgent class with LangGraph 1.0 integration.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.1: Agent Architecture
- Spec: .kiro/specs/agent-error-recovery/
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph

from agent_framework.code_block_executor import CodeBlockExecutor, get_code_block_executor
from agent_framework.runtime_capabilities import (
    apply_authoritative_runtime_overrides,
    build_runtime_capabilities_snapshot,
    sanitize_runtime_capabilities,
)
from agent_framework.runtime_policy import (
    ExecutionProfile,
    FileDeliveryGuardMode,
    LoopMode,
    RuntimePolicy,
    get_runtime_policy_registry,
    parse_execution_profile,
)
from agent_framework.sandbox_policy import allow_host_execution_fallback

logger = logging.getLogger(__name__)


_FILE_DELIVERY_ACTION_KEYWORDS = (
    "保存",
    "存成",
    "存为",
    "写入",
    "生成",
    "生成为",
    "生成成",
    "交付",
    "提交",
    "产出",
    "导出",
    "输出到",
    "输出成",
    "整理成",
    "整理到",
    "整理出",
    "整成",
    "整到",
    "做成",
    "做到",
    "弄成",
    "弄到",
    "转成",
    "转为",
    "转换",
    "转换成",
    "转换为",
    "生成文件",
    "save",
    "export",
    "create",
    "generate",
    "produce",
    "convert",
    "convert to",
    "convert into",
    "deliver",
    "deliverable",
    "submit",
    "write to file",
    "output to file",
)
_FILE_DELIVERY_TARGET_KEYWORDS = (
    "文件",
    "文档",
    "excel",
    "xls",
    "xlsx",
    "表格",
    "spreadsheet",
    "pdf",
    ".pdf",
    "markdown",
    ".md",
    "md文档",
    "md文件",
    "txt文件",
    "json文件",
    "csv文件",
    "yaml文件",
    "doc",
    "docx",
    "xlsx",
    "pptx",
    "document",
    "file",
)
_FILE_DELIVERY_FORCE_PATTERN = re.compile(
    r"(?:整理成|保存为|保存成|生成(?:为|成)?|交付|提交|转(?:成|为)?|转换(?:成|为)?|save as|save to|generate as|generate to|deliver as|deliver to|submit as|submit to|export as|export to|convert to|convert into).{0,16}"
    r"(?:excel|xls|xlsx|表格|spreadsheet|pdf|md|markdown|txt|json|csv|yaml|yml|docx?|xlsx?|pptx?|文件|文档|file|document)",
    re.IGNORECASE,
)
_FILE_DELIVERY_REQUEST_PATTERN = re.compile(
    r"(?:"
    r"(?:给我|给出|提供|交付|提交|发我|send me|give me|provide|deliver|submit).{0,16}"
    r"(?:excel|xls|xlsx|表格|spreadsheet|pdf|md|markdown|txt|json|csv|yaml|yml|docx?|xlsx?|pptx?|文件|文档|file|document)"
    r"|"
    r"(?:excel|xls|xlsx|表格|spreadsheet|pdf|md|markdown|txt|json|csv|yaml|yml|docx?|xlsx?|pptx?|文件|文档|file|document).{0,16}"
    r"(?:给我|给出|提供|交付|提交|发我|send me|give me|provide|deliver|submit)"
    r")",
    re.IGNORECASE,
)
_FILE_DELIVERY_NEGATION_PATTERN = re.compile(
    r"(?:不要|别|无需|不用|不必|不需要).{0,6}"
    r"(?:保存|存为|存成|写入|生成|导出|输出|交付|提交|转换|转成|转为|文件|文档|pdf|md|markdown|txt|json|csv|yaml|yml|docx?|xlsx?|pptx?)"
    r"|(?:直接|仅|只).{0,8}(?:回复|返回|输出).{0,8}(?:不要|别|无需|不用|不必|不需要).{0,8}(?:文件|文档)"
    r"|(?:do\s*not|don't|no\s+need\s+to|without).{0,24}"
    r"(?:save|export|generate|write).{0,12}(?:file|document)?"
    r"|(?:reply|respond).{0,12}(?:directly|in\s+chat).{0,20}"
    r"(?:without|do\s*not|don't).{0,20}(?:file|save|export)",
    re.IGNORECASE,
)
_REQUESTED_FORMAT_PATTERN = re.compile(
    r"(?<![a-z0-9])(pdf|md|markdown|txt|json|csv|yaml|yml|docx|doc|xlsx|xls|pptx|ppt)(?![a-z0-9])",
    re.IGNORECASE,
)
_WORKSPACE_PATH_PATTERN = re.compile(r"(/workspace/[^\s'\"`<>]+)")
_TEXT_FILE_FORMATS = {"md", "txt", "json", "csv", "yml"}
_FORMAT_ALIASES = {
    "markdown": "md",
    "yaml": "yml",
}
_FILE_WRITE_TOOL_NAMES = {"write_file", "append_file", "edit_file"}


def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable with fallback."""
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        logger.warning(f"Invalid value for {key}, using default: {default}")
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float from environment variable with fallback."""
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        logger.warning(f"Invalid value for {key}, using default: {default}")
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable with fallback."""
    value = os.environ.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


class AgentStatus(Enum):
    """Agent status enumeration."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    TERMINATED = "terminated"
    ERROR = "error"


class AgentExecutionCancelled(RuntimeError):
    """Raised when agent execution is cancelled by caller."""


# ============================================================================
# Error Recovery Data Structures
# ============================================================================


@dataclass
class ParseError:
    """Records a tool call parsing error."""

    error_type: str  # "json_decode_error", "missing_field", "unknown_tool", "invalid_type"
    message: str
    malformed_input: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ToolCall:
    """Represents a parsed tool call."""

    tool_name: str
    arguments: Dict[str, Any]
    raw_json: str


@dataclass
class ToolResult:
    """Result of a tool execution attempt."""

    tool_name: str
    status: str  # "success", "error", "timeout"
    result: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # "timeout", "execution_error", "validation_error"
    retry_count: int = 0


@dataclass
class ToolCallRecord:
    """Records a single tool call attempt."""

    round_number: int
    tool_name: str
    arguments: Dict[str, Any]
    status: str  # "success", "parse_error", "execution_error", "timeout"
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_number: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorRecord:
    """Records an error occurrence."""

    round_number: int
    error_type: str  # "parse_error", "execution_error", "timeout", "validation_error"
    error_message: str
    tool_name: Optional[str] = None
    malformed_input: Optional[str] = None
    is_recoverable: bool = True
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorFeedback:
    """Structured feedback for LLM after error."""

    error_type: str
    error_message: str
    malformed_input: Optional[str]
    expected_format: str
    retry_count: int
    max_retries: int
    suggestions: List[str]

    def to_prompt(self) -> str:
        """Convert to human-readable prompt for LLM."""
        prompt = f"⚠️ **{self.error_type}** (Attempt {self.retry_count}/{self.max_retries})\n\n"

        prompt += f"**Error**: {self.error_message}\n\n"

        if self.malformed_input:
            # Truncate if too long
            input_display = self.malformed_input
            if len(input_display) > 200:
                input_display = input_display[:200] + "..."
            prompt += f"**Your input**:\n```\n{input_display}\n```\n\n"

        prompt += f"**Expected format**:\n```json\n{self.expected_format}\n```\n\n"

        if self.suggestions:
            prompt += "**Key fix**: "
            # Only show first 2 suggestions for brevity
            prompt += "; ".join(self.suggestions[:2])
            prompt += "\n\n"

        if self.retry_count < self.max_retries:
            prompt += "⚡ **Action**: Fix the error and retry immediately. Be concise - no lengthy explanations needed.\n"
        else:
            prompt += "⛔ Maximum retry attempts reached. Please provide a final answer without using tools.\n"

        return prompt


@dataclass
class ConversationState:
    """Tracks state of multi-round conversation."""

    round_number: int = 0
    max_rounds: int = 20
    tool_calls_made: List[ToolCallRecord] = field(default_factory=list)
    retry_counts: Dict[str, int] = field(default_factory=dict)  # key -> count
    errors: List[ErrorRecord] = field(default_factory=list)
    is_terminated: bool = False
    termination_reason: Optional[str] = None


# ============================================================================
# Agent Configuration and Base Class
# ============================================================================


@dataclass
class AgentConfig:
    """Agent configuration with environment variable support."""

    agent_id: UUID
    name: str
    agent_type: str
    owner_user_id: UUID
    capabilities: List[str]  # Platform skill IDs plus any non-platform runtime capabilities
    skill_env_user_id: Optional[UUID] = None
    access_level: str = "private"
    allowed_knowledge: List[str] = field(default_factory=list)
    llm_model: str = "ollama"
    temperature: float = 0.7
    max_iterations: int = 20  # Maximum conversation rounds
    system_prompt: Optional[str] = None  # Custom system prompt

    # Error recovery settings (can be overridden by environment variables)
    max_parse_retries: Optional[int] = None
    max_execution_retries: Optional[int] = None
    tool_timeout_seconds: Optional[float] = None
    enable_error_recovery: Optional[bool] = None
    context_window_tokens: Optional[int] = None
    context_compression_threshold: Optional[float] = None
    tool_result_item_max_chars: Optional[int] = None
    tool_result_total_max_chars: Optional[int] = None
    history_compress_chars: Optional[int] = None
    history_tail_protected_messages: Optional[int] = None

    def __post_init__(self):
        """Validate configuration and apply environment variable overrides."""
        if self.allowed_knowledge is None:
            self.allowed_knowledge = []
        if self.skill_env_user_id is None:
            self.skill_env_user_id = self.owner_user_id

        # Apply environment variable overrides with defaults
        if self.max_parse_retries is None:
            self.max_parse_retries = _get_env_int("AGENT_MAX_PARSE_RETRIES", 3)

        if self.max_execution_retries is None:
            self.max_execution_retries = _get_env_int("AGENT_MAX_EXECUTION_RETRIES", 5)

        if self.tool_timeout_seconds is None:
            self.tool_timeout_seconds = _get_env_float("AGENT_TOOL_TIMEOUT", 30.0)

        if self.enable_error_recovery is None:
            self.enable_error_recovery = _get_env_bool("AGENT_ENABLE_ERROR_RECOVERY", True)
        if self.context_window_tokens is None:
            self.context_window_tokens = _get_env_int("AGENT_DEFAULT_CONTEXT_WINDOW_TOKENS", 8192)
        if self.context_compression_threshold is None:
            self.context_compression_threshold = _get_env_float(
                "AGENT_CONTEXT_COMPRESSION_THRESHOLD", 0.8
            )
        if self.tool_result_item_max_chars is None:
            self.tool_result_item_max_chars = _get_env_int("AGENT_TOOL_RESULT_ITEM_MAX_CHARS", 1200)
        if self.tool_result_total_max_chars is None:
            self.tool_result_total_max_chars = _get_env_int(
                "AGENT_TOOL_RESULT_TOTAL_MAX_CHARS", 3200
            )
        if self.history_compress_chars is None:
            self.history_compress_chars = _get_env_int("AGENT_HISTORY_COMPRESS_CHARS", 600)
        if self.history_tail_protected_messages is None:
            self.history_tail_protected_messages = _get_env_int(
                "AGENT_HISTORY_TAIL_PROTECTED_MESSAGES", 6
            )

        # Validate retry limits
        if self.max_parse_retries < 0:
            raise ValueError(
                f"max_parse_retries must be non-negative, got {self.max_parse_retries}"
            )
        if self.max_execution_retries < 0:
            raise ValueError(
                f"max_execution_retries must be non-negative, got {self.max_execution_retries}"
            )

        # Validate timeout
        if not (1.0 <= self.tool_timeout_seconds <= 300.0):
            raise ValueError(
                f"tool_timeout_seconds must be between 1 and 300, got {self.tool_timeout_seconds}"
            )

        # Validate max_iterations
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be positive, got {self.max_iterations}")
        if self.context_window_tokens < 1024:
            raise ValueError(
                f"context_window_tokens must be >= 1024, got {self.context_window_tokens}"
            )
        if not (0.1 <= self.context_compression_threshold <= 0.95):
            raise ValueError(
                f"context_compression_threshold must be between 0.1 and 0.95, got {self.context_compression_threshold}"
            )
        if self.tool_result_item_max_chars < 200:
            raise ValueError(
                f"tool_result_item_max_chars must be >= 200, got {self.tool_result_item_max_chars}"
            )
        if self.tool_result_total_max_chars < self.tool_result_item_max_chars:
            raise ValueError(
                "tool_result_total_max_chars must be >= tool_result_item_max_chars, "
                f"got {self.tool_result_total_max_chars} < {self.tool_result_item_max_chars}"
            )
        if self.history_compress_chars < 200:
            raise ValueError(
                f"history_compress_chars must be >= 200, got {self.history_compress_chars}"
            )
        if self.history_tail_protected_messages < 2:
            raise ValueError(
                "history_tail_protected_messages must be >= 2, "
                f"got {self.history_tail_protected_messages}"
            )

        # Validate temperature
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError(f"temperature must be between 0 and 2, got {self.temperature}")

        logger.debug(
            "AgentConfig validated",
            extra={
                "agent_id": str(self.agent_id),
                "max_parse_retries": self.max_parse_retries,
                "max_execution_retries": self.max_execution_retries,
                "tool_timeout_seconds": self.tool_timeout_seconds,
                "enable_error_recovery": self.enable_error_recovery,
                "context_window_tokens": self.context_window_tokens,
                "context_compression_threshold": self.context_compression_threshold,
                "tool_result_item_max_chars": self.tool_result_item_max_chars,
                "tool_result_total_max_chars": self.tool_result_total_max_chars,
                "history_compress_chars": self.history_compress_chars,
                "history_tail_protected_messages": self.history_tail_protected_messages,
            },
        )


class BaseAgent:
    """Base agent class with LangGraph 1.0 integration.

    Each agent is an autonomous entity with:
    - Identity (agent_id, name, owner)
    - Capabilities (skills from Skill Library)
    - Runtime context access (User Memory + Skills + Knowledge Base)
    - Tools (LangChain tools)
    - Execution environment (isolated container)

    Uses LangGraph 1.0 StateGraph API for agent workflow.
    """

    def __init__(
        self,
        config: AgentConfig,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List] = None,
    ):
        """Initialize base agent.

        Args:
            config: Agent configuration
            llm: LangChain Chat Model instance
            tools: List of LangChain tools
        """
        self.config = config
        self.llm = llm
        self.tools = tools or []
        self.status = AgentStatus.INITIALIZING
        self.agent = None  # Will be CompiledGraph after initialization
        self.tools_by_name: Dict[str, Any] = {}
        self.skill_manager = None  # Will be initialized in initialize()
        self.code_executor = get_code_block_executor()  # Direct code block execution
        self.native_tool_calling_enabled = False
        self.loaded_langchain_tool_skill_count = 0
        self.loaded_agent_skill_count = 0
        self.langchain_tool_skill_names: Set[str] = set()
        self.agent_skill_names: Set[str] = set()
        self._cancel_requested = threading.Event()
        self._cancel_reason = ""
        self._cancel_lock = threading.Lock()

        logger.info(
            f"BaseAgent initialized: {config.name}",
            extra={
                "agent_id": str(config.agent_id),
                "agent_type": config.agent_type,
                "capabilities": config.capabilities,
            },
        )

    async def send_message(
        self,
        to_agent_id: UUID,
        message: str,
        message_type: str = "info",
    ) -> Dict[str, Any]:
        """Backward-compatible inter-agent send wrapper."""
        from agent_framework.inter_agent_communication import get_communicator

        communicator = get_communicator(agent_id=self.config.agent_id, task_id=uuid4())
        return await communicator.send_message(
            from_agent_id=self.config.agent_id,
            to_agent_id=to_agent_id,
            message=message,
            message_type=message_type,
        )

    async def receive_messages(self) -> List[Dict[str, Any]]:
        """Backward-compatible message polling wrapper."""
        from message_bus.pubsub import PubSubManager

        bus = PubSubManager()
        get_messages = getattr(bus, "get_messages", None)
        if callable(get_messages):
            return await get_messages(str(self.config.agent_id))
        return []

    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Return a minimal structured response for older communication tests."""
        message_type = message.get("type", "info")
        if message_type == "request":
            return {"reply": f"Processed request: {message.get('content', '')}"}
        return {"action": "acknowledged", "message_id": message.get("message_id")}

    async def request_assistance(
        self,
        required_capability: str,
        request: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible assistance request wrapper."""
        from agent_framework.inter_agent_communication import get_communicator

        communicator = get_communicator(agent_id=self.config.agent_id, task_id=uuid4())
        return await communicator.request_assistance(
            required_capability=required_capability,
            request=request,
            data=data or {},
        )

    async def delegate_task(self, to_agent_id: UUID, task: str) -> Dict[str, Any]:
        """Backward-compatible collaboration helper."""
        from agent_framework.inter_agent_communication import InterAgentCommunicator

        communicator = InterAgentCommunicator(agent_id=self.config.agent_id, task_id=uuid4())
        return await communicator.send_message(
            from_agent_id=self.config.agent_id,
            to_agent_id=to_agent_id,
            message=task,
            message_type="task_delegation",
        )

    async def send_result(self, to_agent_id: UUID, result: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible result delivery helper."""
        from agent_framework.inter_agent_communication import InterAgentCommunicator

        communicator = InterAgentCommunicator(agent_id=self.config.agent_id, task_id=uuid4())
        return await communicator.send_message(
            from_agent_id=self.config.agent_id,
            to_agent_id=to_agent_id,
            message=json.dumps(result, ensure_ascii=False),
            message_type="result",
        )

    async def initialize(self) -> None:
        """Initialize agent with LangGraph 1.0 components and skills."""
        try:
            if not self.llm:
                raise ValueError("LLM not configured for agent")

            # Initialize SkillManager
            from agent_framework.skill_manager import get_skill_manager

            self.skill_manager = get_skill_manager(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id,
                skill_env_user_id=self.config.skill_env_user_id,
            )

            # Discover and load skills based on agent's capabilities
            skills = await self.skill_manager.discover_skills()

            logger.info(
                f"Discovered {len(skills)} skills for agent {self.config.name}",
                extra={"agent_id": str(self.config.agent_id), "skill_count": len(skills)},
            )

            # Load skills
            langchain_tool_count = 0
            agent_skill_count = 0
            langchain_tool_names: Set[str] = set()
            agent_skill_names: Set[str] = set()

            for skill_info in skills:
                if skill_info.skill_type == "langchain_tool":
                    tool = await self.skill_manager.load_langchain_tool(skill_info)
                    if tool:
                        self.tools.append(tool)
                        langchain_tool_count += 1
                        langchain_tool_names.add(skill_info.skill_slug)
                        logger.info(
                            f"✓ Loaded LangChain tool: {skill_info.skill_slug}",
                            extra={
                                "agent_id": str(self.config.agent_id),
                                "skill_id": str(skill_info.skill_id),
                            },
                        )
                    else:
                        logger.error(
                            f"✗ Failed to load LangChain tool: {skill_info.skill_slug}",
                            extra={
                                "agent_id": str(self.config.agent_id),
                                "skill_id": str(skill_info.skill_id),
                            },
                        )
                elif skill_info.skill_type == "agent_skill":
                    # Agent skills are loaded as documentation, not tools
                    skill_ref = await self.skill_manager.load_agent_skill_doc(skill_info)
                    if skill_ref:
                        agent_skill_count += 1
                        agent_skill_names.add(skill_info.skill_slug)
                        logger.info(
                            f"✓ Loaded Agent Skill doc: {skill_info.skill_slug}",
                            extra={
                                "agent_id": str(self.config.agent_id),
                                "skill_id": str(skill_info.skill_id),
                            },
                        )
                    else:
                        logger.error(
                            f"✗ Failed to load Agent Skill doc: {skill_info.skill_slug}",
                            extra={
                                "agent_id": str(self.config.agent_id),
                                "skill_id": str(skill_info.skill_id),
                            },
                        )

            # Add enhanced bash tool with PTY and background support
            from agent_framework.tools.bash_tool import create_bash_tool
            from agent_framework.tools.process_manager import get_process_manager

            process_manager = get_process_manager()
            bash_tool = create_bash_tool(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id,
                process_manager=process_manager,
            )
            self.tools.append(bash_tool)
            logger.info(
                f"✓ Added enhanced bash tool (PTY + background support)",
                extra={"agent_id": str(self.config.agent_id)},
            )

            # Add process management tool
            from agent_framework.tools.process_tool import create_process_tool

            process_tool = create_process_tool(
                agent_id=self.config.agent_id, user_id=self.config.owner_user_id
            )
            self.tools.append(process_tool)
            logger.info(
                f"✓ Added process management tool", extra={"agent_id": str(self.config.agent_id)}
            )

            # Add code execution tool (for agent to run generated code)
            from agent_framework.tools.code_execution_tool import create_code_execution_tool

            code_exec_tool = create_code_execution_tool(
                agent_id=self.config.agent_id, user_id=self.config.owner_user_id
            )
            self.tools.append(code_exec_tool)

            from agent_framework.tools.manage_schedule_tool import create_manage_schedule_tool

            manage_schedule_tool = create_manage_schedule_tool(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id,
            )
            self.tools.append(manage_schedule_tool)

            # Add file operation tools (read, edit, write, append, list files in workspace)
            from agent_framework.tools.file_tools import create_file_tools

            file_tools = create_file_tools()
            self.tools.extend(file_tools)
            logger.info(
                f"✓ Added file tools (read_file, edit_file, write_file, append_file, list_files)",
                extra={"agent_id": str(self.config.agent_id)},
            )

            # Add read_skill tool (for agent to read Agent Skill documentation)
            if agent_skill_count > 0:
                from agent_framework.tools.read_skill_tool import create_read_skill_tool

                read_skill_tool = create_read_skill_tool(
                    agent_id=self.config.agent_id,
                    user_id=self.config.owner_user_id,
                    skill_manager=self.skill_manager,  # Pass the loaded skill_manager
                )
                self.tools.append(read_skill_tool)
                logger.info(
                    f"✓ Added read_skill tool for {agent_skill_count} Agent Skills",
                    extra={"agent_id": str(self.config.agent_id)},
                )

            logger.info(
                f"Skills loaded: {langchain_tool_count} LangChain tools, {agent_skill_count} Agent Skills",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "langchain_tools": langchain_tool_count,
                    "agent_skills": agent_skill_count,
                },
            )
            self.loaded_langchain_tool_skill_count = langchain_tool_count
            self.loaded_agent_skill_count = agent_skill_count
            self.langchain_tool_skill_names = langchain_tool_names
            self.agent_skill_names = agent_skill_names

            # Bind tools to LLM (if supported)
            if self.tools:
                self.tools_by_name = {tool.name: tool for tool in self.tools}
                try:
                    self.llm_with_tools = self.llm.bind_tools(self.tools)
                    self.native_tool_calling_enabled = True
                except (NotImplementedError, AttributeError) as e:
                    logger.warning(
                        f"LLM does not support bind_tools, using without tool binding: {e}",
                        extra={"agent_id": str(self.config.agent_id)},
                    )
                    self.native_tool_calling_enabled = False
                    self.llm_with_tools = self.llm
            else:
                self.native_tool_calling_enabled = False
                self.llm_with_tools = self.llm

            # Build agent graph using LangGraph 1.0 StateGraph API
            builder = StateGraph(MessagesState)

            # Add LLM node
            def call_llm(state: MessagesState) -> Dict[str, List]:
                """LLM node that processes messages and decides on tool calls."""
                messages = state["messages"]
                system_prompt = self._build_time_aware_system_prompt()

                # Prepend system message if not already present
                if not messages or not isinstance(messages[0], SystemMessage):
                    messages = [SystemMessage(content=system_prompt)] + messages

                response = self.llm_with_tools.invoke(messages)
                return {"messages": [response]}

            # Check if LLM supports tool calls
            llm_supports_tools = self.tools and self.native_tool_calling_enabled

            # Add tool execution node (only if tools are available and LLM supports them)
            if llm_supports_tools:

                def call_tools(state: MessagesState) -> Dict[str, List]:
                    """Tool node that executes tool calls."""
                    messages = state["messages"]
                    last_message = messages[-1]

                    tool_results = []
                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        for tool_call in last_message.tool_calls:
                            tool = self.tools_by_name.get(tool_call["name"])
                            if tool:
                                try:
                                    tool_args = self._normalize_tool_arguments_for_execution(
                                        tool_call["name"],
                                        tool,
                                        tool_call.get("args"),
                                    )
                                    result = tool.invoke(tool_args)
                                    from langchain_core.messages import ToolMessage

                                    tool_results.append(
                                        ToolMessage(
                                            content=str(result), tool_call_id=tool_call["id"]
                                        )
                                    )
                                except Exception as e:
                                    logger.error(f"Tool execution failed: {e}")
                                    from langchain_core.messages import ToolMessage

                                    tool_results.append(
                                        ToolMessage(
                                            content=f"Error: {str(e)}", tool_call_id=tool_call["id"]
                                        )
                                    )

                    return {"messages": tool_results}

                # Conditional edge to decide whether to continue or end
                def should_continue(state: MessagesState) -> str:
                    """Decide whether to continue with tools or end."""
                    messages = state["messages"]
                    last_message = messages[-1]

                    # Check if LLM made tool calls
                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        return "tools"
                    return END

                # Build graph with tools
                builder.add_node("llm", call_llm)
                builder.add_node("tools", call_tools)

                builder.add_edge(START, "llm")
                builder.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
                builder.add_edge("tools", "llm")
            else:
                # Build simple graph without tools
                logger.info(
                    f"Building agent without tool support",
                    extra={"agent_id": str(self.config.agent_id)},
                )
                builder.add_node("llm", call_llm)
                builder.add_edge(START, "llm")
                builder.add_edge("llm", END)

            # Compile the agent graph
            self.agent = builder.compile()

            self.status = AgentStatus.ACTIVE
            logger.info(f"Agent initialized successfully: {self.config.name}")

        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"Agent initialization failed: {e}", exc_info=True)
            raise

    @staticmethod
    def _normalize_history_content(content: Any) -> Any:
        """Normalize history content to plain text or multimodal list."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: List[str] = []
            multimodal_items: List[Dict[str, Any]] = []
            has_image_items = False
            for item in content:
                if isinstance(item, str) and item.strip():
                    text_value = item.strip()
                    text_parts.append(text_value)
                    multimodal_items.append({"type": "text", "text": text_value})
                    continue
                if isinstance(item, dict):
                    item_type = str(item.get("type") or "").strip().lower()
                    if item_type == "image_url":
                        image_url = item.get("image_url")
                        url_value: Optional[str] = None
                        if isinstance(image_url, dict):
                            raw_url = image_url.get("url")
                            if isinstance(raw_url, str):
                                url_value = raw_url.strip()
                        elif isinstance(image_url, str):
                            url_value = image_url.strip()

                        if url_value and (
                            url_value.startswith("data:image/")
                            or url_value.startswith("http://")
                            or url_value.startswith("https://")
                        ):
                            multimodal_items.append(
                                {"type": "image_url", "image_url": {"url": url_value}}
                            )
                            has_image_items = True
                        continue

                    text = item.get("text") or item.get("content")
                    if isinstance(text, str) and text.strip():
                        text_value = text.strip()
                        text_parts.append(text_value)
                        multimodal_items.append({"type": "text", "text": text_value})

            if has_image_items and multimodal_items:
                return multimodal_items
            return "\n".join(text_parts)

        if content is None:
            return ""

        return str(content)

    def _normalize_conversation_history(
        self, conversation_history: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Normalize optional conversation history into role/content pairs."""
        if not isinstance(conversation_history, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for entry in conversation_history:
            role = ""
            content_value: Any = None

            if isinstance(entry, dict):
                role = str(entry.get("role") or "").strip().lower()
                content_value = entry.get("content")
            elif isinstance(entry, HumanMessage):
                role = "user"
                content_value = entry.content
            elif isinstance(entry, AIMessage):
                role = "assistant"
                content_value = entry.content
            else:
                continue

            if role not in {"user", "assistant"}:
                continue

            normalized_content = self._normalize_history_content(content_value)
            if isinstance(normalized_content, list):
                content = normalized_content
            else:
                content = str(normalized_content or "").strip()
            if not content:
                continue

            normalized.append({"role": role, "content": content})

        return normalized

    @staticmethod
    def _build_system_time_context() -> Dict[str, str]:
        """Build authoritative system time context for conversation grounding."""
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        local_now = now_utc.astimezone().replace(microsecond=0)
        local_timezone = local_now.tzname() or str(local_now.tzinfo or "local")
        return {
            "utc_now": now_utc.isoformat().replace("+00:00", "Z"),
            "local_now": local_now.isoformat(),
            "local_timezone": local_timezone,
            "local_date": local_now.date().isoformat(),
        }

    @staticmethod
    def _render_system_time_prompt_block(system_time_context: Dict[str, str]) -> str:
        """Render system time block for agent chat prompts."""
        return (
            "## System Time Context\n"
            f"- UTC now: {system_time_context.get('utc_now', '')}\n"
            f"- Local now: {system_time_context.get('local_now', '')}\n"
            f"- Local timezone: {system_time_context.get('local_timezone', '')}\n"
            f"- Local date: {system_time_context.get('local_date', '')}\n"
            "Treat this context as authoritative current time for all date/time reasoning."
        )

    @staticmethod
    def _resolve_runtime_capabilities(
        context: Optional[Dict[str, Any]],
        *,
        session_workdir: Optional["Path"] = None,
        container_id: Optional[str] = None,
        code_execution_network_access: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Build authoritative runtime capabilities for current execution."""
        defaults = build_runtime_capabilities_snapshot(
            sandbox_enabled=bool(str(container_id or "").strip()),
            sandbox_backend="docker" if container_id else "host_subprocess",
            workspace_root_virtual="/workspace",
            writable_roots=["/workspace"],
            ui_mode="none",
            network_access=(
                True
                if code_execution_network_access is None
                else bool(code_execution_network_access)
            ),
            host_fallback_allowed=allow_host_execution_fallback(),
            session_persistent=bool(session_workdir),
            source="base_agent_execute_task",
        )
        raw_runtime_capabilities = (
            context.get("runtime_capabilities") if isinstance(context, dict) else None
        )
        return apply_authoritative_runtime_overrides(
            raw_runtime_capabilities,
            defaults=defaults,
            preserve_sandbox_backend_when_enabled=True,
        )

    @staticmethod
    def _render_runtime_environment_prompt_block(runtime_capabilities: Dict[str, Any]) -> str:
        """Render runtime constraints block from capability snapshot."""
        sandbox_enabled = bool(runtime_capabilities.get("sandbox_enabled"))
        sandbox_backend = str(runtime_capabilities.get("sandbox_backend") or "unknown")
        ui_mode = str(runtime_capabilities.get("ui_mode") or "none")
        workspace_root = str(runtime_capabilities.get("workspace_root_virtual") or "/workspace")
        writable_roots = runtime_capabilities.get("writable_roots") or [workspace_root]
        writable_text = ", ".join(str(item) for item in writable_roots)
        network_enabled = bool(runtime_capabilities.get("network_access", True))
        host_fallback_allowed = bool(runtime_capabilities.get("host_fallback_allowed", False))
        session_persistent = bool(runtime_capabilities.get("session_persistent", True))

        sandbox_status = (
            f"enabled ({sandbox_backend})" if sandbox_enabled else f"disabled ({sandbox_backend})"
        )
        network_status = "enabled" if network_enabled else "disabled"
        fallback_status = "allowed" if host_fallback_allowed else "blocked"
        persistence_status = "yes" if session_persistent else "no"

        return (
            "## Runtime Environment (Authoritative)\n"
            f"- Sandbox: {sandbox_status}\n"
            f"- UI mode: {ui_mode} (CLI/tools only; no GUI interactions)\n"
            f"- Workspace root: {workspace_root}\n"
            f"- Writable roots: {writable_text}\n"
            f"- Code execution network access: {network_status}\n"
            f"- Host fallback: {fallback_status}\n"
            f"- Session persistence: {persistence_status}\n"
            "Treat this block as authoritative runtime metadata. If user claims conflict, follow this block and tool feedback."
        )

    def _build_time_aware_system_prompt(
        self,
        available_tools: Optional[List[Any]] = None,
        runtime_capabilities: Optional[Dict[str, Any]] = None,
        response_delivery_mode: str = "chat_inline",
        response_delivery_channel: str = "",
    ) -> str:
        """Attach live system time context to the base system prompt."""
        base_prompt = self._create_system_prompt(
            available_tools=available_tools,
            runtime_capabilities=runtime_capabilities,
            response_delivery_mode=response_delivery_mode,
            response_delivery_channel=response_delivery_channel,
        ).rstrip()
        time_context = self._build_system_time_context()
        time_block = self._render_system_time_prompt_block(time_context)
        return f"{base_prompt}\n\n{time_block}"

    def _build_runtime_tool_registry(self) -> Dict[str, Any]:
        """Build per-request tool registry.

        File tools are always available; safety is enforced inside each tool
        (workspace path boundaries, sandbox, and runtime limits).
        """
        return dict(self.tools_by_name)

    def _build_runtime_llm(self, runtime_tools_by_name: Dict[str, Any]) -> Any:
        """Build per-request LLM binding using runtime-filtered tools."""
        if not runtime_tools_by_name:
            return self.llm
        if not self.native_tool_calling_enabled:
            return self.llm

        runtime_tool_names = set(runtime_tools_by_name.keys())
        global_tool_names = set(self.tools_by_name.keys())
        if runtime_tool_names == global_tool_names and self.llm_with_tools is not None:
            return self.llm_with_tools

        try:
            return self.llm.bind_tools(list(runtime_tools_by_name.values()))
        except (NotImplementedError, AttributeError) as bind_error:
            logger.warning(
                "Runtime tool binding not supported, fallback to plain LLM: %s",
                bind_error,
                extra={"agent_id": str(self.config.agent_id)},
            )
            return self.llm

    def _build_messages_with_history(
        self,
        human_content: Any,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        extra_system_messages: Optional[List[str]] = None,
        available_tools: Optional[List[Any]] = None,
        runtime_capabilities: Optional[Dict[str, Any]] = None,
        response_delivery_mode: str = "chat_inline",
        response_delivery_channel: str = "",
    ) -> List[Any]:
        """Build prompt messages with optional conversation history."""
        system_prompt = self._build_time_aware_system_prompt(
            available_tools=available_tools,
            runtime_capabilities=runtime_capabilities,
            response_delivery_mode=response_delivery_mode,
            response_delivery_channel=response_delivery_channel,
        )
        messages: List[Any] = [SystemMessage(content=system_prompt)]
        for system_message in extra_system_messages or []:
            normalized = str(system_message or "").strip()
            if normalized:
                messages.append(SystemMessage(content=normalized))

        for item in self._normalize_conversation_history(conversation_history):
            if item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
            else:
                messages.append(HumanMessage(content=item["content"]))

        messages.append(HumanMessage(content=human_content))
        return messages

    @staticmethod
    def _requires_file_delivery(task_description: str) -> bool:
        """Infer whether user explicitly requests file/document deliverable output."""
        text = str(task_description or "").strip()
        if not text:
            return False

        if _FILE_DELIVERY_NEGATION_PATTERN.search(text):
            return False

        lowered = text.lower()
        has_action = any(keyword in lowered for keyword in _FILE_DELIVERY_ACTION_KEYWORDS)
        has_target = any(keyword in lowered for keyword in _FILE_DELIVERY_TARGET_KEYWORDS)
        if has_action and has_target:
            return True

        if _FILE_DELIVERY_FORCE_PATTERN.search(text):
            return True

        return bool(_FILE_DELIVERY_REQUEST_PATTERN.search(text))

    @staticmethod
    def _resolve_file_delivery_guard_mode(
        runtime_policy: Optional[RuntimePolicy],
    ) -> FileDeliveryGuardMode:
        """Resolve file-delivery guard mode from runtime policy with safe fallback."""
        raw_mode = (
            getattr(runtime_policy, "file_delivery_guard_mode", FileDeliveryGuardMode.SOFT)
            if runtime_policy is not None
            else FileDeliveryGuardMode.SOFT
        )
        if isinstance(raw_mode, FileDeliveryGuardMode):
            return raw_mode
        try:
            return FileDeliveryGuardMode(str(raw_mode).strip().lower())
        except ValueError:
            return FileDeliveryGuardMode.SOFT

    @staticmethod
    def _normalize_requested_file_format(format_name: str) -> str:
        """Normalize aliases for requested file formats."""
        lowered = str(format_name or "").strip().lower().lstrip(".")
        return _FORMAT_ALIASES.get(lowered, lowered)

    def _extract_requested_file_formats(self, task_description: str) -> Set[str]:
        """Extract explicitly requested output file formats from user task text."""
        text = str(task_description or "")
        if not text:
            return set()

        formats: Set[str] = set()
        for match in _REQUESTED_FORMAT_PATTERN.findall(text):
            normalized = self._normalize_requested_file_format(match)
            if normalized:
                formats.add(normalized)
        return formats

    @staticmethod
    def _extract_tool_record_name(record: Any) -> str:
        """Extract normalized tool name from dict/dataclass tool call records."""
        value: Any = None
        if isinstance(record, dict):
            value = record.get("tool_name") or record.get("name") or record.get("tool")
        else:
            value = (
                getattr(record, "tool_name", None)
                or getattr(record, "name", None)
                or getattr(record, "tool", None)
            )
        return str(value or "").strip().lower()

    @staticmethod
    def _extract_tool_record_status(record: Any) -> str:
        """Extract normalized status from dict/dataclass tool call records."""
        value: Any = None
        if isinstance(record, dict):
            value = record.get("status")
        else:
            value = getattr(record, "status", None)
        return str(value or "").strip().lower()

    @staticmethod
    def _extract_tool_record_round_number(record: Any) -> int:
        """Extract round number from dict/dataclass tool call records."""
        value: Any = 0
        if isinstance(record, dict):
            value = record.get("round_number")
            if value is None:
                value = record.get("round")
        else:
            value = getattr(record, "round_number", None)
            if value is None:
                value = getattr(record, "round", None)

        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_tool_record_error(record: Any) -> str:
        """Extract error text from dict/dataclass tool call records."""
        value: Any = None
        if isinstance(record, dict):
            value = record.get("error")
            if value is None:
                value = record.get("message")
        else:
            value = getattr(record, "error", None)
            if value is None:
                value = getattr(record, "message", None)
        return str(value or "").strip()

    @staticmethod
    def _is_failed_tool_status(status: str) -> bool:
        """Check whether normalized status means tool failure."""
        return status in {
            "error",
            "execution_error",
            "timeout",
            "failed",
            "failure",
            "tool_error",
            "runtime_error",
        }

    def _find_latest_failed_tool_record(self, tool_call_records: List[Any]) -> Optional[Any]:
        """Return the latest failed tool call record, if any."""
        for record in reversed(tool_call_records):
            status = self._extract_tool_record_status(record)
            if self._is_failed_tool_status(status):
                return record
            if not status and self._extract_tool_record_error(record):
                return record
        return None

    def _latest_successful_tool_round(self, tool_call_records: List[Any]) -> int:
        """Return the latest round index with successful tool execution."""
        latest_round = 0
        for record in tool_call_records:
            status = self._extract_tool_record_status(record)
            if status and status not in {"success", "ok", "completed"}:
                continue
            latest_round = max(latest_round, self._extract_tool_record_round_number(record))
        return latest_round

    def _summarize_recent_tool_activity(self, tool_call_records: List[Any], limit: int = 8) -> str:
        """Summarize recent tool activity for autonomous completion checks."""
        if not tool_call_records:
            return "No tool activity."

        lines: List[str] = []
        for record in tool_call_records[-max(1, limit) :]:
            tool_name = self._extract_tool_record_name(record) or "unknown_tool"
            status = self._extract_tool_record_status(record) or "unknown"
            round_number = self._extract_tool_record_round_number(record)
            if self._is_failed_tool_status(status):
                error_preview = self._truncate_stream_preview(
                    self._extract_tool_record_error(record), max_chars=120
                )
                lines.append(
                    f"- round={round_number} tool={tool_name} status={status} error={error_preview}"
                )
            else:
                lines.append(f"- round={round_number} tool={tool_name} status={status}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_finish_reason(value: Any) -> str:
        """Normalize heterogeneous provider finish/stop reason labels."""
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not normalized:
            return ""

        aliases = {
            "end_turn": "stop",
            "eot": "stop",
            "tool_call": "tool_calls",
            "function_call": "tool_calls",
            "max_tokens": "length",
            "token_limit": "length",
        }
        return aliases.get(normalized, normalized)

    def _extract_finish_reason(self, payload: Any) -> str:
        """Extract normalized finish reason from model response/chunk metadata."""
        if payload is None:
            return ""

        candidate_dicts: List[Dict[str, Any]] = []

        if isinstance(payload, dict):
            candidate_dicts.append(payload)

        for attr in ("response_metadata", "additional_kwargs", "generation_info"):
            value = getattr(payload, attr, None)
            if isinstance(value, dict):
                candidate_dicts.append(value)

        def _walk(node: Dict[str, Any], depth: int = 0) -> str:
            if depth > 2:
                return ""
            for key, value in node.items():
                lowered_key = str(key).strip().lower()
                if lowered_key in {"finish_reason", "stop_reason", "finishreason", "stopreason"}:
                    normalized = self._normalize_finish_reason(value)
                    if normalized:
                        return normalized
                if isinstance(value, dict):
                    found = _walk(value, depth + 1)
                    if found:
                        return found
            return ""

        for node in candidate_dicts:
            found_reason = _walk(node)
            if found_reason:
                return found_reason

        return ""

    def _build_autonomy_continue_feedback(self, decision: Dict[str, Any]) -> str:
        """Build generic follow-up instruction when autonomous self-check says incomplete."""
        reason = (
            self._truncate_stream_preview(decision.get("reason"), max_chars=220)
            or "Task not complete yet"
        )
        next_action = (
            self._truncate_stream_preview(decision.get("next_action"), max_chars=220)
            or "Decide and execute the most effective next step."
        )
        return (
            "任务尚未完成，请继续自主推进，不要在当前轮次结束。\n"
            f"自检原因：{reason}\n"
            f"建议下一步：{next_action}\n"
            "请自行判断并执行下一步（必要时调用工具），仅在任务完全完成后再给最终答复。"
        )

    @staticmethod
    def _resolve_response_delivery_mode(context: Any) -> str:
        """Resolve whether the current surface expects inline chat output or file-first delivery."""
        if not isinstance(context, dict):
            return "chat_inline"
        normalized = str(context.get("response_delivery_mode") or "").strip().lower()
        if normalized in {"chat_inline", "file_first_summary"}:
            return normalized
        return "chat_inline"

    @staticmethod
    def _resolve_response_delivery_channel(context: Any) -> str:
        """Resolve channel label for response delivery guidance."""
        if not isinstance(context, dict):
            return ""
        return str(context.get("response_delivery_channel") or "").strip().lower()

    def _looks_like_inline_file_delivery_dump(self, text: str) -> bool:
        """Detect outputs that inline large file contents instead of concise delivery status."""
        raw = str(text or "").strip()
        if not raw:
            return False

        lowered = raw.lower()
        preview_tokens = (
            "```",
            "完整代码",
            "完整内容",
            "文档内容预览",
            "内容预览",
            "文档预览",
            "文件预览",
            "内容概览",
            "文档内容概览",
            "全文如下",
            "代码如下",
            "内容如下",
            "full code",
            "full content",
            "source code",
            "preview",
        )
        if any(token in lowered for token in preview_tokens):
            return True

        heading_count = sum(
            1 for line in raw.splitlines() if re.match(r"^\s{0,3}#{1,4}\s+\S", line)
        )
        workspace_path_count = len(self._extract_workspace_paths_from_text(raw))
        if len(raw) >= 1200 and (heading_count >= 4 or workspace_path_count >= 1):
            return True
        return False

    def _assess_autonomous_completion(
        self,
        *,
        task_intent_text: str,
        latest_output: str,
        tool_call_records: List[Any],
        round_number: int,
        max_rounds: int,
        file_delivery_required: bool = False,
        file_delivery_guard_mode: FileDeliveryGuardMode = FileDeliveryGuardMode.SOFT,
        requested_file_formats: Optional[Set[str]] = None,
        response_delivery_mode: str = "chat_inline",
        finish_reason: str = "",
    ) -> Dict[str, Any]:
        """Deterministic state-machine decision for autonomous continue vs stop."""
        _ = task_intent_text  # Keep API stable while using output/tools as primary signals.
        normalized_finish_reason = self._normalize_finish_reason(finish_reason)

        # Hard cap: stop when max rounds reached.
        if round_number >= max_rounds:
            return {
                "should_stop": True,
                "confidence": 0.99,
                "reason": "max rounds reached",
                "next_action": "",
                "feedback_prompt": "",
            }

        # Provider hinted truncation: continue to let model finish.
        if normalized_finish_reason == "length":
            return {
                "should_stop": False,
                "confidence": 0.05,
                "reason": "model output reached token limit",
                "next_action": "Continue from previous partial answer and finish remaining work.",
                "feedback_prompt": (
                    "上一轮输出因长度限制被截断。请直接续写并完成剩余步骤，"
                    "必要时继续调用工具，直到任务完成再停止。"
                ),
            }

        # Provider hinted tool-calling turn but parser got no executable call in this branch.
        if normalized_finish_reason == "tool_calls":
            return {
                "should_stop": False,
                "confidence": 0.05,
                "reason": "model signaled tool call turn",
                "next_action": "Continue by emitting valid tool calls or proceed with executable next step.",
                "feedback_prompt": (
                    "你上一轮进入了工具调用回合，但当前未形成可执行的工具调用。"
                    "请继续并输出可执行的工具调用，或立即执行下一步。"
                ),
            }

        if file_delivery_required:
            missing_file_delivery = False
            if requested_file_formats and not self._has_successful_requested_format_call(
                tool_call_records, requested_file_formats
            ):
                missing_file_delivery = True

            if not requested_file_formats and not self._has_successful_file_write_call(
                tool_call_records
            ):
                missing_file_delivery = True

            if missing_file_delivery:
                if file_delivery_guard_mode == FileDeliveryGuardMode.STRICT:
                    return {
                        "should_stop": False,
                        "confidence": 0.1,
                        "reason": "file deliverable not yet verified",
                        "next_action": "Continue and complete requested file delivery.",
                        "feedback_prompt": self._build_file_delivery_guard_feedback(
                            requested_file_formats
                        ),
                    }

                if file_delivery_guard_mode == FileDeliveryGuardMode.SOFT:
                    return {
                        "should_stop": True,
                        "confidence": 0.65,
                        "reason": "file deliverable not yet verified (soft mode advisory)",
                        "next_action": "",
                        "feedback_prompt": "",
                        "advisory_message": self._build_file_delivery_soft_advisory(
                            requested_file_formats
                        ),
                    }

            if self._looks_like_inline_file_delivery_dump(latest_output):
                return {
                    "should_stop": False,
                    "confidence": 0.15,
                    "reason": "final answer inlined delivered file contents",
                    "next_action": (
                        "Rewrite the final reply as a concise delivery confirmation "
                        "with exact file paths and a short summary only."
                    ),
                    "feedback_prompt": (
                        "当前界面会把文件结果单独展示给用户。请重写最终答复："
                        "只保留交付状态、准确文件路径，以及最多 1-3 句摘要或章节概览；"
                        "不要粘贴文件原文、长篇预览或完整代码。"
                    ),
                }

        latest_failed_record = self._find_latest_failed_tool_record(tool_call_records)
        if latest_failed_record is not None:
            failed_round = self._extract_tool_record_round_number(latest_failed_record)
            latest_success_round = self._latest_successful_tool_round(tool_call_records)
            if latest_success_round < failed_round:
                return {
                    "should_stop": False,
                    "confidence": 0.1,
                    "reason": "unresolved tool failure still exists",
                    "next_action": "Continue and resolve the failed step before final answer.",
                    "feedback_prompt": self._build_execution_recovery_guard_feedback(
                        latest_failed_record
                    ),
                }

        lowered_output = str(latest_output or "").strip().lower()
        if not lowered_output:
            return {
                "should_stop": False,
                "confidence": 0.05,
                "reason": "latest output is empty",
                "next_action": "Continue with a concrete executable step.",
                "feedback_prompt": "",
            }

        incomplete_patterns = (
            r"(任务|当前任务|工作).{0,8}(未完成|尚未完成|还未完成|还没完成)",
            r"(我|当前).{0,8}(需要|还需).{0,8}(继续|下一步|进一步)",
            r"(将|会).{0,6}(继续|下一步).{0,10}(执行|处理|调用)",
            r"(请|先).{0,4}(继续|稍等)",
            r"i\s+(still\s+)?need\s+to",
            r"not\s+complete",
            r"incomplete",
            r"(unable\s+to|cannot|can't)",
        )
        if any(re.search(pattern, lowered_output) for pattern in incomplete_patterns):
            return {
                "should_stop": False,
                "confidence": 0.2,
                "reason": "latest output indicates incomplete state",
                "next_action": "Continue autonomous execution until deliverables are complete.",
                "feedback_prompt": "",
            }

        return {
            "should_stop": True,
            "confidence": 0.85,
            "reason": "no pending execution signals detected",
            "next_action": "",
            "feedback_prompt": "",
        }

    @staticmethod
    def _extract_workspace_paths_from_text(text: Any) -> List[str]:
        """Extract /workspace paths from free-form text/code snippets."""
        raw = str(text or "")
        if not raw:
            return []

        extracted: List[str] = []
        for match in _WORKSPACE_PATH_PATTERN.findall(raw):
            path = str(match or "").strip()
            if not path:
                continue
            normalized = path.rstrip(".,;:!?)]}>\"'")
            if normalized and normalized not in extracted:
                extracted.append(normalized)
        return extracted

    @staticmethod
    def _extract_tool_record_arguments(record: Any) -> Dict[str, Any]:
        """Extract tool arguments from dict/dataclass records."""
        args: Any = None
        if isinstance(record, dict):
            args = record.get("arguments")
            if args is None:
                args = record.get("args")
        else:
            args = getattr(record, "arguments", None)
            if args is None:
                args = getattr(record, "args", None)
        return args if isinstance(args, dict) else {}

    @staticmethod
    def _extract_tool_record_result(record: Any) -> Any:
        """Extract tool result payload from dict/dataclass records."""
        if isinstance(record, dict):
            return record.get("result")
        return getattr(record, "result", None)

    def _extract_tool_record_paths(self, record: Any) -> List[str]:
        """Extract file paths referenced by a tool call record."""
        paths: List[str] = []
        args = self._extract_tool_record_arguments(record)
        tool_name = self._extract_tool_record_name(record)

        file_path = args.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            normalized_path = file_path.strip()
            if normalized_path.startswith("/workspace/") and normalized_path not in paths:
                paths.append(normalized_path)

        if tool_name == "code_execution":
            code = args.get("code")
            for code_path in self._extract_workspace_paths_from_text(code):
                if code_path not in paths:
                    paths.append(code_path)

        result = self._extract_tool_record_result(record)
        for result_path in self._extract_workspace_paths_from_text(result):
            if result_path not in paths:
                paths.append(result_path)

        return paths

    @staticmethod
    def _path_matches_requested_formats(path: str, requested_formats: Set[str]) -> bool:
        """Check whether path extension satisfies requested file formats."""
        if not requested_formats:
            return True

        normalized_path = str(path or "").strip()
        if not normalized_path:
            return False

        _, dot_ext = os.path.splitext(normalized_path)
        ext = dot_ext.lower().lstrip(".")
        if not ext:
            return False

        normalized_ext = _FORMAT_ALIASES.get(ext, ext)
        return normalized_ext in requested_formats

    def _has_successful_requested_format_call(
        self, tool_call_records: List[Any], requested_formats: Set[str]
    ) -> bool:
        """Check whether successful tool execution produced requested output format."""
        if not requested_formats:
            return self._has_successful_file_write_call(tool_call_records)

        for record in tool_call_records:
            status = self._extract_tool_record_status(record)
            if status and status not in {"success", "ok", "completed"}:
                continue

            tool_name = self._extract_tool_record_name(record)
            if tool_name not in _FILE_WRITE_TOOL_NAMES and tool_name != "code_execution":
                continue

            for path in self._extract_tool_record_paths(record):
                if self._path_matches_requested_formats(path, requested_formats):
                    return True

        return False

    def _has_successful_file_write_call(self, tool_call_records: List[Any]) -> bool:
        """Check whether any successful file-writing tool call has already happened."""
        for record in tool_call_records:
            tool_name = self._extract_tool_record_name(record)
            if tool_name not in _FILE_WRITE_TOOL_NAMES:
                continue

            status = self._extract_tool_record_status(record)
            # Legacy AUTO loop only stores successful calls and has no explicit status.
            if not status or status in {"success", "ok", "completed"}:
                return True
        return False

    def _build_file_delivery_guard_feedback(
        self, requested_formats: Optional[Set[str]] = None
    ) -> str:
        """Build corrective prompt when user requested file output but no file write happened."""
        normalized_formats = {
            self._normalize_requested_file_format(fmt)
            for fmt in (requested_formats or set())
            if fmt
        }
        target_format = sorted(normalized_formats)[0] if normalized_formats else "md"
        suggested_path = f"/workspace/output/result.{target_format}"
        format_hint = (
            f"用户明确要求的交付格式是: {', '.join(sorted(normalized_formats))}。\n"
            if normalized_formats
            else ""
        )
        binary_delivery = bool(normalized_formats - _TEXT_FILE_FORMATS)

        if binary_delivery:
            delivery_rule = (
                "你可以先用 write_file/append_file 生成中间文本，再使用 code_execution 产出目标格式文件。\n"
                "生成后请调用 list_files 验证目标文件存在。"
            )
        else:
            delivery_rule = "不要使用 code_execution 来代替文件交付步骤。"

        return (
            "你上一轮尚未把结果保存成文件。用户明确要求交付文档/文件。\n"
            + format_hint
            + "请立即调用文件工具完成保存：首次使用 write_file 创建目标文件，后续内容使用 append_file 追加（优先单文件）。\n"
            + delivery_rule
            + "\n"
            + f"建议路径：{suggested_path}\n"
            + "完成后仅简要回复保存路径与状态，不要只输出正文。"
        )

    def _build_file_delivery_soft_advisory(
        self, requested_formats: Optional[Set[str]] = None
    ) -> str:
        """Build lightweight advisory when soft guard detects missing file delivery."""
        normalized_formats = {
            self._normalize_requested_file_format(fmt)
            for fmt in (requested_formats or set())
            if fmt
        }
        format_hint = (
            f"目标格式: {', '.join(sorted(normalized_formats))}。"
            if normalized_formats
            else "目标格式未明确。"
        )
        return (
            "检测到请求可能包含文件交付，但尚未验证已落盘。"
            + format_hint
            + "当前策略为 soft：不会强制继续轮次。"
            + "若你确实需要文件，请明确要求“保存为文件”并指定格式或路径。"
        )

    def _build_execution_recovery_guard_feedback(self, failed_record: Any) -> str:
        """Build corrective prompt when previous tool attempt failed but model stopped tool usage."""
        tool_name = self._extract_tool_record_name(failed_record) or "unknown_tool"
        error_message = self._extract_tool_record_error(failed_record) or "Unknown tool error"
        error_preview = self._truncate_stream_preview(error_message, max_chars=300)
        suggestions = self._build_execution_error_suggestions(
            ToolResult(
                tool_name=tool_name,
                status="error",
                error=error_message,
                error_type="execution_error",
            )
        )
        suggestion_lines = "\n".join(f"- {item}" for item in suggestions[:3])

        return (
            "你上一轮工具执行失败，任务尚未完成，不能在此直接结束。\n"
            f"失败工具：{tool_name}\n"
            f"错误摘要：{error_preview}\n"
            "请立刻继续调用工具修复并重试（优先最小改动）。\n"
            + ("修复建议：\n" + suggestion_lines + "\n" if suggestion_lines else "")
            + "完成后再给最终答案，并明确提供产出结果或文件路径。"
        )

    @staticmethod
    def _extract_tool_runtime_error(result: Any) -> Optional[str]:
        """Infer tool-level failure from returned payload/content."""
        if isinstance(result, dict):
            success_value = result.get("success")
            status_value = str(result.get("status", "")).strip().lower()
            if success_value is False or status_value in {"error", "failed", "failure", "timeout"}:
                detail = result.get("error") or result.get("message") or result
                return str(detail)

        text = str(result or "").strip()
        if not text:
            return None

        lowered = text.lower()
        if re.match(r"^error(?:\s+[a-z0-9_./-]+){0,4}\s*:", lowered):
            return text
        if lowered.startswith("code execution failed:") or lowered.startswith(
            "code execution error:"
        ):
            return text
        if lowered.startswith("❌") or "command failed (exit code" in lowered:
            return text

        return None

    @staticmethod
    def _truncate_stream_preview(value: Any, max_chars: int = 220) -> str:
        """Normalize and truncate stream-facing text previews."""
        if value is None:
            return ""

        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"\s+", " ", text).strip()
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max(0, max_chars - 3)] + "..."

    def _summarize_tool_arguments_for_stream(
        self, tool_name: str, arguments: Optional[Dict[str, Any]]
    ) -> str:
        """Build compact argument summary for tool_call stream events."""
        if not isinstance(arguments, dict) or not arguments:
            return "(无)"

        normalized_tool = str(tool_name or "").strip().lower()

        if normalized_tool in {"write_file", "append_file"}:
            file_path = str(arguments.get("file_path") or "").strip() or "<missing>"
            content_value = arguments.get("content")
            content_chars = len(content_value) if isinstance(content_value, str) else 0
            return f"file_path={file_path}, content_chars={content_chars}"

        if normalized_tool == "edit_file":
            file_path = str(arguments.get("file_path") or "").strip() or "<missing>"
            old_value = arguments.get("old_string")
            new_value = arguments.get("new_string")
            old_chars = len(old_value) if isinstance(old_value, str) else 0
            new_chars = len(new_value) if isinstance(new_value, str) else 0
            return (
                f"file_path={file_path}, old_string_chars={old_chars}, "
                f"new_string_chars={new_chars}"
            )

        if normalized_tool == "code_execution":
            code_value = arguments.get("code")
            code_chars = len(code_value) if isinstance(code_value, str) else 0
            timeout = arguments.get("timeout")
            timeout_text = f", timeout={timeout}s" if timeout is not None else ""
            workspace_paths: List[str] = []
            if isinstance(code_value, str):
                workspace_paths = list(dict.fromkeys(_WORKSPACE_PATH_PATTERN.findall(code_value)))

            if workspace_paths:
                shown_paths = workspace_paths[:2]
                more_count = len(workspace_paths) - len(shown_paths)
                shown_text = ", ".join(shown_paths)
                more_text = f", +{more_count} more" if more_count > 0 else ""
                return (
                    f"code_chars={code_chars}{timeout_text}, "
                    f"workspace_paths=[{shown_text}{more_text}]"
                )

            return f"code_chars={code_chars}{timeout_text}"

        if normalized_tool == "bash":
            command_value = arguments.get("command")
            if not isinstance(command_value, str):
                maybe_positional = arguments.get("__arg1")
                if isinstance(maybe_positional, str):
                    command_value = maybe_positional
            command_preview = self._truncate_stream_preview(command_value, max_chars=180)

            summary_parts = [f"command={command_preview or '<empty>'}"]
            if "pty" in arguments:
                summary_parts.append(f"pty={bool(arguments.get('pty'))}")
            if "background" in arguments:
                summary_parts.append(f"background={bool(arguments.get('background'))}")
            if arguments.get("workdir"):
                summary_parts.append(f"workdir={arguments.get('workdir')}")
            return ", ".join(summary_parts)

        if normalized_tool == "list_files":
            path = str(arguments.get("path") or "/workspace")
            recursive = bool(arguments.get("recursive", False))
            return f"path={path}, recursive={recursive}"

        keys = ", ".join(sorted(str(key) for key in arguments.keys())[:8])
        return f"keys=[{keys}]"

    @staticmethod
    def _decode_positional_tool_payload(payload: Any) -> Optional[Dict[str, Any]]:
        """Decode JSON-like positional tool payloads emitted under __arg1."""
        if isinstance(payload, dict):
            return dict(payload)
        if not isinstance(payload, str):
            return None

        stripped = payload.strip()
        if not stripped or stripped[0] not in "{[":
            return None

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None

        return dict(parsed) if isinstance(parsed, dict) else None

    def _normalize_tool_arguments_for_execution(
        self,
        tool_name: str,
        tool: Any,
        arguments: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Normalize fallback positional payloads into structured tool kwargs."""
        normalized_arguments = dict(arguments or {})
        positional_payload = normalized_arguments.pop("__arg1", None)
        normalized_tool_name = str(tool_name or "").strip().lower()

        if normalized_tool_name == "bash":
            current_command = normalized_arguments.get("command")
            if (
                (not isinstance(current_command, str) or not current_command.strip())
                and isinstance(positional_payload, str)
                and positional_payload.strip()
            ):
                normalized_arguments["command"] = positional_payload
            return normalized_arguments

        if positional_payload is None:
            return normalized_arguments

        if getattr(tool, "args_schema", None) is not None and not normalized_arguments:
            decoded_payload = self._decode_positional_tool_payload(positional_payload)
            if decoded_payload is not None:
                return decoded_payload

        normalized_arguments["__arg1"] = positional_payload
        return normalized_arguments

    def _summarize_tool_result_for_stream(self, tool_name: str, result: Any) -> str:
        """Build compact result summary for tool_result stream events."""
        normalized_tool = str(tool_name or "").strip().lower()

        if isinstance(result, dict):
            status = str(result.get("status") or "").strip()
            success = result.get("success")
            summary_parts: List[str] = []
            if status:
                summary_parts.append(f"status={status}")
            elif success is not None:
                summary_parts.append(f"success={bool(success)}")

            preview_source: Any = None
            for key in ("message", "error", "output", "stdout", "stderr", "result"):
                candidate = result.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    preview_source = candidate
                    break

            preview = self._truncate_stream_preview(preview_source, max_chars=200)
            if preview:
                summary_parts.append(f"preview={preview}")
                return ", ".join(summary_parts)

            keys = ", ".join(sorted(str(key) for key in result.keys())[:8])
            summary_parts.append(f"keys=[{keys}]")
            return ", ".join(summary_parts)

        if normalized_tool == "bash":
            preview = self._truncate_stream_preview(result, max_chars=220)
            return preview or "命令执行成功（无标准输出）"

        if normalized_tool in _FILE_WRITE_TOOL_NAMES:
            preview = self._truncate_stream_preview(result, max_chars=260)
            return preview or "(空结果)"

        preview = self._truncate_stream_preview(result, max_chars=220)
        return preview or "(空结果)"

    @staticmethod
    def _is_simple_langchain_tool_instance(tool: Any) -> bool:
        """Detect LangChain single-input Tool (no structured args schema)."""
        if tool is None:
            return False
        tool_type = type(tool)
        return (
            getattr(tool_type, "__name__", "") == "Tool"
            and str(getattr(tool_type, "__module__", "")).startswith("langchain_core.tools")
            and callable(getattr(tool, "func", None))
            and getattr(tool, "args_schema", None) is None
        )

    @staticmethod
    def _merge_stream_message(accumulated: Any, chunk: Any) -> Any:
        """Best-effort merge of streamed chunks into a final message object."""
        if accumulated is None:
            return chunk

        try:
            return accumulated + chunk
        except Exception:
            return accumulated

    def _extract_native_tool_calls(
        self,
        message: Any,
        available_tools: Optional[Dict[str, Any]] = None,
    ) -> List[ToolCall]:
        """Extract LangChain-native tool calls from AI message/chunk objects."""
        if message is None:
            return []

        raw_calls = getattr(message, "tool_calls", None)
        if not isinstance(raw_calls, (list, tuple)):
            return []
        normalized_calls: List[ToolCall] = []
        tool_registry = available_tools if available_tools is not None else self.tools_by_name

        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue

            tool_name = str(raw_call.get("name") or "").strip()
            if not tool_name:
                continue
            if tool_name not in tool_registry:
                continue

            args = raw_call.get("args")
            if args is None:
                args = raw_call.get("arguments")

            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            if not isinstance(args, dict):
                args = {}

            raw_json = json.dumps({"tool": tool_name, **args}, ensure_ascii=False)
            normalized_calls.append(
                ToolCall(tool_name=tool_name, arguments=args, raw_json=raw_json)
            )

        return normalized_calls

    def _handle_native_tool_http_rejection(self, error: Exception, runtime_path: str) -> bool:
        """Downgrade native tool-calling when upstream rejects tool payloads."""
        if not isinstance(error, httpx.HTTPStatusError):
            return False
        if not self.native_tool_calling_enabled or not self.tools:
            return False
        if error.response is None or error.response.status_code not in (400, 422):
            return False

        self.native_tool_calling_enabled = False
        self.llm_with_tools = self.llm
        logger.warning(
            "Native tool-calling rejected by upstream; downgraded to plain chat fallback",
            extra={
                "agent_id": str(self.config.agent_id),
                "runtime_path": runtime_path,
                "status_code": error.response.status_code,
            },
        )
        return True

    def _resolve_runtime_policy(
        self,
        execution_profile: Optional[ExecutionProfile | str],
        runtime_policy: Optional[RuntimePolicy],
        stream_callback: Optional[Callable[..., Any]],
    ) -> RuntimePolicy:
        """Resolve runtime policy with legacy-compatible fallback."""
        if runtime_policy is not None:
            return runtime_policy

        # Explicit profile always uses registry policy.
        if execution_profile is not None:
            profile = parse_execution_profile(execution_profile)
            return get_runtime_policy_registry().resolve(profile)

        # Backward-compatible fallback for old callers not passing profile.
        if stream_callback:
            if self.config.enable_error_recovery:
                loop_mode = LoopMode.RECOVERY_MULTI_TURN
            else:
                loop_mode = LoopMode.AUTO_MULTI_TURN
        else:
            loop_mode = LoopMode.SINGLE_TURN

        return RuntimePolicy(
            profile=ExecutionProfile.LEGACY,
            loop_mode=loop_mode,
            max_rounds=int(self.config.max_iterations or 20),
            enable_error_recovery=bool(self.config.enable_error_recovery),
            stream_output=bool(stream_callback),
            file_delivery_guard_mode=FileDeliveryGuardMode.SOFT,
        )

    @staticmethod
    def _emit_stream_chunk(
        stream_callback: Optional[Callable[..., Any]],
        content: str,
        content_type: str = "content",
    ) -> None:
        """Emit stream content when callback exists."""
        if stream_callback:
            stream_callback((content, content_type))

    @staticmethod
    def _iter_stream_segments(content: str, max_chars: int = 48) -> List[str]:
        """Split oversized chunks so coarse provider output still feels incremental."""
        text = str(content or "")
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]

        segments: List[str] = []
        remaining = text
        separators = ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", "；", "; ", "，", ", ", " ")

        while remaining:
            if len(remaining) <= max_chars:
                segments.append(remaining)
                break

            window = remaining[:max_chars]
            split_at = -1
            for separator in separators:
                candidate = window.rfind(separator)
                if candidate > split_at:
                    split_at = candidate + len(separator)

            if split_at <= max_chars // 3:
                split_at = max_chars

            segments.append(remaining[:split_at])
            remaining = remaining[split_at:]

        return [segment for segment in segments if segment]

    @classmethod
    def _emit_stream_content_incrementally(
        cls,
        stream_callback: Optional[Callable[..., Any]],
        content: str,
        content_type: str = "content",
        *,
        chunk_delay_seconds: float = 0.01,
    ) -> None:
        """Emit content in smaller pieces when upstream returns a coarse chunk."""
        if not stream_callback:
            return

        segments = cls._iter_stream_segments(content)
        if len(segments) <= 1:
            if segments:
                stream_callback((segments[0], content_type))
            return

        for index, segment in enumerate(segments):
            stream_callback((segment, content_type))
            if index < len(segments) - 1:
                time.sleep(chunk_delay_seconds)

    def _looks_like_agent_skill_task(self, task_description: str) -> bool:
        """Heuristic: whether this request likely expects agent-skill workflows."""
        if self.loaded_agent_skill_count <= 0:
            return False

        text = str(task_description or "").strip().lower()
        if not text:
            return False

        skill_hint_keywords = (
            "skill",
            "技能",
            "脚本",
            "script",
            "workflow",
            "read_skill",
            "skill.md",
        )
        if any(keyword in text for keyword in skill_hint_keywords):
            return True

        for name in self.agent_skill_names:
            normalized_name = str(name or "").strip().lower()
            if normalized_name and normalized_name in text:
                return True

        return False

    def _is_direct_tool_request(self, task_description: str) -> bool:
        """Heuristic: whether the request is a direct tool task."""
        text = str(task_description or "").strip()
        if not text:
            return False

        lowered = text.lower()
        for skill_name in self.langchain_tool_skill_names:
            normalized_name = str(skill_name or "").strip().lower()
            if normalized_name and normalized_name in lowered:
                return True

        # Explicit JSON tool invocation intent.
        if '"tool"' in lowered or "<tool_call>" in lowered or "<function_call>" in lowered:
            return True

        # Calculator-like pure expression.
        if re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s=\?]+", text):
            return True

        if lowered.startswith("计算") or lowered.startswith("calc"):
            return True

        return False

    def _should_use_native_tool_fast_path(self, task_description: str) -> bool:
        """Prefer single-turn native tool-calling for direct tool tasks."""
        if not self.native_tool_calling_enabled:
            return False
        if self.loaded_langchain_tool_skill_count <= 0:
            return False
        if self._looks_like_agent_skill_task(task_description):
            return False
        return self._is_direct_tool_request(task_description)

    @staticmethod
    def _resolve_task_intent_text(
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        task_intent_text: Optional[str] = None,
    ) -> str:
        """Resolve user-intent text used by policy heuristics.

        Some adapters append attachment/context blocks into task_description for model grounding.
        Heuristic policies (for example file-delivery guard) should evaluate raw user intent instead.
        """
        explicit_intent = str(task_intent_text or "").strip()
        if explicit_intent:
            return explicit_intent

        if isinstance(context, dict):
            context_intent = context.get("task_intent_text")
            if isinstance(context_intent, str) and context_intent.strip():
                return context_intent.strip()

        return str(task_description or "")

    def _iter_cancellation_targets(self) -> List[Any]:
        """Collect LLM instances that may support cooperative cancellation."""
        queue: List[Any] = [self.llm, getattr(self, "llm_with_tools", None)]
        seen: Set[int] = set()
        targets: List[Any] = []

        while queue:
            candidate = queue.pop()
            if candidate is None:
                continue
            candidate_id = id(candidate)
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            targets.append(candidate)

            candidate_dict = getattr(candidate, "__dict__", {})
            for attr_name in ("bound", "runnable", "model"):
                nested = None
                if isinstance(candidate_dict, dict) and attr_name in candidate_dict:
                    nested = candidate_dict.get(attr_name)
                elif hasattr(type(candidate), attr_name):
                    try:
                        nested = getattr(candidate, attr_name)
                    except Exception:
                        nested = None

                if nested is not None and nested is not candidate:
                    queue.append(nested)

        return targets

    def _propagate_cancellation_to_llm(self, *, reason: str = "", reset: bool = False) -> None:
        """Forward cancellation/reset signals to underlying LLM adapters."""
        for target in self._iter_cancellation_targets():
            if reset:
                reset_methods = ("reset_cancellation", "clear_cancellation")
                for method_name in reset_methods:
                    method = getattr(target, method_name, None)
                    if callable(method):
                        try:
                            method()
                        except Exception as reset_error:
                            logger.debug(
                                "Failed to reset LLM cancellation state (%s): %s",
                                method_name,
                                reset_error,
                            )
                        break
                continue

            cancel_methods = (
                "request_cancellation",
                "cancel_active_requests",
                "abort_active_requests",
            )
            for method_name in cancel_methods:
                method = getattr(target, method_name, None)
                if not callable(method):
                    continue
                try:
                    method(reason=reason)
                except TypeError:
                    method()
                except Exception as cancel_error:
                    logger.debug(
                        "Failed to propagate LLM cancellation (%s): %s",
                        method_name,
                        cancel_error,
                    )
                break

    def _reset_cancellation_state(self) -> None:
        """Reset cancellation marker at the beginning of an execution."""
        with self._cancel_lock:
            self._cancel_reason = ""
            self._cancel_requested.clear()
        self._propagate_cancellation_to_llm(reset=True)

    def request_cancellation(self, reason: Optional[str] = None) -> None:
        """Request cooperative cancellation for the current execution."""
        cancel_reason = str(reason or "cancelled by caller").strip() or "cancelled by caller"
        with self._cancel_lock:
            self._cancel_reason = cancel_reason
            self._cancel_requested.set()

        self._propagate_cancellation_to_llm(reason=cancel_reason, reset=False)
        logger.warning(
            "Cancellation requested for agent execution",
            extra={"agent_id": str(self.config.agent_id), "reason": cancel_reason},
        )

    def _is_cancellation_requested(self) -> bool:
        return self._cancel_requested.is_set()

    def _raise_if_cancelled(self) -> None:
        if not self._is_cancellation_requested():
            return
        reason = self._cancel_reason or "cancelled by caller"
        raise AgentExecutionCancelled(reason)

    @staticmethod
    def _looks_like_cancellation_error(error: BaseException) -> bool:
        if isinstance(error, AgentExecutionCancelled):
            return True

        name = error.__class__.__name__.lower()
        message = str(error).lower()
        if "cancel" in name or "abort" in name:
            return True

        tokens = (
            "cancel",
            "aborted",
            "client disconnected",
            "stream cancelled",
            "stream canceled",
        )
        return any(token in message for token in tokens)

    def execute_task(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        execution_profile: Optional[ExecutionProfile | str] = None,
        runtime_policy: Optional[RuntimePolicy] = None,
        stream_callback: Optional[callable] = None,
        session_workdir: Optional["Path"] = None,
        container_id: Optional[str] = None,
        code_execution_network_access: Optional[bool] = None,
        message_content: Optional[Any] = None,
        task_intent_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a task using the agent.

        Args:
            task_description: Description of the task to execute
            context: Optional context information (e.g., memories)
            conversation_history: Optional prior user/assistant turns to prepend
                before the current user prompt.
            execution_profile: Optional runtime profile controlling strategy selection.
            runtime_policy: Optional explicit runtime policy override.
            stream_callback: Optional callback for streaming tokens (callable(str))
            session_workdir: Optional pre-existing workdir from a conversation session.
                If provided, reuses the session workdir so files and state persist
                across conversation rounds.
            container_id: Optional Docker container ID for sandbox execution.
                If provided, code blocks will be executed inside the container.
            code_execution_network_access: Optional network toggle for code_execution tool.
            message_content: Optional multimodal content (list of dicts) for vision models.
                When provided, used as HumanMessage content instead of plain text.
            task_intent_text: Optional raw user-intent text for policy heuristics. When omitted,
                task_description is used.

        Returns:
            Dict with execution results
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        if self.status != AgentStatus.ACTIVE:
            if self.status == AgentStatus.ERROR and self.agent is not None:
                logger.warning(
                    "Agent in error state; auto-resetting to ACTIVE for retry",
                    extra={"agent_id": str(self.config.agent_id)},
                )
                self.status = AgentStatus.ACTIVE
            else:
                raise RuntimeError(f"Agent not active. Current status: {self.status.value}")

        try:
            self._reset_cancellation_state()
            self.status = AgentStatus.BUSY
            logger.info(f"Agent executing task: {self.config.name}")
            resolved_task_intent_text = self._resolve_task_intent_text(
                task_description=task_description,
                context=context,
                task_intent_text=task_intent_text,
            )
            if not isinstance(context, dict):
                context = {}
            else:
                context = dict(context)

            # Propagate session/runtime settings to code_execution tool.
            session_sandbox_id = str(container_id).strip() if container_id else None
            for tool in self.tools:
                if getattr(tool, "name", "") not in {"code_execution", "bash"}:
                    continue
                try:
                    if hasattr(tool, "set_execution_context"):
                        tool.set_execution_context(session_sandbox_id)
                except Exception as cfg_error:
                    logger.warning(
                        "Failed to set code_execution session context: %s",
                        cfg_error,
                        extra={"agent_id": str(self.config.agent_id)},
                    )

                if code_execution_network_access is not None:
                    try:
                        if hasattr(tool, "set_network_access"):
                            tool.set_network_access(bool(code_execution_network_access))
                    except Exception as cfg_error:
                        logger.warning(
                            "Failed to set code_execution network policy: %s",
                            cfg_error,
                            extra={"agent_id": str(self.config.agent_id)},
                        )

            # Set workspace root for file tools; clear stale root when not provided.
            from agent_framework.tools.file_tools import clear_workspace_root, set_workspace_root

            if session_workdir:
                set_workspace_root(session_workdir)
                logger.debug(f"Set workspace root to {session_workdir}")
            else:
                clear_workspace_root()

            runtime_capabilities = self._resolve_runtime_capabilities(
                context,
                session_workdir=session_workdir,
                container_id=session_sandbox_id,
                code_execution_network_access=code_execution_network_access,
            )
            context["runtime_capabilities"] = runtime_capabilities
            response_delivery_mode = self._resolve_response_delivery_mode(context)
            response_delivery_channel = self._resolve_response_delivery_channel(context)

            resolved_policy = self._resolve_runtime_policy(
                execution_profile=execution_profile,
                runtime_policy=runtime_policy,
                stream_callback=stream_callback,
            )
            loop_mode = resolved_policy.loop_mode
            pre_fast_path_loop_mode = loop_mode
            used_native_tool_fast_path = False

            # Respect policy intent but stay safe when agent-level recovery is disabled.
            if loop_mode == LoopMode.RECOVERY_MULTI_TURN and (
                not self.config.enable_error_recovery
                or not bool(resolved_policy.enable_error_recovery)
            ):
                loop_mode = LoopMode.AUTO_MULTI_TURN

            if (
                loop_mode in (LoopMode.RECOVERY_MULTI_TURN, LoopMode.AUTO_MULTI_TURN)
                and resolved_policy.profile == ExecutionProfile.DEBUG_CHAT
                and self._should_use_native_tool_fast_path(resolved_task_intent_text)
            ):
                loop_mode = LoopMode.SINGLE_TURN
                used_native_tool_fast_path = True
                logger.info(
                    "Switching to native tool-calling fast path",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "runtime_path": "native_tool_fast_path",
                        "langchain_tool_skills": self.loaded_langchain_tool_skill_count,
                        "agent_skills": self.loaded_agent_skill_count,
                    },
                )

            execution_context_tag = ""
            if isinstance(context, dict):
                execution_context_tag = str(
                    context.get("execution_context_tag")
                    or context.get("runtime_context_tag")
                    or context.get("runtime_execution_context")
                    or ""
                ).strip()

            logger.info(
                "Resolved agent runtime policy",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "runtime_path": "base_agent_execute",
                    "runtime_profile": resolved_policy.profile.value,
                    "runtime_loop_mode": loop_mode.value,
                    "runtime_stream_output": resolved_policy.stream_output,
                    "runtime_has_stream_callback": bool(stream_callback),
                    "runtime_execution_context_tag": execution_context_tag or "unspecified",
                    "runtime_has_execution_context_tag": bool(execution_context_tag),
                },
            )

            if loop_mode == LoopMode.RECOVERY_MULTI_TURN:
                import asyncio

                # Run async method in sync context
                # Always create a new event loop for this thread to avoid conflicts
                # with the main thread's FastAPI event loop
                try:
                    # Try to get the running loop - if it exists and is running,
                    # we're being called from an async context (shouldn't happen normally)
                    loop = asyncio.get_running_loop()
                    # If we get here, there's a running loop - this is unusual
                    logger.warning(
                        "Event loop already running in current thread, using legacy implementation"
                    )
                except RuntimeError:
                    # No running loop - this is the expected case when called from a thread
                    # Create a new event loop for this thread
                    result = asyncio.run(
                        self.execute_task_with_recovery(
                            task_description=task_description,
                            context=context,
                            conversation_history=conversation_history,
                            execution_profile=resolved_policy.profile,
                            runtime_policy=resolved_policy,
                            stream_callback=stream_callback,
                            session_workdir=session_workdir,
                            container_id=container_id,
                            code_execution_network_access=code_execution_network_access,
                            message_content=message_content,
                            task_intent_text=resolved_task_intent_text,
                        )
                    )
                    self.status = AgentStatus.ACTIVE
                    return result

            # Legacy implementation (original code)
            # Prepare input messages
            user_message = task_description

            # Add context information if provided
            if context:
                context_info = []
                if context.get("skills"):
                    context_info.append(
                        "Relevant learned skills (non-binding, verify against current task): "
                        + ", ".join(context["skills"][:3])
                    )
                if context.get("user_memory"):
                    context_info.append(
                        "User memory facts (non-binding): " + ", ".join(context["user_memory"][:3])
                    )
                if context.get("knowledge_refs"):
                    context_info.append(
                        f"Knowledge references: {', '.join(context['knowledge_refs'][:3])}"
                    )

                if context_info:
                    user_message = f"{task_description}\n\nContext:\n" + "\n".join(context_info)
                    # Also inject context into multimodal content if present
                    if message_content is not None and isinstance(message_content, list):
                        context_text = "\n\nContext:\n" + "\n".join(context_info)
                        for item in message_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                item["text"] += context_text
                                break

            # Multi-round mode (policy-driven, callback optional for transport).
            if loop_mode == LoopMode.AUTO_MULTI_TURN:
                file_delivery_guard_mode = self._resolve_file_delivery_guard_mode(resolved_policy)
                file_delivery_required = (
                    file_delivery_guard_mode != FileDeliveryGuardMode.OFF
                    and self._requires_file_delivery(resolved_task_intent_text)
                )
                requested_file_formats = (
                    self._extract_requested_file_formats(resolved_task_intent_text)
                    if file_delivery_required
                    else set()
                )
                runtime_tools_by_name = self._build_runtime_tool_registry()
                runtime_tools = list(runtime_tools_by_name.values())
                runtime_llm_with_tools = self._build_runtime_llm(runtime_tools_by_name)

                human_content = message_content if message_content is not None else user_message
                messages = self._build_messages_with_history(
                    human_content=human_content,
                    conversation_history=conversation_history,
                    available_tools=runtime_tools,
                    runtime_capabilities=runtime_capabilities,
                    response_delivery_mode=response_delivery_mode,
                    response_delivery_channel=response_delivery_channel,
                )

                # Multi-round conversation loop for tool execution
                tool_calls_made = []
                max_iterations = max(1, int(resolved_policy.max_rounds or 20))
                iteration = 0
                final_output = ""
                conversation_completed = False

                logger.info(
                    f"[TOOL-LOOP] Starting multi-round conversation (max {max_iterations} iterations)",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "has_tools": len(runtime_tools_by_name) > 0,
                    },
                )

                while iteration < max_iterations:
                    self._raise_if_cancelled()
                    iteration += 1

                    logger.info(
                        f"[TOOL-LOOP] Round {iteration}/{max_iterations}",
                        extra={"agent_id": str(self.config.agent_id)},
                    )

                    # Stream LLM response for this round
                    round_output = ""
                    round_thinking = ""
                    round_finish_reason = ""
                    chunk_count = 0
                    streamed_content_chars = 0
                    stream_failed = False
                    used_non_stream_fallback = False
                    native_tool_calls: List[ToolCall] = []
                    merged_stream_message: Any = None
                    llm_for_round = runtime_llm_with_tools if runtime_tools_by_name else self.llm

                    try:
                        for chunk in llm_for_round.stream(messages):
                            self._raise_if_cancelled()
                            merged_stream_message = self._merge_stream_message(
                                merged_stream_message, chunk
                            )
                            if not round_finish_reason:
                                round_finish_reason = self._extract_finish_reason(chunk)
                            if hasattr(chunk, "content") and chunk.content:
                                # Check for content_type in additional_kwargs
                                content_type = "content"  # default
                                if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
                                    content_type = chunk.additional_kwargs.get(
                                        "content_type", "content"
                                    )

                                # Send to frontend immediately for real-time streaming
                                self._emit_stream_chunk(
                                    stream_callback=stream_callback,
                                    content=chunk.content,
                                    content_type=content_type,
                                )

                                # Also accumulate for tool detection
                                if content_type == "thinking":
                                    round_thinking += chunk.content
                                else:
                                    round_output += chunk.content
                                    streamed_content_chars += len(chunk.content)
                                chunk_count += 1

                        native_tool_calls = self._extract_native_tool_calls(
                            merged_stream_message,
                            available_tools=runtime_tools_by_name,
                        )
                        if not round_finish_reason:
                            round_finish_reason = self._extract_finish_reason(merged_stream_message)

                        # If no chunks were received, mark streaming as failed
                        if chunk_count == 0 and not native_tool_calls:
                            stream_failed = True
                            logger.warning("LLM streaming returned no chunks")

                    except Exception as stream_error:
                        if self._is_cancellation_requested() or self._looks_like_cancellation_error(
                            stream_error
                        ):
                            raise AgentExecutionCancelled(
                                self._cancel_reason or "cancelled during LLM streaming"
                            ) from stream_error
                        if self._handle_native_tool_http_rejection(
                            stream_error, runtime_path="auto_multi_stream_http_fallback"
                        ):
                            runtime_llm_with_tools = self.llm
                            llm_for_round = self.llm
                        stream_failed = True
                        logger.warning(f"Streaming failed: {stream_error}")

                    # If streaming failed, fall back to non-streaming
                    if stream_failed:
                        self._raise_if_cancelled()
                        logger.info("Falling back to non-streaming mode")
                        try:
                            result = llm_for_round.invoke(messages)
                        except Exception as invoke_error:
                            if (
                                self._is_cancellation_requested()
                                or self._looks_like_cancellation_error(invoke_error)
                            ):
                                raise AgentExecutionCancelled(
                                    self._cancel_reason or "cancelled during LLM invoke"
                                ) from invoke_error
                            if self._handle_native_tool_http_rejection(
                                invoke_error, runtime_path="auto_multi_invoke_http_fallback"
                            ):
                                runtime_llm_with_tools = self.llm
                                llm_for_round = self.llm
                                result = llm_for_round.invoke(messages)
                            else:
                                logger.error(f"Non-streaming fallback also failed: {invoke_error}")
                                raise

                        if hasattr(result, "content"):
                            content_value = result.content
                            round_output = (
                                content_value
                                if isinstance(content_value, str)
                                else str(content_value)
                            )
                        else:
                            round_output = str(result)
                        used_non_stream_fallback = True
                        native_tool_calls = self._extract_native_tool_calls(
                            result,
                            available_tools=runtime_tools_by_name,
                        )
                        if not round_finish_reason:
                            round_finish_reason = self._extract_finish_reason(result)

                        if not round_output:
                            if native_tool_calls:
                                round_output = ""
                            else:
                                raise ValueError("LLM returned empty content")

                    if (
                        used_non_stream_fallback
                        and stream_callback
                        and round_output
                        and streamed_content_chars == 0
                    ):
                        self._emit_stream_chunk(
                            stream_callback=stream_callback,
                            content=round_output,
                            content_type="content",
                        )

                    logger.info(
                        f"[TOOL-LOOP] Round {iteration} LLM output: "
                        f"thinking={len(round_thinking)} chars, "
                        f"content={len(round_output)} chars, "
                        f"finish_reason={round_finish_reason or 'unknown'}",
                        extra={"agent_id": str(self.config.agent_id)},
                    )

                    # Check if output contains tool calls
                    import json
                    import re

                    parsed_calls, parsed_errors = self._parse_tool_calls(
                        round_output,
                        available_tools=runtime_tools_by_name,
                    )
                    if not parsed_calls and native_tool_calls:
                        parsed_calls = native_tool_calls
                        parsed_errors = []
                    tool_json_blocks = []
                    for tc in parsed_calls:
                        tool_json_blocks.append(tc.raw_json)

                    if tool_json_blocks:
                        # This round contains tool calls
                        logger.info(
                            f"[TOOL-LOOP] Found {len(parsed_calls)} tool calls in round {iteration}",
                            extra={"agent_id": str(self.config.agent_id)},
                        )

                        # Note: thinking and content already sent during streaming above
                        # Now just execute tools and send tool execution info

                        # Execute tools
                        tool_results = []
                        for tc in parsed_calls:
                            self._raise_if_cancelled()
                            tool_name = tc.tool_name
                            tool = runtime_tools_by_name.get(tool_name)

                            if tool:
                                tool_args = self._normalize_tool_arguments_for_execution(
                                    tool_name,
                                    tool,
                                    tc.arguments,
                                )
                                args_summary = self._summarize_tool_arguments_for_stream(
                                    tool_name, tool_args
                                )
                                # Send "calling tool" message BEFORE execution
                                self._emit_stream_chunk(
                                    stream_callback=stream_callback,
                                    content=(
                                        f"\n\n🔧 **调用工具: {tool_name}**\n"
                                        f"参数摘要: {args_summary}\n"
                                    ),
                                    content_type="tool_call",
                                )

                                logger.info(
                                    f"Executing tool: {tool_name}",
                                    extra={
                                        "agent_id": str(self.config.agent_id),
                                        "tool_name": tool_name,
                                        "tool_args_summary": args_summary,
                                        "tool_args_chars": len(str(tool_args or "")),
                                    },
                                )

                                # Execute tool
                                try:
                                    result = tool.invoke(tool_args)
                                    runtime_error = self._extract_tool_runtime_error(result)
                                    if runtime_error:
                                        raise RuntimeError(runtime_error)

                                    tool_calls_made.append(
                                        {
                                            "tool_name": tool_name,
                                            "name": tool_name,
                                            "args": tool_args,
                                            "result": str(result),
                                            "status": "success",
                                            "round_number": iteration,
                                        }
                                    )
                                    tool_results.append(
                                        {
                                            "tool": tool_name,
                                            "args": tool_args,
                                            "result": str(result),
                                        }
                                    )

                                    # Send tool execution result to frontend
                                    result_summary = self._summarize_tool_result_for_stream(
                                        tool_name, result
                                    )
                                    self._emit_stream_chunk(
                                        stream_callback=stream_callback,
                                        content=f"✅ **执行结果**: {result_summary}\n",
                                        content_type="tool_result",
                                    )

                                    logger.info(
                                        f"Tool executed successfully: {tool_name} = {result}",
                                        extra={"agent_id": str(self.config.agent_id)},
                                    )
                                except Exception as tool_error:
                                    logger.error(
                                        f"Tool execution failed: {tool_error}", exc_info=True
                                    )
                                    self._emit_stream_chunk(
                                        stream_callback=stream_callback,
                                        content=f"❌ **执行失败**: {str(tool_error)}\n",
                                        content_type="tool_error",
                                    )
                                    tool_results.append(
                                        {
                                            "tool": tool_name,
                                            "args": tool_args,
                                            "error": str(tool_error),
                                        }
                                    )
                                    tool_calls_made.append(
                                        {
                                            "tool_name": tool_name,
                                            "name": tool_name,
                                            "args": tool_args,
                                            "error": str(tool_error),
                                            "status": "execution_error",
                                            "round_number": iteration,
                                        }
                                    )
                            else:
                                logger.warning(f"Tool not found: {tool_name}")
                                self._emit_stream_chunk(
                                    stream_callback=stream_callback,
                                    content=f"⚠️ 工具未找到: {tool_name}\n",
                                    content_type="tool_error",
                                )

                        # If tools were executed, continue to next round with tool results
                        if tool_results:
                            logger.info(
                                f"[TOOL-LOOP] Executed {len(tool_results)} tools, continuing to round {iteration + 1}",
                                extra={"agent_id": str(self.config.agent_id)},
                            )

                            # Send separator before continuation
                            self._emit_stream_chunk(
                                stream_callback=stream_callback,
                                content=f"\n\n---\n\n💭 **根据工具结果生成最终回答...**\n\n",
                                content_type="info",
                            )

                            # Build a message with tool results
                            tool_results_text = "\n\n工具执行结果：\n"
                            for tr in tool_results:
                                if "error" in tr:
                                    tool_results_text += f"- {tr['tool']}: 错误 - {tr['error']}\n"
                                else:
                                    tool_results_text += f"- {tr['tool']}: {tr['result']}\n"

                            # Check if we just read skill documentation - if so, encourage using it
                            if any(tr.get("tool") == "read_skill" for tr in tool_results):
                                tool_results_text += (
                                    "\n你已经获得了技能文档。若要执行技能中的脚本/命令，请优先使用 bash 工具。"
                                    "code_execution 用于运行 Python/JavaScript/TypeScript 代码；"
                                    "shell 命令请使用 bash 工具。不要在 code_execution 中用 subprocess 或 "
                                    "child_process 调外部脚本。"
                                    "如果信息已足够，可以直接回答用户。"
                                )
                            else:
                                tool_results_text += "\n请根据以上工具执行结果，给出最终回答。如果还需要更多信息或执行其他操作，可以继续调用工具。"

                            # Add to conversation history
                            messages.append(AIMessage(content=round_output))
                            messages.append(HumanMessage(content=tool_results_text))

                            # Continue to next round
                            continue
                        else:
                            # No tools executed, but tool calls were found - shouldn't happen
                            logger.warning(f"[TOOL-LOOP] Tool calls found but none executed")
                            break
                    else:
                        # No tool calls in this round - use deterministic state machine.
                        if iteration >= max_iterations:
                            logger.info(
                                "[TOOL-LOOP] Max round reached; accepting current output as final",
                                extra={"agent_id": str(self.config.agent_id), "round": iteration},
                            )
                            messages.append(AIMessage(content=round_output))
                            final_output = round_output
                            conversation_completed = True
                            break

                        completion_decision = self._assess_autonomous_completion(
                            task_intent_text=resolved_task_intent_text,
                            latest_output=round_output,
                            tool_call_records=tool_calls_made,
                            round_number=iteration,
                            max_rounds=max_iterations,
                            file_delivery_required=file_delivery_required,
                            file_delivery_guard_mode=file_delivery_guard_mode,
                            requested_file_formats=requested_file_formats,
                            response_delivery_mode=response_delivery_mode,
                            finish_reason=round_finish_reason,
                        )
                        should_stop = bool(completion_decision.get("should_stop"))

                        if iteration < max_iterations and not should_stop:
                            logger.info(
                                "[TOOL-LOOP] State-machine check: incomplete, continue iterating",
                                extra={
                                    "agent_id": str(self.config.agent_id),
                                    "round": iteration,
                                    "confidence": completion_decision.get("confidence", 0.0),
                                    "reason": completion_decision.get("reason", ""),
                                    "finish_reason": round_finish_reason or "unknown",
                                },
                            )
                            self._emit_stream_chunk(
                                stream_callback=stream_callback,
                                content="任务尚未确认完成，继续自主执行下一步。",
                                content_type="info",
                            )
                            messages.append(AIMessage(content=round_output))
                            continue_feedback = str(
                                completion_decision.get("feedback_prompt") or ""
                            ).strip() or self._build_autonomy_continue_feedback(completion_decision)
                            messages.append(HumanMessage(content=continue_feedback))
                            continue

                        logger.info(
                            "[TOOL-LOOP] State-machine check: task complete, stopping loop",
                            extra={
                                "agent_id": str(self.config.agent_id),
                                "round": iteration,
                                "confidence": completion_decision.get("confidence", 0.0),
                                "finish_reason": round_finish_reason or "unknown",
                            },
                        )
                        advisory_message = str(
                            completion_decision.get("advisory_message") or ""
                        ).strip()
                        if advisory_message:
                            logger.warning(
                                "[TOOL-LOOP] File-delivery soft advisory",
                                extra={
                                    "agent_id": str(self.config.agent_id),
                                    "round": iteration,
                                    "file_delivery_guard_mode": file_delivery_guard_mode.value,
                                    "advisory_message": advisory_message,
                                },
                            )
                            self._emit_stream_chunk(
                                stream_callback=stream_callback,
                                content=f"\n\n⚠️ {advisory_message}\n",
                                content_type="warning",
                            )
                        messages.append(AIMessage(content=round_output))
                        final_output = round_output
                        conversation_completed = True
                        break

                if not conversation_completed and iteration >= max_iterations:
                    logger.warning(
                        "[TOOL-LOOP] Max rounds reached before autonomous completion",
                        extra={
                            "agent_id": str(self.config.agent_id),
                            "rounds": iteration,
                            "max_rounds": max_iterations,
                        },
                    )
                    self._emit_stream_chunk(
                        stream_callback=stream_callback,
                        content=f"\n\n⚠️ 已达到最大对话轮数 ({max_iterations})，任务未确认完成。\n",
                        content_type="warning",
                    )
                    final_output = final_output or "Max rounds reached before completion"

                logger.info(
                    f"[TOOL-LOOP] Conversation completed after {iteration} rounds",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_calls_count": len(tool_calls_made),
                    },
                )

                self.status = AgentStatus.ACTIVE
                logger.info(
                    f"Task completed: {self.config.name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_calls_count": len(tool_calls_made),
                        "rounds": iteration,
                    },
                )

                return {
                    "success": conversation_completed,
                    "output": final_output or "Conversation completed",
                    "messages": messages,
                    "tool_calls": tool_calls_made,
                }
            else:
                # Non-streaming mode - invoke normally
                messages = self._build_messages_with_history(
                    human_content=user_message,
                    conversation_history=conversation_history,
                    runtime_capabilities=runtime_capabilities,
                    response_delivery_mode=response_delivery_mode,
                    response_delivery_channel=response_delivery_channel,
                )
                invoke_payload = {"messages": messages}
                invoke_config = None
                if self.native_tool_calling_enabled and self.tools:
                    # Cap LangGraph tool-call recursion so single-turn runs cannot loop indefinitely.
                    invoke_config = {"recursion_limit": 12}

                try:
                    self._raise_if_cancelled()
                    if invoke_config is not None:
                        result = self.agent.invoke(invoke_payload, config=invoke_config)
                    else:
                        result = self.agent.invoke(invoke_payload)
                except httpx.HTTPStatusError as http_error:
                    if not self._handle_native_tool_http_rejection(
                        http_error, runtime_path="single_turn_native_tool_http_fallback"
                    ):
                        raise
                    if used_native_tool_fast_path and pre_fast_path_loop_mode in (
                        LoopMode.RECOVERY_MULTI_TURN,
                        LoopMode.AUTO_MULTI_TURN,
                    ):
                        logger.info(
                            "Native tool fast path downgraded; rerouting to multi-turn parser loop",
                            extra={
                                "agent_id": str(self.config.agent_id),
                                "runtime_path": "single_turn_native_tool_http_fallback_reroute",
                                "fallback_loop_mode": pre_fast_path_loop_mode.value,
                            },
                        )
                        fallback_policy = RuntimePolicy(
                            profile=resolved_policy.profile,
                            loop_mode=pre_fast_path_loop_mode,
                            max_rounds=resolved_policy.max_rounds,
                            enable_error_recovery=resolved_policy.enable_error_recovery,
                            max_retries=resolved_policy.max_retries,
                            timeout_seconds=resolved_policy.timeout_seconds,
                            include_context=resolved_policy.include_context,
                            include_memory=resolved_policy.include_memory,
                            stream_output=resolved_policy.stream_output,
                            file_delivery_guard_mode=resolved_policy.file_delivery_guard_mode,
                        )
                        self.status = AgentStatus.ACTIVE
                        return self.execute_task(
                            task_description=task_description,
                            context=context,
                            conversation_history=conversation_history,
                            runtime_policy=fallback_policy,
                            stream_callback=stream_callback,
                            session_workdir=session_workdir,
                            container_id=container_id,
                            code_execution_network_access=code_execution_network_access,
                            message_content=message_content,
                            task_intent_text=resolved_task_intent_text,
                        )
                    self._raise_if_cancelled()
                    result = self.agent.invoke(invoke_payload)
                except GraphRecursionError as recursion_error:
                    logger.warning(
                        "Single-turn graph recursion limit reached, fallback to plain LLM invoke",
                        extra={
                            "agent_id": str(self.config.agent_id),
                            "runtime_path": "single_turn_graph_fallback",
                            "reason": str(recursion_error),
                        },
                    )
                    self._raise_if_cancelled()
                    fallback_response = self.llm.invoke(messages)
                    result = {"messages": [fallback_response]}

                # Extract output from result
                messages = result.get("messages", [])
                final_output = ""

                if messages:
                    # Get the last AI message
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage):
                            final_output = msg.content
                            break

                    if not final_output and messages:
                        # Fallback to last message
                        final_output = (
                            str(messages[-1].content)
                            if hasattr(messages[-1], "content")
                            else str(messages[-1])
                        )

                # Parse and execute tool calls if LLM doesn't support function calling
                if self.tools and not self.native_tool_calling_enabled:
                    final_output = self._parse_and_execute_tools_sync(final_output)

                # Single-turn path does not stream chunks by default; emit final output once.
                if stream_callback and final_output:
                    self._emit_stream_chunk(
                        stream_callback=stream_callback,
                        content=final_output,
                        content_type="content",
                    )

                self.status = AgentStatus.ACTIVE
                logger.info(f"Task completed: {self.config.name}")

                return {
                    "success": True,
                    "output": final_output,
                    "messages": messages,
                }

        except AgentExecutionCancelled as cancel_error:
            self.status = AgentStatus.ACTIVE
            logger.info(
                "Task execution cancelled",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "reason": str(cancel_error),
                },
            )
            return {
                "success": False,
                "error": str(cancel_error),
                "output": None,
                "cancelled": True,
            }
        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"Task execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }
        except BaseException as e:
            # asyncio.CancelledError inherits BaseException (not Exception) in Python 3.12.
            # Without this guard, a cancelled run can leak BUSY status and block later runs.
            if self._looks_like_cancellation_error(e):
                self.status = AgentStatus.ACTIVE
                logger.info(
                    "Task execution interrupted by cancellation",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "reason": str(e),
                    },
                )
                return {
                    "success": False,
                    "error": str(e),
                    "output": None,
                    "cancelled": True,
                }

            self.status = AgentStatus.ERROR
            logger.error(f"Task execution interrupted: {e}", exc_info=True)
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }

    def terminate(self) -> None:
        """Terminate the agent."""
        logger.info(f"Terminating agent: {self.config.name}")
        self.request_cancellation("agent terminated")
        self.status = AgentStatus.TERMINATED
        self.agent = None

    def get_status(self) -> AgentStatus:
        """Get current agent status.

        Returns:
            Current AgentStatus
        """
        return self.status

    def get_capabilities(self) -> List[str]:
        """Get agent capabilities.

        Returns:
            List of skill names
        """
        return self.config.capabilities

    def add_tool(self, tool) -> None:
        """Add a tool to the agent.

        Args:
            tool: LangChain tool to add
        """
        self.tools.append(tool)
        logger.info(f"Tool added to agent: {tool.name}")

        # Re-initialize if agent is already initialized
        if self.agent:
            logger.info("Re-initializing agent with new tool")
            self.initialize()

    def _extract_balanced_json_objects(self, text: str) -> List[Tuple[str, int, int]]:
        """Extract balanced JSON object substrings with spans from arbitrary text.

        This scanner is quote-aware, so braces inside JSON strings do not break extraction.
        """
        objects: List[Tuple[str, int, int]] = []
        if not text:
            return objects

        depth = 0
        start_idx: Optional[int] = None
        in_string = False
        escape_next = False

        for idx, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue

            if in_string:
                if char == "\\":
                    escape_next = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue

            if char == "{":
                if depth == 0:
                    start_idx = idx
                depth += 1
                continue

            if char == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start_idx is not None:
                    objects.append((text[start_idx : idx + 1], start_idx, idx + 1))
                    start_idx = None

        return objects

    def _parse_tool_calls(
        self,
        llm_output: str,
        available_tools: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ToolCall], List[ParseError]]:
        """Parse tool calls from LLM output, collecting all errors.

        Args:
            llm_output: Raw output from LLM

        Returns:
            Tuple of (tool_calls, parse_errors)
        """
        tool_calls: List[ToolCall] = []
        parse_errors: List[ParseError] = []
        preprocessed = llm_output or ""
        tool_registry = available_tools if available_tools is not None else self.tools_by_name

        candidates: List[Tuple[str, bool]] = []  # (json_str, explicit_tool_intent)
        seen_candidates: Set[str] = set()

        def _add_candidate(raw_json: str, explicit: bool) -> None:
            candidate = (raw_json or "").strip()
            if not candidate:
                return
            if '"tool"' not in candidate:
                return
            if candidate in seen_candidates:
                return
            seen_candidates.add(candidate)
            candidates.append((candidate, explicit))

        # Qwen / ChatGLM style: <tool_call>{"name":"x","arguments":{...}}</tool_call>
        qwen_tool_pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
        for qwen_json in re.findall(qwen_tool_pattern, preprocessed, re.DOTALL):
            try:
                data = json.loads(qwen_json)
                if not isinstance(data, dict):
                    continue
                tool_name = data.get("name")
                args = data.get("arguments", {})
                if isinstance(tool_name, str) and isinstance(args, dict):
                    normalized = json.dumps({"tool": tool_name, **args}, ensure_ascii=False)
                    _add_candidate(normalized, explicit=True)
            except json.JSONDecodeError as err:
                parse_errors.append(
                    ParseError(
                        error_type="json_decode_error",
                        message=f"Failed to parse tool_call JSON: {str(err)}",
                        malformed_input=qwen_json,
                        details={"line": err.lineno, "column": err.colno, "pos": err.pos},
                    )
                )

        # GLM boxed format: first block usually tool name, following blocks key:value args.
        glm_blocks = re.findall(
            r"<tool_call>\s*(.*?)\s*(?:<\|end_of_box\|>|</tool_call>)",
            preprocessed,
            re.DOTALL,
        )
        if glm_blocks:
            tool_name: Optional[str] = None
            args: Dict[str, Any] = {}
            for block in glm_blocks:
                value = block.strip()
                if ":" in value:
                    key, _, val = value.partition(":")
                    if key.strip():
                        args[key.strip()] = val.strip()
                elif not tool_name:
                    tool_name = value
            if tool_name:
                normalized = json.dumps({"tool": tool_name, **args}, ensure_ascii=False)
                _add_candidate(normalized, explicit=True)

        # XML-style function call payloads.
        fc_pattern = r"<function_call>\s*(\{.*?\})\s*</function_call>"
        for fc_json in re.findall(fc_pattern, preprocessed, re.DOTALL):
            try:
                data = json.loads(fc_json)
                if not isinstance(data, dict):
                    continue
                tool_name = data.get("name")
                args = data.get("arguments", data)
                if isinstance(tool_name, str):
                    normalized_args = args if isinstance(args, dict) else {}
                    normalized = json.dumps(
                        {"tool": tool_name, **normalized_args},
                        ensure_ascii=False,
                    )
                    _add_candidate(normalized, explicit=True)
            except json.JSONDecodeError as err:
                parse_errors.append(
                    ParseError(
                        error_type="json_decode_error",
                        message=f"Failed to parse function_call JSON: {str(err)}",
                        malformed_input=fc_json,
                        details={"line": err.lineno, "column": err.colno, "pos": err.pos},
                    )
                )

        # JSON code fences are strong tool-call signals.
        fenced_pattern = r"```(?:json)?\s*(.*?)\s*```"
        for fenced_payload in re.findall(fenced_pattern, preprocessed, re.DOTALL | re.IGNORECASE):
            for obj_text, _, _ in self._extract_balanced_json_objects(fenced_payload):
                _add_candidate(obj_text, explicit=True)

        stripped_output = preprocessed.strip()
        if (
            stripped_output.startswith("{")
            and stripped_output.endswith("}")
            and '"tool"' in stripped_output
        ):
            _add_candidate(stripped_output, explicit=True)

        # Fallback scan: collect balanced objects containing "tool". Mark as explicit only
        # when nearby context indicates the model is trying to call tools.
        for obj_text, start, end in self._extract_balanced_json_objects(preprocessed):
            if '"tool"' not in obj_text:
                continue
            context = preprocessed[max(0, start - 64) : min(len(preprocessed), end + 64)].lower()
            explicit_intent = any(
                marker in context
                for marker in ("tool_call", "function_call", "调用工具", "use tool", "call tool")
            )
            _add_candidate(obj_text, explicit=explicit_intent)

        for json_str, explicit in candidates:
            try:
                tool_data = json.loads(json_str)
            except json.JSONDecodeError as err:
                if explicit:
                    parse_errors.append(
                        ParseError(
                            error_type="json_decode_error",
                            message=f"Failed to parse JSON: {str(err)}",
                            malformed_input=json_str,
                            details={"line": err.lineno, "column": err.colno, "pos": err.pos},
                        )
                    )
                continue

            if not isinstance(tool_data, dict):
                if explicit:
                    parse_errors.append(
                        ParseError(
                            error_type="invalid_type",
                            message="Tool call payload must be a JSON object",
                            malformed_input=json_str,
                        )
                    )
                continue

            if "tool" not in tool_data:
                if explicit:
                    parse_errors.append(
                        ParseError(
                            error_type="missing_field",
                            message="Missing required field 'tool'",
                            malformed_input=json_str,
                        )
                    )
                continue

            tool_name = tool_data["tool"]
            if not isinstance(tool_name, str):
                if explicit:
                    parse_errors.append(
                        ParseError(
                            error_type="invalid_type",
                            message="Field 'tool' must be a string",
                            malformed_input=json_str,
                        )
                    )
                continue

            if tool_name not in tool_registry:
                if explicit:
                    available_tools_text = ", ".join(tool_registry.keys())
                    parse_errors.append(
                        ParseError(
                            error_type="unknown_tool",
                            message=(
                                f"Tool '{tool_name}' not found. "
                                f"Available tools: {available_tools_text}"
                            ),
                            malformed_input=json_str,
                        )
                    )
                continue

            args = {k: v for k, v in tool_data.items() if k != "tool"}
            tool_calls.append(ToolCall(tool_name=tool_name, arguments=args, raw_json=json_str))

        # If at least one valid tool call is available, execute it and ignore malformed extras.
        if tool_calls:
            parse_errors = []

        return tool_calls, parse_errors

    def _handle_parse_errors(
        self,
        parse_errors: List[ParseError],
        state: ConversationState,
        available_tool_names: Optional[List[str]] = None,
    ) -> Optional[ErrorFeedback]:
        """Generate feedback for parse errors.

        Args:
            parse_errors: List of parse errors
            state: Current conversation state

        Returns:
            ErrorFeedback if recoverable, None if max retries exceeded
        """
        if not parse_errors:
            return None

        # Get the first error (focus on one at a time)
        error = parse_errors[0]

        # Check retry count
        retry_key = f"parse_error_{error.error_type}"
        retry_count = state.retry_counts.get(retry_key, 0)

        if retry_count >= self.config.max_parse_retries:
            logger.error(
                f"[RECOVERY] Max parse retries exceeded for {error.error_type}",
                extra={"agent_id": str(self.config.agent_id), "error_type": error.error_type},
            )
            return None

        # Increment retry count
        state.retry_counts[retry_key] = retry_count + 1

        # Record error
        state.errors.append(
            ErrorRecord(
                round_number=state.round_number,
                error_type=error.error_type,
                error_message=error.message,
                malformed_input=error.malformed_input,
                is_recoverable=True,
                retry_count=retry_count + 1,
            )
        )

        logger.warning(
            f"[RECOVERY] Parse error detected: {error.error_type}",
            extra={
                "agent_id": str(self.config.agent_id),
                "error_type": error.error_type,
                "retry_count": retry_count + 1,
                "max_retries": self.config.max_parse_retries,
            },
        )

        # Generate feedback based on error type
        if error.error_type == "json_decode_error":
            return ErrorFeedback(
                error_type="JSON Format Error",
                error_message=error.message,
                malformed_input=error.malformed_input,
                expected_format='{"tool": "tool_name", "arg1": "value1"}',
                retry_count=retry_count + 1,
                max_retries=self.config.max_parse_retries,
                suggestions=[
                    "Check for unterminated strings (missing closing quotes)",
                    "Ensure all quotes are properly escaped",
                    "Verify JSON structure is valid",
                    "Use double quotes for strings, not single quotes",
                    "Check for missing commas between fields",
                ],
            )

        elif error.error_type == "missing_field":
            return ErrorFeedback(
                error_type="Missing Required Field",
                error_message=error.message,
                malformed_input=error.malformed_input,
                expected_format='{"tool": "tool_name", "arg1": "value1"}',
                retry_count=retry_count + 1,
                max_retries=self.config.max_parse_retries,
                suggestions=[
                    "Every tool call must have a 'tool' field",
                    "The 'tool' field specifies which tool to use",
                    'Example: {"tool": "calculator", "expression": "1+1"}',
                ],
            )

        elif error.error_type == "unknown_tool":
            tool_names = available_tool_names or list(self.tools_by_name.keys())
            available_tools = ", ".join(tool_names)
            return ErrorFeedback(
                error_type="Unknown Tool",
                error_message=error.message,
                malformed_input=error.malformed_input,
                expected_format=f"Available tools: {available_tools}",
                retry_count=retry_count + 1,
                max_retries=self.config.max_parse_retries,
                suggestions=[
                    f"Use one of these tools: {available_tools}",
                    "Check the tool name spelling",
                    "Refer to the Available Tools section in the system prompt",
                ],
            )

        else:
            return ErrorFeedback(
                error_type="Tool Call Error",
                error_message=error.message,
                malformed_input=error.malformed_input,
                expected_format='{"tool": "tool_name", "arg1": "value1"}',
                retry_count=retry_count + 1,
                max_retries=self.config.max_parse_retries,
                suggestions=["Review the tool call format and try again"],
            )

    def _sync_skill_package_files_to_workdir(
        self, workdir: "Path", log_prefix: str = "[SKILL_SYNC]"
    ) -> int:
        """Copy loaded Agent Skill package files into the active workspace."""
        if not self.skill_manager:
            return 0

        copied_files = 0
        try:
            agent_skills = self.skill_manager.get_agent_skill_docs()
            for skill_ref in agent_skills:
                copied_for_skill = 0
                skill_doc_path_for_log: Optional[str] = None
                skill_slug = str(
                    getattr(skill_ref, "skill_slug", None)
                    or getattr(skill_ref, "slug", None)
                    or getattr(skill_ref, "name", None)
                    or getattr(skill_ref, "display_name", None)
                    or "skill"
                ).strip()
                skill_dir_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", skill_slug).strip("._")
                if not skill_dir_name:
                    skill_dir_name = "skill"
                skill_workspace_root = workdir / ".skills" / skill_dir_name
                package_files = getattr(skill_ref, "package_files", None) or {}

                def _sanitize_relative_path(raw_path: str) -> Optional[Path]:
                    parts = []
                    for part in Path(str(raw_path or "").replace("\\", "/")).parts:
                        if part in {"", ".", ".."}:
                            continue
                        parts.append(part)
                    if not parts:
                        return None
                    return Path(*parts)

                def _infer_package_root_dir(files: Dict[str, str]) -> Optional[str]:
                    normalized_paths: List[Path] = []
                    for rel_path in files:
                        safe_path = _sanitize_relative_path(rel_path)
                        if safe_path is not None:
                            normalized_paths.append(safe_path)

                    if not normalized_paths:
                        return None

                    for path_obj in normalized_paths:
                        if path_obj.name == "SKILL.md" and len(path_obj.parts) > 1:
                            return path_obj.parts[0]

                    top_level_dirs = {p.parts[0] for p in normalized_paths if len(p.parts) > 1}
                    has_root_files = any(len(p.parts) == 1 for p in normalized_paths)
                    if len(top_level_dirs) == 1 and not has_root_files:
                        only_dir = next(iter(top_level_dirs))
                        if only_dir.lower() not in {"scripts", "src", "lib", "docs"}:
                            return only_dir
                    return None

                package_root_dir = _infer_package_root_dir(package_files)

                def _normalize_package_path(raw_path: str) -> Optional[Path]:
                    safe_path = _sanitize_relative_path(raw_path)
                    if safe_path is None:
                        return None
                    if (
                        package_root_dir
                        and safe_path.parts
                        and safe_path.parts[0] == package_root_dir
                    ):
                        stripped_parts = safe_path.parts[1:]
                        if stripped_parts:
                            return Path(*stripped_parts)
                    return safe_path

                if package_files:
                    for filename, content in package_files.items():
                        safe_relative_path = _normalize_package_path(filename)
                        if safe_relative_path is None:
                            continue
                        file_path = skill_workspace_root / safe_relative_path
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(content, encoding="utf-8")
                        if filename.endswith((".sh", ".py")):
                            file_path.chmod(0o755)
                        copied_files += 1
                        copied_for_skill += 1

                has_skill_doc_in_package = bool(
                    package_files and any(Path(path).name == "SKILL.md" for path in package_files)
                )

                # Backward-compatible fallback for old packages where SKILL.md
                # was not included in loaded package files.
                skill_md_content = getattr(skill_ref, "skill_md_content", None)
                if skill_md_content and not has_skill_doc_in_package:
                    skill_doc_path = skill_workspace_root / "SKILL.md"
                    skill_doc_path.parent.mkdir(parents=True, exist_ok=True)
                    skill_doc_path.write_text(skill_md_content, encoding="utf-8")
                    skill_doc_path_for_log = str(skill_doc_path.relative_to(workdir)).replace(
                        "\\", "/"
                    )
                    copied_files += 1
                    copied_for_skill += 1

                if not copied_for_skill:
                    continue

                logger.info(
                    f"{log_prefix} Copied {copied_for_skill} skill files to workdir",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "skill_slug": skill_slug,
                        "workdir": str(workdir),
                        "workspace_skill_root": str((Path(".skills") / skill_dir_name).as_posix()),
                        "copied_package_files": len(package_files),
                        "skill_doc_path": skill_doc_path_for_log,
                    },
                )
        except Exception as e:
            logger.warning(f"{log_prefix} Failed to copy skill files: {e}")

        return copied_files

    async def _execute_code_blocks(
        self,
        code_blocks: List,
        state: "ConversationState",
        stream_callback: Optional[callable] = None,
        session_workdir: Optional["Path"] = None,
        container_id: Optional[str] = None,
    ) -> List:
        """Execute code blocks extracted from LLM output.

        This is the preferred execution path when LLM outputs code blocks
        (```python or ```bash) instead of JSON tool calls.

        Args:
            code_blocks: List of CodeBlock objects to execute
            state: Current conversation state
            stream_callback: Optional callback for streaming updates
            session_workdir: Optional pre-existing workdir from a conversation session.
                If provided, reuses the session workdir so files and state persist
                across conversation rounds.
            container_id: Optional Docker container ID for sandbox execution.
                If provided, code will be executed inside the container.

        Returns:
            List of ExecutionResult objects
        """
        from pathlib import Path
        from uuid import uuid4

        from agent_framework.code_block_executor import ExecutionResult

        results = []

        # Get user's skill environment variables
        skill_env = {}
        try:
            from skill_library.skill_env_manager import get_skill_env_manager

            env_manager = get_skill_env_manager()
            skill_env = env_manager.get_env_for_user(self.config.owner_user_id)
            logger.debug(
                f"[CODE_BLOCK] Loaded {len(skill_env)} skill environment variables",
                extra={"agent_id": str(self.config.agent_id)},
            )
        except Exception as e:
            logger.warning(f"[CODE_BLOCK] Failed to load skill env vars: {e}")

        # Use session workdir if available, otherwise create a new one
        if session_workdir is not None:
            workdir = session_workdir
            logger.info(
                f"[CODE_BLOCK] Reusing session workdir: {workdir}",
                extra={"agent_id": str(self.config.agent_id)},
            )
        else:
            session_id = uuid4().hex[:8]
            workdir = self.code_executor.create_workdir(session_id)

        for i, block in enumerate(code_blocks):
            # Send execution indicator to frontend
            if stream_callback:
                stream_callback(
                    (
                        f"\n\n🔧 **执行代码块 {i+1}/{len(code_blocks)}**: {block.language}\n文件: {block.filename}\n",
                        "code_execution",
                    )
                )

            logger.info(
                f"[CODE_BLOCK] Executing block {i+1}/{len(code_blocks)}: {block.language}",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "language": block.language,
                    "script_name": block.filename,
                    "code_length": len(block.code),
                },
            )

            # Execute the code block with skill environment variables and shared workdir
            result = await self.code_executor.execute(
                block,
                timeout=self.config.tool_timeout_seconds,
                env=skill_env,
                workdir=workdir,  # Use shared workdir with skill files
                container_id=container_id,  # Docker sandbox (None = subprocess)
            )
            results.append(result)

            # Send result to frontend
            if stream_callback:
                if result.success:
                    output_preview = (
                        result.output[:500] if len(result.output) > 500 else result.output
                    )
                    stream_callback(
                        (
                            f"✅ **执行成功** ({result.execution_time:.2f}s)\n```\n{output_preview}\n```\n",
                            "code_result",
                        )
                    )
                else:
                    error_preview = (result.error or result.output)[:500]
                    stream_callback(
                        (
                            f"❌ **执行失败** (exit code {result.exit_code})\n```\n{error_preview}\n```\n",
                            "code_error",
                        )
                    )

            logger.info(
                f"[CODE_BLOCK] Block {i+1} {'succeeded' if result.success else 'failed'}",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "execution_time": result.execution_time,
                },
            )

            # Stop on first error (can be made configurable)
            if not result.success:
                break

        return results

    async def _execute_tools_with_recovery(
        self,
        tool_calls: List[ToolCall],
        state: ConversationState,
        stream_callback: Optional[callable] = None,
        tool_registry: Optional[Dict[str, Any]] = None,
    ) -> List[ToolResult]:
        """Execute tools with error handling and recovery.

        Args:
            tool_calls: List of tool calls to execute
            state: Current conversation state
            stream_callback: Optional callback for streaming updates

        Returns:
            List of tool results
        """
        import asyncio

        results = []
        runtime_tool_registry = tool_registry if tool_registry is not None else self.tools_by_name
        tool_timeout_cap = max(1, int(self.config.tool_timeout_seconds))

        for tool_call in tool_calls:
            tool_name = tool_call.tool_name
            tool = runtime_tool_registry.get(tool_name)
            tool_arguments = tool_call.arguments

            # Check retry count for this specific tool
            retry_key = f"tool_{tool_name}"
            retry_count = state.retry_counts.get(retry_key, 0)

            if tool is None:
                available_tools = ", ".join(runtime_tool_registry.keys())
                error_msg = (
                    f"Tool '{tool_name}' is unavailable in current policy context. "
                    f"Available tools: {available_tools}"
                )
                results.append(
                    ToolResult(
                        tool_name=tool_name,
                        status="error",
                        error=error_msg,
                        error_type="unknown_tool",
                        retry_count=retry_count,
                    )
                )
                state.retry_counts[retry_key] = retry_count + 1
                state.tool_calls_made.append(
                    ToolCallRecord(
                        round_number=state.round_number,
                        tool_name=tool_name,
                        arguments=tool_call.arguments,
                        status="execution_error",
                        error=error_msg,
                        retry_number=retry_count,
                    )
                )
                logger.warning(
                    "[RECOVERY] Tool unavailable under runtime policy",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                    },
                )
                continue

            try:
                # Keep bash command-level timeout aligned with recovery timeout.
                # Otherwise, asyncio.wait_for can time out while the underlying sync tool
                # thread keeps running (e.g. long-lived servers), which blocks asyncio.run
                # teardown and leaves stream completion pending.
                tool_arguments = self._normalize_tool_arguments_for_execution(
                    tool_name,
                    tool,
                    dict(tool_call.arguments or {}),
                )
                if tool_name == "bash":
                    requested_timeout = tool_arguments.get("timeout")
                    try:
                        normalized_timeout = (
                            int(requested_timeout)
                            if requested_timeout is not None
                            else tool_timeout_cap
                        )
                    except (TypeError, ValueError):
                        normalized_timeout = tool_timeout_cap
                    if normalized_timeout <= 0 or normalized_timeout > tool_timeout_cap:
                        normalized_timeout = tool_timeout_cap
                    tool_arguments["timeout"] = normalized_timeout

                args_summary = self._summarize_tool_arguments_for_stream(tool_name, tool_arguments)
                # Send "calling tool" message
                if stream_callback:
                    retry_indicator = f" (重试 {retry_count})" if retry_count > 0 else ""
                    stream_callback(
                        (
                            f"\n\n🔧 **调用工具: {tool_name}{retry_indicator}**\n"
                            f"参数摘要: {args_summary}\n",
                            "tool_call",
                        )
                    )

                logger.info(
                    f"[RECOVERY] Executing tool: {tool_name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                        "tool_args_summary": args_summary,
                        "tool_args_chars": len(str(tool_arguments or "")),
                        "retry_count": retry_count,
                    },
                )

                # Execute tool with timeout
                if tool_name == "bash" and self._is_simple_langchain_tool_instance(tool):
                    # Single-input Tool cannot accept extra keys via ainvoke();
                    # call func directly so timeout/pty/workdir/background kwargs remain valid.
                    timeout_window_seconds = float(tool_timeout_cap) + 1.0
                    result = await asyncio.wait_for(
                        asyncio.to_thread(tool.func, **tool_arguments),
                        timeout=timeout_window_seconds,
                    )
                else:
                    result = await asyncio.wait_for(
                        tool.ainvoke(tool_arguments), timeout=self.config.tool_timeout_seconds
                    )

                runtime_error = self._extract_tool_runtime_error(result)
                if runtime_error:
                    raise RuntimeError(runtime_error)

                # Success
                results.append(
                    ToolResult(
                        tool_name=tool_name,
                        status="success",
                        result=result,
                        retry_count=retry_count,
                    )
                )

                # Reset retry count on success
                state.retry_counts[retry_key] = 0

                # Send success message
                if stream_callback:
                    result_summary = self._summarize_tool_result_for_stream(tool_name, result)
                    stream_callback((f"✅ **执行结果**: {result_summary}\n", "tool_result"))

                # Record success
                state.tool_calls_made.append(
                    ToolCallRecord(
                        round_number=state.round_number,
                        tool_name=tool_name,
                        arguments=tool_arguments,
                        status="success",
                        result=result,
                        retry_number=retry_count,
                    )
                )

                logger.info(
                    f"[RECOVERY] Tool executed successfully: {tool_name}",
                    extra={"agent_id": str(self.config.agent_id), "tool_name": tool_name},
                )

            except asyncio.TimeoutError:
                # Timeout error
                error_msg = (
                    f"Tool execution timed out after {self.config.tool_timeout_seconds} seconds"
                )

                results.append(
                    ToolResult(
                        tool_name=tool_name,
                        status="error",
                        error=error_msg,
                        error_type="timeout",
                        retry_count=retry_count,
                    )
                )

                # Increment retry count
                state.retry_counts[retry_key] = retry_count + 1

                # Send error message
                if stream_callback:
                    stream_callback((f"⏱️ **超时错误**: {error_msg}\n", "tool_error"))

                # Record error
                state.tool_calls_made.append(
                    ToolCallRecord(
                        round_number=state.round_number,
                        tool_name=tool_name,
                        arguments=tool_arguments,
                        status="timeout",
                        error=error_msg,
                        retry_number=retry_count,
                    )
                )

                logger.warning(
                    f"[RECOVERY] Tool execution timeout: {tool_name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                        "timeout": self.config.tool_timeout_seconds,
                    },
                )

            except Exception as e:
                # Execution error
                error_msg = str(e)

                results.append(
                    ToolResult(
                        tool_name=tool_name,
                        status="error",
                        error=error_msg,
                        error_type="execution_error",
                        retry_count=retry_count,
                    )
                )

                # Increment retry count
                state.retry_counts[retry_key] = retry_count + 1

                # Send error message
                if stream_callback:
                    stream_callback((f"❌ **执行失败**: {error_msg}\n", "tool_error"))

                # Record error
                state.tool_calls_made.append(
                    ToolCallRecord(
                        round_number=state.round_number,
                        tool_name=tool_name,
                        arguments=tool_arguments,
                        status="execution_error",
                        error=error_msg,
                        retry_number=retry_count,
                    )
                )

                logger.error(
                    f"[RECOVERY] Tool execution failed: {tool_name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                        "error": error_msg,
                    },
                    exc_info=True,
                )

        return results

    def _estimate_text_tokens(self, text: str) -> int:
        """Estimate token count from text length (mixed CN/EN heuristic)."""
        if not text:
            return 0
        return max(1, int(len(text) * 0.5))

    def _estimate_messages_tokens(self, messages: List[Any]) -> int:
        """Estimate token count for a message list."""
        total = 0
        for msg in messages:
            content = getattr(msg, "content", msg)

            if isinstance(content, str):
                total += self._estimate_text_tokens(content)
                continue

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        total += self._estimate_text_tokens(item)
                    elif isinstance(item, dict):
                        if item.get("type") == "text":
                            total += self._estimate_text_tokens(str(item.get("text", "")))
                        elif isinstance(item.get("content"), str):
                            total += self._estimate_text_tokens(item["content"])
                continue

            if content is not None:
                total += self._estimate_text_tokens(str(content))

        return total

    def _truncate_text_for_context(self, text: str, max_chars: int) -> str:
        """Truncate long text while keeping head and tail context."""
        if len(text) <= max_chars:
            return text

        if max_chars < 80:
            return text[:max_chars]

        marker = "\n...[内容已压缩]...\n"
        keep = max_chars - len(marker)
        head = int(keep * 0.75)
        tail = keep - head
        return text[:head] + marker + text[-tail:]

    def _clone_message_with_content(self, msg: Any, content: Any) -> Any:
        """Clone known message types with replaced content."""
        if isinstance(msg, SystemMessage):
            return SystemMessage(content=content)
        if isinstance(msg, HumanMessage):
            return HumanMessage(content=content)
        if isinstance(msg, AIMessage):
            return AIMessage(content=content)
        return msg

    def _compress_messages_if_needed(
        self, messages: List[Any]
    ) -> Tuple[List[Any], Optional[Dict[str, int]]]:
        """Compress history when estimated prompt tokens approach context limit."""
        context_window = int(self.config.context_window_tokens or 8192)
        threshold_tokens = int(
            context_window * float(self.config.context_compression_threshold or 0.8)
        )

        estimated_before = self._estimate_messages_tokens(messages)
        if estimated_before <= threshold_tokens:
            return messages, None

        compressed_messages = list(messages)
        truncated_messages = 0
        removed_messages = 0

        protected_tail = max(2, int(self.config.history_tail_protected_messages or 6))
        history_truncate_chars = int(self.config.history_compress_chars or 600)

        mutable_end = max(1, len(compressed_messages) - protected_tail)

        # Step 1: truncate old long messages (keep recent tail unchanged).
        for idx in range(1, mutable_end):
            msg = compressed_messages[idx]
            content = getattr(msg, "content", None)
            if isinstance(content, str) and len(content) > history_truncate_chars:
                compressed_content = self._truncate_text_for_context(
                    content, history_truncate_chars
                )
                compressed_messages[idx] = self._clone_message_with_content(msg, compressed_content)
                truncated_messages += 1

        estimated_after_truncate = self._estimate_messages_tokens(compressed_messages)

        # Step 2: if still above threshold, prune oldest messages while preserving newest tail.
        if estimated_after_truncate > threshold_tokens and len(compressed_messages) > 2:
            system_messages = compressed_messages[:1]
            tail_start = max(1, len(compressed_messages) - protected_tail)
            head_messages = compressed_messages[1:tail_start]
            tail_messages = compressed_messages[tail_start:]

            compact_messages = list(system_messages) + list(tail_messages)
            compact_tokens = self._estimate_messages_tokens(compact_messages)
            kept_head_reversed: List[Any] = []

            for msg in reversed(head_messages):
                msg_tokens = self._estimate_messages_tokens([msg])
                if compact_tokens + msg_tokens <= threshold_tokens:
                    kept_head_reversed.append(msg)
                    compact_tokens += msg_tokens
                else:
                    removed_messages += 1

            kept_head = list(reversed(kept_head_reversed))
            compressed_messages = list(system_messages) + kept_head + list(tail_messages)

        estimated_after = self._estimate_messages_tokens(compressed_messages)

        if (
            truncated_messages == 0
            and removed_messages == 0
            and estimated_after >= estimated_before
        ):
            return messages, None

        meta = {
            "context_window": context_window,
            "threshold_tokens": threshold_tokens,
            "estimated_before": estimated_before,
            "estimated_after": estimated_after,
            "truncated_messages": truncated_messages,
            "removed_messages": removed_messages,
        }
        return compressed_messages, meta

    def _format_tool_results(self, tool_results: List[ToolResult]) -> str:
        """Format tool results for LLM feedback.

        Args:
            tool_results: List of tool results

        Returns:
            Formatted string for LLM
        """
        if not tool_results:
            return ""

        per_item_limit = int(self.config.tool_result_item_max_chars or 1200)
        total_limit = int(self.config.tool_result_total_max_chars or 3200)

        result_lines = ["\n\n工具执行结果：\n"]
        used_chars = 0
        truncated_items = 0
        omitted_items = 0

        for idx, tr in enumerate(tool_results):
            raw_value = tr.result if tr.status == "success" else f"错误 - {tr.error}"
            value_text = str(raw_value)
            if len(value_text) > per_item_limit:
                value_text = self._truncate_text_for_context(value_text, per_item_limit)
                truncated_items += 1

            line = f"- {tr.tool_name}: {value_text}\n"
            if used_chars + len(line) > total_limit:
                omitted_items = len(tool_results) - idx
                result_lines.append(f"- 其余 {omitted_items} 条工具结果省略（超出上下文预算）\n")
                break

            result_lines.append(line)
            used_chars += len(line)

        if truncated_items > 0:
            result_lines.append(f"\n注：已压缩 {truncated_items} 条过长工具结果。\n")
        if omitted_items > 0:
            result_lines.append("注：部分工具结果已省略，优先保留最新信息。\n")

        result_text = "".join(result_lines)

        # Check if we just read skill documentation
        if any(tr.tool_name == "read_skill" and tr.status == "success" for tr in tool_results):
            result_text += (
                "\n你已经获得了技能文档。若要执行技能中的脚本/命令，请优先使用 bash 工具。"
                "code_execution 用于运行 Python/JavaScript/TypeScript 代码；"
                "shell 命令请使用 bash 工具。不要在 code_execution 中用 subprocess 或 "
                "child_process 调外部脚本。"
                "如果信息已足够，可以直接回答用户。"
            )
        else:
            result_text += "\n请根据以上工具执行结果，给出最终回答。如果还需要更多信息或执行其他操作，可以继续调用工具。"

        return result_text

    async def execute_task_with_recovery(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        execution_profile: Optional[ExecutionProfile | str] = None,
        runtime_policy: Optional[RuntimePolicy] = None,
        stream_callback: Optional[callable] = None,
        session_workdir: Optional["Path"] = None,
        container_id: Optional[str] = None,
        code_execution_network_access: Optional[bool] = None,
        message_content: Optional[Any] = None,
        task_intent_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute task with error recovery (new implementation).

        Args:
            task_description: Description of the task to execute
            context: Optional context information (e.g., memories)
            conversation_history: Optional prior user/assistant turns to prepend
                before the current user prompt.
            execution_profile: Optional runtime profile for telemetry.
            runtime_policy: Optional resolved runtime policy for telemetry.
            stream_callback: Optional callback for streaming tokens
            session_workdir: Optional pre-existing workdir from a conversation session.
                If provided, reuses the session workdir so files and state persist
                across conversation rounds.
            container_id: Optional Docker container ID for sandbox execution.
                If provided, code blocks will be executed inside the container.
            code_execution_network_access: Optional network toggle for code_execution tool.
            message_content: Optional multimodal content (list of dicts) for vision models.
                When provided, used as HumanMessage content instead of plain text.
            task_intent_text: Optional raw user-intent text for policy heuristics. When omitted,
                task_description is used.

        Returns:
            Dict with execution results including conversation state
        """
        import asyncio

        # Initialize conversation state (single source: runtime policy max_rounds)
        resolved_max_rounds = int((runtime_policy.max_rounds if runtime_policy else None) or 20)
        state = ConversationState(max_rounds=max(1, resolved_max_rounds))
        resolved_task_intent_text = self._resolve_task_intent_text(
            task_description=task_description,
            context=context,
            task_intent_text=task_intent_text,
        )
        file_delivery_guard_mode = self._resolve_file_delivery_guard_mode(runtime_policy)
        file_delivery_required = (
            file_delivery_guard_mode != FileDeliveryGuardMode.OFF
            and self._requires_file_delivery(resolved_task_intent_text)
        )
        requested_file_formats = (
            self._extract_requested_file_formats(resolved_task_intent_text)
            if file_delivery_required
            else set()
        )
        runtime_tools_by_name = self._build_runtime_tool_registry()
        runtime_tools = list(runtime_tools_by_name.values())
        runtime_llm_with_tools = self._build_runtime_llm(runtime_tools_by_name)
        runtime_capabilities = self._resolve_runtime_capabilities(
            context,
            session_workdir=session_workdir,
            container_id=container_id,
            code_execution_network_access=code_execution_network_access,
        )
        if not isinstance(context, dict):
            context = {}
        else:
            context = dict(context)
        context["runtime_capabilities"] = runtime_capabilities
        extra_system_messages = [
            str(message).strip()
            for message in (context.get("ephemeral_system_messages") or [])
            if str(message or "").strip()
        ]
        response_delivery_mode = self._resolve_response_delivery_mode(context)
        response_delivery_channel = self._resolve_response_delivery_channel(context)

        # Prepare system prompt and initial messages
        user_message = task_description

        # Add context information if provided
        if context:
            context_info = []
            if context.get("skills"):
                context_info.append(
                    "Relevant learned skills (non-binding, verify against current task): "
                    + ", ".join(context["skills"][:3])
                )
            if context.get("user_memory"):
                context_info.append(
                    "User memory facts (non-binding): " + ", ".join(context["user_memory"][:3])
                )
            if context.get("knowledge_refs"):
                context_info.append(
                    f"Knowledge references: {', '.join(context['knowledge_refs'][:3])}"
                )

            if context_info:
                user_message = f"{task_description}\n\nContext:\n" + "\n".join(context_info)
                # Also inject context into multimodal content if present
                if message_content is not None and isinstance(message_content, list):
                    context_text = "\n\nContext:\n" + "\n".join(context_info)
                    for item in message_content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            item["text"] += context_text
                            break

        # Use multimodal content (with images) if provided, otherwise plain text
        human_content = message_content if message_content is not None else user_message
        messages = self._build_messages_with_history(
            human_content=human_content,
            conversation_history=conversation_history,
            extra_system_messages=extra_system_messages,
            available_tools=runtime_tools,
            runtime_capabilities=runtime_capabilities,
            response_delivery_mode=response_delivery_mode,
            response_delivery_channel=response_delivery_channel,
        )

        logger.info(
            f"[RECOVERY] Starting conversation with error recovery",
            extra={
                "agent_id": str(self.config.agent_id),
                "max_rounds": state.max_rounds,
                "runtime_profile": parse_execution_profile(execution_profile).value,
                "runtime_loop_mode": (
                    runtime_policy.loop_mode.value
                    if runtime_policy
                    else LoopMode.RECOVERY_MULTI_TURN.value
                ),
                "file_delivery_guard_mode": file_delivery_guard_mode.value,
            },
        )

        self._raise_if_cancelled()

        # Main conversation loop
        while (
            state.round_number < state.max_rounds
            and not state.is_terminated
            and not self._is_cancellation_requested()
        ):
            self._raise_if_cancelled()
            state.round_number += 1

            # Track per-round timing
            round_start_time = time.time()
            round_first_token_time = None
            round_last_token_time = None
            round_output_chars = 0

            logger.info(
                f"[RECOVERY] Round {state.round_number}/{state.max_rounds}",
                extra={"agent_id": str(self.config.agent_id)},
            )

            # Send round indicator to frontend (only for rounds > 1)
            if state.round_number > 1 and stream_callback:
                stream_callback((f"\n\n💭 **第 {state.round_number} 轮对话**\n", "info"))

            # Force compression when context reaches configured threshold (default 80%).
            compressed_messages, compression_meta = self._compress_messages_if_needed(messages)
            if compression_meta:
                messages = compressed_messages
                logger.warning(
                    "[RECOVERY] Context pressure detected, compressed conversation history",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "context_window": compression_meta["context_window"],
                        "threshold_tokens": compression_meta["threshold_tokens"],
                        "estimated_before": compression_meta["estimated_before"],
                        "estimated_after": compression_meta["estimated_after"],
                        "truncated_messages": compression_meta["truncated_messages"],
                        "removed_messages": compression_meta["removed_messages"],
                    },
                )
                if stream_callback:
                    stream_callback(
                        (
                            (
                                "\n\n🗜️ 上下文已接近上限，已自动压缩历史与工具结果。"
                                f" 估算 {compression_meta['estimated_before']} -> {compression_meta['estimated_after']} tokens"
                                f"（阈值 {compression_meta['threshold_tokens']} / 窗口 {compression_meta['context_window']}）\n"
                            ),
                            "info",
                        )
                    )

            # 1. Get LLM response
            round_output = ""
            round_thinking = ""
            round_finish_reason = ""
            round_usage = None  # Track usage from LLM response
            streamed_content_chars = 0
            used_non_stream_fallback = False
            native_tool_calls: List[ToolCall] = []
            merged_stream_message: Any = None
            llm_for_round = runtime_llm_with_tools if runtime_tools_by_name else self.llm

            try:
                for chunk in llm_for_round.stream(messages):
                    self._raise_if_cancelled()
                    merged_stream_message = self._merge_stream_message(merged_stream_message, chunk)
                    if not round_finish_reason:
                        round_finish_reason = self._extract_finish_reason(chunk)
                    # Check for usage info in the chunk
                    # LangChain's stream() returns AIMessageChunk objects
                    # The final chunk contains response_metadata with usage info
                    if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                        meta = chunk.response_metadata
                        if "usage" in meta:
                            round_usage = meta["usage"]
                            logger.info(
                                f"[RECOVERY] Got usage from response_metadata: {round_usage}"
                            )
                        elif "token_usage" in meta:
                            round_usage = meta["token_usage"]
                            logger.info(f"[RECOVERY] Got usage from token_usage: {round_usage}")
                    if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                        um = chunk.usage_metadata
                        round_usage = {
                            "prompt_tokens": getattr(um, "input_tokens", 0),
                            "completion_tokens": getattr(um, "output_tokens", 0),
                        }
                        logger.info(f"[RECOVERY] Got usage from usage_metadata: {round_usage}")

                    if hasattr(chunk, "content") and chunk.content:
                        content_type = "content"
                        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
                            content_type = chunk.additional_kwargs.get("content_type", "content")

                        # Track round timing for content tokens only
                        if content_type in ("content", "thinking"):
                            if round_first_token_time is None:
                                round_first_token_time = time.time()
                            round_last_token_time = time.time()
                            round_output_chars += len(chunk.content)

                        if stream_callback:
                            self._emit_stream_content_incrementally(
                                stream_callback,
                                chunk.content,
                                content_type,
                            )

                        if content_type == "thinking":
                            round_thinking += chunk.content
                        else:
                            round_output += chunk.content
                            streamed_content_chars += len(chunk.content)
                native_tool_calls = self._extract_native_tool_calls(
                    merged_stream_message,
                    available_tools=runtime_tools_by_name,
                )
                if not round_finish_reason:
                    round_finish_reason = self._extract_finish_reason(merged_stream_message)
            except Exception as e:
                if self._is_cancellation_requested() or self._looks_like_cancellation_error(e):
                    raise AgentExecutionCancelled(
                        self._cancel_reason or "cancelled during recovery streaming"
                    ) from e
                if self._handle_native_tool_http_rejection(
                    e, runtime_path="recovery_stream_http_fallback"
                ):
                    runtime_llm_with_tools = self.llm
                    llm_for_round = self.llm
                logger.error(f"[RECOVERY] LLM streaming failed: {e}", exc_info=True)
                # Try non-streaming fallback
                try:
                    self._raise_if_cancelled()
                    result = llm_for_round.invoke(messages)
                except Exception as fallback_error:
                    if self._is_cancellation_requested() or self._looks_like_cancellation_error(
                        fallback_error
                    ):
                        raise AgentExecutionCancelled(
                            self._cancel_reason or "cancelled during recovery invoke"
                        ) from fallback_error
                    if self._handle_native_tool_http_rejection(
                        fallback_error, runtime_path="recovery_invoke_http_fallback"
                    ):
                        runtime_llm_with_tools = self.llm
                        llm_for_round = self.llm
                        try:
                            result = llm_for_round.invoke(messages)
                        except Exception as downgraded_error:
                            logger.error(
                                f"[RECOVERY] LLM fallback after downgrade failed: {downgraded_error}"
                            )
                            state.is_terminated = True
                            state.termination_reason = "llm_failure"
                            break
                    else:
                        logger.error(f"[RECOVERY] LLM fallback also failed: {fallback_error}")
                        state.is_terminated = True
                        state.termination_reason = "llm_failure"
                        break

                if hasattr(result, "content"):
                    content_value = result.content
                    round_output = (
                        content_value if isinstance(content_value, str) else str(content_value)
                    )
                else:
                    round_output = str(result)
                used_non_stream_fallback = True
                native_tool_calls = self._extract_native_tool_calls(
                    result,
                    available_tools=runtime_tools_by_name,
                )
                if not round_finish_reason:
                    round_finish_reason = self._extract_finish_reason(result)
                if not round_output and native_tool_calls:
                    round_output = ""

            if (
                used_non_stream_fallback
                and stream_callback
                and round_output
                and streamed_content_chars == 0
            ):
                self._emit_stream_content_incrementally(stream_callback, round_output, "content")

            logger.info(
                f"[RECOVERY] Round {state.round_number} output: "
                f"thinking={len(round_thinking)} chars, "
                f"content={len(round_output)} chars, "
                f"finish_reason={round_finish_reason or 'unknown'}, "
                f"usage={round_usage}",
                extra={"agent_id": str(self.config.agent_id)},
            )

            # Helper function to send round stats
            def send_round_stats():
                """Calculate and send stats for this round."""
                if stream_callback and round_output_chars > 0:
                    round_end_time = time.time()

                    # Use actual usage from LLM if available, otherwise estimate
                    if round_usage:
                        input_tokens = round_usage.get("prompt_tokens", 0) or round_usage.get(
                            "input_tokens", 0
                        )
                        output_tokens = round_usage.get("completion_tokens", 0) or round_usage.get(
                            "output_tokens", 0
                        )
                        logger.info(
                            f"[RECOVERY] Using actual token counts: in={input_tokens}, out={output_tokens}"
                        )
                    else:
                        # Estimate tokens (Chinese avg ~1.5 tokens/char, English ~0.25, mixed ~0.5)
                        output_tokens = int(round_output_chars * 0.5)
                        # Estimate input tokens from messages
                        input_chars = 0
                        for msg in messages:
                            if hasattr(msg, "content"):
                                if isinstance(msg.content, str):
                                    input_chars += len(msg.content)
                                elif isinstance(msg.content, list):
                                    for item in msg.content:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            input_chars += len(item.get("text", ""))
                        input_tokens = int(input_chars * 0.5)
                        logger.info(
                            f"[RECOVERY] Using estimated token counts: in={input_tokens}, out={output_tokens}"
                        )

                    # Calculate time to first token
                    if round_first_token_time is not None:
                        time_to_first = round(round_first_token_time - round_start_time, 2)
                    else:
                        time_to_first = 0

                    # Calculate tokens per second (generation time only)
                    # Use a minimum generation time of 0.1s to avoid unrealistic speeds
                    # when LLM returns in "fake streaming" mode (all at once)
                    if round_first_token_time and round_last_token_time and output_tokens > 0:
                        generation_time = round_last_token_time - round_first_token_time
                        # If generation_time is too small, it's likely fake streaming
                        # Use total_time as fallback to get more realistic speed
                        if generation_time < 0.1:
                            # Fake streaming detected - use total time minus time_to_first
                            effective_time = (round_end_time - round_start_time) - time_to_first
                            if effective_time > 0.1:
                                tokens_per_second = round(output_tokens / effective_time, 1)
                            else:
                                tokens_per_second = 0
                        else:
                            tokens_per_second = round(output_tokens / generation_time, 1)
                    else:
                        tokens_per_second = 0

                    total_time = round(round_end_time - round_start_time, 2)

                    # Send round stats
                    stream_callback(
                        (
                            json.dumps(
                                {
                                    "roundNumber": state.round_number,
                                    "timeToFirstToken": time_to_first,
                                    "tokensPerSecond": tokens_per_second,
                                    "inputTokens": input_tokens,
                                    "outputTokens": output_tokens,
                                    "totalTime": total_time,
                                }
                            ),
                            "round_stats",
                        )
                    )

                    logger.info(
                        f"[RECOVERY] Round {state.round_number} stats: "
                        f"ttft={time_to_first}s, speed={tokens_per_second}tok/s, "
                        f"in={input_tokens}, out={output_tokens}, time={total_time}s",
                        extra={"agent_id": str(self.config.agent_id)},
                    )

            # 2. FIRST: Check for executable code blocks (```python, ```bash)
            # This takes priority over JSON tool calls for cleaner execution
            code_blocks = self.code_executor.get_executable_blocks(round_output)

            if code_blocks:
                logger.info(
                    f"[CODE_BLOCK] Found {len(code_blocks)} executable code blocks",
                    extra={"agent_id": str(self.config.agent_id)},
                )

                # Execute code blocks
                code_results = await self._execute_code_blocks(
                    code_blocks,
                    state,
                    stream_callback,
                    session_workdir=session_workdir,
                    container_id=container_id,
                )

                # Check if any execution succeeded
                any_success = any(r.success for r in code_results)

                if any_success:
                    # Format results as feedback and continue conversation
                    results_feedback = "\n".join([r.to_feedback() for r in code_results])
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=f"代码执行结果:\n{results_feedback}"))
                    send_round_stats()
                    continue
                else:
                    # All code blocks failed, let LLM try to fix
                    error_feedback = "\n".join([r.to_feedback() for r in code_results])
                    messages.append(AIMessage(content=round_output))
                    messages.append(
                        HumanMessage(content=f"代码执行失败，请修正:\n{error_feedback}")
                    )
                    send_round_stats()
                    continue

            # 3. Parse JSON tool calls (fallback if no code blocks)
            tool_calls, parse_errors = self._parse_tool_calls(
                round_output,
                available_tools=runtime_tools_by_name,
            )
            if not tool_calls and native_tool_calls:
                tool_calls = native_tool_calls
                parse_errors = []

            # 4. Handle parse errors
            if parse_errors:
                logger.warning(
                    f"[RECOVERY] Found {len(parse_errors)} parse errors",
                    extra={"agent_id": str(self.config.agent_id)},
                )

                # Send retry indicator to frontend
                if stream_callback:
                    stream_callback(
                        (
                            f"\n\n🔄 **检测到错误，正在重试** (第 {state.retry_counts.get('parse_error_' + parse_errors[0].error_type, 0) + 1}/{self.config.max_parse_retries} 次)\n",
                            "retry_attempt",
                        )
                    )

                feedback = self._handle_parse_errors(
                    parse_errors,
                    state,
                    available_tool_names=sorted(runtime_tools_by_name.keys()),
                )

                if feedback:
                    # Send error feedback to frontend
                    if stream_callback:
                        stream_callback((f"\n\n{feedback.to_prompt()}", "error_feedback"))

                    # Add to conversation and retry
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=feedback.to_prompt()))
                    send_round_stats()
                    continue
                else:
                    # Max retries exceeded
                    logger.error("[RECOVERY] Max parse retries exceeded, terminating")
                    state.is_terminated = True
                    state.termination_reason = "max_parse_retries_exceeded"

                    if stream_callback:
                        stream_callback(
                            (
                                "\n\n⛔ 工具调用格式错误次数过多，无法继续。请直接提供答案。\n",
                                "error",
                            )
                        )
                    send_round_stats()
                    break

            # 5. No tool calls -> run deterministic state-machine completion check
            if not tool_calls:
                if state.round_number >= state.max_rounds:
                    logger.info(
                        "[RECOVERY] Max round reached; accepting current output as final",
                        extra={"agent_id": str(self.config.agent_id), "round": state.round_number},
                    )
                    state.is_terminated = True
                    state.termination_reason = "final_answer_provided"
                    send_round_stats()
                    break

                completion_decision = self._assess_autonomous_completion(
                    task_intent_text=resolved_task_intent_text,
                    latest_output=round_output,
                    tool_call_records=state.tool_calls_made,
                    round_number=state.round_number,
                    max_rounds=state.max_rounds,
                    file_delivery_required=file_delivery_required,
                    file_delivery_guard_mode=file_delivery_guard_mode,
                    requested_file_formats=requested_file_formats,
                    response_delivery_mode=response_delivery_mode,
                    finish_reason=round_finish_reason,
                )
                should_stop = bool(completion_decision.get("should_stop"))

                if state.round_number < state.max_rounds and not should_stop:
                    logger.info(
                        "[RECOVERY] State-machine check: incomplete, continue iterating",
                        extra={
                            "agent_id": str(self.config.agent_id),
                            "round": state.round_number,
                            "confidence": completion_decision.get("confidence", 0.0),
                            "reason": completion_decision.get("reason", ""),
                            "finish_reason": round_finish_reason or "unknown",
                        },
                    )
                    if stream_callback:
                        stream_callback(
                            (
                                "\n\n🔁 当前任务尚未确认完成，继续自主执行下一步。\n",
                                "info",
                            )
                        )
                    messages.append(AIMessage(content=round_output))
                    continue_feedback = str(
                        completion_decision.get("feedback_prompt") or ""
                    ).strip() or self._build_autonomy_continue_feedback(completion_decision)
                    messages.append(HumanMessage(content=continue_feedback))
                    send_round_stats()
                    continue

                logger.info(
                    "[RECOVERY] State-machine check: task complete, stopping loop",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "round": state.round_number,
                        "confidence": completion_decision.get("confidence", 0.0),
                        "finish_reason": round_finish_reason or "unknown",
                    },
                )
                advisory_message = str(completion_decision.get("advisory_message") or "").strip()
                if advisory_message:
                    logger.warning(
                        "[RECOVERY] File-delivery soft advisory",
                        extra={
                            "agent_id": str(self.config.agent_id),
                            "round": state.round_number,
                            "file_delivery_guard_mode": file_delivery_guard_mode.value,
                            "advisory_message": advisory_message,
                        },
                    )
                    if stream_callback:
                        stream_callback((f"\n\n⚠️ {advisory_message}\n", "warning"))
                state.is_terminated = True
                state.termination_reason = "final_answer_provided"
                send_round_stats()
                break

            # 6. Execute tool calls with recovery
            tool_results = await self._execute_tools_with_recovery(
                tool_calls,
                state,
                stream_callback,
                tool_registry=runtime_tools_by_name,
            )

            # 7. Check if all tools failed
            all_failed = all(r.status == "error" for r in tool_results)

            if all_failed:
                logger.warning("[RECOVERY] All tools failed")

                # Send retry indicator to frontend
                failed_tool = tool_results[0].tool_name
                retry_key = f"tool_{failed_tool}"
                retry_count = state.retry_counts.get(retry_key, 0)

                if stream_callback:
                    stream_callback(
                        (
                            f"\n\n🔄 **工具执行失败，正在重试** (第 {retry_count}/{self.config.max_execution_retries} 次)\n",
                            "retry_attempt",
                        )
                    )

                feedback = self._handle_execution_failures(tool_results, state)

                if feedback:
                    # Send error feedback
                    if stream_callback:
                        stream_callback((f"\n\n{feedback.to_prompt()}", "error_feedback"))

                    # Add to conversation and retry
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=feedback.to_prompt()))
                    send_round_stats()
                    continue
                else:
                    # Max retries exceeded
                    logger.error("[RECOVERY] Max execution retries exceeded, terminating")
                    state.is_terminated = True
                    state.termination_reason = "max_execution_retries_exceeded"

                    if stream_callback:
                        stream_callback(
                            (
                                "\n\n⛔ 工具执行失败次数过多，无法继续。请根据已有信息提供答案。\n",
                                "error",
                            )
                        )
                    send_round_stats()
                    break

            # 7. Add results to conversation and continue
            if stream_callback:
                stream_callback((f"\n\n---\n\n💭 **根据工具结果生成最终回答...**\n\n", "info"))

            # Send round stats before continuing to next round
            send_round_stats()

            messages.append(AIMessage(content=round_output))
            messages.append(HumanMessage(content=self._format_tool_results(tool_results)))

        # Handle max rounds reached (only when loop exits without an earlier terminal decision)
        if not state.is_terminated and state.round_number >= state.max_rounds:
            logger.warning(
                f"[RECOVERY] Max rounds reached ({state.max_rounds})",
                extra={"agent_id": str(self.config.agent_id)},
            )
            state.is_terminated = True
            state.termination_reason = "max_rounds_reached"

            if stream_callback:
                stream_callback(
                    (f"\n\n⚠️ 已达到最大对话轮数 ({state.max_rounds})，对话结束。\n", "warning")
                )

        logger.info(
            f"[RECOVERY] Conversation completed: reason={state.termination_reason}, rounds={state.round_number}, errors={len(state.errors)}",
            extra={
                "agent_id": str(self.config.agent_id),
                "termination_reason": state.termination_reason,
                "rounds": state.round_number,
                "tool_calls": len(state.tool_calls_made),
                "errors": len(state.errors),
            },
        )

        self._raise_if_cancelled()

        success = state.termination_reason in ["final_answer_provided"]
        error_message: Optional[str] = None
        if not success:
            if state.errors:
                error_message = state.errors[-1].error_message
            elif state.termination_reason == "max_execution_retries_exceeded":
                error_message = "Tool execution failed after maximum retries"
            elif state.termination_reason == "max_parse_retries_exceeded":
                error_message = "Tool call parsing failed after maximum retries"
            elif state.termination_reason == "max_rounds_reached":
                error_message = f"Max conversation rounds reached ({state.max_rounds})"
            elif state.termination_reason == "llm_failure":
                error_message = "LLM request failed during recovery conversation"
            elif state.termination_reason:
                error_message = f"Conversation terminated: {state.termination_reason}"
            else:
                error_message = "Conversation terminated without final answer"

        return {
            "success": success,
            "output": round_output if state.is_terminated else "Incomplete",
            "messages": messages,
            "state": state,
            "error": error_message,
            "error_recovery_stats": {
                "total_errors": len(state.errors),
                "recovered_errors": len([e for e in state.errors if e.is_recoverable]),
                "retry_attempts": sum(state.retry_counts.values()),
            },
        }

    def _build_execution_error_suggestions(self, failed_result: ToolResult) -> List[str]:
        """Generate generic recovery hints for execution failures."""
        raw_error = failed_result.error or ""
        error_text = raw_error.lower()

        if "command not found" in error_text:
            return [
                "Verify command availability in current runtime before retrying",
                "Prefer runtime-native dependency installation paths (for Python, use pip first)",
                "Retry the original step after minimal environment adjustments",
            ]

        if "modulenotfounderror" in error_text or "no module named" in error_text:
            return [
                "Install missing runtime dependencies first",
                "Retry the original operation after dependency installation",
                "Avoid unrelated rewrites until dependency issues are resolved",
            ]

        if (
            "file not found" in error_text
            or "no such file" in error_text
            or "can't open file" in error_text
        ):
            return [
                "Re-check file paths and ensure required files are created before use",
                "List workspace files and validate expected input/output locations",
                "Retry with corrected paths using minimal command changes",
            ]

        if "permission denied" in error_text:
            return [
                "Avoid protected system locations and use workspace-scoped paths",
                "Adjust operation to the current sandbox permission model",
                "Retry with least-privilege compatible commands",
            ]

        if "timeout" in error_text:
            return [
                "Reduce task scope per execution step and retry incrementally",
                "Split heavy operations into smaller deterministic steps",
                "Re-run the failed step with a tighter, minimal command",
            ]

        return [
            "Read the exact error and identify the immediate blocker",
            "Verify tool arguments, file paths, and environment assumptions",
            "Apply a minimal fix, then retry the same step",
            "Only switch approach if the current path is provably blocked",
        ]

    def _handle_execution_failures(
        self, tool_results: List[ToolResult], state: ConversationState
    ) -> Optional[ErrorFeedback]:
        """Generate feedback for execution failures.

        Args:
            tool_results: List of tool results with errors
            state: Current conversation state

        Returns:
            ErrorFeedback if recoverable, None if max retries exceeded
        """
        # Find first failed tool
        failed_result = next((r for r in tool_results if r.status == "error"), None)
        if not failed_result:
            return None

        # Check retry count
        retry_key = f"tool_{failed_result.tool_name}"
        retry_count = state.retry_counts.get(retry_key, 0)

        if retry_count >= self.config.max_execution_retries:
            logger.error(
                f"[RECOVERY] Max execution retries exceeded for {failed_result.tool_name}",
                extra={"agent_id": str(self.config.agent_id), "tool_name": failed_result.tool_name},
            )
            return None

        # Record error
        state.errors.append(
            ErrorRecord(
                round_number=state.round_number,
                error_type=failed_result.error_type or "execution_error",
                error_message=failed_result.error or "Unknown error",
                tool_name=failed_result.tool_name,
                is_recoverable=True,
                retry_count=retry_count,
            )
        )

        # Generate feedback based on error type
        if failed_result.error_type == "timeout":
            return ErrorFeedback(
                error_type="Timeout Error",
                error_message=failed_result.error or "Tool execution timed out",
                malformed_input=None,
                expected_format='{"tool": "<same_tool>", "...": "retry_with_smaller_scope"}',
                retry_count=retry_count,
                max_retries=self.config.max_execution_retries,
                suggestions=[
                    "The operation took too long to complete",
                    "Consider breaking it into smaller steps",
                    "Check if there's an infinite loop",
                    "Try a simpler approach",
                ],
            )
        else:
            return ErrorFeedback(
                error_type="Execution Error",
                error_message=failed_result.error or "Tool execution failed",
                malformed_input=None,
                expected_format='{"tool": "<same_tool>", "...": "corrected_arguments"}',
                retry_count=retry_count,
                max_retries=self.config.max_execution_retries,
                suggestions=self._build_execution_error_suggestions(failed_result),
            )

    def _parse_and_execute_tools_sync(self, output: str) -> str:
        """Parse tool calls from LLM output and execute them synchronously.

        For LLMs that don't support function calling, we parse tool invocations
        from the text output and execute them manually.

        Args:
            output: LLM output text

        Returns:
            Modified output with tool results
        """
        import asyncio
        import json
        import re

        # Pattern to match tool invocations: ```tool:tool_name\n{json}\n```
        pattern = r"```tool:(\w+)\s*\n(.*?)\n```"
        matches = re.findall(pattern, output, re.DOTALL)

        if not matches:
            return output

        logger.info(
            f"Found {len(matches)} tool invocations in output",
            extra={"agent_id": str(self.config.agent_id)},
        )

        modified_output = output

        for tool_name, args_json in matches:
            tool = self.tools_by_name.get(tool_name)
            if not tool:
                logger.warning(f"Tool not found: {tool_name}")
                continue

            try:
                # Parse arguments
                args = json.loads(args_json)

                logger.info(
                    f"Executing tool: {tool_name}",
                    extra={"agent_id": str(self.config.agent_id), "args": args},
                )

                # Execute tool (handle both sync and async)
                if hasattr(tool, "_arun"):
                    # Run async tool in new event loop
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # If loop is running, create new loop in thread
                            import concurrent.futures

                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(asyncio.run, tool._arun(**args))
                                result = future.result()
                        else:
                            result = loop.run_until_complete(tool._arun(**args))
                    except RuntimeError:
                        # No event loop, create new one
                        result = asyncio.run(tool._arun(**args))
                else:
                    result = tool._run(**args)

                # Replace tool invocation with result in output
                tool_block = f"```tool:{tool_name}\n{args_json}\n```"
                result_block = f"```tool_result:{tool_name}\n{result}\n```"
                modified_output = modified_output.replace(tool_block, result_block)

                logger.info(
                    f"Tool executed successfully: {tool_name}",
                    extra={"agent_id": str(self.config.agent_id)},
                )

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool arguments: {e}")
            except Exception as e:
                logger.error(f"Tool execution failed: {e}", exc_info=True)

        return modified_output

    def _create_system_prompt(
        self,
        available_tools: Optional[List[Any]] = None,
        runtime_capabilities: Optional[Dict[str, Any]] = None,
        response_delivery_mode: str = "chat_inline",
        response_delivery_channel: str = "",
    ) -> str:
        """Create system prompt for the agent.

        Includes Agent Skills documentation and available tools if available.

        Returns:
            System prompt string
        """
        # Use custom system prompt if provided
        if self.config.system_prompt:
            base_prompt = self.config.system_prompt
        else:
            # Generate default system prompt
            capability_labels = sorted(self.langchain_tool_skill_names | self.agent_skill_names)
            capability_text = ", ".join(capability_labels) if capability_labels else "general"
            base_prompt = f"""You are {self.config.name}, a {self.config.agent_type} agent with the following capabilities: {capability_text}.

Your role is to help users accomplish tasks using your available tools and capabilities.

When solving problems:
1. Analyze the user's request carefully
2. Use available tools when needed
3. Provide clear and helpful responses
4. If you need more information, ask clarifying questions
5. For key parameters (e.g., city, date, person, account), prioritize values explicitly given in the current user message
6. If a required parameter is missing, ask for clarification instead of guessing from old memory/context

Always be professional, accurate, and helpful."""

        # Add tools description for LangChain tools
        # Include tools in prompt if:
        # 1. LLM doesn't support bind_tools, OR
        # 2. LLM supports bind_tools but we want tools visible in prompt anyway (for better awareness)
        runtime_tools = available_tools if available_tools is not None else self.tools
        if runtime_tools:
            # Include ALL tools in the prompt (including code_execution)
            langchain_tools = runtime_tools

            if langchain_tools:
                tools_prompt = "\n\n## Available Tools\n\n"
                tools_prompt += "You have access to the following tools:\n\n"

                for tool in langchain_tools:
                    tools_prompt += f"### {tool.name}\n"
                    tools_prompt += f"{tool.description}\n\n"

                # Add note about how to use tools
                if not self.native_tool_calling_enabled:
                    # LLM doesn't support function calling - need manual format
                    tools_prompt += "\n**IMPORTANT - How to use tools**: To use a tool, you MUST write it in this EXACT format:\n\n"
                    tools_prompt += "```json\n"
                    tools_prompt += '{"tool": "tool_name", "arg_name": "arg_value"}\n'
                    tools_prompt += "```\n\n"
                    tools_prompt += "Example for calculator:\n"
                    tools_prompt += "```json\n"
                    tools_prompt += '{"tool": "calculator", "expression": "132 * 223"}\n'
                    tools_prompt += "```\n\n"
                    tools_prompt += "Example for code_execution:\n"
                    tools_prompt += "```json\n"
                    tools_prompt += (
                        '{"tool": "code_execution", "code": "print(\'Hello World\')", '
                        '"language": "python"}\n'
                    )
                    tools_prompt += "```\n\n"
                    tools_prompt += "**DO NOT** just write about using the tool - you MUST use the exact JSON format above!\n\n"
                else:
                    # LLM supports function calling, but may not work properly
                    # Provide both formats
                    tools_prompt += "\n**How to use tools**: \n\n"
                    tools_prompt += (
                        "**Method 1 (Preferred)**: Use function calling if supported.\n\n"
                    )
                    tools_prompt += "**Method 2 (Fallback)**: If function calling doesn't work, use this JSON format:\n"
                    tools_prompt += "```json\n"
                    tools_prompt += '{"tool": "tool_name", "arg_name": "arg_value"}\n'
                    tools_prompt += "```\n\n"
                    tools_prompt += "Example for calculator:\n"
                    tools_prompt += "```json\n"
                    tools_prompt += '{"tool": "calculator", "expression": "2323 * 23"}\n'
                    tools_prompt += "```\n\n"
                    tools_prompt += "Example for code_execution:\n"
                    tools_prompt += "```json\n"
                    tools_prompt += (
                        '{"tool": "code_execution", "code": "console.log(\'Hello from Node.js\')", '
                        '"language": "javascript"}\n'
                    )
                    tools_prompt += "```\n\n"

                base_prompt += tools_prompt

        resolved_runtime_capabilities = sanitize_runtime_capabilities(
            runtime_capabilities,
            defaults=build_runtime_capabilities_snapshot(
                sandbox_enabled=False,
                sandbox_backend="unknown",
                workspace_root_virtual="/workspace",
                writable_roots=["/workspace"],
                ui_mode="none",
                network_access=True,
                host_fallback_allowed=allow_host_execution_fallback(),
                session_persistent=False,
                source="base_agent_prompt_default",
            ),
        )
        runtime_environment_block = self._render_runtime_environment_prompt_block(
            resolved_runtime_capabilities
        )

        file_tools_lines = [
            "- **read_file**: Read file contents. Supports `offset` (start line, 1-based) and `limit` (max lines) for large files.",
            "- **edit_file**: Replace exact string in a file (`old_string` -> `new_string`). The old_string must match exactly.",
            "- **write_file**: Create or overwrite a file. Creates parent directories automatically.",
            "- **append_file**: Append additional content to an existing file (or create it if missing).",
            "- **list_files**: List files in a directory. Supports `recursive=true`.",
        ]
        file_delivery_policy = """
**When users ask for deliverables as files/documents** (for example "整理成md文档", "save as markdown"):
1. You MUST use `write_file` to save the deliverable under `/workspace` (prefer `/workspace/output/...`). Default target path MUST be `/workspace/output/...`; only write to another location when the user explicitly specifies that exact path.
2. Prefer a single target file and update it incrementally across rounds (create first, then continue writing).
3. Only split into multiple files when explicitly requested by the user or when one file is clearly impractical.
4. Do NOT use `code_execution` as the final file-delivery step for plain text documents.
5. In your final response, report the exact saved file path(s) and keep the summary concise.
6. Do NOT paste the full file contents, long previews, or complete code blocks once the deliverable has been saved as a file.
7. If the user later asks to inspect file contents inline, provide only the specific excerpt or section they ask for instead of dumping the whole file.
8. Never claim a file was saved unless the tool call succeeded.
"""
        dependency_recovery_policy = """
**Dependency/tool failure strategy**:
1. If a Python dependency is missing, prefer `python3 -m pip install <package>` (or `pip/pip3`) first.
2. Do NOT jump to OS package managers (`apt-get`, `yum`) unless you have explicitly confirmed they exist.
3. After installing dependencies, retry the original command with minimal changes.
4. For PDF/Office files and Chinese text, avoid hardcoded font paths; use runtime-available fonts or portable fallbacks.
"""

        file_tools_section = "\n".join(file_tools_lines)
        workspace_prompt = f"""

## Sandbox Workspace

{runtime_environment_block}

**File operation tools available:**
{file_tools_section}

**Default behavior**:
- For ordinary Q&A or short content, respond directly in chat.
- Use file tools when the user asks for deliverable files or when file output materially improves usability.

{file_delivery_policy}
{dependency_recovery_policy}

**You can also create/manipulate files through code blocks** (Python/Bash) that run in the same workspace.

All file paths should use `/workspace/` as the root, e.g. `/workspace/main.py`.
"""
        base_prompt += workspace_prompt

        # Add Agent Skills documentation if available
        if self.skill_manager:
            skills_prompt = self.skill_manager.format_skills_for_prompt()
            return base_prompt + skills_prompt

        return base_prompt
