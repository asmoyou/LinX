"""LangChain tools integration for agents.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4: Agent Framework Design
"""

import logging
from typing import List, Optional

from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)


class AgentToolkit:
    """Toolkit for creating and managing LangChain tools."""
    
    def __init__(self):
        """Initialize agent toolkit."""
        self.tools: List[BaseTool] = []
        logger.info("AgentToolkit initialized")
    
    def add_tool(self, tool: BaseTool) -> None:
        """Add a tool to the toolkit.
        
        Args:
            tool: LangChain tool to add
        """
        self.tools.append(tool)
        logger.info(f"Tool added: {tool.name}")
    
    def get_tools(self) -> List[BaseTool]:
        """Get all tools in the toolkit.
        
        Returns:
            List of LangChain tools
        """
        return self.tools
    
    def get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool or None if not found
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


def create_langchain_tools() -> List[BaseTool]:
    """Create default LangChain tools for agents.
    
    Returns:
        List of LangChain tools
    """
    tools = []
    
    # Example tool: Calculator
    calculator_tool = Tool(
        name="Calculator",
        func=lambda x: eval(x),  # Simple eval for demo (use safe eval in production)
        description="Useful for mathematical calculations. Input should be a mathematical expression.",
    )
    tools.append(calculator_tool)
    
    # Example tool: String operations
    string_tool = Tool(
        name="StringLength",
        func=lambda x: len(str(x)),
        description="Returns the length of a string. Input should be a string.",
    )
    tools.append(string_tool)
    
    logger.info(f"Created {len(tools)} default tools")
    return tools


# Singleton instance
_agent_toolkit: Optional[AgentToolkit] = None


def get_agent_toolkit() -> AgentToolkit:
    """Get or create the agent toolkit singleton.
    
    Returns:
        AgentToolkit instance
    """
    global _agent_toolkit
    if _agent_toolkit is None:
        _agent_toolkit = AgentToolkit()
        # Add default tools
        for tool in create_langchain_tools():
            _agent_toolkit.add_tool(tool)
    return _agent_toolkit
