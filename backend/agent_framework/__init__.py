"""Lazy exports for the agent framework package."""

from importlib import import_module

_EXPORTS = {
    "BaseAgent": ("agent_framework.base_agent", "BaseAgent"),
    "AgentConfig": ("agent_framework.base_agent", "AgentConfig"),
    "AgentStatus": ("agent_framework.base_agent", "AgentStatus"),
    "AgentRegistry": ("agent_framework.agent_registry", "AgentRegistry"),
    "AgentInfo": ("agent_framework.agent_registry", "AgentInfo"),
    "get_agent_registry": ("agent_framework.agent_registry", "get_agent_registry"),
    "AgentLifecycleManager": (
        "agent_framework.agent_lifecycle",
        "AgentLifecycleManager",
    ),
    "LifecyclePhase": ("agent_framework.agent_lifecycle", "LifecyclePhase"),
    "get_lifecycle_manager": ("agent_framework.agent_lifecycle", "get_lifecycle_manager"),
    "AgentStatusTracker": ("agent_framework.agent_status", "AgentStatusTracker"),
    "StatusUpdate": ("agent_framework.agent_status", "StatusUpdate"),
    "get_status_tracker": ("agent_framework.agent_status", "get_status_tracker"),
    "CapabilityMatcher": ("agent_framework.capability_matcher", "CapabilityMatcher"),
    "CapabilityMatch": ("agent_framework.capability_matcher", "CapabilityMatch"),
    "get_capability_matcher": (
        "agent_framework.capability_matcher",
        "get_capability_matcher",
    ),
    "RuntimeContextService": (
        "agent_framework.runtime_context_service",
        "RuntimeContextService",
    ),
    "get_runtime_context_service": (
        "agent_framework.runtime_context_service",
        "get_runtime_context_service",
    ),
    "AgentToolkit": ("agent_framework.agent_tools", "AgentToolkit"),
    "create_langchain_tools": ("agent_framework.agent_tools", "create_langchain_tools"),
    "get_agent_toolkit": ("agent_framework.agent_tools", "get_agent_toolkit"),
    "AgentExecutor": ("agent_framework.agent_executor", "AgentExecutor"),
    "ExecutionContext": ("agent_framework.agent_executor", "ExecutionContext"),
    "get_agent_executor": ("agent_framework.agent_executor", "get_agent_executor"),
    "AgentTemplate": ("agent_framework.agent_template", "AgentTemplate"),
    "AgentTemplateManager": ("agent_framework.agent_template", "AgentTemplateManager"),
    "get_default_templates": (
        "agent_framework.default_templates",
        "get_default_templates",
    ),
    "initialize_default_templates": (
        "agent_framework.default_templates",
        "initialize_default_templates",
    ),
    "InterAgentCommunicator": (
        "agent_framework.inter_agent_communication",
        "InterAgentCommunicator",
    ),
    "MessageResponse": (
        "agent_framework.inter_agent_communication",
        "MessageResponse",
    ),
    "get_communicator": (
        "agent_framework.inter_agent_communication",
        "get_communicator",
    ),
    "ExecutionProfile": ("agent_framework.runtime_policy", "ExecutionProfile"),
    "FileDeliveryGuardMode": (
        "agent_framework.runtime_policy",
        "FileDeliveryGuardMode",
    ),
    "LoopMode": ("agent_framework.runtime_policy", "LoopMode"),
    "RuntimePolicy": ("agent_framework.runtime_policy", "RuntimePolicy"),
    "RuntimeExecutionRequest": (
        "agent_framework.runtime_policy",
        "RuntimeExecutionRequest",
    ),
    "RuntimePolicyRegistry": (
        "agent_framework.runtime_policy",
        "RuntimePolicyRegistry",
    ),
    "get_runtime_policy_registry": (
        "agent_framework.runtime_policy",
        "get_runtime_policy_registry",
    ),
    "is_agent_test_chat_unified_runtime_enabled": (
        "agent_framework.runtime_policy",
        "is_agent_test_chat_unified_runtime_enabled",
    ),
    "is_execution_task_unified_runtime_enabled": (
        "agent_framework.runtime_policy",
        "is_execution_task_unified_runtime_enabled",
    ),
    "RuntimeAdapterRequest": (
        "agent_framework.runtime_service",
        "RuntimeAdapterRequest",
    ),
    "UnifiedAgentRuntimeService": (
        "agent_framework.runtime_service",
        "UnifiedAgentRuntimeService",
    ),
    "get_unified_agent_runtime_service": (
        "agent_framework.runtime_service",
        "get_unified_agent_runtime_service",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'agent_framework' has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
