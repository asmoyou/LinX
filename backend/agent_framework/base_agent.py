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

from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLLM

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
        llm: Optional[BaseLLM] = None,
        tools: Optional[List] = None,
    ):
        """Initialize base agent.
        
        Args:
            config: Agent configuration
            llm: LangChain LLM instance
            tools: List of LangChain tools
        """
        self.config = config
        self.llm = llm
        self.tools = tools or []
        self.status = AgentStatus.INITIALIZING
        self.agent_executor: Optional[AgentExecutor] = None
        
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
            
            # Create ReAct agent with LangChain
            prompt = self._create_agent_prompt()
            agent = create_react_agent(
                llm=self.llm,
                tools=self.tools,
                prompt=prompt,
            )
            
            # Create agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                max_iterations=self.config.max_iterations,
                verbose=True,
                handle_parsing_errors=True,
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
        if not self.agent_executor:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        if self.status != AgentStatus.ACTIVE:
            raise RuntimeError(f"Agent not active. Current status: {self.status.value}")
        
        try:
            self.status = AgentStatus.BUSY
            logger.info(f"Agent executing task: {self.config.name}")
            
            # Prepare input
            input_data = {
                "input": task_description,
                "agent_scratchpad": "",
            }
            
            if context:
                input_data.update(context)
            
            # Execute task
            result = self.agent_executor.invoke(input_data)
            
            self.status = AgentStatus.ACTIVE
            logger.info(f"Task completed: {self.config.name}")
            
            return {
                "success": True,
                "output": result.get("output", ""),
                "intermediate_steps": result.get("intermediate_steps", []),
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
        self.agent_executor = None
    
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
    
    def _create_agent_prompt(self) -> PromptTemplate:
        """Create agent prompt template.
        
        Returns:
            PromptTemplate for the agent
        """
        template = """You are {agent_name}, a {agent_type} agent with the following capabilities: {capabilities}.

You have access to the following tools:
{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought: {agent_scratchpad}"""
        
        return PromptTemplate(
            template=template,
            input_variables=["input", "agent_scratchpad"],
            partial_variables={
                "agent_name": self.config.name,
                "agent_type": self.config.agent_type,
                "capabilities": ", ".join(self.config.capabilities),
            },
        )
