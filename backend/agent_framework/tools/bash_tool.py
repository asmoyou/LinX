"""Enhanced Bash Tool with PTY and background process support.

This module provides an enhanced bash execution tool inspired by OpenClaw's
bash-first approach with PTY mode for interactive terminals and background
process management.

References:
- Requirements: .kiro/specs/code-execution-improvement/requirements.md
- Design: .kiro/specs/code-execution-improvement/design.md
- OpenClaw: examples-of-reference/openclaw/skills/coding-agent/SKILL.md
"""

import asyncio
import logging
import os
import pty
import re
import select
import shlex
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from langchain_core.tools import Tool

from agent_framework.sandbox_policy import allow_host_execution_fallback
from virtualization.container_manager import ContainerStatus, get_container_manager

logger = logging.getLogger(__name__)

_WORKSPACE_PATH_PATTERN = re.compile(r"(/workspace(?:/[^\s'\"`<>(){},;]+)?)")


@dataclass
class BashToolConfig:
    """Configuration for bash tool execution."""
    
    command: str
    pty: bool = False  # Allocate pseudo-terminal for interactive tools
    workdir: Optional[str] = None  # Working directory
    background: bool = False  # Run in background, returns session ID
    timeout: Optional[int] = None  # Timeout in seconds
    elevated: bool = False  # Run on host (if allowed)
    env: Optional[Dict[str, str]] = None  # Environment variables


@dataclass
class BashResult:
    """Result of bash command execution."""
    
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    session_id: Optional[str] = None  # For background processes
    execution_time: float = 0.0
    error_message: Optional[str] = None


