"""Unified runtime service for executing agents via a shared request contract."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent_framework.base_agent import BaseAgent
from agent_framework.runtime_policy import ExecutionProfile, RuntimePolicy

logger = logging.getLogger(__name__)


@dataclass
class RuntimeAdapterRequest:
    """Adapter-facing runtime request for direct agent execution."""

    agent: BaseAgent
    task_description: str
    context: Optional[Dict[str, Any]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    execution_profile: Optional[ExecutionProfile | str] = None
    runtime_policy: Optional[RuntimePolicy] = None
    stream_callback: Optional[callable] = None
    session_workdir: Optional[Any] = None
    container_id: Optional[str] = None
    code_execution_network_access: Optional[bool] = None
    message_content: Optional[Any] = None


class UnifiedAgentRuntimeService:
    """Centralized execution bridge used by multiple entry-point adapters."""

    def execute(self, request: RuntimeAdapterRequest) -> Dict[str, Any]:
        """Execute an agent task through one shared invocation path."""
        execute_kwargs: Dict[str, Any] = {
            "task_description": request.task_description,
        }
        if request.context is not None:
            execute_kwargs["context"] = request.context
        if request.conversation_history:
            execute_kwargs["conversation_history"] = request.conversation_history
        if request.execution_profile is not None:
            execute_kwargs["execution_profile"] = request.execution_profile
        if request.runtime_policy is not None:
            execute_kwargs["runtime_policy"] = request.runtime_policy
        if request.stream_callback is not None:
            execute_kwargs["stream_callback"] = request.stream_callback
        if request.session_workdir is not None:
            execute_kwargs["session_workdir"] = request.session_workdir
        if request.container_id is not None:
            execute_kwargs["container_id"] = request.container_id
        if request.code_execution_network_access is not None:
            execute_kwargs["code_execution_network_access"] = request.code_execution_network_access
        if request.message_content is not None:
            execute_kwargs["message_content"] = request.message_content

        agent_config = getattr(request.agent, "config", None)
        agent_id = getattr(agent_config, "agent_id", None) or getattr(request.agent, "agent_id", None)
        logger.info(
            "Unified runtime execute",
            extra={
                "agent_id": str(agent_id or "-"),
                "runtime_path": "unified_runtime_service",
                "runtime_profile": str(request.execution_profile or "legacy"),
                "has_stream_callback": bool(request.stream_callback),
                "has_context": bool(request.context),
                "history_count": len(request.conversation_history or []),
            },
        )
        return request.agent.execute_task(**execute_kwargs)


_runtime_service: Optional[UnifiedAgentRuntimeService] = None


def get_unified_agent_runtime_service() -> UnifiedAgentRuntimeService:
    """Get singleton unified runtime service."""
    global _runtime_service
    if _runtime_service is None:
        _runtime_service = UnifiedAgentRuntimeService()
    return _runtime_service
