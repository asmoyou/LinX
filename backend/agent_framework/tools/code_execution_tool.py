"""Code Execution Tool for agents.

Wraps the virtualization sandbox as a LangChain tool so agents can execute code.

References:
- Design: docs/backend/agent-skill-integration-design.md
- Virtualization: backend/virtualization/code_execution_sandbox.py
"""

import asyncio
import logging
from typing import Any, Optional, Type
from uuid import UUID

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from virtualization.code_execution_sandbox import get_code_execution_sandbox

logger = logging.getLogger(__name__)


class CodeExecutionInput(BaseModel):
    """Input schema for code execution tool."""
    
    code: str = Field(
        description="Python code to execute. Should be complete and self-contained."
    )
    language: str = Field(
        default="python",
        description="Programming language (currently only 'python' is supported)"
    )


class CodeExecutionTool(BaseTool):
    """Tool for executing code in a secure sandbox.
    
    This tool allows agents to execute Python code safely in an isolated environment.
    The code runs with resource limits and security restrictions.
    """
    
    name: str = "code_execution"
    description: str = """Execute Python code in a secure sandbox environment.
    
Use this tool when you need to:
- Run Python code to accomplish a task
- Execute scripts from Agent Skills
- Perform calculations or data processing
- Test code snippets

The code will run in an isolated environment with:
- Resource limits (CPU, memory, time)
- Network disabled
- File system restrictions
- Security validation

Input should be valid Python code as a string.
The tool returns the output (stdout) or any errors.

Example usage:
```python
code = '''
import math
result = math.sqrt(16)
print(f"Square root of 16 is {result}")
'''
```
"""
    
    args_schema: Type[BaseModel] = CodeExecutionInput
    
    # Agent context
    agent_id: UUID
    user_id: UUID
    
    # Pydantic config to allow arbitrary types
    model_config = {"arbitrary_types_allowed": True}

    # Private attribute for sandbox (not validated by Pydantic)
    _sandbox: Optional[Any] = None
    network_access: bool = False
    
    def __init__(self, agent_id: UUID, user_id: UUID, **kwargs):
        """Initialize code execution tool.
        
        Args:
            agent_id: Agent UUID
            user_id: User UUID
            **kwargs: Additional arguments for BaseTool
        """
        super().__init__(agent_id=agent_id, user_id=user_id, **kwargs)
        # Use private attribute to avoid Pydantic validation
        object.__setattr__(self, '_sandbox', get_code_execution_sandbox())
        
        logger.debug(
            f"CodeExecutionTool initialized",
            extra={"agent_id": str(agent_id), "user_id": str(user_id)}
        )
    
    @property
    def sandbox(self):
        """Get sandbox instance."""
        if self._sandbox is None:
            object.__setattr__(self, '_sandbox', get_code_execution_sandbox())
        return self._sandbox

    def set_network_access(self, enabled: bool) -> None:
        """Set whether tool sandbox execution may use network."""
        self.network_access = bool(enabled)
    
    def _run(
        self,
        code: str,
        language: str = "python",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute code synchronously.
        
        Args:
            code: Python code to execute
            language: Programming language (default: python)
            run_manager: Callback manager
        
        Returns:
            Execution output or error message
        """
        # Run async code in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self._execute_code(code, language)
                )
                return future.result()
        else:
            return loop.run_until_complete(self._execute_code(code, language))
    
    async def _arun(
        self,
        code: str,
        language: str = "python",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute code asynchronously.
        
        Args:
            code: Python code to execute
            language: Programming language (default: python)
            run_manager: Callback manager
        
        Returns:
            Execution output or error message
        """
        return await self._execute_code(code, language)
    
    async def _execute_code(self, code: str, language: str) -> str:
        """Execute code in sandbox.
        
        Args:
            code: Code to execute
            language: Programming language
        
        Returns:
            Formatted result string
        """
        logger.info(
            f"Executing code for agent {self.agent_id}",
            extra={
                "agent_id": str(self.agent_id),
                "code_length": len(code),
                "language": language
            }
        )
        
        try:
            # Get user environment variables from SkillEnvManager
            from skill_library.skill_env_manager import get_skill_env_manager
            from agent_framework.tools.file_tools import get_workspace_root

            env_manager = get_skill_env_manager()
            user_env_vars = env_manager.get_env_for_user(self.user_id)
            workspace_root = get_workspace_root()

            logger.debug(
                f"Loaded {len(user_env_vars)} environment variables for user",
                extra={
                    "agent_id": str(self.agent_id),
                    "user_id": str(self.user_id),
                    "env_keys": list(user_env_vars.keys()),
                    "workspace_root": str(workspace_root) if workspace_root else None,
                }
            )

            # Execute in sandbox with user environment variables
            result = await self.sandbox.execute_code(
                code=code,
                language=language,
                context={
                    "agent_id": str(self.agent_id),
                    "user_id": str(self.user_id),
                    "environment": user_env_vars,  # Pass user env vars
                    "network_access": bool(self.network_access),
                    "workspace_root": str(workspace_root) if workspace_root else None,
                }
            )
            
            # Format result
            if result.success:
                output = result.output.strip()
                if output:
                    return f"Code executed successfully:\n{output}"
                else:
                    return "Code executed successfully (no output)"
            else:
                error_msg = result.error.strip()
                return f"Code execution failed:\n{error_msg}"
        
        except Exception as e:
            logger.error(
                f"Code execution error: {e}",
                extra={"agent_id": str(self.agent_id)},
                exc_info=True
            )
            return f"Code execution error: {str(e)}"


def create_code_execution_tool(agent_id: UUID, user_id: UUID) -> CodeExecutionTool:
    """Create a code execution tool for an agent.
    
    Args:
        agent_id: Agent UUID
        user_id: User UUID
    
    Returns:
        CodeExecutionTool instance
    """
    return CodeExecutionTool(agent_id=agent_id, user_id=user_id)
