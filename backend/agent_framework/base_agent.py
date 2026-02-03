"""BaseAgent class with LangGraph 1.0 integration.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.1: Agent Architecture
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import MessagesState, StateGraph, START, END

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent status enumeration."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    TERMINATED = "terminated"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Agent configuration."""

    agent_id: UUID
    name: str
    agent_type: str
    owner_user_id: UUID
    capabilities: List[str]  # List of skill names
    llm_model: str = "ollama"
    temperature: float = 0.7
    max_iterations: int = 10
    system_prompt: Optional[str] = None  # Custom system prompt


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
                            
                            tool_results_text += "\n请根据以上工具执行结果，给出最终回答。不要再调用工具，直接回答用户。"
                            
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
            # Filter out code_execution tool from the list (it's always available)
            langchain_tools = [t for t in self.tools if t.name != "code_execution"]
            
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
                
                base_prompt += tools_prompt
        
        # Add Agent Skills documentation if available
        if self.skill_manager:
            skills_prompt = self.skill_manager.format_skills_for_prompt()
            return base_prompt + skills_prompt
        
        return base_prompt
