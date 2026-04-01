"""Runtime capability snapshot helpers for agent execution.

This module defines a compact, backend-authoritative runtime metadata payload
that can be injected into agent execution context and rendered in prompts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_framework.sandbox_policy import allow_host_execution_fallback
from virtualization.sandbox_capability_probe import (
    DEFAULT_CAPABILITY_SNAPSHOT_PATH,
    build_document_toolchain_summary,
)
from virtualization.sandbox_runtime_env import build_python_runtime_summary

RUNTIME_CAPABILITIES_VERSION = "1"
DEFAULT_WORKSPACE_ROOT_VIRTUAL = "/workspace"
DEFAULT_UI_MODE = "none"


def _normalize_python_runtime(value: Any, *, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = dict(default or build_python_runtime_summary())
    if not isinstance(value, dict):
        return base

    if value.get("executable"):
        base["executable"] = str(value.get("executable"))
    if value.get("pip_target"):
        base["pip_target"] = str(value.get("pip_target"))
    if value.get("pythonpath"):
        base["pythonpath"] = str(value.get("pythonpath"))
    if "python_nousersite" in value:
        base["python_nousersite"] = _coerce_bool(
            value.get("python_nousersite"),
            default=bool(base.get("python_nousersite", True)),
        )
    return base


def _normalize_document_toolchain(
    value: Any,
    *,
    default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = dict(default or build_document_toolchain_summary())
    if not isinstance(value, dict):
        return base

    for key in ("renderers", "preferred_cjk_fonts", "commands"):
        raw_list = value.get(key)
        if isinstance(raw_list, list):
            base[key] = [str(item) for item in raw_list if str(item).strip()]
    return base


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return default


def _normalize_virtual_path(path: Any, default: str = DEFAULT_WORKSPACE_ROOT_VIRTUAL) -> str:
    raw = str(path or "").strip()
    if not raw:
        return default

    normalized = raw.replace("\\", "/")
    if not normalized.startswith("/"):
        normalized = f"/{normalized.lstrip('/')}"
    normalized = normalized.rstrip("/")
    return normalized or "/"


def _normalize_writable_roots(
    roots: Any,
    *,
    workspace_root_virtual: str,
) -> List[str]:
    normalized: List[str] = []
    if isinstance(roots, list):
        for value in roots:
            root = _normalize_virtual_path(value, default="")
            if root and root not in normalized:
                normalized.append(root)
    if not normalized:
        normalized = [workspace_root_virtual]
    return normalized


def build_runtime_capabilities_snapshot(
    *,
    sandbox_enabled: bool,
    sandbox_backend: Optional[str] = None,
    workspace_root_virtual: str = DEFAULT_WORKSPACE_ROOT_VIRTUAL,
    writable_roots: Optional[List[str]] = None,
    ui_mode: str = DEFAULT_UI_MODE,
    network_access: Optional[bool] = None,
    host_fallback_allowed: Optional[bool] = None,
    session_persistent: bool = True,
    capability_snapshot_path: str = DEFAULT_CAPABILITY_SNAPSHOT_PATH,
    python_runtime: Optional[Dict[str, Any]] = None,
    document_toolchain: Optional[Dict[str, Any]] = None,
    source: str = "backend_runtime",
) -> Dict[str, Any]:
    """Build a normalized runtime capability snapshot."""
    resolved_workspace_root = _normalize_virtual_path(workspace_root_virtual)
    resolved_writable_roots = _normalize_writable_roots(
        writable_roots,
        workspace_root_virtual=resolved_workspace_root,
    )

    resolved_backend = str(
        sandbox_backend or ("docker" if sandbox_enabled else "host_subprocess")
    ).strip().lower()
    if not resolved_backend:
        resolved_backend = "docker" if sandbox_enabled else "host_subprocess"

    resolved_network_access = True if network_access is None else bool(network_access)
    resolved_host_fallback = (
        allow_host_execution_fallback()
        if host_fallback_allowed is None
        else bool(host_fallback_allowed)
    )
    resolved_capability_snapshot_path = _normalize_virtual_path(
        capability_snapshot_path,
        default=DEFAULT_CAPABILITY_SNAPSHOT_PATH,
    )
    resolved_python_runtime = _normalize_python_runtime(python_runtime)
    resolved_document_toolchain = _normalize_document_toolchain(document_toolchain)

    return {
        "version": RUNTIME_CAPABILITIES_VERSION,
        "source": str(source or "backend_runtime"),
        "sandbox_enabled": bool(sandbox_enabled),
        "sandbox_backend": resolved_backend,
        "ui_mode": str(ui_mode or DEFAULT_UI_MODE).strip().lower() or DEFAULT_UI_MODE,
        "workspace_root_virtual": resolved_workspace_root,
        "writable_roots": resolved_writable_roots,
        "network_access": resolved_network_access,
        "host_fallback_allowed": resolved_host_fallback,
        "session_persistent": bool(session_persistent),
        "capability_snapshot_path": resolved_capability_snapshot_path,
        "python_runtime": resolved_python_runtime,
        "document_toolchain": resolved_document_toolchain,
    }


def sanitize_runtime_capabilities(
    raw: Any,
    *,
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize runtime capabilities and apply safe defaults."""
    merged: Dict[str, Any] = {}
    if isinstance(defaults, dict):
        merged.update(defaults)
    if isinstance(raw, dict):
        merged.update(raw)

    return build_runtime_capabilities_snapshot(
        sandbox_enabled=_coerce_bool(
            merged.get("sandbox_enabled"),
            default=_coerce_bool((defaults or {}).get("sandbox_enabled"), False),
        ),
        sandbox_backend=str(
            merged.get("sandbox_backend")
            or (defaults or {}).get("sandbox_backend")
            or ""
        ).strip()
        or None,
        workspace_root_virtual=merged.get("workspace_root_virtual")
        or (defaults or {}).get("workspace_root_virtual")
        or DEFAULT_WORKSPACE_ROOT_VIRTUAL,
        writable_roots=merged.get("writable_roots")
        if isinstance(merged.get("writable_roots"), list)
        else (defaults or {}).get("writable_roots"),
        ui_mode=merged.get("ui_mode") or (defaults or {}).get("ui_mode") or DEFAULT_UI_MODE,
        network_access=_coerce_bool(
            merged.get("network_access"),
            default=_coerce_bool((defaults or {}).get("network_access"), True),
        ),
        host_fallback_allowed=_coerce_bool(
            merged.get("host_fallback_allowed"),
            default=_coerce_bool((defaults or {}).get("host_fallback_allowed"), True),
        ),
        session_persistent=_coerce_bool(
            merged.get("session_persistent"),
            default=_coerce_bool((defaults or {}).get("session_persistent"), True),
        ),
        capability_snapshot_path=merged.get("capability_snapshot_path")
        or (defaults or {}).get("capability_snapshot_path")
        or DEFAULT_CAPABILITY_SNAPSHOT_PATH,
        python_runtime=_normalize_python_runtime(
            merged.get("python_runtime"),
            default=_normalize_python_runtime((defaults or {}).get("python_runtime")),
        ),
        document_toolchain=_normalize_document_toolchain(
            merged.get("document_toolchain"),
            default=_normalize_document_toolchain((defaults or {}).get("document_toolchain")),
        ),
        source=str(merged.get("source") or (defaults or {}).get("source") or "backend_runtime"),
    )


