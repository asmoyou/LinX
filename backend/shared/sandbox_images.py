"""Shared sandbox image resolution helpers."""

from __future__ import annotations

import os

DEFAULT_FALLBACK_SANDBOX_IMAGE = "python:3.11-bookworm"


def _resolve_image(*env_names: str, fallback: str = DEFAULT_FALLBACK_SANDBOX_IMAGE) -> str:
    for env_name in env_names:
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return fallback


def resolve_shared_sandbox_image() -> str:
    return _resolve_image("LINX_SANDBOX_PYTHON_IMAGE")


def resolve_mission_sandbox_image() -> str:
    return _resolve_image(
        "LINX_MISSION_SANDBOX_IMAGE",
        "LINX_SANDBOX_PYTHON_IMAGE",
    )


def resolve_persistent_conversation_sandbox_image() -> str:
    return _resolve_image(
        "LINX_PERSISTENT_CONVERSATION_SANDBOX_IMAGE",
        "LINX_MISSION_SANDBOX_IMAGE",
        "LINX_SANDBOX_PYTHON_IMAGE",
    )


__all__ = [
    "DEFAULT_FALLBACK_SANDBOX_IMAGE",
    "resolve_mission_sandbox_image",
    "resolve_persistent_conversation_sandbox_image",
    "resolve_shared_sandbox_image",
]