class EnhancedBashTool:
    """Enhanced bash tool with PTY and background support.
    
    Features:
    - PTY mode for interactive terminal applications
    - Background process execution with session management
    - Working directory support
    - Environment variable injection
    - Timeout protection
    """
    
    def __init__(self, process_manager=None, allow_host_fallback: Optional[bool] = None):
        """Initialize enhanced bash tool.
        
        Args:
            process_manager: Optional ProcessManager for background processes
            allow_host_fallback: Optional override for host subprocess fallback policy
        """
        self.process_manager = process_manager
        self.logger = logging.getLogger(__name__)
        self._container_manager = get_container_manager()
        self.session_sandbox_id: Optional[str] = None
        self.network_access: bool = True
        if allow_host_fallback is None:
            self.allow_host_fallback = allow_host_execution_fallback()
        else:
            self.allow_host_fallback = bool(allow_host_fallback)

    def set_execution_context(self, sandbox_id: Optional[str]) -> None:
        """Set session sandbox container context for command execution."""
        normalized = str(sandbox_id).strip() if sandbox_id else ""
        self.session_sandbox_id = normalized or None

    def set_network_access(self, enabled: bool) -> None:
        """Set sandbox network policy flag (informational for bash commands)."""
        self.network_access = bool(enabled)

    def _get_workspace_root(self) -> Optional[Path]:
        """Return current session workspace root when available."""
        try:
            from agent_framework.tools.file_tools import get_workspace_root

            root = get_workspace_root()
            return Path(root) if root else None
        except Exception:
            return None

    def _resolve_workdir(self, workdir: Optional[str], workspace_root: Optional[Path]) -> Optional[str]:
        """Resolve workdir with /workspace semantics."""
        if workspace_root is None:
            return workdir

        if not workdir:
            return str(workspace_root)

        if workdir == "/workspace":
            return str(workspace_root)

        if workdir.startswith("/workspace/"):
            relative = workdir[len("/workspace/") :]
            return str((workspace_root / relative).resolve())

        candidate = Path(workdir).expanduser()
        if candidate.is_absolute():
            return str(candidate)

        return str((workspace_root / candidate).resolve())

    def _rewrite_workspace_paths(self, command: str, workspace_root: Optional[Path]) -> str:
        """Rewrite /workspace paths inside shell command to host workspace paths."""
        if workspace_root is None or "/workspace" not in command:
            return command

        root_str = str(workspace_root)

        def _replace(match: re.Match[str]) -> str:
            token = match.group(1)
            if token == "/workspace":
                return root_str
            relative = token[len("/workspace/") :]
            return str((workspace_root / relative).resolve())

        return _WORKSPACE_PATH_PATTERN.sub(_replace, command)

    def _prepare_config(self, config: BashToolConfig) -> BashToolConfig:
        """Apply workspace-aware defaults and path normalization."""
        workspace_root = self._get_workspace_root()
        resolved_workdir = self._resolve_workdir(config.workdir, workspace_root)
        resolved_command = self._rewrite_workspace_paths(config.command, workspace_root)
        return replace(config, command=resolved_command, workdir=resolved_workdir)

    def _prepare_container_config(self, config: BashToolConfig) -> BashToolConfig:
        """Apply container-aware defaults and path normalization."""
        workspace_root = self._get_workspace_root()

        resolved_workdir = "/workspace"
        if config.workdir:
            candidate = config.workdir.strip()
            if candidate.startswith("/workspace"):
                resolved_workdir = candidate
            else:
                candidate_path = Path(candidate).expanduser()
                if workspace_root and candidate_path.is_absolute():
                    try:
                        rel = candidate_path.resolve().relative_to(workspace_root.resolve())
                        resolved_workdir = f"/workspace/{rel.as_posix()}" if rel.as_posix() != "." else "/workspace"
                    except Exception:
                        resolved_workdir = candidate
                elif candidate_path.is_absolute():
                    resolved_workdir = candidate
                else:
                    resolved_workdir = f"/workspace/{candidate_path.as_posix()}"

        resolved_command = config.command
        if workspace_root:
            host_workspace = str(workspace_root.resolve())
            if host_workspace in resolved_command:
                resolved_command = resolved_command.replace(host_workspace, "/workspace")

        return replace(config, command=resolved_command, workdir=resolved_workdir)

    def _should_execute_in_sandbox(self, config: BashToolConfig) -> bool:
        """Whether command should be executed in current session sandbox."""
        return bool(self.session_sandbox_id) and not config.elevated

    def _ensure_sandbox_running(self) -> Optional[str]:
        """Ensure session sandbox exists and is running."""
        sandbox_id = self.session_sandbox_id
        if not sandbox_id:
            return None

        status = self._container_manager.get_container_status(sandbox_id)
        if status is None:
            self.logger.warning("Session sandbox not found", extra={"sandbox_id": sandbox_id})
            return None

        if status != ContainerStatus.RUNNING:
            started = self._container_manager.start_container(sandbox_id)
            if not started:
                self.logger.error("Failed to start session sandbox", extra={"sandbox_id": sandbox_id})
                return None
        return sandbox_id

    def _execute_in_sandbox(self, config: BashToolConfig) -> BashResult:
        """Execute bash command inside session sandbox container."""
        sandbox_id = self._ensure_sandbox_running()
        if not sandbox_id:
            return BashResult(
                success=False,
                stdout="",
                stderr="Session sandbox is unavailable",
                exit_code=-1,
                error_message="Session sandbox unavailable",
            )

        container_config = self._prepare_container_config(config)
        self.logger.info(
            "Executing bash command (sandbox mode)",
            extra={
                "sandbox_id": sandbox_id,
                "command": container_config.command[:100],
                "workdir": container_config.workdir,
            },
        )
        if container_config.background:
            return BashResult(
                success=False,
                stdout="",
                stderr=(
                    "Background execution in sandbox is not supported yet. "
                    "Run the command in foreground mode."
                ),
                exit_code=-1,
                error_message="Sandbox background execution not supported",
            )

        command = container_config.command
        if container_config.timeout:
            timeout_seconds = max(1, int(container_config.timeout))
            command = (
                f"timeout {timeout_seconds}s /bin/sh -lc "
                f"{shlex.quote(container_config.command)}"
            )

        env = dict(container_config.env or {})
        if container_config.pty:
            # Hint interactive-capable CLIs to preserve colorized output.
            env.setdefault("TERM", "xterm-256color")

        try:
            exit_code, stdout, stderr = self._container_manager.exec_in_container(
                container_id=sandbox_id,
                command=command,
                workdir=container_config.workdir,
                environment=env or None,
            )
            return BashResult(
                success=exit_code == 0,
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=exit_code,
            )
        except Exception as e:
            self.logger.error(
                "Sandbox bash execution failed",
                extra={
                    "sandbox_id": sandbox_id,
                    "error": str(e),
                },
            )
            return BashResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                error_message=str(e),
            )
    
    def execute(self, config: BashToolConfig) -> BashResult:
        """Execute bash command with enhanced features.
        
        Args:
            config: Bash tool configuration
        
        Returns:
            BashResult with execution details
        """
        start_time = time.time()
        
        try:
            if self._should_execute_in_sandbox(config):
                result = self._execute_in_sandbox(config)
            else:
                if not self.allow_host_fallback:
                    message = (
                        "Host bash execution is disabled by sandbox isolation policy. "
                        "No active session sandbox is available."
                    )
                    self.logger.error(
                        message,
                        extra={
                            "command": config.command[:100],
                            "sandbox_id": self.session_sandbox_id,
                        },
                    )
                    result = BashResult(
                        success=False,
                        stdout="",
                        stderr=message,
                        exit_code=-1,
                        error_message="Host execution fallback disabled",
                    )
                    result.execution_time = time.time() - start_time
                    return result
                resolved_config = self._prepare_config(config)
                if resolved_config.background:
                    result = self._execute_background(resolved_config)
                elif resolved_config.pty:
                    result = self._execute_pty(resolved_config)
                else:
                    result = self._execute_normal(resolved_config)
            
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            self.logger.error(
                f"Bash execution failed: {e}",
                extra={"command": config.command, "error": str(e)}
            )
            return BashResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=time.time() - start_time,
                error_message=f"Execution error: {str(e)}"
            )
    
    def _execute_normal(self, config: BashToolConfig) -> BashResult:
        """Execute bash command in normal mode.
        
        Args:
            config: Bash tool configuration
        
        Returns:
            BashResult with output
        """
        self.logger.info(
            f"Executing bash command (normal mode)",
            extra={"command": config.command[:100], "workdir": config.workdir}
        )
        
        # Prepare environment
        env = os.environ.copy()
        if config.env:
            env.update(config.env)
        
        try:
            # Execute command
            process = subprocess.Popen(
                config.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=config.workdir,
                env=env,
                text=True
            )
            
            # Wait with timeout
            try:
                stdout, stderr = process.communicate(timeout=config.timeout)
                exit_code = process.returncode
                
                success = exit_code == 0
                
                self.logger.info(
                    f"Bash command completed",
                    extra={
                        "exit_code": exit_code,
                        "success": success,
                        "stdout_length": len(stdout),
                        "stderr_length": len(stderr)
                    }
                )
                
                return BashResult(
                    success=success,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code
                )
                
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                
                self.logger.warning(
                    f"Bash command timeout",
                    extra={"command": config.command[:100], "timeout": config.timeout}
                )
                
                return BashResult(
                    success=False,
                    stdout=stdout,
                    stderr=stderr + f"\n\nCommand timed out after {config.timeout} seconds",
                    exit_code=-1,
                    error_message=f"Timeout after {config.timeout} seconds"
                )
        
        except Exception as e:
            self.logger.error(f"Normal execution failed: {e}")
            return BashResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                error_message=str(e)
            )
    
    def _execute_pty(self, config: BashToolConfig) -> BashResult:
        """Execute bash command with pseudo-terminal (PTY mode).
        
        PTY mode is essential for interactive terminal applications like
        coding agents (Codex, Claude Code, Pi) that need proper terminal
        output with colors and formatting.
        
        Args:
            config: Bash tool configuration
        
        Returns:
            BashResult with terminal output
        """
        self.logger.info(
            f"Executing bash command (PTY mode)",
            extra={"command": config.command[:100], "workdir": config.workdir}
        )
        
        # Prepare environment
        env = os.environ.copy()
        if config.env:
            env.update(config.env)
        
        # Set working directory
        original_cwd = None
        if config.workdir:
            original_cwd = os.getcwd()
            os.chdir(config.workdir)
        
        try:
            # Create pseudo-terminal
            master_fd, slave_fd = pty.openpty()
            
            # Start process with PTY
            process = subprocess.Popen(
                config.command,
                shell=True,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                preexec_fn=os.setsid  # Create new session
            )
            
            # Close slave fd in parent process
            os.close(slave_fd)
            
            # Read output from master fd
            output = []
            start_time = time.time()
            timeout = config.timeout or 300  # Default 5 minutes
            
            while True:
                # Check if process is still running
                if process.poll() is not None:
                    break
                
                # Check timeout
                if time.time() - start_time > timeout:
                    process.kill()
                    output.append(f"\n\n[Timeout after {timeout} seconds]")
                    break
                
                # Check if data is available
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                
                if ready:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            output.append(data.decode('utf-8', errors='replace'))
                    except OSError:
                        break
            
            # Get exit code
            exit_code = process.wait()
            
            # Close master fd
            os.close(master_fd)
            
            # Combine output
            full_output = ''.join(output)
            success = exit_code == 0
            
            self.logger.info(
                f"PTY command completed",
                extra={
                    "exit_code": exit_code,
                    "success": success,
                    "output_length": len(full_output)
                }
            )
            
            return BashResult(
                success=success,
                stdout=full_output,
                stderr="",  # PTY combines stdout/stderr
                exit_code=exit_code
            )
        
        except Exception as e:
            self.logger.error(f"PTY execution failed: {e}")
            return BashResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                error_message=str(e)
            )
        
        finally:
            # Restore working directory
            if original_cwd:
                os.chdir(original_cwd)
    
    def _execute_background(self, config: BashToolConfig) -> BashResult:
        """Execute bash command in background.
        
        Returns immediately with a session ID that can be used to monitor
        the process with the process tool.
        
        Args:
            config: Bash tool configuration
        
        Returns:
            BashResult with session_id
        """
        if not self.process_manager:
            return BashResult(
                success=False,
                stdout="",
                stderr="Background execution requires ProcessManager",
                exit_code=-1,
                error_message="ProcessManager not available"
            )
        
        self.logger.info(
            f"Starting background process",
            extra={"command": config.command[:100], "workdir": config.workdir}
        )
        
        try:
            # Start background process via ProcessManager
            session_id = self.process_manager.start_process(config)
            
            self.logger.info(
                f"Background process started",
                extra={"session_id": session_id}
            )
            
            return BashResult(
                success=True,
                stdout=f"Background process started with session ID: {session_id}",
                stderr="",
                exit_code=0,
                session_id=session_id
            )
        
        except Exception as e:
            self.logger.error(f"Failed to start background process: {e}")
            return BashResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                error_message=str(e)
            )


