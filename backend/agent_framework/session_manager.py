"""Session Manager for conversation-level persistent sandboxes.

This module manages session lifecycles for agent code execution, enabling
multiple rounds of code execution to share the same working directory and
environment state within a single conversation.

Features:
- Session-level workdir persistence (files, installed dependencies persist across rounds)
- Automatic session TTL and cleanup
- Optional Docker sandbox integration via SandboxPool
- Fallback cleanup for abnormally closed frontends

References:
- Design: .kiro/specs/code-execution-improvement/design.md
- Requirements: Session persistence for multi-turn code execution
"""

import asyncio
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import UUID, uuid4

from agent_framework.sandbox_policy import allow_host_execution_fallback

logger = logging.getLogger(__name__)

DEFAULT_SESSION_SANDBOX_IMAGE = (
    os.getenv("LINX_SANDBOX_PYTHON_IMAGE", "python:3.11-bookworm").strip()
    or "python:3.11-bookworm"
)
DEFAULT_SANDBOX_TMPFS_SIZE = (
    os.getenv("LINX_SANDBOX_TMPFS_SIZE", "1G").strip() or "1G"
)
DEFAULT_INTERNAL_PIP_CACHE_DIR = "/opt/linx_pip_cache"
DEFAULT_INTERNAL_PYTHON_DEPS_DIR = "/opt/linx_python_deps"
DEFAULT_INTERNAL_DEP_WORKDIR = "/opt/linx_runtime"

SessionEndCallback = Callable[["ConversationSession", str], Optional[Awaitable[None]]]


