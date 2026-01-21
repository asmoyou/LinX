"""Sandbox Pool Management for performance optimization.

This module implements a pool of pre-warmed sandboxes for fast agent execution.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.8: Performance Optimization
"""

import asyncio
import logging
from typing import Dict, Optional, Set
from uuid import UUID

from virtualization.container_manager import ContainerManager, ContainerConfig, ContainerStatus
from virtualization.sandbox_selector import SandboxType

logger = logging.getLogger(__name__)


class SandboxPool:
    """Pre-warmed sandbox pool for fast allocation."""
    
    def __init__(self, pool_size: int = 10, container_manager: Optional[ContainerManager] = None):
        """Initialize the sandbox pool.
        
        Args:
            pool_size: Number of pre-warmed sandboxes to maintain
            container_manager: Container manager instance (creates new if None)
        """
        self.pool_size = pool_size
        self.container_manager = container_manager or ContainerManager()
        self.available_sandboxes: asyncio.Queue = asyncio.Queue()
        self.active_sandboxes: Dict[str, UUID] = {}  # container_id -> agent_id
        self.warming_sandboxes: Set[str] = set()
        self.logger = logging.getLogger(__name__)
        self._initialized = False
    
    async def initialize_pool(self) -> None:
        """Pre-create sandboxes for fast allocation."""
        if self._initialized:
            self.logger.warning("Sandbox pool already initialized")
            return
        
        self.logger.info(
            "Initializing sandbox pool",
            extra={"pool_size": self.pool_size},
        )
        
        tasks = []
        for i in range(self.pool_size):
            task = asyncio.create_task(self._create_and_warm_sandbox(i))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        
        self.logger.info(
            "Sandbox pool initialized",
            extra={
                "requested": self.pool_size,
                "created": success_count,
                "failed": self.pool_size - success_count,
            },
        )
        
        self._initialized = True
    
    async def _create_and_warm_sandbox(self, index: int) -> str:
        """Create and warm up a sandbox.
        
        Args:
            index: Sandbox index for logging
        
        Returns:
            Container ID
        """
        try:
            # Create a temporary agent ID for pool sandbox
            temp_agent_id = UUID(int=index)
            
            config = ContainerConfig(
                agent_id=temp_agent_id,
                name=f"pool-sandbox-{index}",
                sandbox_type=self.container_manager.default_sandbox,
            )
            
            container_id = self.container_manager.create_container(
                agent_id=temp_agent_id,
                config=config,
            )
            
            self.warming_sandboxes.add(container_id)
            
            # Start the container
            success = self.container_manager.start_container(container_id)
            
            if success:
                await self.available_sandboxes.put(container_id)
                self.warming_sandboxes.discard(container_id)
                
                self.logger.debug(
                    "Sandbox warmed and added to pool",
                    extra={
                        "container_id": container_id,
                        "index": index,
                    },
                )
                
                return container_id
            else:
                raise RuntimeError(f"Failed to start sandbox {container_id}")
                
        except Exception as e:
            self.logger.error(
                "Failed to create sandbox for pool",
                extra={
                    "index": index,
                    "error": str(e),
                },
            )
            raise
    
    async def acquire_sandbox(self, agent_id: UUID, timeout: float = 5.0) -> Optional[str]:
        """Get sandbox from pool or create new one.
        
        Args:
            agent_id: Agent ID requesting the sandbox
            timeout: Timeout in seconds to wait for available sandbox
        
        Returns:
            Container ID or None if acquisition failed
        """
        try:
            # Try to get from pool with timeout
            container_id = await asyncio.wait_for(
                self.available_sandboxes.get(),
                timeout=timeout,
            )
            
            # Mark as active
            self.active_sandboxes[container_id] = agent_id
            
            self.logger.info(
                "Sandbox acquired from pool",
                extra={
                    "container_id": container_id,
                    "agent_id": str(agent_id),
                    "pool_size": self.available_sandboxes.qsize(),
                },
            )
            
            return container_id
            
        except asyncio.TimeoutError:
            # Pool exhausted, create new sandbox
            self.logger.warning(
                "Sandbox pool exhausted, creating new sandbox",
                extra={
                    "agent_id": str(agent_id),
                    "pool_size": self.pool_size,
                },
            )
            
            try:
                config = ContainerConfig(
                    agent_id=agent_id,
                    sandbox_type=self.container_manager.default_sandbox,
                )
                
                container_id = self.container_manager.create_container(
                    agent_id=agent_id,
                    config=config,
                )
                
                self.container_manager.start_container(container_id)
                self.active_sandboxes[container_id] = agent_id
                
                return container_id
                
            except Exception as e:
                self.logger.error(
                    "Failed to create new sandbox",
                    extra={
                        "agent_id": str(agent_id),
                        "error": str(e),
                    },
                )
                return None
    
    async def release_sandbox(self, container_id: str) -> bool:
        """Return sandbox to pool or destroy if pool full.
        
        Args:
            container_id: Container ID to release
        
        Returns:
            True if released successfully, False otherwise
        """
        if container_id not in self.active_sandboxes:
            self.logger.warning(
                "Attempted to release unknown sandbox",
                extra={"container_id": container_id},
            )
            return False
        
        agent_id = self.active_sandboxes.pop(container_id)
        
        try:
            # Check if pool has space
            if self.available_sandboxes.qsize() < self.pool_size:
                # Reset sandbox and return to pool
                await self._reset_sandbox(container_id)
                await self.available_sandboxes.put(container_id)
                
                self.logger.info(
                    "Sandbox returned to pool",
                    extra={
                        "container_id": container_id,
                        "agent_id": str(agent_id),
                        "pool_size": self.available_sandboxes.qsize(),
                    },
                )
            else:
                # Pool full, destroy sandbox
                self.container_manager.terminate_container(container_id)
                
                self.logger.info(
                    "Sandbox destroyed (pool full)",
                    extra={
                        "container_id": container_id,
                        "agent_id": str(agent_id),
                    },
                )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to release sandbox",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                },
            )
            return False
    
    async def _reset_sandbox(self, container_id: str) -> None:
        """Reset sandbox to clean state.
        
        Args:
            container_id: Container ID to reset
        """
        # In a real implementation, this would:
        # 1. Clear temporary files
        # 2. Reset environment variables
        # 3. Clear any cached data
        # 4. Verify sandbox is in clean state
        
        self.logger.debug(
            "Sandbox reset",
            extra={"container_id": container_id},
        )
    
    def get_pool_stats(self) -> Dict[str, int]:
        """Get current pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        return {
            "pool_size": self.pool_size,
            "available": self.available_sandboxes.qsize(),
            "active": len(self.active_sandboxes),
            "warming": len(self.warming_sandboxes),
            "total": (
                self.available_sandboxes.qsize() +
                len(self.active_sandboxes) +
                len(self.warming_sandboxes)
            ),
        }
    
    async def shutdown(self) -> None:
        """Shutdown the sandbox pool and cleanup resources."""
        self.logger.info("Shutting down sandbox pool")
        
        # Terminate all active sandboxes
        for container_id in list(self.active_sandboxes.keys()):
            self.container_manager.terminate_container(container_id)
        
        # Terminate all available sandboxes
        while not self.available_sandboxes.empty():
            try:
                container_id = self.available_sandboxes.get_nowait()
                self.container_manager.terminate_container(container_id)
            except asyncio.QueueEmpty:
                break
        
        # Terminate warming sandboxes
        for container_id in self.warming_sandboxes:
            self.container_manager.terminate_container(container_id)
        
        self.active_sandboxes.clear()
        self.warming_sandboxes.clear()
        
        self.logger.info("Sandbox pool shutdown complete")


# Global sandbox pool instance
_sandbox_pool: Optional[SandboxPool] = None


def get_sandbox_pool(pool_size: int = 10) -> SandboxPool:
    """Get the global sandbox pool instance.
    
    Args:
        pool_size: Size of the pool (only used on first call)
    
    Returns:
        SandboxPool instance
    """
    global _sandbox_pool
    if _sandbox_pool is None:
        _sandbox_pool = SandboxPool(pool_size=pool_size)
    return _sandbox_pool
