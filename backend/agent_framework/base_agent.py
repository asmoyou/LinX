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
            for skill_info in skills:
                if skill_info.skill_type == "langchain_tool":
                    tool = await self.skill_manager.load_langchain_tool(skill_info)
                    if tool:
                        self.tools.append(tool)
                elif skill_info.skill_type == "agent_skill":
                    # Agent skills are loaded as documentation, not tools
                    await self.skill_manager.load_agent_skill_doc(skill_info)
            
            # Add code execution tool (for agent to run generated code)
            from agent_framework.tools.code_execution_tool import create_code_execution_tool
            code_exec_tool = create_code_execution_tool(
                agent_id=self.config.agent_id,
                user_id=self.config.owner_user_id
            )
            self.tools.append(code_exec_tool)
            
            logger.info(
                f"Loaded {len(self.tools)} tools for agent {self.config.name}",
                extra={"agent_id": str(self.config.agent_id), "tool_count": len(self.tools)}
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
                # Stream mode - use LLM's native streaming
                # Build messages manually to get token-by-token streaming
                system_prompt = self._create_system_prompt()
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message)
                ]
                
                # Try streaming from LLM
                final_output = ""
                chunk_count = 0
                stream_failed = False
                
                try:
                    for chunk in self.llm.stream(messages):
                        if hasattr(chunk, 'content') and chunk.content:
                            stream_callback(chunk.content)
                            final_output += chunk.content
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
                            final_output = result.content
                        else:
                            final_output = str(result)
                        
                        # Send the complete response as one chunk
                        if final_output:
                            stream_callback(final_output)
                        else:
                            raise ValueError("LLM returned empty content")
                    except Exception as invoke_error:
                        logger.error(f"Non-streaming fallback also failed: {invoke_error}")
                        raise
                
                self.status = AgentStatus.ACTIVE
                logger.info(f"Task completed: {self.config.name}")
                
                return {
                    "success": True,
                    "output": final_output,
                    "messages": [HumanMessage(content=user_message), AIMessage(content=final_output)],
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
                    final_output = await self._parse_and_execute_tools(final_output)

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

    async def _parse_and_execute_tools(self, output: str) -> str:
        """Parse tool calls from LLM output and execute them.
        
        For LLMs that don't support function calling, we parse tool invocations
        from the text output and execute them manually.
        
        Args:
            output: LLM output text
        
        Returns:
            Modified output with tool results
        """
        import re
        import json
        
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
                    result = await tool._arun(**args)
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
        
        # Add tools description if LLM doesn't support function calling
        if self.tools and not hasattr(self.llm, 'bind_tools'):
            tools_prompt = "\n\n## Available Tools\n\n"
            tools_prompt += "You have access to the following tools. To use a tool, you MUST write the exact tool invocation in your response:\n\n"
            
            for tool in self.tools:
                tools_prompt += f"### {tool.name}\n"
                tools_prompt += f"{tool.description}\n\n"
                
                # Add usage example for code_execution tool
                if tool.name == "code_execution":
                    tools_prompt += """**IMPORTANT**: To execute code, you MUST use this exact format:

```tool:code_execution
{
  "code": "your python code here",
  "language": "python"
}
```

Example:
```tool:code_execution
{
  "code": "import os\\napi_key = os.environ.get('WEATHER_API_KEY')\\nprint(f'API Key: {api_key}')",
  "language": "python"
}
```

The code will be executed in a secure sandbox with access to environment variables.

"""
            
            base_prompt += tools_prompt
        
        # Add Agent Skills documentation if available
        if self.skill_manager:
            skills_prompt = self.skill_manager.format_skills_for_prompt()
            return base_prompt + skills_prompt
        
        return base_prompt