def create_bash_tool(agent_id: UUID, user_id: UUID, process_manager=None) -> Tool:
    """Create enhanced bash tool for agent.
    
    Args:
        agent_id: Agent UUID
        user_id: User UUID
        process_manager: Optional ProcessManager for background processes
    
    Returns:
        LangChain Tool for bash execution
    """
    bash_executor = EnhancedBashTool(process_manager=process_manager)

    def _load_user_skill_env() -> Dict[str, str]:
        """Load user-level skill environment variables for shell execution."""
        try:
            from skill_library.skill_env_manager import get_skill_env_manager

            env_manager = get_skill_env_manager()
            env_vars = env_manager.get_env_for_user(user_id)
            normalized = {str(k): str(v) for k, v in (env_vars or {}).items()}
            logger.debug(
                "Loaded skill env vars for bash tool",
                extra={
                    "agent_id": str(agent_id),
                    "user_id": str(user_id),
                    "env_keys": sorted(normalized.keys()),
                    "env_count": len(normalized),
                },
            )
            return normalized
        except Exception as env_error:
            logger.warning(
                "Failed to load skill env vars for bash tool",
                extra={
                    "agent_id": str(agent_id),
                    "user_id": str(user_id),
                    "error": str(env_error),
                },
            )
            return {}
    
    def bash_execute(
        command: str,
        pty: bool = False,
        workdir: Optional[str] = None,
        background: bool = False,
        timeout: Optional[int] = None
    ) -> str:
        """Execute bash command with enhanced features.
        
        Args:
            command: Shell command to execute
            pty: Allocate pseudo-terminal (use for interactive tools like codex, claude, pi)
            workdir: Working directory (agent sees only this folder's context)
            background: Run in background, returns session ID for monitoring
            timeout: Timeout in seconds (default: 300)
        
        Returns:
            Command output or session ID (if background)
        
        Examples:
            # Normal execution
            bash(command="ls -la")
            
            # PTY mode for interactive tools (REQUIRED for coding agents!)
            bash(command="codex exec 'Your prompt'", pty=True, workdir="~/project")
            
            # Background execution for long-running tasks
            bash(command="npm run build", background=True, workdir="~/project")
        """
        config = BashToolConfig(
            command=command,
            pty=pty,
            workdir=workdir,
            background=background,
            timeout=timeout or 300,
            env=_load_user_skill_env() or None,
        )
        
        result = bash_executor.execute(config)
        
        if background and result.session_id:
            return f"✅ Background process started\nSession ID: {result.session_id}\n\nUse process tool to monitor:\n- process(action='poll', session_id='{result.session_id}')\n- process(action='log', session_id='{result.session_id}')"
        
        if result.success:
            return result.stdout
        else:
            error_output = f"❌ Command failed (exit code {result.exit_code})\n\n"
            if result.stderr:
                error_output += f"Error:\n{result.stderr}\n\n"
            if result.stdout:
                error_output += f"Output:\n{result.stdout}"
            return error_output
    
    tool = Tool(
        name="bash",
        description=(
            "Execute bash commands. "
            "Use pty=True for interactive tools (codex, claude, pi). "
            "Use background=True for long-running processes. "
            "Use workdir to set working directory."
        ),
        func=bash_execute
    )

    # Expose runtime hooks so BaseAgent can propagate session/container context.
    object.__setattr__(tool, "set_execution_context", bash_executor.set_execution_context)
    object.__setattr__(tool, "set_network_access", bash_executor.set_network_access)
    return tool
