"""Agent Framework module for Digital Workforce Platform.

This module provides LangChain-based agent framework including:
- BaseAgent class with LangChain integration
- Agent lifecycle management (create, update, terminate)
- Agent registry and capability matching
- Agent status tracking
- Agent memory access interface
- Agent tool integration
- Agent execution loop
- Agent templates for common use cases

References:
- Requirements 2, 12, 21: Agent Framework, Lifecycle Management, and Templates
- Design Section 4: Agent Framework Design
"""

from agent_framework.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentStatus,
)

from agent_framework.agent_registry import (
    AgentRegistry,
    AgentInfo,
    get_agent_registry,
)

from agent_framework.agent_lifecycle import (
    AgentLifecycleManager,
    LifecyclePhase,
    get_lifecycle_manager,
)

from agent_framework.agent_status import (
    AgentStatusTracker,
    StatusUpdate,
    get_status_tracker,
)

from agent_framework.capability_matcher import (
    CapabilityMatcher,
    CapabilityMatch,
    get_capability_matcher,
)

from agent_framework.agent_memory_interface import (
    AgentMemoryInterface,
    get_agent_memory_interface,
)

from agent_framework.agent_tools import (
    AgentToolkit,
    create_langchain_tools,
    get_agent_toolkit,
)

from agent_framework.agent_executor import (
    AgentExecutor,
    ExecutionContext,
    get_agent_executor,
)

from agent_framework.agent_template import (
    AgentTemplate,
    AgentTemplateManager,
)

from agent_framework.default_templates import (
    get_default_templates,
    initialize_default_templates,
)

__all__ = [
    # Base agent
    'BaseAgent',
    'AgentConfig',
    'AgentStatus',
    
    # Agent registry
    'AgentRegistry',
    'AgentInfo',
    'get_agent_registry',
    
    # Lifecycle management
    'AgentLifecycleManager',
    'LifecyclePhase',
    'get_lifecycle_manager',
    
    # Status tracking
    'AgentStatusTracker',
    'StatusUpdate',
    'get_status_tracker',
    
    # Capability matching
    'CapabilityMatcher',
    'CapabilityMatch',
    'get_capability_matcher',
    
    # Memory interface
    'AgentMemoryInterface',
    'get_agent_memory_interface',
    
    # Tools integration
    'AgentToolkit',
    'create_langchain_tools',
    'get_agent_toolkit',
    
    # Agent executor
    'AgentExecutor',
    'ExecutionContext',
    'get_agent_executor',
    
    # Agent templates
    'AgentTemplate',
    'AgentTemplateManager',
    'get_default_templates',
    'initialize_default_templates',
]
