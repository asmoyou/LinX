"""Graceful shutdown for all services.

References:
- All requirements
- Design Section 10: Scalability and Performance
"""

import asyncio
import logging
import signal
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class ShutdownPhase(Enum):
    """Shutdown phases."""

    STOP_ACCEPTING_REQUESTS = "stop_accepting_requests"
    DRAIN_CONNECTIONS = "drain_connections"
    FINISH_TASKS = "finish_tasks"
    CLEANUP_RESOURCES = "cleanup_resources"
    SHUTDOWN_COMPLETE = "shutdown_complete"


@dataclass
class ShutdownHook:
    """Shutdown hook definition."""

    name: str
    phase: ShutdownPhase
    callback: Callable
    timeout_seconds: int = 30


class GracefulShutdownManager:
    """Graceful shutdown manager.

    Manages graceful shutdown of services:
    - Stop accepting new requests
    - Drain existing connections
    - Finish in-progress tasks
    - Clean up resources
    - Shutdown services
    """

    def __init__(self, shutdown_timeout: int = 60):
        """Initialize graceful shutdown manager.

        Args:
            shutdown_timeout: Maximum time to wait for shutdown (seconds)
        """
        self.shutdown_timeout = shutdown_timeout
        self.hooks: List[ShutdownHook] = []
        self.is_shutting_down = False
        self.shutdown_started_at: Optional[datetime] = None

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info("GracefulShutdownManager initialized")

    def register_hook(
        self,
        name: str,
        phase: ShutdownPhase,
        callback: Callable,
        timeout_seconds: int = 30,
    ):
        """Register shutdown hook.

        Args:
            name: Hook name
            phase: Shutdown phase
            callback: Callback function
            timeout_seconds: Timeout for this hook
        """
        hook = ShutdownHook(
            name=name,
            phase=phase,
            callback=callback,
            timeout_seconds=timeout_seconds,
        )

        self.hooks.append(hook)
        logger.info(f"Registered shutdown hook: {name} (phase: {phase.value})")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        signal_name = signal.Signals(signum).name
        logger.warning(f"Received signal: {signal_name}")

        # Start graceful shutdown
        asyncio.create_task(self.shutdown())

    async def shutdown(self):
        """Execute graceful shutdown."""
        if self.is_shutting_down:
            logger.warning("Shutdown already in progress")
            return

        self.is_shutting_down = True
        self.shutdown_started_at = datetime.now()

        logger.warning("Starting graceful shutdown")

        # Execute hooks by phase
        phases = [
            ShutdownPhase.STOP_ACCEPTING_REQUESTS,
            ShutdownPhase.DRAIN_CONNECTIONS,
            ShutdownPhase.FINISH_TASKS,
            ShutdownPhase.CLEANUP_RESOURCES,
        ]

        for phase in phases:
            await self._execute_phase(phase)

        duration = (datetime.now() - self.shutdown_started_at).total_seconds()
        logger.warning(f"Graceful shutdown completed in {duration:.2f}s")

    async def _execute_phase(self, phase: ShutdownPhase):
        """Execute shutdown phase.

        Args:
            phase: Shutdown phase
        """
        phase_hooks = [h for h in self.hooks if h.phase == phase]

        if not phase_hooks:
            logger.info(f"No hooks for phase: {phase.value}")
            return

        logger.info(f"Executing shutdown phase: {phase.value}")

        for hook in phase_hooks:
            try:
                logger.info(f"Executing hook: {hook.name}")

                # Execute hook with timeout
                if asyncio.iscoroutinefunction(hook.callback):
                    await asyncio.wait_for(
                        hook.callback(),
                        timeout=hook.timeout_seconds,
                    )
                else:
                    hook.callback()

                logger.info(f"Hook completed: {hook.name}")

            except asyncio.TimeoutError:
                logger.error(f"Hook timed out: {hook.name}")
            except Exception as e:
                logger.error(f"Hook failed: {hook.name} - {e}")

    def is_shutdown_in_progress(self) -> bool:
        """Check if shutdown is in progress.

        Returns:
            True if shutting down
        """
        return self.is_shutting_down


# Example usage hooks


async def stop_accepting_requests():
    """Stop accepting new requests."""
    logger.info("Stopping acceptance of new requests")
    # Set flag to reject new requests
    # In FastAPI, this would be done via middleware


async def drain_connections():
    """Drain existing connections."""
    logger.info("Draining existing connections")
    # Wait for active connections to complete
    await asyncio.sleep(5)  # Mock wait


async def finish_tasks():
    """Finish in-progress tasks."""
    logger.info("Finishing in-progress tasks")
    # Wait for tasks to complete
    await asyncio.sleep(10)  # Mock wait


async def cleanup_resources():
    """Clean up resources."""
    logger.info("Cleaning up resources")
    # Close database connections
    # Close Redis connections
    # Close file handles
    await asyncio.sleep(2)  # Mock cleanup


def create_default_shutdown_manager() -> GracefulShutdownManager:
    """Create shutdown manager with default hooks.

    Returns:
        Configured shutdown manager
    """
    manager = GracefulShutdownManager(shutdown_timeout=60)

    # Register default hooks
    manager.register_hook(
        name="stop_accepting_requests",
        phase=ShutdownPhase.STOP_ACCEPTING_REQUESTS,
        callback=stop_accepting_requests,
        timeout_seconds=5,
    )

    manager.register_hook(
        name="drain_connections",
        phase=ShutdownPhase.DRAIN_CONNECTIONS,
        callback=drain_connections,
        timeout_seconds=15,
    )

    manager.register_hook(
        name="finish_tasks",
        phase=ShutdownPhase.FINISH_TASKS,
        callback=finish_tasks,
        timeout_seconds=30,
    )

    manager.register_hook(
        name="cleanup_resources",
        phase=ShutdownPhase.CLEANUP_RESOURCES,
        callback=cleanup_resources,
        timeout_seconds=10,
    )

    return manager
