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
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import MessagesState, StateGraph, START, END

from agent_framework.code_block_executor import CodeBlockExecutor, get_code_block_executor

logger = logging.getLogger(__name__)


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
    return value in ('true', '1', 'yes', 'on')


class AgentStatus(Enum):
    """Agent status enumeration."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    TERMINATED = "terminated"
    ERROR = "error"


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
    capabilities: List[str]  # List of skill names
    llm_model: str = "ollama"
    temperature: float = 0.7
    max_iterations: int = 20  # Maximum conversation rounds
    system_prompt: Optional[str] = None  # Custom system prompt
    
    # Error recovery settings (can be overridden by environment variables)
    max_parse_retries: Optional[int] = None
    max_execution_retries: Optional[int] = None
    tool_timeout_seconds: Optional[float] = None
    enable_error_recovery: Optional[bool] = None
    
    def __post_init__(self):
        """Validate configuration and apply environment variable overrides."""
        # Apply environment variable overrides with defaults
        if self.max_parse_retries is None:
            self.max_parse_retries = _get_env_int('AGENT_MAX_PARSE_RETRIES', 3)
        
        if self.max_execution_retries is None:
            self.max_execution_retries = _get_env_int('AGENT_MAX_EXECUTION_RETRIES', 3)
        
        if self.tool_timeout_seconds is None:
            self.tool_timeout_seconds = _get_env_float('AGENT_TOOL_TIMEOUT', 30.0)
        
        if self.enable_error_recovery is None:
            self.enable_error_recovery = _get_env_bool('AGENT_ENABLE_ERROR_RECOVERY', True)
        
        # Validate retry limits
        if self.max_parse_retries < 0:
            raise ValueError(f"max_parse_retries must be non-negative, got {self.max_parse_retries}")
        if self.max_execution_retries < 0:
            raise ValueError(f"max_execution_retries must be non-negative, got {self.max_execution_retries}")
        
        # Validate timeout
        if not (1.0 <= self.tool_timeout_seconds <= 300.0):
            raise ValueError(f"tool_timeout_seconds must be between 1 and 300, got {self.tool_timeout_seconds}")
        
        # Validate max_iterations
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be positive, got {self.max_iterations}")
        
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
                "enable_error_recovery": self.enable_error_recovery
            }
        )


class BaseAgent:
    """Base agent class with LangGraph 1.0 integration.

    Each agent is an autonomous entity with:
    - Identity (agent_id, name, owner)
    - Capabilities (skills from Skill Library)
    - Memory access (Agent Memory + Company Memory)
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

        logger.info(
            f"BaseAgent initialized: {config.name}",
            extra={
                "agent_id": str(config.agent_id),
                "agent_type": config.agent_type,
                "capabilities": config.capabilities,
            },
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
                user_id=self.config.owner_user_id
            )
            
            # Discover and load skills based on agent's capabilities
            skills = await self.skill_manager.discover_skills(
                agent_capabilities=self.config.capabilities
            )
            
            logger.info(
                f"Discovered {len(skills)} skills for agent {self.config.name}",
                extra={"agent_id": str(self.config.agent_id), "skill_count": len(skills)}
            )
            
            # Load skills
            langchain_tool_count = 0
            agent_skill_count = 0
            
            for skill_info in skills:
                if skill_info.skill_type == "langchain_tool":
                    tool = await self.skill_manager.load_langchain_tool(skill_info)
                    if tool:
                        self.tools.append(tool)
                        langchain_tool_count += 1
                        logger.info(
                            f"✓ Loaded LangChain tool: {skill_info.name}",
                            extra={"agent_id": str(self.config.agent_id), "skill_id": str(skill_info.skill_id)}
                        )
                    else:
                        logger.error(
                            f"✗ Failed to load LangChain tool: {skill_info.name}",
                            extra={"agent_id": str(self.config.agent_id), "skill_id": str(skill_info.skill_id)}
                        )
                elif skill_info.skill_type == "agent_skill":
                    # Agent skills are loaded as documentation, not tools
                    skill_ref = await self.skill_manager.load_agent_skill_doc(skill_info)
                    if skill_ref:
                        agent_skill_count += 1
                        logger.info(
                            f"✓ Loaded Agent Skill doc: {skill_info.name}",
                            extra={"agent_id": str(self.config.agent_id), "skill_id": str(skill_info.skill_id)}
                        )
                    else:
                        logger.error(
                            f"✗ Failed to load Agent Skill doc: {skill_info.name}",
                            extra={"agent_id": str(self.config.agent_id), "skill_id": str(skill_info.skill_id)}
                        )
            
            # Add enhanced bash tool with PTY and background support
            from agent_framework.tools.process_manager import get_process_manager
            from agent_framework.tools.bash_tool import create_bash_tool
            process_manager = get_process_manager()
            bash_tool = create_bash_tool(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id,
                process_manager=process_manager
            )
            self.tools.append(bash_tool)
            logger.info(
                f"✓ Added enhanced bash tool (PTY + background support)",
                extra={"agent_id": str(self.config.agent_id)}
            )
            
            # Add process management tool
            from agent_framework.tools.process_tool import create_process_tool
            process_tool = create_process_tool(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id
            )
            self.tools.append(process_tool)
            logger.info(
                f"✓ Added process management tool",
                extra={"agent_id": str(self.config.agent_id)}
            )
            
            # Add code execution tool (for agent to run generated code)
            from agent_framework.tools.code_execution_tool import create_code_execution_tool
            code_exec_tool = create_code_execution_tool(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id
            )
            self.tools.append(code_exec_tool)
            
            # Add read_skill tool (for agent to read Agent Skill documentation)
            if agent_skill_count > 0:
                from agent_framework.tools.read_skill_tool import create_read_skill_tool
                read_skill_tool = create_read_skill_tool(
                    agent_id=self.config.agent_id,
                    user_id=self.config.owner_user_id,
                    skill_manager=self.skill_manager  # Pass the loaded skill_manager
                )
                self.tools.append(read_skill_tool)
                logger.info(
                    f"✓ Added read_skill tool for {agent_skill_count} Agent Skills",
                    extra={"agent_id": str(self.config.agent_id)}
                )
            
            logger.info(
                f"Skills loaded: {langchain_tool_count} LangChain tools, {agent_skill_count} Agent Skills",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "langchain_tools": langchain_tool_count,
                    "agent_skills": agent_skill_count
                }
            )

            # Bind tools to LLM (if supported)
            if self.tools:
                self.tools_by_name = {tool.name: tool for tool in self.tools}
                try:
                    self.llm_with_tools = self.llm.bind_tools(self.tools)
                except (NotImplementedError, AttributeError) as e:
                    logger.warning(
                        f"LLM does not support bind_tools, using without tool binding: {e}",
                        extra={"agent_id": str(self.config.agent_id)}
                    )
                    self.llm_with_tools = self.llm
            else:
                self.llm_with_tools = self.llm

            # Create system prompt (includes Agent Skills documentation)
            system_prompt = self._create_system_prompt()

            # Build agent graph using LangGraph 1.0 StateGraph API
            builder = StateGraph(MessagesState)

            # Add LLM node
            def call_llm(state: MessagesState) -> Dict[str, List]:
                """LLM node that processes messages and decides on tool calls."""
                messages = state["messages"]
                
                # Prepend system message if not already present
                if not messages or not isinstance(messages[0], SystemMessage):
                    messages = [SystemMessage(content=system_prompt)] + messages
                
                response = self.llm_with_tools.invoke(messages)
                return {"messages": [response]}

            # Check if LLM supports tool calls
            llm_supports_tools = self.tools and hasattr(self.llm, 'bind_tools')
            
            # Add tool execution node (only if tools are available and LLM supports them)
            if llm_supports_tools:
                def call_tools(state: MessagesState) -> Dict[str, List]:
                    """Tool node that executes tool calls."""
                    messages = state["messages"]
                    last_message = messages[-1]
                    
                    tool_results = []
                    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                        for tool_call in last_message.tool_calls:
                            tool = self.tools_by_name.get(tool_call["name"])
                            if tool:
                                try:
                                    result = tool.invoke(tool_call["args"])
                                    from langchain_core.messages import ToolMessage
                                    tool_results.append(
                                        ToolMessage(
                                            content=str(result),
                                            tool_call_id=tool_call["id"]
                                        )
                                    )
                                except Exception as e:
                                    logger.error(f"Tool execution failed: {e}")
                                    from langchain_core.messages import ToolMessage
                                    tool_results.append(
                                        ToolMessage(
                                            content=f"Error: {str(e)}",
                                            tool_call_id=tool_call["id"]
                                        )
                                    )
                    
                    return {"messages": tool_results}

                # Conditional edge to decide whether to continue or end
                def should_continue(state: MessagesState) -> str:
                    """Decide whether to continue with tools or end."""
                    messages = state["messages"]
                    last_message = messages[-1]
                    
                    # Check if LLM made tool calls
                    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                        return "tools"
                    return END

                # Build graph with tools
                builder.add_node("llm", call_llm)
                builder.add_node("tools", call_tools)
                
                builder.add_edge(START, "llm")
                builder.add_conditional_edges(
                    "llm",
                    should_continue,
                    {"tools": "tools", END: END}
                )
                builder.add_edge("tools", "llm")
            else:
                # Build simple graph without tools
                logger.info(
                    f"Building agent without tool support",
                    extra={"agent_id": str(self.config.agent_id)}
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

    def execute_task(
        self, task_description: str, context: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Execute a task using the agent.

        Args:
            task_description: Description of the task to execute
            context: Optional context information (e.g., memories)
            stream_callback: Optional callback for streaming tokens (callable(str))

        Returns:
            Dict with execution results
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        if self.status != AgentStatus.ACTIVE:
            raise RuntimeError(f"Agent not active. Current status: {self.status.value}")

        try:
            self.status = AgentStatus.BUSY
            logger.info(f"Agent executing task: {self.config.name}")

            # Route to new implementation if error recovery is enabled
            if self.config.enable_error_recovery and stream_callback:
                import asyncio
                # Run async method in sync context
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, we're already in async context
                        # This shouldn't happen in normal usage
                        logger.warning("Event loop already running, using legacy implementation")
                    else:
                        result = loop.run_until_complete(
                            self.execute_task_with_recovery(
                                task_description, context, stream_callback
                            )
                        )
                        self.status = AgentStatus.ACTIVE
                        return result
                except RuntimeError:
                    # No event loop, create new one
                    result = asyncio.run(
                        self.execute_task_with_recovery(
                            task_description, context, stream_callback
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
                if context.get("agent_memories"):
                    context_info.append(f"Relevant memories: {', '.join(context['agent_memories'][:3])}")
                if context.get("company_memories"):
                    context_info.append(f"Company knowledge: {', '.join(context['company_memories'][:3])}")
                
                if context_info:
                    user_message = f"{task_description}\n\nContext:\n" + "\n".join(context_info)

            # Invoke agent with streaming support
            if stream_callback:
                # Stream mode - use LLM's native streaming for token-by-token output
                # Then check for tool calls and execute them
                system_prompt = self._create_system_prompt()
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message)
                ]
                
                # Multi-round conversation loop for tool execution
                tool_calls_made = []
                max_iterations = 20  # 最多20轮
                iteration = 0
                
                logger.info(
                    f"[TOOL-LOOP] Starting multi-round conversation (max {max_iterations} iterations)",
                    extra={"agent_id": str(self.config.agent_id), "has_tools": len(self.tools) > 0}
                )
                
                while iteration < max_iterations:
                    iteration += 1
                    
                    logger.info(
                        f"[TOOL-LOOP] Round {iteration}/{max_iterations}",
                        extra={"agent_id": str(self.config.agent_id)}
                    )
                    
                    # Stream LLM response for this round
                    round_output = ""
                    round_thinking = ""
                    chunk_count = 0
                    stream_failed = False
                    
                    try:
                        for chunk in self.llm.stream(messages):
                            if hasattr(chunk, 'content') and chunk.content:
                                # Check for content_type in additional_kwargs
                                content_type = "content"  # default
                                if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                                    content_type = chunk.additional_kwargs.get('content_type', 'content')
                                
                                # Send to frontend immediately for real-time streaming
                                stream_callback((chunk.content, content_type))
                                
                                # Also accumulate for tool detection
                                if content_type == "thinking":
                                    round_thinking += chunk.content
                                else:
                                    round_output += chunk.content
                                chunk_count += 1
                        
                        # If no chunks were received, mark streaming as failed
                        if chunk_count == 0:
                            stream_failed = True
                            logger.warning("LLM streaming returned no chunks")
                        
                    except Exception as stream_error:
                        stream_failed = True
                        logger.warning(f"Streaming failed: {stream_error}")
                    
                    # If streaming failed, fall back to non-streaming
                    if stream_failed:
                        logger.info("Falling back to non-streaming mode")
                        try:
                            result = self.llm.invoke(messages)
                            if hasattr(result, 'content'):
                                round_output = result.content
                            else:
                                round_output = str(result)
                            
                            if not round_output:
                                raise ValueError("LLM returned empty content")
                        except Exception as invoke_error:
                            logger.error(f"Non-streaming fallback also failed: {invoke_error}")
                            raise
                    
                    logger.info(
                        f"[TOOL-LOOP] Round {iteration} LLM output: thinking={len(round_thinking)} chars, content={len(round_output)} chars",
                        extra={"agent_id": str(self.config.agent_id)}
                    )
                    
                    # Check if output contains tool calls
                    import re
                    import json
                    
                    # Pattern 1: JSON block with ```json wrapper
                    json_pattern1 = r'```json\s*\n\s*(\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\})\s*\n\s*```'
                    
                    # Pattern 2: Plain JSON without wrapper (more common)
                    json_pattern2 = r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\}'
                    
                    # Try pattern 1 first (with wrapper)
                    matches1 = re.findall(json_pattern1, round_output, re.DOTALL)
                    
                    # Try pattern 2 (without wrapper)
                    matches2 = re.findall(json_pattern2, round_output, re.DOTALL)
                    
                    # Combine matches
                    tool_json_blocks = []
                    
                    # Process pattern 1 matches
                    for json_str, tool_name in matches1:
                        tool_json_blocks.append(json_str)
                    
                    # Process pattern 2 matches (only if pattern 1 didn't match)
                    if not matches1 and matches2:
                        for tool_name in matches2:
                            # Extract the full JSON block
                            match = re.search(r'\{[^}]*"tool"\s*:\s*"' + re.escape(tool_name) + r'"[^}]*\}', round_output)
                            if match:
                                tool_json_blocks.append(match.group(0))
                    
                    if tool_json_blocks:
                        # This round contains tool calls
                        logger.info(
                            f"[TOOL-LOOP] Found {len(tool_json_blocks)} tool calls in round {iteration}",
                            extra={"agent_id": str(self.config.agent_id)}
                        )
                        
                        # Note: thinking and content already sent during streaming above
                        # Now just execute tools and send tool execution info
                        
                        # Execute tools
                        tool_results = []
                        for json_str in tool_json_blocks:
                            try:
                                tool_data = json.loads(json_str)
                                tool_name = tool_data.get("tool")
                                
                                # Find the tool
                                tool = self.tools_by_name.get(tool_name)
                                if tool:
                                    # Prepare arguments based on tool
                                    if tool_name == "calculator":
                                        tool_args = {"expression": tool_data.get("expression", "")}
                                    else:
                                        # Generic args extraction
                                        tool_args = {k: v for k, v in tool_data.items() if k != "tool"}
                                    
                                    # Send "calling tool" message BEFORE execution
                                    stream_callback((
                                        f"\n\n🔧 **调用工具: {tool_name}**\n参数: {tool_args}\n",
                                        "tool_call"
                                    ))
                                    
                                    logger.info(
                                        f"Executing tool: {tool_name}",
                                        extra={
                                            "agent_id": str(self.config.agent_id),
                                            "tool_name": tool_name,
                                            "tool_args": str(tool_args)
                                        }
                                    )
                                    
                                    # Execute tool
                                    try:
                                        result = tool.invoke(tool_args)
                                        tool_calls_made.append({
                                            "name": tool_name,
                                            "args": tool_args,
                                            "result": str(result)
                                        })
                                        tool_results.append({
                                            "tool": tool_name,
                                            "args": tool_args,
                                            "result": str(result)
                                        })
                                        
                                        # Send tool execution result to frontend
                                        stream_callback((
                                            f"✅ **执行结果**: {result}\n",
                                            "tool_result"
                                        ))
                                        
                                        logger.info(
                                            f"Tool executed successfully: {tool_name} = {result}",
                                            extra={"agent_id": str(self.config.agent_id)}
                                        )
                                    except Exception as tool_error:
                                        logger.error(f"Tool execution failed: {tool_error}", exc_info=True)
                                        stream_callback((
                                            f"❌ **执行失败**: {str(tool_error)}\n",
                                            "tool_error"
                                        ))
                                        tool_results.append({
                                            "tool": tool_name,
                                            "args": tool_args,
                                            "error": str(tool_error)
                                        })
                                else:
                                    logger.warning(f"Tool not found: {tool_name}")
                                    stream_callback((
                                        f"⚠️ 工具未找到: {tool_name}\n",
                                        "tool_error"
                                    ))
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse tool JSON: {e}")
                                stream_callback((
                                    f"⚠️ 工具调用格式错误: {e}\n",
                                    "tool_error"
                                ))
                        
                        # If tools were executed, continue to next round with tool results
                        if tool_results:
                            logger.info(
                                f"[TOOL-LOOP] Executed {len(tool_results)} tools, continuing to round {iteration + 1}",
                                extra={"agent_id": str(self.config.agent_id)}
                            )
                            
                            # Send separator before continuation
                            stream_callback((
                                f"\n\n---\n\n💭 **根据工具结果生成最终回答...**\n\n",
                                "info"
                            ))
                            
                            # Build a message with tool results
                            tool_results_text = "\n\n工具执行结果：\n"
                            for tr in tool_results:
                                if "error" in tr:
                                    tool_results_text += f"- {tr['tool']}: 错误 - {tr['error']}\n"
                                else:
                                    tool_results_text += f"- {tr['tool']}: {tr['result']}\n"
                            
                            # Check if we just read skill documentation - if so, encourage using it
                            if any(tr.get('tool') == 'read_skill' for tr in tool_results):
                                tool_results_text += "\n你已经获得了技能文档。如果需要执行技能中的脚本或命令，请使用 code_execution 工具。如果已经有足够信息，可以直接回答用户。"
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
                        # No tool calls in this round - this is the final answer
                        logger.info(
                            f"[TOOL-LOOP] No tool calls in round {iteration}, conversation complete",
                            extra={"agent_id": str(self.config.agent_id)}
                        )
                        
                        # Note: thinking and content already sent during streaming above
                        # Exit loop - we have the final answer
                        break
                
                logger.info(
                    f"[TOOL-LOOP] Conversation completed after {iteration} rounds",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_calls_count": len(tool_calls_made)
                    }
                )
                
                self.status = AgentStatus.ACTIVE
                logger.info(
                    f"Task completed: {self.config.name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_calls_count": len(tool_calls_made),
                        "rounds": iteration
                    }
                )
                
                return {
                    "success": True,
                    "output": "Conversation completed",  # Not used in streaming mode
                    "messages": messages,
                    "tool_calls": tool_calls_made,
                }
            else:
                # Non-streaming mode - invoke normally
                result = self.agent.invoke({
                    "messages": [HumanMessage(content=user_message)]
                })

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
                        final_output = str(messages[-1].content) if hasattr(messages[-1], 'content') else str(messages[-1])
                
                # Parse and execute tool calls if LLM doesn't support function calling
                if self.tools and not hasattr(self.llm, 'bind_tools'):
                    final_output = self._parse_and_execute_tools_sync(final_output)

                self.status = AgentStatus.ACTIVE
                logger.info(f"Task completed: {self.config.name}")

                return {
                    "success": True,
                    "output": final_output,
                    "messages": messages,
                }

        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"Task execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }

    def terminate(self) -> None:
        """Terminate the agent."""
        logger.info(f"Terminating agent: {self.config.name}")
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

    def _parse_tool_calls(self, llm_output: str) -> Tuple[List[ToolCall], List[ParseError]]:
        """Parse tool calls from LLM output, collecting all errors.
        
        Args:
            llm_output: Raw output from LLM
            
        Returns:
            Tuple of (tool_calls, parse_errors)
        """
        import re
        import json
        
        tool_calls = []
        parse_errors = []
        
        # Pattern 1: JSON block with ```json wrapper
        json_pattern1 = r'```json\s*\n\s*(\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\})\s*\n\s*```'
        
        # Pattern 2: Plain JSON without wrapper (more common)
        json_pattern2 = r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\}'
        
        # Try pattern 1 first (with wrapper)
        matches1 = re.findall(json_pattern1, llm_output, re.DOTALL)
        
        # Try pattern 2 (without wrapper)
        matches2 = re.findall(json_pattern2, llm_output, re.DOTALL)
        
        # Combine matches
        json_blocks = []
        
        # Process pattern 1 matches
        for json_str, tool_name in matches1:
            json_blocks.append(json_str)
        
        # Process pattern 2 matches (only if pattern 1 didn't match)
        if not matches1 and matches2:
            for tool_name in matches2:
                # Extract the full JSON block
                match = re.search(
                    r'\{[^}]*"tool"\s*:\s*"' + re.escape(tool_name) + r'"[^}]*\}',
                    llm_output
                )
                if match:
                    json_blocks.append(match.group(0))
        
        # Parse each JSON block
        for json_str in json_blocks:
            try:
                tool_data = json.loads(json_str)
                
                # Validate required fields
                if "tool" not in tool_data:
                    parse_errors.append(ParseError(
                        error_type="missing_field",
                        message="Missing required field 'tool'",
                        malformed_input=json_str
                    ))
                    continue
                
                tool_name = tool_data["tool"]
                
                # Check if tool exists
                if tool_name not in self.tools_by_name:
                    available_tools = ", ".join(self.tools_by_name.keys())
                    parse_errors.append(ParseError(
                        error_type="unknown_tool",
                        message=f"Tool '{tool_name}' not found. Available tools: {available_tools}",
                        malformed_input=json_str
                    ))
                    continue
                
                # Extract arguments
                args = {k: v for k, v in tool_data.items() if k != "tool"}
                
                tool_calls.append(ToolCall(
                    tool_name=tool_name,
                    arguments=args,
                    raw_json=json_str
                ))
                
            except json.JSONDecodeError as e:
                parse_errors.append(ParseError(
                    error_type="json_decode_error",
                    message=f"Failed to parse JSON: {str(e)}",
                    malformed_input=json_str,
                    details={"line": e.lineno, "column": e.colno, "pos": e.pos}
                ))
            except Exception as e:
                parse_errors.append(ParseError(
                    error_type="unknown_error",
                    message=f"Unexpected error: {str(e)}",
                    malformed_input=json_str
                ))
        
        return tool_calls, parse_errors

    def _handle_parse_errors(
        self,
        parse_errors: List[ParseError],
        state: ConversationState
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
                extra={"agent_id": str(self.config.agent_id), "error_type": error.error_type}
            )
            return None
        
        # Increment retry count
        state.retry_counts[retry_key] = retry_count + 1
        
        # Record error
        state.errors.append(ErrorRecord(
            round_number=state.round_number,
            error_type=error.error_type,
            error_message=error.message,
            malformed_input=error.malformed_input,
            is_recoverable=True,
            retry_count=retry_count + 1
        ))
        
        logger.warning(
            f"[RECOVERY] Parse error detected: {error.error_type}",
            extra={
                "agent_id": str(self.config.agent_id),
                "error_type": error.error_type,
                "retry_count": retry_count + 1,
                "max_retries": self.config.max_parse_retries
            }
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
                    "Check for missing commas between fields"
                ]
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
                    "Example: {\"tool\": \"calculator\", \"expression\": \"1+1\"}"
                ]
            )
        
        elif error.error_type == "unknown_tool":
            available_tools = ", ".join(self.tools_by_name.keys())
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
                    "Refer to the Available Tools section in the system prompt"
                ]
            )
        
        else:
            return ErrorFeedback(
                error_type="Tool Call Error",
                error_message=error.message,
                malformed_input=error.malformed_input,
                expected_format='{"tool": "tool_name", "arg1": "value1"}',
                retry_count=retry_count + 1,
                max_retries=self.config.max_parse_retries,
                suggestions=["Review the tool call format and try again"]
            )

    async def _execute_code_blocks(
        self,
        code_blocks: List,
        state: 'ConversationState',
        stream_callback: Optional[callable] = None
    ) -> List:
        """Execute code blocks extracted from LLM output.

        This is the preferred execution path when LLM outputs code blocks
        (```python or ```bash) instead of JSON tool calls.

        Args:
            code_blocks: List of CodeBlock objects to execute
            state: Current conversation state
            stream_callback: Optional callback for streaming updates

        Returns:
            List of ExecutionResult objects
        """
        from agent_framework.code_block_executor import ExecutionResult

        results = []

        for i, block in enumerate(code_blocks):
            # Send execution indicator to frontend
            if stream_callback:
                stream_callback((
                    f"\n\n🔧 **执行代码块 {i+1}/{len(code_blocks)}**: {block.language}\n文件: {block.filename}\n",
                    "code_execution"
                ))

            logger.info(
                f"[CODE_BLOCK] Executing block {i+1}/{len(code_blocks)}: {block.language}",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "language": block.language,
                    "filename": block.filename,
                    "code_length": len(block.code)
                }
            )

            # Execute the code block
            result = await self.code_executor.execute(
                block,
                timeout=self.config.tool_timeout_seconds
            )
            results.append(result)

            # Send result to frontend
            if stream_callback:
                if result.success:
                    output_preview = result.output[:500] if len(result.output) > 500 else result.output
                    stream_callback((
                        f"✅ **执行成功** ({result.execution_time:.2f}s)\n```\n{output_preview}\n```\n",
                        "code_result"
                    ))
                else:
                    error_preview = (result.error or result.output)[:500]
                    stream_callback((
                        f"❌ **执行失败** (exit code {result.exit_code})\n```\n{error_preview}\n```\n",
                        "code_error"
                    ))

            logger.info(
                f"[CODE_BLOCK] Block {i+1} {'succeeded' if result.success else 'failed'}",
                extra={
                    "agent_id": str(self.config.agent_id),
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "execution_time": result.execution_time
                }
            )

            # Stop on first error (can be made configurable)
            if not result.success:
                break

        return results

    async def _execute_tools_with_recovery(
        self,
        tool_calls: List[ToolCall],
        state: ConversationState,
        stream_callback: Optional[callable] = None
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
        
        for tool_call in tool_calls:
            tool_name = tool_call.tool_name
            tool = self.tools_by_name[tool_name]
            
            # Check retry count for this specific tool
            retry_key = f"tool_{tool_name}"
            retry_count = state.retry_counts.get(retry_key, 0)
            
            try:
                # Send "calling tool" message
                if stream_callback:
                    retry_indicator = f" (重试 {retry_count})" if retry_count > 0 else ""
                    stream_callback((
                        f"\n\n🔧 **调用工具: {tool_name}{retry_indicator}**\n参数: {tool_call.arguments}\n",
                        "tool_call"
                    ))
                
                logger.info(
                    f"[RECOVERY] Executing tool: {tool_name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                        "tool_args": str(tool_call.arguments),
                        "retry_count": retry_count
                    }
                )
                
                # Execute tool with timeout
                result = await asyncio.wait_for(
                    tool.ainvoke(tool_call.arguments),
                    timeout=self.config.tool_timeout_seconds
                )
                
                # Success
                results.append(ToolResult(
                    tool_name=tool_name,
                    status="success",
                    result=result,
                    retry_count=retry_count
                ))
                
                # Reset retry count on success
                state.retry_counts[retry_key] = 0
                
                # Send success message
                if stream_callback:
                    stream_callback((
                        f"✅ **执行结果**: {result}\n",
                        "tool_result"
                    ))
                
                # Record success
                state.tool_calls_made.append(ToolCallRecord(
                    round_number=state.round_number,
                    tool_name=tool_name,
                    arguments=tool_call.arguments,
                    status="success",
                    result=result,
                    retry_number=retry_count
                ))
                
                logger.info(
                    f"[RECOVERY] Tool executed successfully: {tool_name}",
                    extra={"agent_id": str(self.config.agent_id), "tool_name": tool_name}
                )
                
            except asyncio.TimeoutError:
                # Timeout error
                error_msg = f"Tool execution timed out after {self.config.tool_timeout_seconds} seconds"
                
                results.append(ToolResult(
                    tool_name=tool_name,
                    status="error",
                    error=error_msg,
                    error_type="timeout",
                    retry_count=retry_count
                ))
                
                # Increment retry count
                state.retry_counts[retry_key] = retry_count + 1
                
                # Send error message
                if stream_callback:
                    stream_callback((
                        f"⏱️ **超时错误**: {error_msg}\n",
                        "tool_error"
                    ))
                
                # Record error
                state.tool_calls_made.append(ToolCallRecord(
                    round_number=state.round_number,
                    tool_name=tool_name,
                    arguments=tool_call.arguments,
                    status="timeout",
                    error=error_msg,
                    retry_number=retry_count
                ))
                
                logger.warning(
                    f"[RECOVERY] Tool execution timeout: {tool_name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                        "timeout": self.config.tool_timeout_seconds
                    }
                )
                
            except Exception as e:
                # Execution error
                error_msg = str(e)
                
                results.append(ToolResult(
                    tool_name=tool_name,
                    status="error",
                    error=error_msg,
                    error_type="execution_error",
                    retry_count=retry_count
                ))
                
                # Increment retry count
                state.retry_counts[retry_key] = retry_count + 1
                
                # Send error message
                if stream_callback:
                    stream_callback((
                        f"❌ **执行失败**: {error_msg}\n",
                        "tool_error"
                    ))
                
                # Record error
                state.tool_calls_made.append(ToolCallRecord(
                    round_number=state.round_number,
                    tool_name=tool_name,
                    arguments=tool_call.arguments,
                    status="execution_error",
                    error=error_msg,
                    retry_number=retry_count
                ))
                
                logger.error(
                    f"[RECOVERY] Tool execution failed: {tool_name}",
                    extra={
                        "agent_id": str(self.config.agent_id),
                        "tool_name": tool_name,
                        "error": error_msg
                    },
                    exc_info=True
                )
        
        return results

    def _format_tool_results(self, tool_results: List[ToolResult]) -> str:
        """Format tool results for LLM feedback.
        
        Args:
            tool_results: List of tool results
            
        Returns:
            Formatted string for LLM
        """
        if not tool_results:
            return ""
        
        result_text = "\n\n工具执行结果：\n"
        
        for tr in tool_results:
            if tr.status == "success":
                result_text += f"- {tr.tool_name}: {tr.result}\n"
            else:
                result_text += f"- {tr.tool_name}: 错误 - {tr.error}\n"
        
        # Check if we just read skill documentation
        if any(tr.tool_name == 'read_skill' and tr.status == "success" for tr in tool_results):
            result_text += "\n你已经获得了技能文档。如果需要执行技能中的脚本或命令，请使用 code_execution 工具。如果已经有足够信息，可以直接回答用户。"
        else:
            result_text += "\n请根据以上工具执行结果，给出最终回答。如果还需要更多信息或执行其他操作，可以继续调用工具。"
        
        return result_text

    async def execute_task_with_recovery(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        stream_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Execute task with error recovery (new implementation).
        
        Args:
            task_description: Description of the task to execute
            context: Optional context information (e.g., memories)
            stream_callback: Optional callback for streaming tokens
            
        Returns:
            Dict with execution results including conversation state
        """
        import asyncio
        
        # Initialize conversation state
        state = ConversationState(max_rounds=self.config.max_iterations)
        
        # Prepare system prompt and initial messages
        system_prompt = self._create_system_prompt()
        user_message = task_description
        
        # Add context information if provided
        if context:
            context_info = []
            if context.get("agent_memories"):
                context_info.append(f"Relevant memories: {', '.join(context['agent_memories'][:3])}")
            if context.get("company_memories"):
                context_info.append(f"Company knowledge: {', '.join(context['company_memories'][:3])}")
            
            if context_info:
                user_message = f"{task_description}\n\nContext:\n" + "\n".join(context_info)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        logger.info(
            f"[RECOVERY] Starting conversation with error recovery",
            extra={
                "agent_id": str(self.config.agent_id),
                "max_rounds": state.max_rounds
            }
        )
        
        # Main conversation loop
        while state.round_number < state.max_rounds and not state.is_terminated:
            state.round_number += 1
            
            logger.info(
                f"[RECOVERY] Round {state.round_number}/{state.max_rounds}",
                extra={"agent_id": str(self.config.agent_id)}
            )
            
            # Send round indicator to frontend (only for rounds > 1)
            if state.round_number > 1 and stream_callback:
                stream_callback((
                    f"\n\n💭 **第 {state.round_number} 轮对话**\n",
                    "info"
                ))
            
            # 1. Get LLM response
            round_output = ""
            round_thinking = ""
            
            try:
                for chunk in self.llm.stream(messages):
                    if hasattr(chunk, 'content') and chunk.content:
                        content_type = "content"
                        if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                            content_type = chunk.additional_kwargs.get('content_type', 'content')
                        
                        if stream_callback:
                            stream_callback((chunk.content, content_type))
                        
                        if content_type == "thinking":
                            round_thinking += chunk.content
                        else:
                            round_output += chunk.content
            except Exception as e:
                logger.error(f"[RECOVERY] LLM streaming failed: {e}", exc_info=True)
                # Try non-streaming fallback
                try:
                    result = self.llm.invoke(messages)
                    round_output = result.content if hasattr(result, 'content') else str(result)
                except Exception as fallback_error:
                    logger.error(f"[RECOVERY] LLM fallback also failed: {fallback_error}")
                    state.is_terminated = True
                    state.termination_reason = "llm_failure"
                    break
            
            logger.info(
                f"[RECOVERY] Round {state.round_number} output: thinking={len(round_thinking)} chars, content={len(round_output)} chars",
                extra={"agent_id": str(self.config.agent_id)}
            )

            # 2. FIRST: Check for executable code blocks (```python, ```bash)
            # This takes priority over JSON tool calls for cleaner execution
            code_blocks = self.code_executor.get_executable_blocks(round_output)

            if code_blocks:
                logger.info(
                    f"[CODE_BLOCK] Found {len(code_blocks)} executable code blocks",
                    extra={"agent_id": str(self.config.agent_id)}
                )

                # Execute code blocks
                code_results = await self._execute_code_blocks(
                    code_blocks, state, stream_callback
                )

                # Check if any execution succeeded
                any_success = any(r.success for r in code_results)

                if any_success:
                    # Format results as feedback and continue conversation
                    results_feedback = "\n".join([r.to_feedback() for r in code_results])
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=f"代码执行结果:\n{results_feedback}"))
                    continue
                else:
                    # All code blocks failed, let LLM try to fix
                    error_feedback = "\n".join([r.to_feedback() for r in code_results])
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=f"代码执行失败，请修正:\n{error_feedback}"))
                    continue

            # 3. Parse JSON tool calls (fallback if no code blocks)
            tool_calls, parse_errors = self._parse_tool_calls(round_output)
            
            # 4. Handle parse errors
            if parse_errors:
                logger.warning(
                    f"[RECOVERY] Found {len(parse_errors)} parse errors",
                    extra={"agent_id": str(self.config.agent_id)}
                )
                
                # Send retry indicator to frontend
                if stream_callback:
                    stream_callback((
                        f"\n\n🔄 **检测到错误，正在重试** (第 {state.retry_counts.get('parse_error_' + parse_errors[0].error_type, 0) + 1}/{self.config.max_parse_retries} 次)\n",
                        "retry_attempt"
                    ))
                
                feedback = self._handle_parse_errors(parse_errors, state)
                
                if feedback:
                    # Send error feedback to frontend
                    if stream_callback:
                        stream_callback((
                            f"\n\n{feedback.to_prompt()}",
                            "error_feedback"
                        ))
                    
                    # Add to conversation and retry
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=feedback.to_prompt()))
                    continue
                else:
                    # Max retries exceeded
                    logger.error("[RECOVERY] Max parse retries exceeded, terminating")
                    state.is_terminated = True
                    state.termination_reason = "max_parse_retries_exceeded"
                    
                    if stream_callback:
                        stream_callback((
                            "\n\n⛔ 工具调用格式错误次数过多，无法继续。请直接提供答案。\n",
                            "error"
                        ))
                    break
            
            # 5. No tool calls = final answer
            if not tool_calls:
                logger.info(
                    f"[RECOVERY] No tool calls in round {state.round_number}, conversation complete",
                    extra={"agent_id": str(self.config.agent_id)}
                )
                state.is_terminated = True
                state.termination_reason = "final_answer_provided"
                break
            
            # 6. Execute tool calls with recovery
            tool_results = await self._execute_tools_with_recovery(
                tool_calls, state, stream_callback
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
                    stream_callback((
                        f"\n\n🔄 **工具执行失败，正在重试** (第 {retry_count}/{self.config.max_execution_retries} 次)\n",
                        "retry_attempt"
                    ))
                
                feedback = self._handle_execution_failures(tool_results, state)
                
                if feedback:
                    # Send error feedback
                    if stream_callback:
                        stream_callback((
                            f"\n\n{feedback.to_prompt()}",
                            "error_feedback"
                        ))
                    
                    # Add to conversation and retry
                    messages.append(AIMessage(content=round_output))
                    messages.append(HumanMessage(content=feedback.to_prompt()))
                    continue
                else:
                    # Max retries exceeded
                    logger.error("[RECOVERY] Max execution retries exceeded, terminating")
                    state.is_terminated = True
                    state.termination_reason = "max_execution_retries_exceeded"
                    
                    if stream_callback:
                        stream_callback((
                            "\n\n⛔ 工具执行失败次数过多，无法继续。请根据已有信息提供答案。\n",
                            "error"
                        ))
                    break
            
            # 7. Add results to conversation and continue
            if stream_callback:
                stream_callback((
                    f"\n\n---\n\n💭 **根据工具结果生成最终回答...**\n\n",
                    "info"
                ))
            
            messages.append(AIMessage(content=round_output))
            messages.append(HumanMessage(content=self._format_tool_results(tool_results)))
        
        # Handle max rounds reached
        if state.round_number >= state.max_rounds:
            logger.warning(
                f"[RECOVERY] Max rounds reached ({state.max_rounds})",
                extra={"agent_id": str(self.config.agent_id)}
            )
            state.is_terminated = True
            state.termination_reason = "max_rounds_reached"
            
            if stream_callback:
                stream_callback((
                    f"\n\n⚠️ 已达到最大对话轮数 ({state.max_rounds})，对话结束。\n",
                    "warning"
                ))
        
        logger.info(
            f"[RECOVERY] Conversation completed: reason={state.termination_reason}, rounds={state.round_number}, errors={len(state.errors)}",
            extra={
                "agent_id": str(self.config.agent_id),
                "termination_reason": state.termination_reason,
                "rounds": state.round_number,
                "tool_calls": len(state.tool_calls_made),
                "errors": len(state.errors)
            }
        )
        
        return {
            "success": state.termination_reason in ["final_answer_provided"],
            "output": round_output if state.is_terminated else "Incomplete",
            "messages": messages,
            "state": state,
            "error_recovery_stats": {
                "total_errors": len(state.errors),
                "recovered_errors": len([e for e in state.errors if e.is_recoverable]),
                "retry_attempts": sum(state.retry_counts.values())
            }
        }

    def _handle_execution_failures(
        self,
        tool_results: List[ToolResult],
        state: ConversationState
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
                extra={
                    "agent_id": str(self.config.agent_id),
                    "tool_name": failed_result.tool_name
                }
            )
            return None
        
        # Record error
        state.errors.append(ErrorRecord(
            round_number=state.round_number,
            error_type=failed_result.error_type or "execution_error",
            error_message=failed_result.error or "Unknown error",
            tool_name=failed_result.tool_name,
            is_recoverable=True,
            retry_count=retry_count
        ))
        
        # Generate feedback based on error type
        if failed_result.error_type == "timeout":
            return ErrorFeedback(
                error_type="Timeout Error",
                error_message=failed_result.error or "Tool execution timed out",
                malformed_input=None,
                expected_format="",
                retry_count=retry_count,
                max_retries=self.config.max_execution_retries,
                suggestions=[
                    "The operation took too long to complete",
                    "Consider breaking it into smaller steps",
                    "Check if there's an infinite loop",
                    "Try a simpler approach"
                ]
            )
        else:
            return ErrorFeedback(
                error_type="Execution Error",
                error_message=failed_result.error or "Tool execution failed",
                malformed_input=None,
                expected_format="",
                retry_count=retry_count,
                max_retries=self.config.max_execution_retries,
                suggestions=[
                    "Check the error message for details",
                    "Verify the arguments are correct",
                    "Try a different approach",
                    "Consider using an alternative tool"
                ]
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
        import re
        import json
        import asyncio
        
        # Pattern to match tool invocations: ```tool:tool_name\n{json}\n```
        pattern = r'```tool:(\w+)\s*\n(.*?)\n```'
        matches = re.findall(pattern, output, re.DOTALL)
        
        if not matches:
            return output
        
        logger.info(
            f"Found {len(matches)} tool invocations in output",
            extra={"agent_id": str(self.config.agent_id)}
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
                    extra={"agent_id": str(self.config.agent_id), "args": args}
                )
                
                # Execute tool (handle both sync and async)
                if hasattr(tool, '_arun'):
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
                    extra={"agent_id": str(self.config.agent_id)}
                )
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool arguments: {e}")
            except Exception as e:
                logger.error(f"Tool execution failed: {e}", exc_info=True)
        
        return modified_output

    def _create_system_prompt(self) -> str:
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
            base_prompt = f"""You are {self.config.name}, a {self.config.agent_type} agent with the following capabilities: {', '.join(self.config.capabilities)}.

Your role is to help users accomplish tasks using your available tools and capabilities.

When solving problems:
1. Analyze the user's request carefully
2. Use available tools when needed
3. Provide clear and helpful responses
4. If you need more information, ask clarifying questions

Always be professional, accurate, and helpful."""
        
        # Add tools description for LangChain tools
        # Include tools in prompt if:
        # 1. LLM doesn't support bind_tools, OR
        # 2. LLM supports bind_tools but we want tools visible in prompt anyway (for better awareness)
        if self.tools:
            # Include ALL tools in the prompt (including code_execution)
            langchain_tools = self.tools
            
            if langchain_tools:
                tools_prompt = "\n\n## Available Tools\n\n"
                tools_prompt += "You have access to the following tools:\n\n"
                
                for tool in langchain_tools:
                    tools_prompt += f"### {tool.name}\n"
                    tools_prompt += f"{tool.description}\n\n"
                
                # Add note about how to use tools
                if not hasattr(self.llm, 'bind_tools'):
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
                    tools_prompt += '{"tool": "code_execution", "code": "print(\'Hello World\')"}\n'
                    tools_prompt += "```\n\n"
                    tools_prompt += "**DO NOT** just write about using the tool - you MUST use the exact JSON format above!\n\n"
                else:
                    # LLM supports function calling, but may not work properly
                    # Provide both formats
                    tools_prompt += "\n**How to use tools**: \n\n"
                    tools_prompt += "**Method 1 (Preferred)**: Use function calling if supported.\n\n"
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
                    tools_prompt += '{"tool": "code_execution", "code": "import requests; print(requests.get(\'https://api.example.com\').text)"}\n'
                    tools_prompt += "```\n\n"
                
                base_prompt += tools_prompt
        
        # Add Agent Skills documentation if available
        if self.skill_manager:
            skills_prompt = self.skill_manager.format_skills_for_prompt()
            return base_prompt + skills_prompt
        
        return base_prompt