def apply_authoritative_runtime_overrides(
    raw: Any,
    *,
    defaults: Dict[str, Any],
    preserve_sandbox_backend_when_enabled: bool = True,
) -> Dict[str, Any]:
    """Merge raw payload then enforce backend-authoritative runtime fields.

    Critical execution constraints (sandbox enabled, network policy, workspace scope)
    are always sourced from `defaults`.
    """
    resolved = sanitize_runtime_capabilities(raw, defaults=defaults)

    authoritative_keys = (
        "sandbox_enabled",
        "workspace_root_virtual",
        "writable_roots",
        "ui_mode",
        "network_access",
        "host_fallback_allowed",
        "session_persistent",
        "capability_snapshot_path",
        "python_runtime",
        "document_toolchain",
    )
    for key in authoritative_keys:
        if key in defaults:
            resolved[key] = defaults[key]

    if not bool(defaults.get("sandbox_enabled")):
        resolved["sandbox_backend"] = str(defaults.get("sandbox_backend") or "host_subprocess")
        return resolved

    raw_backend = ""
    if isinstance(raw, dict):
        raw_backend = str(raw.get("sandbox_backend") or "").strip().lower()
    if preserve_sandbox_backend_when_enabled and raw_backend:
        resolved["sandbox_backend"] = raw_backend
    else:
        resolved["sandbox_backend"] = str(defaults.get("sandbox_backend") or "docker")
    return resolved
