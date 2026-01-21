"""Agent execution loop and context management.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.3: Agent Lifecycle
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
from uuid import UUID

from agent_framework.base_agent import BaseAgent
from agent_framework.agent_memory_interface import AgentMemoryInterface, get_agent_memory_interface

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for agent execution."""
    
    agent_id: UUID
    user_id: UUID
    task_id: Optional[UUID] = None
    task_description: str = ""
    additional_context: Optional[Dict[str, Any]] = None


class AgentExecutor:
    """Execute agents with proper context and memory access."""
    
    def __init__(self, memory_interface: Optional[AgentMemoryInterface] = None):
        """Initialize agent executor.
        
        Args:
            memory_interface: AgentMemoryInterface instance
        """
        self.memory_interface = memory_interface or get_agent_memory_interface()
        logger.info("AgentExecutor initialized")
    
    def execute(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute agent with given context.
        
        Args:
            agent: BaseAgent instance
            context: ExecutionContext with task details
            
        Returns:
            Dict with execution results
        """
        logger.info(
            f"Executing agent: {agent.config.name}",
            extra={"agent_id": str(context.agent_id), "task_id": str(context.task_id)}
        )
        
        try:
            # Retrieve relevant memories
            agent_memories = self.memory_interface.retrieve_agent_memory(
                agent_id=context.agent_id,
                query=context.task_description,
                top_k=3,
            )
            
            company_memories = self.memory_interface.retrieve_company_memory(
                user_id=context.user_id,
                query=context.task_description,
                top_k=3,
            )
            
            # Prepare execution context
            exec_context = {
                "agent_memories": [m.content for m in agent_memories],
                "company_memories": [m.content for m in company_memories],
            }
            
            if context.additional_context:
                exec_context.update(context.additional_context)
            
            # Execute task
            result = agent.execute_task(
                task_description=context.task_description,
                context=exec_context,
            )
            
            # Store result in memory if successful
            if result.get("success"):
                self.memory_interface.store_agent_memory(
                    agent_id=context.agent_id,
                    content=f"Task: {context.task_description}\nResult: {result.get('output')}",
                    metadata={"task_id": str(context.task_id) if context.task_id else None},
                )
            
            logger.info(f"Agent execution completed: {agent.config.name}")
            return result
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }


# Singleton instance
_agent_executor: Optional[AgentExecutor] = None


def get_agent_executor() -> AgentExecutor:
    """Get or create the agent executor singleton.
    
    Returns:
        AgentExecutor instance
    """
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = AgentExecutor()
    return _agent_executor
