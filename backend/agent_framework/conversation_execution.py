"""Conversation execution principals shared by HTTP and background schedulers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversationExecutionPrincipal:
    user_id: str
    role: str
    username: str | None = None


def build_conversation_execution_principal(
    *,
    user_id: Any,
    role: Any,
    username: Any = None,
) -> ConversationExecutionPrincipal:
    return ConversationExecutionPrincipal(
        user_id=str(user_id),
        role=str(role or ""),
        username=(str(username) if username is not None else None),
    )
