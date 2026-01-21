"""BaseAgent class with LangChain integration.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.1: Agent Architecture
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional
from uuid import UUID

from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

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


class BaseAgent:
    """Base agent class with LangChain integration.
    
    Each agent is an autonomous entity with:
    - Identity (agent_id, name, owner)
    - Capabilities (skills from Skill Library)
    - Memory access (Agent Memory + Company Memory)
    - Tools (LangChain tools)
    - Execution environment (isolated container)
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
        self.agent: Optional[Runnable] = None
        
        logger.info(
            f"BaseAgent initialized: {config.name}",
            extra={
                "agent_id": str(config.agent_id),
                "agent_type": config.agent_type,
                "capabilities": config.capabilities,
            }
        )
    
    def initialize(self) -> None:
        """Initialize agent with LangChain components."""
        try:
            if not self.llm:
                raise ValueError("LLM not configured for agent")
            
            # Create system prompt for the agent
            system_prompt = self._create_system_prompt()
            
            # Create ReAct agent with LangGraph
            self.agent = create_react_agent(
                model=self.llm,
                tools=self.tools,
                prompt=system_prompt,
            )
            
            self.status = AgentStatus.ACTIVE
            logger.info(f"Agent initialized successfully: {self.config.name}")
            
        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"Agent initialization failed: {e}", exc_info=True)
            raise
    
    def execute_task(self, task_description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a task using the agent.
        
        Args:
            task_description: Description of the task to execute
            context: Optional context information
            
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
            messages = [{"role": "user", "content": task_description}]
            
            # Execute task with LangGraph agent
            result = self.agent.invoke({"messages": messages})
            
            # Extract output from result
            output_messages = result.get("messages", [])
            final_output = ""
            if output_messages:
                last_message = output_messages[-1]
                if hasattr(last_message, "content"):
                    final_output = last_message.content
                else:
                    final_output = str(last_message)
            
            self.status = AgentStatus.ACTIVE
            logger.info(f"Task completed: {self.config.name}")
            
            return {
                "success": True,
                "output": final_output,
                "messages": output_messages,
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
    
    def _create_system_prompt(self) -> str:
        """Create system prompt for the agent.
        
        Returns:
            System prompt string
        """
        prompt = f"""You are {self.config.name}, a {self.config.agent_type} agent with the following capabilities: {', '.join(self.config.capabilities)}.

Your role is to help users accomplish tasks using your available tools and capabilities.

When solving problems:
1. Analyze the user's request carefully
2. Use available tools when needed
3. Provide clear and helpful responses
4. If you need more information, ask clarifying questions

Always be professional, accurate, and helpful."""
        
        return prompt