@dataclass
class ConversationSession:
    """Represents a conversation session with its associated resources.

    A session tracks all resources needed for code execution within a conversation,
    including the working directory and optional sandbox container.
    """

    session_id: str
    agent_id: UUID
    user_id: UUID
    workdir: Path
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    ttl_minutes: int = 30
    use_sandbox: bool = False
    sandbox_id: Optional[str] = None  # Docker container ID if sandbox is enabled
    memory_turns: list[dict[str, str]] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if session has exceeded its TTL."""
        from datetime import timedelta

        return datetime.now() - self.last_activity > timedelta(minutes=self.ttl_minutes)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()

    def remaining_ttl_seconds(self) -> float:
        """Get remaining TTL in seconds."""
        from datetime import timedelta

        elapsed = datetime.now() - self.last_activity
        remaining = timedelta(minutes=self.ttl_minutes) - elapsed
        return max(0, remaining.total_seconds())

    def append_memory_turn(
        self,
        user_message: str,
        agent_response: str,
        agent_name: str = "",
        max_turns: int = 24,
    ) -> None:
        """Append one conversation turn as a memory candidate."""
        user_text = str(user_message or "").strip()
        agent_text = str(agent_response or "").strip()
        if not user_text or not agent_text:
            return

        self.memory_turns.append(
            {
                "user_message": user_text,
                "agent_response": agent_text,
                "agent_name": str(agent_name or "").strip(),
                "timestamp": datetime.now().isoformat(),
            }
        )
        if len(self.memory_turns) > max_turns:
            self.memory_turns = self.memory_turns[-max_turns:]
        self.touch()

    def drain_memory_turns(self) -> list[dict[str, str]]:
        """Drain buffered memory candidates and clear the buffer."""
        turns = list(self.memory_turns)
        self.memory_turns.clear()
        return turns


class SessionManager:
    """Manages conversation sessions for persistent code execution environments.

    The SessionManager provides:
    - Session creation with isolated working directories
    - Session reuse across conversation rounds
    - Automatic cleanup of expired sessions
    - Optional sandbox container management

    Usage:
        session_mgr = get_session_manager()

        # Get or create session for a conversation
        session = await session_mgr.get_or_create_session(
            session_id="abc123",  # None for new session
            agent_id=agent_uuid,
            user_id=user_uuid
        )

        # Use session.workdir for code execution
        # ...

        # End session explicitly (or let TTL cleanup)
        await session_mgr.end_session(session.session_id, user_uuid)
    """

    def __init__(
        self,
        base_workdir: str = "/tmp/agent_sessions",
        default_ttl_minutes: int = 30,
        cleanup_interval_seconds: int = 300,
        max_sessions_per_user: int = 5,
        use_sandbox_by_default: bool = True,  # Enable sandbox by default
    ):
        """Initialize SessionManager.

        Args:
            base_workdir: Base directory for session working directories
            default_ttl_minutes: Default session TTL (inactivity timeout)
            cleanup_interval_seconds: Interval for automatic cleanup task
            max_sessions_per_user: Maximum concurrent sessions per user
            use_sandbox_by_default: Whether to use Docker sandbox by default
        """
        self.base_workdir = Path(base_workdir)
        self.base_workdir.mkdir(parents=True, exist_ok=True)

        self.default_ttl_minutes = default_ttl_minutes
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.max_sessions_per_user = max_sessions_per_user
        self.use_sandbox_by_default = use_sandbox_by_default
        self.allow_host_execution_fallback = allow_host_execution_fallback()

        # Session storage: session_id -> ConversationSession
        self._sessions: Dict[str, ConversationSession] = {}

        # User session index: user_id -> list of session_ids
        self._user_sessions: Dict[str, list] = {}
        self._session_end_callbacks: list[SessionEndCallback] = []

        # Cleanup task handle
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Sandbox pool reference (lazy loaded)
        self._sandbox_pool = None

        # Check Docker availability
        self._docker_available = self._check_docker_availability()

        logger.info(
            f"SessionManager initialized",
            extra={
                "base_workdir": str(self.base_workdir),
                "default_ttl_minutes": default_ttl_minutes,
                "max_sessions_per_user": max_sessions_per_user,
                "use_sandbox_by_default": use_sandbox_by_default,
                "allow_host_execution_fallback": self.allow_host_execution_fallback,
                "docker_available": self._docker_available,
            },
        )

    def register_session_end_callback(self, callback: SessionEndCallback) -> None:
        """Register a callback that runs before a session is finalized."""
        if callback in self._session_end_callbacks:
            return
        self._session_end_callbacks.append(callback)
        logger.debug(
            "Registered session end callback",
            extra={"callback_count": len(self._session_end_callbacks)},
        )

    async def _trigger_session_end_callbacks(
        self, session: ConversationSession, reason: str
    ) -> None:
        """Run all registered session-end callbacks."""
        if not self._session_end_callbacks:
            return

        for callback in list(self._session_end_callbacks):
            try:
                result = callback(session, reason)
                if asyncio.iscoroutine(result):
                    await result
                elif hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.warning(
                    "Session end callback failed",
                    extra={
                        "session_id": session.session_id,
                        "reason": reason,
                        "error": str(e),
                    },
                )

    def _check_docker_availability(self) -> bool:
        """Check if Docker is available for sandbox execution."""
        try:
            import docker

            client = docker.from_env()
            client.ping()
            logger.info("Docker is available for sandbox execution")
            return True
        except Exception as e:
            logger.warning(f"Docker not available: {e}. Code will run in subprocess mode.")
            return False

    async def start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._shutdown = False
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session cleanup task started")

    async def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        self._shutdown = True
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Session cleanup task stopped")

    async def _cleanup_loop(self) -> None:
        """Background loop to clean up expired sessions and Docker resources.

        Session cleanup runs every cycle (default 5 min).
        Docker cleanup runs every 6 cycles (~30 min).
        """
        docker_cleanup_counter = 0
        docker_cleanup_every = 6  # Run Docker cleanup every 6th cycle

        while not self._shutdown:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)

                # Session cleanup (every cycle)
                await self._cleanup_expired_sessions()

                # Docker resource cleanup (every 6th cycle)
                docker_cleanup_counter += 1
                if docker_cleanup_counter >= docker_cleanup_every:
                    docker_cleanup_counter = 0
                    await self._run_docker_cleanup()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)

    async def _run_docker_cleanup(self) -> None:
        """Run Docker resource cleanup (containers, images, build cache)."""
        try:
            from virtualization.container_manager import (
                get_container_manager,
                get_docker_cleanup_manager,
            )

            # Clean terminated containers from in-memory tracking
            container_manager = get_container_manager()
            tracked_cleaned = container_manager.cleanup_terminated_containers()
            if tracked_cleaned > 0:
                logger.info(f"Cleaned {tracked_cleaned} terminated containers from tracking")

            # Run full Docker cleanup
            cleanup_manager = get_docker_cleanup_manager()
            stats = cleanup_manager.run_full_cleanup()
            logger.debug("Docker cleanup cycle completed", extra=stats)

        except ImportError:
            logger.debug("Docker cleanup skipped: virtualization module not available")
        except Exception as e:
            logger.error(f"Error during Docker cleanup: {e}", exc_info=True)

    async def _cleanup_expired_sessions(self) -> int:
        """Clean up all expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        expired_ids = [sid for sid, session in self._sessions.items() if session.is_expired()]

        cleaned = 0
        for session_id in expired_ids:
            try:
                session = self._sessions.get(session_id)
                if session:
                    await self._finalize_session(session, reason="expired")
                    cleaned += 1
                    logger.info(
                        f"Cleaned up expired session: {session_id}",
                        extra={
                            "session_id": session_id,
                            "agent_id": str(session.agent_id),
                            "age_minutes": (datetime.now() - session.created_at).total_seconds()
                            / 60,
                        },
                    )
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {e}", exc_info=True)

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired sessions")

        return cleaned

    async def _finalize_session(self, session: ConversationSession, reason: str) -> None:
        """Finalize one session by running callbacks then cleaning resources."""
        await self._trigger_session_end_callbacks(session, reason)
        await self._cleanup_session_resources(session)
        self._remove_session(session.session_id)

    async def _cleanup_session_resources(self, session: ConversationSession) -> None:
        """Clean up resources associated with a session.

        Args:
            session: Session to clean up
        """
        # Release sandbox container if in use
        if session.sandbox_id:
            try:
                released = await self._release_sandbox(session.sandbox_id)
                if released:
                    logger.debug(
                        f"Released sandbox {session.sandbox_id} for session {session.session_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to release sandbox {session.sandbox_id} "
                        f"for session {session.session_id}"
                    )
            except Exception as e:
                logger.warning(f"Failed to release sandbox {session.sandbox_id}: {e}")

        # Remove working directory
        if session.workdir.exists():
            try:
                shutil.rmtree(session.workdir)
                logger.debug(f"Removed workdir {session.workdir} for session {session.session_id}")
            except Exception as e:
                logger.warning(f"Failed to remove workdir {session.workdir}: {e}")

    def _remove_session(self, session_id: str) -> None:
        """Remove session from internal tracking."""
        session = self._sessions.pop(session_id, None)
        if session:
            user_id_str = str(session.user_id)
            if user_id_str in self._user_sessions:
                self._user_sessions[user_id_str] = [
                    sid for sid in self._user_sessions[user_id_str] if sid != session_id
                ]

    async def get_or_create_session(
        self,
        agent_id: UUID,
        user_id: UUID,
        session_id: Optional[str] = None,
        use_sandbox: Optional[bool] = None,
        ttl_minutes: Optional[int] = None,
    ) -> tuple[ConversationSession, bool]:
        """Get existing session or create new one.

        Args:
            agent_id: Agent ID for the session
            user_id: User ID for the session
            session_id: Optional existing session ID to resume
            use_sandbox: Override default sandbox setting
            ttl_minutes: Override default TTL

        Returns:
            Tuple of (session, is_new_session)
        """
        # Try to get existing session
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]

            # Verify ownership
            if session.user_id != user_id:
                logger.warning(
                    f"Session {session_id} belongs to different user",
                    extra={"session_user": str(session.user_id), "request_user": str(user_id)},
                )
                # Create new session instead
            elif session.agent_id != agent_id:
                logger.warning(
                    f"Session {session_id} belongs to different agent",
                    extra={"session_agent": str(session.agent_id), "request_agent": str(agent_id)},
                )
                # Create new session instead
            elif session.is_expired():
                logger.info(f"Session {session_id} has expired, creating new one")
                await self.end_session(session_id, user_id)
            else:
                # Valid existing session
                session.touch()
                logger.info(
                    f"Resumed session {session_id}",
                    extra={
                        "session_id": session_id,
                        "agent_id": str(agent_id),
                        "remaining_ttl": session.remaining_ttl_seconds(),
                    },
                )
                return session, False

        # Create new session
        return (
            await self._create_session(
                agent_id=agent_id,
                user_id=user_id,
                use_sandbox=use_sandbox if use_sandbox is not None else self.use_sandbox_by_default,
                ttl_minutes=ttl_minutes if ttl_minutes is not None else self.default_ttl_minutes,
            ),
            True,
        )

    async def _create_session(
        self,
        agent_id: UUID,
        user_id: UUID,
        use_sandbox: bool,
        ttl_minutes: int,
    ) -> ConversationSession:
        """Create a new session.

        Args:
            agent_id: Agent ID
            user_id: User ID
            use_sandbox: Whether to use Docker sandbox
            ttl_minutes: Session TTL

        Returns:
            New ConversationSession
        """
        user_id_str = str(user_id)

        # Enforce max sessions per user
        user_session_ids = self._user_sessions.get(user_id_str, [])
        if len(user_session_ids) >= self.max_sessions_per_user:
            # Remove oldest session
            oldest_id = user_session_ids[0]
            logger.info(f"User {user_id_str} at session limit, removing oldest: {oldest_id}")
            await self.end_session(oldest_id, user_id)

        # Generate session ID
        session_id = uuid4().hex[:12]

        # Create working directory
        workdir = self.base_workdir / f"session_{session_id}"
        workdir.mkdir(parents=True, exist_ok=True)

        # Optionally acquire sandbox (only if Docker is available)
        sandbox_id = None
        if not use_sandbox and not self.allow_host_execution_fallback:
            raise RuntimeError(
                "Host execution fallback is disabled by sandbox isolation policy; "
                "session must run in a sandbox."
            )

        if use_sandbox:
            if not self._docker_available:
                message = (
                    "Docker not available for required sandbox session "
                    f"(session_id={session_id})"
                )
                if self.allow_host_execution_fallback:
                    logger.info(
                        f"{message}; falling back to subprocess execution",
                        extra={"session_id": session_id},
                    )
                    use_sandbox = False
                else:
                    logger.error(
                        f"{message}; host fallback is disabled",
                        extra={"session_id": session_id},
                    )
                    raise RuntimeError(message)
            else:
                try:
                    sandbox_id = await self._acquire_sandbox(agent_id, workdir)
                    if sandbox_id:
                        logger.info(
                            f"Acquired sandbox for session {session_id}: {sandbox_id}",
                            extra={"session_id": session_id, "sandbox_id": sandbox_id},
                        )
                    else:
                        message = f"Failed to acquire sandbox for session {session_id}"
                        if self.allow_host_execution_fallback:
                            logger.warning(f"{message}, using subprocess")
                            use_sandbox = False
                        else:
                            logger.error(f"{message}; host fallback is disabled")
                            raise RuntimeError(message)
                except Exception as e:
                    message = f"Failed to acquire sandbox: {e}"
                    if self.allow_host_execution_fallback:
                        logger.warning(f"{message}; using subprocess")
                        use_sandbox = False
                    else:
                        logger.error(f"{message}; host fallback is disabled")
                        raise RuntimeError(message) from e

        # Create session
        session = ConversationSession(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            workdir=workdir,
            ttl_minutes=ttl_minutes,
            use_sandbox=use_sandbox,
            sandbox_id=sandbox_id,
        )

        # Store session
        self._sessions[session_id] = session

        # Track user sessions
        if user_id_str not in self._user_sessions:
            self._user_sessions[user_id_str] = []
        self._user_sessions[user_id_str].append(session_id)

        logger.info(
            f"Created new session: {session_id}",
            extra={
                "session_id": session_id,
                "agent_id": str(agent_id),
                "user_id": user_id_str,
                "workdir": str(workdir),
                "use_sandbox": use_sandbox,
                "sandbox_id": sandbox_id,
                "ttl_minutes": ttl_minutes,
            },
        )

        return session

    async def _acquire_sandbox(self, agent_id: UUID, session_workdir: Path) -> Optional[str]:
        """Acquire a sandbox container for code execution.

        Creates a dedicated Docker container for the session with configuration
        optimized for code execution (writable filesystem, bounded /tmp tmpfs).

        Args:
            agent_id: Agent ID requesting sandbox
            session_workdir: Session working directory to mount in container

        Returns:
            Container ID (the internal ID from ContainerManager) or None
        """
        try:
            from virtualization.container_manager import (
                ContainerConfig,
                get_container_manager,
            )
            from virtualization.sandbox_selector import SandboxType

            container_manager = get_container_manager()

            if not container_manager.docker_available:
                logger.warning("Docker not available for sandbox creation")
                return None

            # Container path for session workdir
            container_workdir = "/workspace"
            session_suffix = session_workdir.name.removeprefix("session_")
            container_name = f"session-{agent_id.hex[:8]}-{session_suffix}"

            # Create a container config optimized for code execution sessions
            config = ContainerConfig(
                agent_id=agent_id,
                name=container_name,
                sandbox_type=container_manager.default_sandbox,
                image=DEFAULT_SESSION_SANDBOX_IMAGE,
                read_only_root=False,  # Need writable filesystem for pip install
                # Keep /tmp fast and bounded for short-lived session workloads.
                tmpfs_mounts={
                    "/tmp": f"size={DEFAULT_SANDBOX_TMPFS_SIZE},mode=1777",
                },
                # Mount session workspace for user-visible files.
                volume_mounts={
                    str(session_workdir): container_workdir,  # Mount workdir at /workspace
                },
                # Keep dependency and pip cache fully inside the container.
                environment={
                    "PIP_CACHE_DIR": DEFAULT_INTERNAL_PIP_CACHE_DIR,
                    "LINX_DEP_WORKDIR": DEFAULT_INTERNAL_DEP_WORKDIR,
                    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "PIP_DEFAULT_TIMEOUT": "120",
                    "PIP_RETRIES": "6",
                    "PIP_TARGET": DEFAULT_INTERNAL_PYTHON_DEPS_DIR,
                    "PYTHONPATH": DEFAULT_INTERNAL_PYTHON_DEPS_DIR,
                    "PYTHONNOUSERSITE": "1",
                    "PIP_USER": "0",
                },
                network_disabled=False,  # Allow network for pip install etc.
                network_mode="bridge",  # Use default bridge network
            )

            # Create and start the container
            container_id = container_manager.create_container(
                agent_id=agent_id,
                config=config,
            )

            started = container_manager.start_container(container_id)
            if not started:
                logger.error(f"Failed to start sandbox container {container_id}")
                container_manager.terminate_container(container_id)
                return None

            logger.info(
                f"Created sandbox container for session",
                extra={
                    "container_id": container_id,
                    "agent_id": str(agent_id),
                },
            )
            return container_id

        except ImportError:
            logger.warning("ContainerManager not available")
            return None
        except Exception as e:
            logger.error(f"Failed to acquire sandbox: {e}", exc_info=True)
            return None

    async def _release_sandbox(self, sandbox_id: str) -> bool:
        """Release a sandbox container.

        Args:
            sandbox_id: Container ID to release

        Returns:
            True if cleanup succeeded, False otherwise
        """
        try:
            from virtualization.container_manager import (
                get_container_manager,
                get_docker_cleanup_manager,
            )

            container_manager = get_container_manager()
            terminated = container_manager.terminate_container(sandbox_id)
            if terminated:
                logger.info(f"Released sandbox container: {sandbox_id}")
                return True

            # Fallback: manager may have lost in-memory tracking, try direct Docker cleanup by label
            cleanup_manager = get_docker_cleanup_manager()
            removed = cleanup_manager.cleanup_container_by_internal_id(sandbox_id)
            if removed:
                logger.info(f"Released sandbox container via fallback cleanup: {sandbox_id}")
                return True

            logger.warning(f"Sandbox container cleanup reported failure: {sandbox_id}")
            return False
        except Exception as e:
            logger.warning(f"Failed to release sandbox {sandbox_id}: {e}")
            return False

    async def end_session(self, session_id: str, user_id: UUID) -> bool:
        """End a session and clean up resources.

        Args:
            session_id: Session ID to end
            user_id: User ID (for authorization)

        Returns:
            True if session was ended, False if not found or unauthorized
        """
        session = self._sessions.get(session_id)

        if not session:
            logger.warning(f"Session {session_id} not found")
            return False

        if session.user_id != user_id:
            logger.warning(
                f"Unauthorized attempt to end session {session_id}",
                extra={"session_user": str(session.user_id), "request_user": str(user_id)},
            )
            return False

        # Clean up resources
        await self._finalize_session(session, reason="user")

        logger.info(
            f"Ended session: {session_id}",
            extra={
                "session_id": session_id,
                "agent_id": str(session.agent_id),
                "lifetime_seconds": (datetime.now() - session.created_at).total_seconds(),
            },
        )

        return True

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID without updating activity.

        Args:
            session_id: Session ID

        Returns:
            Session or None if not found
        """
        return self._sessions.get(session_id)

    def get_user_sessions(self, user_id: UUID) -> list[ConversationSession]:
        """Get all sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of user's sessions
        """
        user_id_str = str(user_id)
        session_ids = self._user_sessions.get(user_id_str, [])
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def get_stats(self) -> dict:
        """Get session manager statistics.

        Returns:
            Dictionary with statistics
        """
        total_sessions = len(self._sessions)
        expired_sessions = sum(1 for s in self._sessions.values() if s.is_expired())
        sandbox_sessions = sum(1 for s in self._sessions.values() if s.use_sandbox)

        return {
            "total_sessions": total_sessions,
            "active_sessions": total_sessions - expired_sessions,
            "expired_sessions": expired_sessions,
            "sandbox_sessions": sandbox_sessions,
            "users_with_sessions": len(self._user_sessions),
            "base_workdir": str(self.base_workdir),
            "default_ttl_minutes": self.default_ttl_minutes,
            "cleanup_interval_seconds": self.cleanup_interval_seconds,
        }

    async def shutdown(self) -> None:
        """Shutdown the session manager and clean up all sessions."""
        logger.info("Shutting down SessionManager...")

        # Stop cleanup task
        await self.stop_cleanup_task()

        # Clean up all sessions
        for session_id in list(self._sessions.keys()):
            session = self._sessions.get(session_id)
            if session:
                try:
                    await self._finalize_session(session, reason="shutdown")
                except Exception as e:
                    logger.error(f"Error cleaning up session {session_id}: {e}")

        self._sessions.clear()
        self._user_sessions.clear()

        # Final Docker cleanup
        await self._run_docker_cleanup()

        logger.info("SessionManager shutdown complete")


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(
    base_workdir: str = "/tmp/agent_sessions",
    default_ttl_minutes: int = 30,
    cleanup_interval_seconds: int = 300,
    max_sessions_per_user: int = 5,
    use_sandbox_by_default: bool = True,  # Enable sandbox by default
) -> SessionManager:
    """Get the global SessionManager instance.

    Args:
        base_workdir: Base directory for session working directories
        default_ttl_minutes: Default session TTL
        cleanup_interval_seconds: Cleanup task interval
        max_sessions_per_user: Max sessions per user
        use_sandbox_by_default: Whether to use sandbox by default

    Returns:
        SessionManager singleton instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(
            base_workdir=base_workdir,
            default_ttl_minutes=default_ttl_minutes,
            cleanup_interval_seconds=cleanup_interval_seconds,
            max_sessions_per_user=max_sessions_per_user,
            use_sandbox_by_default=use_sandbox_by_default,
        )
    return _session_manager


async def initialize_session_manager() -> SessionManager:
    """Initialize and start the session manager.

    Call this during application startup.

    Returns:
        Initialized SessionManager
    """
    manager = get_session_manager()
    await manager.start_cleanup_task()
    return manager


async def shutdown_session_manager() -> None:
    """Shutdown the session manager.

    Call this during application shutdown.
    """
    global _session_manager
    if _session_manager:
        await _session_manager.shutdown()
        _session_manager = None
