"""Workspace decay helpers for persistent conversations."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import AgentConversationMessage
from shared.config import Config, get_config

logger = logging.getLogger(__name__)

RETENTION_CLASS_DURABLE = "durable"
RETENTION_CLASS_REBUILDABLE = "rebuildable"
RETENTION_CLASS_EPHEMERAL = "ephemeral"
RETENTION_CLASS_STATEFUL_RUNTIME = "stateful_runtime"

_RUNTIME_SCRIPT_PATTERNS = (
    re.compile(r"^code_[0-9a-f]{8}\.(?:py|sh|js|ts|tsx|jsx|bash|zsh|txt)$", re.IGNORECASE),
    re.compile(r"^requirements(?:\.[a-z0-9_-]+)?\.txt$", re.IGNORECASE),
)
_RUNTIME_EXACT_NAMES = {"runtime_requirements.txt"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _cfg_int(
    value: Any,
    default: int,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _normalize_relative_path(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    if normalized.startswith("workspace/"):
        normalized = normalized[len("workspace/") :]
    return normalized.strip("/")


@dataclass(frozen=True)
class ConversationWorkspaceDecaySettings:
    enabled: bool = True
    ephemeral_ttl_hours: int = 6
    rebuildable_ttl_hours: int = 24
    soft_limit_mb: int = 500
    hard_limit_mb: int = 1024
    soft_limit_files: int = 5000
    hard_limit_files: int = 10000

    @property
    def soft_limit_bytes(self) -> int:
        return int(self.soft_limit_mb) * 1024 * 1024

    @property
    def hard_limit_bytes(self) -> int:
        return int(self.hard_limit_mb) * 1024 * 1024

    def with_defaults(self) -> "ConversationWorkspaceDecaySettings":
        return ConversationWorkspaceDecaySettings(
            enabled=self.enabled,
            ephemeral_ttl_hours=self.ephemeral_ttl_hours,
            rebuildable_ttl_hours=self.rebuildable_ttl_hours,
            soft_limit_mb=self.soft_limit_mb,
            hard_limit_mb=self.hard_limit_mb,
            soft_limit_files=self.soft_limit_files,
            hard_limit_files=self.hard_limit_files,
        )


def load_conversation_workspace_decay_settings(
    config: Optional[Config] = None,
) -> ConversationWorkspaceDecaySettings:
    cfg = config or get_config()
    raw = cfg.get("persistent_conversations.workspace", {}) or {}
    return ConversationWorkspaceDecaySettings(
        enabled=_cfg_bool(raw.get("decay_enabled"), True),
        ephemeral_ttl_hours=_cfg_int(raw.get("ephemeral_ttl_hours"), 6, minimum=1, maximum=168),
        rebuildable_ttl_hours=_cfg_int(
            raw.get("rebuildable_ttl_hours"), 24, minimum=1, maximum=720
        ),
        soft_limit_mb=_cfg_int(raw.get("soft_limit_mb"), 500, minimum=64, maximum=10240),
        hard_limit_mb=_cfg_int(raw.get("hard_limit_mb"), 1024, minimum=128, maximum=20480),
        soft_limit_files=_cfg_int(raw.get("soft_limit_files"), 5000, minimum=100, maximum=100000),
        hard_limit_files=_cfg_int(raw.get("hard_limit_files"), 10000, minimum=200, maximum=200000),
    ).with_defaults()


@dataclass(frozen=True)
class WorkspacePathState:
    relative_path: str
    absolute_path: Path
    is_dir: bool
    size_bytes: int
    modified_at: datetime
    retention_class: str


class ConversationWorkspaceLimitExceeded(RuntimeError):
    """Raised when a workspace cannot be shrunk under the hard limit."""


class ConversationWorkspaceDecayService:
    def __init__(
        self,
        *,
        settings: Optional[ConversationWorkspaceDecaySettings] = None,
    ) -> None:
        self.settings = (settings or load_conversation_workspace_decay_settings()).with_defaults()

    def classify_relative_path(
        self,
        relative_path: str,
        *,
        durable_paths: Optional[set[str]] = None,
    ) -> str:
        normalized = _normalize_relative_path(relative_path)
        if not normalized:
            return RETENTION_CLASS_EPHEMERAL

        lower = normalized.lower()
        if self._is_stateful_runtime_path(lower):
            return RETENTION_CLASS_STATEFUL_RUNTIME
        if self._is_ephemeral_path(lower):
            return RETENTION_CLASS_EPHEMERAL
        if lower.startswith("input/"):
            return RETENTION_CLASS_REBUILDABLE
        if lower.startswith("output/") or lower.startswith("shared/"):
            return RETENTION_CLASS_DURABLE
        if durable_paths and normalized in durable_paths:
            return RETENTION_CLASS_DURABLE
        return RETENTION_CLASS_DURABLE

    def collect_workspace_states(
        self,
        *,
        conversation_id: UUID,
        workdir: Path,
        recursive: bool = True,
    ) -> list[WorkspacePathState]:
        root = workdir.resolve()
        if not root.exists():
            return []
        durable_paths = self._load_recent_durable_paths(conversation_id)
        candidates: Iterable[Path] = root.rglob("*") if recursive else root.iterdir()
        states: list[WorkspacePathState] = []
        for item in candidates:
            try:
                stat_result = item.stat()
            except OSError:
                continue
            relative_path = str(item.resolve().relative_to(root)).replace("\\", "/")
            modified_at = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
            is_dir = item.is_dir()
            retention_class = self.classify_relative_path(
                relative_path,
                durable_paths=durable_paths,
            )
            states.append(
                WorkspacePathState(
                    relative_path=relative_path,
                    absolute_path=item,
                    is_dir=is_dir,
                    size_bytes=0 if is_dir else int(stat_result.st_size),
                    modified_at=modified_at,
                    retention_class=retention_class,
                )
            )
        return states

    def build_retention_index(
        self,
        *,
        conversation_id: UUID,
        workdir: Path,
    ) -> dict[str, str]:
        return {
            state.relative_path: state.retention_class
            for state in self.collect_workspace_states(
                conversation_id=conversation_id,
                workdir=workdir,
                recursive=True,
            )
        }

    def decay_workspace(
        self,
        *,
        conversation_id: UUID,
        workdir: Path,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            states = self.collect_workspace_states(
                conversation_id=conversation_id,
                workdir=workdir,
                recursive=True,
            )
            return self._build_result(states, deleted_paths=[], limit_exceeded=False)

        effective_now = now or _utcnow()
        deleted_paths: list[str] = []
        states = self.collect_workspace_states(
            conversation_id=conversation_id,
            workdir=workdir,
            recursive=True,
        )

        for state in states:
            if state.is_dir or state.retention_class != RETENTION_CLASS_EPHEMERAL:
                continue
            if self._delete_path(state.absolute_path, root=workdir.resolve()):
                deleted_paths.append(state.relative_path)

        states = self.collect_workspace_states(
            conversation_id=conversation_id,
            workdir=workdir,
            recursive=True,
        )
        rebuildable_cutoff = effective_now - timedelta(hours=self.settings.rebuildable_ttl_hours)
        for state in states:
            if state.is_dir or state.retention_class != RETENTION_CLASS_REBUILDABLE:
                continue
            if state.modified_at <= rebuildable_cutoff and self._delete_path(
                state.absolute_path,
                root=workdir.resolve(),
            ):
                deleted_paths.append(state.relative_path)

        states = self.collect_workspace_states(
            conversation_id=conversation_id,
            workdir=workdir,
            recursive=True,
        )
        total_bytes, total_files = self._totals(states)
        if (
            total_bytes > self.settings.soft_limit_bytes
            or total_files > self.settings.soft_limit_files
        ):
            rebuildable_states = sorted(
                [
                    state
                    for state in states
                    if not state.is_dir and state.retention_class == RETENTION_CLASS_REBUILDABLE
                ],
                key=lambda state: (state.modified_at, state.relative_path),
            )
            for state in rebuildable_states:
                if self._delete_path(state.absolute_path, root=workdir.resolve()):
                    deleted_paths.append(state.relative_path)
                states = self.collect_workspace_states(
                    conversation_id=conversation_id,
                    workdir=workdir,
                    recursive=True,
                )
                total_bytes, total_files = self._totals(states)
                if (
                    total_bytes <= self.settings.soft_limit_bytes
                    and total_files <= self.settings.soft_limit_files
                ):
                    break

        states = self.collect_workspace_states(
            conversation_id=conversation_id,
            workdir=workdir,
            recursive=True,
        )
        total_bytes, total_files = self._totals(states)
        limit_exceeded = (
            total_bytes > self.settings.hard_limit_bytes
            or total_files > self.settings.hard_limit_files
        )
        if limit_exceeded:
            raise ConversationWorkspaceLimitExceeded(
                "Conversation workspace exceeds the hard retention limit after cleanup. "
                "Move durable files to /workspace/output or /workspace/shared and start a new conversation."
            )

        return self._build_result(states, deleted_paths=deleted_paths, limit_exceeded=False)

    def _build_result(
        self,
        states: list[WorkspacePathState],
        *,
        deleted_paths: list[str],
        limit_exceeded: bool,
    ) -> dict[str, Any]:
        total_bytes, total_files = self._totals(states)
        excluded_paths = sorted(
            state.relative_path
            for state in states
            if state.retention_class == RETENTION_CLASS_EPHEMERAL
        )
        return {
            "total_bytes": total_bytes,
            "total_files": total_files,
            "deleted_paths": sorted(set(deleted_paths)),
            "excluded_paths": excluded_paths,
            "retention_index": {state.relative_path: state.retention_class for state in states},
            "limit_exceeded": limit_exceeded,
        }

    @staticmethod
    def _totals(states: Iterable[WorkspacePathState]) -> tuple[int, int]:
        total_bytes = 0
        total_files = 0
        for state in states:
            if state.is_dir:
                continue
            total_bytes += int(state.size_bytes)
            total_files += 1
        return total_bytes, total_files

    @staticmethod
    def _delete_path(path: Path, *, root: Optional[Path] = None) -> bool:
        try:
            if not path.exists() or path.is_dir():
                return False
            path.unlink(missing_ok=True)
            stop_at = root.resolve() if root is not None else None
            current = path.parent.resolve()
            while current.exists() and current != current.parent:
                if stop_at is not None and current == stop_at:
                    break
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent
            return True
        except OSError as exc:
            logger.warning("Failed to delete workspace decay path %s: %s", path, exc)
            return False

    def _load_recent_durable_paths(self, conversation_id: UUID) -> set[str]:
        with get_db_session() as session:
            row = (
                session.query(AgentConversationMessage.content_json)
                .filter(AgentConversationMessage.conversation_id == conversation_id)
                .filter(AgentConversationMessage.role == "assistant")
                .order_by(AgentConversationMessage.created_at.desc())
                .first()
            )
        if row is None:
            return set()
        content_json = row[0] if isinstance(row, tuple) else row
        if not isinstance(content_json, dict):
            return set()
        durable_paths: set[str] = set()
        for key in ("artifacts", "artifactDelta"):
            for item in list(content_json.get(key) or []):
                if not isinstance(item, dict):
                    continue
                relative_path = _normalize_relative_path(str(item.get("path") or ""))
                if not relative_path:
                    continue
                if self._is_ephemeral_path(relative_path.lower()):
                    continue
                durable_paths.add(relative_path)
        return durable_paths

    @staticmethod
    def _is_stateful_runtime_path(lower_path: str) -> bool:
        normalized = f"/{lower_path.strip('/')}/"
        return normalized.startswith("/.linx_runtime/python_deps/")

    @staticmethod
    def _is_ephemeral_path(lower_path: str) -> bool:
        normalized = lower_path.strip("/")
        basename = normalized.rsplit("/", 1)[-1]
        normalized_wrapped = f"/{normalized}/"
        if normalized.startswith("logs/") or normalized.startswith("tasks/"):
            return True
        if normalized.startswith(".linx_runtime/pip_cache/"):
            return True
        if basename in _RUNTIME_EXACT_NAMES:
            return True
        if basename.endswith((".log", ".tmp", ".temp", ".pyc", ".pyo")):
            return True
        if "/__pycache__/" in normalized_wrapped:
            return True
        return any(pattern.match(basename) for pattern in _RUNTIME_SCRIPT_PATTERNS)


_workspace_decay_service: Optional[ConversationWorkspaceDecayService] = None


def get_conversation_workspace_decay_service() -> ConversationWorkspaceDecayService:
    global _workspace_decay_service
    if _workspace_decay_service is None:
        _workspace_decay_service = ConversationWorkspaceDecayService()
    return _workspace_decay_service


__all__ = [
    "ConversationWorkspaceDecayService",
    "ConversationWorkspaceDecaySettings",
    "ConversationWorkspaceLimitExceeded",
    "RETENTION_CLASS_DURABLE",
    "RETENTION_CLASS_EPHEMERAL",
    "RETENTION_CLASS_REBUILDABLE",
    "RETENTION_CLASS_STATEFUL_RUNTIME",
    "get_conversation_workspace_decay_service",
    "load_conversation_workspace_decay_settings",
]
