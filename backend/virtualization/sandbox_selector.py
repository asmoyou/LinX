"""Sandbox Selector for automatic platform detection and sandbox selection.

This module implements automatic detection of the best available sandbox technology
based on platform capabilities and availability.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.3: Automatic Sandbox Selection
"""

import logging
import os
import platform
import subprocess
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SandboxType(Enum):
    """Available sandbox technologies."""
    
    GVISOR = "gvisor"
    FIRECRACKER = "firecracker"
    DOCKER_ENHANCED = "docker_enhanced"


class SandboxSelector:
    """Automatically select best available sandbox technology.
    
    Priority:
    1. gVisor (if Linux + Kubernetes + gVisor available)
    2. Firecracker (if Linux + KVM available)
    3. Docker Enhanced (fallback for all platforms)
    """
    
    def __init__(self):
        """Initialize the sandbox selector."""
        self.logger = logging.getLogger(__name__)
        self._detected_sandbox: Optional[SandboxType] = None
        self._platform = platform.system()
    
    def detect_best_sandbox(self) -> SandboxType:
        """Detect and return the best available sandbox technology.
        
        Returns:
            SandboxType enum value for the best available sandbox
        """
        if self._detected_sandbox:
            return self._detected_sandbox
        
        self.logger.info(
            "Detecting best sandbox technology",
            extra={"platform": self._platform},
        )
        
        # Check gVisor (Linux only)
        if self._platform == "Linux":
            if self._is_gvisor_available():
                self.logger.info(
                    "Using gVisor sandbox (highest security)",
                    extra={"security_level": "high", "overhead": "10-15%"},
                )
                self._detected_sandbox = SandboxType.GVISOR
                return self._detected_sandbox
            
            # Check Firecracker (Linux with KVM)
            if self._is_firecracker_available():
                self.logger.info(
                    "Using Firecracker sandbox (high security)",
                    extra={"security_level": "very_high", "overhead": "20-30%"},
                )
                self._detected_sandbox = SandboxType.FIRECRACKER
                return self._detected_sandbox
        
        # Fallback to Docker Enhanced (all platforms)
        self.logger.info(
            f"Using Docker Enhanced sandbox on {self._platform}",
            extra={
                "reason": "gVisor/Firecracker not available",
                "security_level": "medium",
                "overhead": "5%",
            },
        )
        self._detected_sandbox = SandboxType.DOCKER_ENHANCED
        return self._detected_sandbox
    
    def _is_gvisor_available(self) -> bool:
        """Check if gVisor is available on the system.
        
        Returns:
            True if gVisor is available, False otherwise
        """
        try:
            # Check if runsc binary exists
            result = subprocess.run(
                ['which', 'runsc'],
                capture_output=True,
                timeout=1,
                text=True,
            )
            if result.returncode != 0:
                self.logger.debug("gVisor not available: runsc binary not found")
                return False
            
            # Check if Docker supports gVisor runtime
            result = subprocess.run(
                ['docker', 'info', '--format', '{{.Runtimes}}'],
                capture_output=True,
                timeout=2,
                text=True,
            )
            
            if result.returncode == 0 and 'runsc' in result.stdout:
                self.logger.debug("gVisor is available")
                return True
            
            self.logger.debug("gVisor not available: Docker runtime not configured")
            return False
            
        except subprocess.TimeoutExpired:
            self.logger.debug("gVisor check timed out")
            return False
        except FileNotFoundError:
            self.logger.debug("gVisor check failed: command not found")
            return False
        except Exception as e:
            self.logger.debug(f"gVisor check failed: {e}")
            return False
    
    def _is_firecracker_available(self) -> bool:
        """Check if Firecracker is available on the system.
        
        Returns:
            True if Firecracker is available, False otherwise
        """
        try:
            # Check if KVM is available
            if not os.path.exists('/dev/kvm'):
                self.logger.debug("Firecracker not available: /dev/kvm not found")
                return False
            
            # Check if firecracker binary exists
            result = subprocess.run(
                ['which', 'firecracker'],
                capture_output=True,
                timeout=1,
                text=True,
            )
            
            if result.returncode == 0:
                self.logger.debug("Firecracker is available")
                return True
            
            self.logger.debug("Firecracker not available: binary not found")
            return False
            
        except subprocess.TimeoutExpired:
            self.logger.debug("Firecracker check timed out")
            return False
        except FileNotFoundError:
            self.logger.debug("Firecracker check failed: command not found")
            return False
        except Exception as e:
            self.logger.debug(f"Firecracker check failed: {e}")
            return False
    
    def get_sandbox_config(self, sandbox_type: Optional[SandboxType] = None) -> Dict[str, Any]:
        """Get configuration for specified sandbox type.
        
        Args:
            sandbox_type: Sandbox type to get config for. If None, uses detected sandbox.
        
        Returns:
            Dictionary with sandbox configuration
        """
        if sandbox_type is None:
            sandbox_type = self.detect_best_sandbox()
        
        configs = {
            SandboxType.GVISOR: {
                "runtime": "runsc",
                "security_level": "high",
                "overhead": "10-15%",
                "startup_time_ms": 150,
                "platform": "linux",
                "features": [
                    "system_call_filtering",
                    "network_namespace_isolation",
                    "filesystem_isolation",
                    "resource_limits",
                ],
            },
            SandboxType.FIRECRACKER: {
                "runtime": "firecracker",
                "security_level": "very_high",
                "overhead": "20-30%",
                "startup_time_ms": 125,
                "platform": "linux",
                "features": [
                    "hardware_isolation",
                    "minimal_guest_kernel",
                    "strong_memory_isolation",
                    "secure_boot",
                ],
            },
            SandboxType.DOCKER_ENHANCED: {
                "runtime": "docker",
                "security_level": "medium",
                "overhead": "5%",
                "startup_time_ms": 50,
                "platform": "all",
                "features": [
                    "container_isolation",
                    "resource_limits",
                    "network_isolation",
                    "capability_dropping",
                ],
            },
        }
        
        return configs[sandbox_type]
    
    def get_platform_info(self) -> Dict[str, Any]:
        """Get current platform information.
        
        Returns:
            Dictionary with platform details
        """
        return {
            "system": self._platform,
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        }
    
    def validate_sandbox_requirements(self, sandbox_type: SandboxType) -> bool:
        """Validate if system meets requirements for specified sandbox type.
        
        Args:
            sandbox_type: Sandbox type to validate
        
        Returns:
            True if requirements are met, False otherwise
        """
        if sandbox_type == SandboxType.GVISOR:
            return self._platform == "Linux" and self._is_gvisor_available()
        elif sandbox_type == SandboxType.FIRECRACKER:
            return self._platform == "Linux" and self._is_firecracker_available()
        elif sandbox_type == SandboxType.DOCKER_ENHANCED:
            # Docker Enhanced works on all platforms
            return True
        
        return False


# Global sandbox selector instance
_sandbox_selector: Optional[SandboxSelector] = None


def get_sandbox_selector() -> SandboxSelector:
    """Get the global sandbox selector instance.
    
    Returns:
        SandboxSelector instance
    """
    global _sandbox_selector
    if _sandbox_selector is None:
        _sandbox_selector = SandboxSelector()
    return _sandbox_selector
