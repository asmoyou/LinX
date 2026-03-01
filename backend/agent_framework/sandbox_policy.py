"""Sandbox execution policy helpers.

Centralizes runtime switches for host-execution fallback behavior.
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_sandbox_isolation_enforced() -> bool:
    """Whether host fallback should be blocked by default."""
    return _env_bool("LINX_ENFORCE_SANDBOX_ISOLATION", True)


def allow_host_execution_fallback() -> bool:
    """Whether host subprocess fallback is allowed.

    `LINX_ALLOW_HOST_EXECUTION_FALLBACK=1` has highest priority and can be
    used as an emergency compatibility switch.
    """
    if _env_bool("LINX_ALLOW_HOST_EXECUTION_FALLBACK", False):
        return True
    return not is_sandbox_isolation_enforced()

