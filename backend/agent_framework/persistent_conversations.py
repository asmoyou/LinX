"""Persistent conversation runtime and snapshot management."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from agent_framework.sandbox_policy import allow_host_execution_fallback
from database.connection import get_db_session
from database.models import AgentConversation, AgentConversationSnapshot
from object_storage.minio_client import get_minio_client
from shared.config import get_config
from shared.secret_crypto import sha256_text

logger = logging.getLogger(__name__)

_PERSISTENT_CONVERSATION_SANDBOX_SCOPE = "persistent_conversation"
_PERSISTENT_CONVERSATION_CONTAINER_PREFIX = "conversation-"

_WORKSPACE_INLINE_PREVIEW_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".sql",
    ".log",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_docker_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    match = re.match(
        r"^(?P<prefix>.+?)(?P<fraction>\.\d+)?(?P<suffix>Z|[+-]\d{2}:\d{2})?$",
        raw,
    )
    if not match:
        return None

    prefix = match.group("prefix")
    fraction = match.group("fraction") or ""
    suffix = match.group("suffix") or ""
    if fraction:
        fraction = f".{fraction[1:7]}"
    if suffix == "Z":
        suffix = "+00:00"

    try:
        parsed = datetime.fromisoformat(f"{prefix}{fraction}{suffix}")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _load_runtime_service_settings() -> dict[str, Any]:
    raw = get_config().get("persistent_conversations.runtime", {}) or {}
    return {
        "base_workdir": str(
            raw.get("base_workdir") or "/tmp/persistent_agent_conversations"
        ).strip()
        or "/tmp/persistent_agent_conversations",
        "ttl_minutes": _cfg_int(raw.get("ttl_minutes"), 30, minimum=1, maximum=1440),
        "cleanup_interval_seconds": _cfg_int(
            raw.get("cleanup_interval_seconds"),
            300,
            minimum=30,
            maximum=86400,
        ),
        "use_sandbox_by_default": _cfg_bool(raw.get("use_sandbox_by_default"), True),
    }


def _object_ref(bucket_name: str, object_key: str) -> str:
    return f"minio:{bucket_name}:{object_key}"


def _ensure_runtime_dirs(workdir: Path) -> None:
    runtime_root = workdir / ".linx_runtime"
    (runtime_root / "pip_cache").mkdir(parents=True, exist_ok=True)
    (runtime_root / "python_deps").mkdir(parents=True, exist_ok=True)


def _normalize_archive_relative_path(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip()
    if normalized in {"", "."}:
        return ""
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _is_excluded_relative_path(relative_path: str, excluded_paths: set[str]) -> bool:
    normalized = _normalize_archive_relative_path(relative_path)
    if not normalized:
        return False
    for excluded in excluded_paths:
        if normalized == excluded or normalized.startswith(f"{excluded}/"):
            return True
    return False


def _build_manifest_entries(
    workdir: Path,
    *,
    excluded_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    root = workdir.resolve()
    excluded = {
        _normalize_archive_relative_path(path) for path in (excluded_paths or set()) if path
    }
    for item in sorted(root.rglob("*")):
        try:
            stat = item.stat()
        except OSError:
            continue
        relative = str(item.relative_to(root)).replace("\\", "/")
        if not relative:
            continue
        if _is_excluded_relative_path(relative, excluded):
            continue
        entries.append(
            {
                "name": item.name,
                "path": relative,
                "size": 0 if item.is_dir() else int(stat.st_size),
                "is_dir": item.is_dir(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "previewable_inline": (
                    (item.suffix or "").lower() in _WORKSPACE_INLINE_PREVIEW_EXTENSIONS
                ),
            }
        )
    return entries


def _safe_extract_tar_bytes(archive_bytes: bytes, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            candidate = (target_root / member.name).resolve()
            if candidate != target_root and target_root not in candidate.parents:
                raise ValueError(f"Blocked unsafe archive member: {member.name}")
        archive.extractall(path=target_root)


def _build_archive_bytes(
    workdir: Path,
    *,
    excluded_paths: Optional[set[str]] = None,
) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    excluded = {
        _normalize_archive_relative_path(path) for path in (excluded_paths or set()) if path
    }
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.add(
            workdir,
            arcname=".",
            filter=(
                lambda tarinfo: (
                    None
                    if _is_excluded_relative_path(str(getattr(tarinfo, "name", "")), excluded)
                    else tarinfo
                )
            ),
        )
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def _trim_title_from_text(text: str, max_chars: int = 60) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def _is_default_conversation_title(title: str) -> bool:
    value = str(title or "").strip()
    normalized = value.lower()
    invalid_markers = (
        "thinking process:",
        "reasoning process:",
        "output format",
        "single line json",
        '{"title"',
        "task:",
        "task：",
        "input:",
        "output:",
        "role:",
        "system:",
        "assistant:",
        "user:",
        "good at naming conversations",
        "good at naming dialogue",
        "conversation naming assistant",
        "擅长给对话命名的助手",
        "对话命名助手",
        "标题内容",
        "title content",
    )
    return (
        value.startswith("新对话")
        or value.startswith("New conversation")
        or re.match(r"^(role|system|assistant|user)\s*[:：]", normalized) is not None
        or any(marker in normalized for marker in invalid_markers)
    )


@dataclass
class PersistentConversationRuntime:
    conversation_id: UUID
    agent_id: UUID
    owner_user_id: UUID
    runtime_session_id: str
    workdir: Path
    use_sandbox: bool
    sandbox_id: Optional[str]
    restored_from_snapshot: bool
    snapshot_generation: int
    last_activity: datetime = field(default_factory=utcnow)
    dirty: bool = False

    def touch(self) -> None:
        self.last_activity = utcnow()

    def is_expired(self, ttl_minutes: int) -> bool:
        return utcnow() - self.last_activity > timedelta(minutes=ttl_minutes)


class PersistentConversationRuntimeService:
    """Manages active runtimes and latest restorable snapshots for persistent conversations."""

    def __init__(
        self,
        *,
        base_workdir: str = "/tmp/persistent_agent_conversations",
        ttl_minutes: int = 30,
        cleanup_interval_seconds: int = 300,
        use_sandbox_by_default: bool = True,
    ) -> None:
        self.base_workdir = Path(base_workdir)
        self.base_workdir.mkdir(parents=True, exist_ok=True)
        self.ttl_minutes = ttl_minutes
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.use_sandbox_by_default = use_sandbox_by_default
        self._runtimes: dict[str, PersistentConversationRuntime] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._shutdown = False

    async def start(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._shutdown = False
        try:
            removed = await asyncio.to_thread(
                self._cleanup_orphaned_sandboxes,
                True,
            )
            if removed > 0:
                logger.info(
                    "Cleaned orphaned persistent conversation sandboxes on startup",
                    extra={"count": removed},
                )
        except Exception as exc:
            logger.warning(
                "Failed to clean orphaned persistent conversation sandboxes on startup: %s",
                exc,
            )
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def shutdown(self) -> None:
        self._shutdown = True
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        for conversation_id in list(self._runtimes.keys()):
            await self.release_runtime(UUID(conversation_id), reason="shutdown")

    async def _cleanup_loop(self) -> None:
        while not self._shutdown:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                for runtime in list(self._runtimes.values()):
                    if runtime.is_expired(self.ttl_minutes):
                        await self.release_runtime(runtime.conversation_id, reason="expired")
                removed = await asyncio.to_thread(self._cleanup_orphaned_sandboxes, False)
                if removed > 0:
                    logger.info(
                        "Cleaned orphaned persistent conversation sandboxes",
                        extra={"count": removed},
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Persistent runtime cleanup failed: %s", exc, exc_info=True)

    def get_active_runtime(self, conversation_id: UUID) -> PersistentConversationRuntime | None:
        runtime = self._runtimes.get(str(conversation_id))
        if runtime:
            runtime.touch()
        return runtime

    async def get_or_create_runtime(
        self,
        *,
        conversation: AgentConversation,
    ) -> tuple[PersistentConversationRuntime, bool]:
        current = self.get_active_runtime(conversation.conversation_id)
        if current and not current.is_expired(self.ttl_minutes):
            return current, False
        if current:
            await self.release_runtime(conversation.conversation_id, reason="expired")

        runtime_id = uuid4().hex[:12]
        workdir = (
            self.base_workdir
            / f"conversation_{conversation.conversation_id}"
            / f"runtime_{runtime_id}"
        )
        workdir.mkdir(parents=True, exist_ok=True)
        _ensure_runtime_dirs(workdir)

        latest_ready_snapshot = self._get_latest_ready_snapshot(conversation.conversation_id)
        restored = False
        generation = 0
        if latest_ready_snapshot and latest_ready_snapshot.archive_ref:
            await asyncio.to_thread(
                self._restore_snapshot_to_workdir, latest_ready_snapshot, workdir
            )
            restored = True
            generation = int(latest_ready_snapshot.generation or 0)

        sandbox_id, use_sandbox = await self._acquire_sandbox(
            conversation_id=conversation.conversation_id,
            agent_id=conversation.agent_id,
            workdir=workdir,
            runtime_session_id=runtime_id,
        )
        runtime = PersistentConversationRuntime(
            conversation_id=conversation.conversation_id,
            agent_id=conversation.agent_id,
            owner_user_id=conversation.owner_user_id,
            runtime_session_id=runtime_id,
            workdir=workdir,
            use_sandbox=use_sandbox,
            sandbox_id=sandbox_id,
            restored_from_snapshot=restored,
            snapshot_generation=generation,
        )
        self._runtimes[str(conversation.conversation_id)] = runtime
        return runtime, True

    async def mark_runtime_dirty(self, conversation_id: UUID) -> None:
        runtime = self._runtimes.get(str(conversation_id))
        if runtime:
            runtime.dirty = True
            runtime.touch()

    async def snapshot_runtime(
        self,
        *,
        conversation_id: UUID,
        snapshot_status: str = "ready",
    ) -> AgentConversationSnapshot | None:
        runtime = self._runtimes.get(str(conversation_id))
        if runtime is None:
            return None

        runtime.touch()
        try:
            from agent_framework.conversation_workspace_decay import (
                get_conversation_workspace_decay_service,
            )

            decay_result = get_conversation_workspace_decay_service().decay_workspace(
                conversation_id=conversation_id,
                workdir=runtime.workdir,
            )
            snapshot = await asyncio.to_thread(
                self._create_snapshot_record,
                conversation_id,
                runtime.agent_id,
                runtime.owner_user_id,
                runtime.workdir,
                snapshot_status,
                set(decay_result.get("excluded_paths") or []),
                int(decay_result.get("total_bytes") or 0),
                int(decay_result.get("total_files") or 0),
            )
            if snapshot and snapshot.snapshot_status == "ready":
                runtime.snapshot_generation = int(
                    snapshot.generation or runtime.snapshot_generation
                )
                runtime.dirty = False
            return snapshot
        except Exception as exc:
            logger.error(
                "Failed to snapshot conversation runtime %s: %s",
                conversation_id,
                exc,
                exc_info=True,
            )
            return self._record_failed_snapshot(conversation_id, error_text=str(exc))

    async def release_runtime(self, conversation_id: UUID, *, reason: str) -> None:
        try:
            from user_memory.conversation_memory_service import get_conversation_memory_service

            await get_conversation_memory_service().flush_conversation_memory_delta(
                conversation_id,
                reason=reason,
            )
        except Exception as exc:
            logger.warning(
                "Failed to flush persistent conversation memory before runtime release %s: %s",
                conversation_id,
                exc,
            )

        runtime = self._runtimes.get(str(conversation_id))
        if runtime is None:
            return
        if runtime.dirty and reason != "delete":
            try:
                await self.snapshot_runtime(conversation_id=conversation_id)
            except Exception:
                logger.warning("Dirty runtime snapshot failed during release", exc_info=True)
        runtime = self._runtimes.pop(str(conversation_id), runtime)
        if runtime.sandbox_id:
            try:
                from agent_framework.session_manager import get_session_manager

                await get_session_manager()._release_sandbox(runtime.sandbox_id)
            except Exception as exc:
                logger.warning("Failed to release persistent runtime sandbox: %s", exc)
        try:
            shutil.rmtree(runtime.workdir, ignore_errors=True)
            parent_dir = runtime.workdir.parent
            if parent_dir.exists() and not any(parent_dir.iterdir()):
                parent_dir.rmdir()
        except Exception as exc:
            logger.warning("Failed to clean persistent runtime workdir: %s", exc)
        logger.info(
            "Released persistent conversation runtime",
            extra={
                "conversation_id": str(conversation_id),
                "reason": reason,
                "runtime_session_id": runtime.runtime_session_id,
            },
        )

    def _get_latest_ready_snapshot(self, conversation_id: UUID) -> AgentConversationSnapshot | None:
        with get_db_session() as session:
            return (
                session.query(AgentConversationSnapshot)
                .filter(AgentConversationSnapshot.conversation_id == conversation_id)
                .filter(AgentConversationSnapshot.snapshot_status == "ready")
                .order_by(AgentConversationSnapshot.generation.desc())
                .first()
            )

    def _restore_snapshot_to_workdir(
        self,
        snapshot: AgentConversationSnapshot,
        workdir: Path,
    ) -> None:
        minio = get_minio_client()
        archive_ref = minio.parse_object_reference(snapshot.archive_ref)
        if not archive_ref:
            raise ValueError("Latest snapshot archive reference is missing or invalid")
        archive_bucket, archive_key = archive_ref
        archive_stream, _ = minio.download_file(archive_bucket, archive_key)
        _safe_extract_tar_bytes(archive_stream.read(), workdir)
        _ensure_runtime_dirs(workdir)

    def _cleanup_orphaned_sandboxes(self, force_remove: bool = False) -> int:
        from virtualization.container_manager import get_container_manager, get_docker_cleanup_manager

        cleanup_manager = get_docker_cleanup_manager()
        if not cleanup_manager.docker_available or cleanup_manager.docker_client is None:
            return 0

        try:
            containers = cleanup_manager.docker_client.containers.list(
                all=True,
                filters={"label": ["com.linx.managed=true", "com.linx.type=sandbox"]},
            )
        except Exception as exc:
            logger.warning("Failed to inspect sandbox containers for orphan cleanup: %s", exc)
            return 0

        active_sandbox_ids = {
            str(runtime.sandbox_id).strip()
            for runtime in self._runtimes.values()
            if str(runtime.sandbox_id or "").strip()
        }
        cutoff = utcnow() - timedelta(seconds=max(self.cleanup_interval_seconds, 60))
        container_manager = get_container_manager()
        removed = 0

        for container in containers:
            labels = self._get_container_labels(container)
            internal_id = str(labels.get("com.linx.container_id") or "").strip()
            if internal_id and internal_id in active_sandbox_ids:
                continue
            if not self._is_persistent_conversation_sandbox(container, labels):
                continue
            if not force_remove and not self._is_container_older_than(container, cutoff):
                continue

            try:
                container.remove(force=True)
                if internal_id:
                    container_manager.containers.pop(internal_id, None)
                removed += 1
                logger.info(
                    "Removed orphaned persistent conversation sandbox",
                    extra={
                        "sandbox_id": internal_id or None,
                        "container_name": str(getattr(container, "name", "") or ""),
                        "force_remove": force_remove,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to remove orphaned persistent conversation sandbox %s: %s",
                    internal_id or getattr(container, "name", "unknown"),
                    exc,
                )

        return removed

    @staticmethod
    def _get_container_labels(container: Any) -> dict[str, str]:
        raw_labels = getattr(container, "labels", None)
        if not isinstance(raw_labels, dict):
            attrs = getattr(container, "attrs", None)
            if not isinstance(attrs, dict) or not attrs:
                try:
                    container.reload()
                except Exception:
                    pass
                attrs = getattr(container, "attrs", None)
            if isinstance(attrs, dict):
                raw_labels = ((attrs.get("Config") or {}).get("Labels") or {})
        if not isinstance(raw_labels, dict):
            return {}
        return {str(key): str(value) for key, value in raw_labels.items() if value is not None}

    @staticmethod
    def _is_persistent_conversation_sandbox(container: Any, labels: dict[str, str]) -> bool:
        if str(labels.get("com.linx.runtime_scope") or "").strip() == (
            _PERSISTENT_CONVERSATION_SANDBOX_SCOPE
        ):
            return True
        container_name = str(getattr(container, "name", "") or "").lstrip("/")
        return container_name.startswith(_PERSISTENT_CONVERSATION_CONTAINER_PREFIX)

    @staticmethod
    def _is_container_older_than(container: Any, cutoff: datetime) -> bool:
        attrs = getattr(container, "attrs", None)
        if not isinstance(attrs, dict) or not attrs:
            try:
                container.reload()
            except Exception:
                return False
            attrs = getattr(container, "attrs", None)
        if not isinstance(attrs, dict):
            return False

        created_at = _parse_docker_timestamp(
            ((attrs.get("State") or {}).get("StartedAt")) or attrs.get("Created")
        )
        if created_at is None:
            return False
        return created_at <= cutoff

    async def _acquire_sandbox(
        self,
        *,
        conversation_id: UUID,
        agent_id: UUID,
        workdir: Path,
        runtime_session_id: str,
    ) -> tuple[Optional[str], bool]:
        from agent_framework.session_manager import get_session_manager

        session_manager = get_session_manager()
        if not self.use_sandbox_by_default:
            if not allow_host_execution_fallback():
                raise RuntimeError(
                    "Host execution fallback is disabled by sandbox isolation policy; "
                    "persistent conversations must run in a sandbox."
                )
            return None, False
        if not getattr(session_manager, "_docker_available", False):
            if not allow_host_execution_fallback():
                raise RuntimeError(
                    "Docker not available for required persistent conversation sandbox "
                    f"(conversation_id={conversation_id})"
                )
            return None, False

        try:
            from virtualization.container_manager import ContainerConfig, get_container_manager

            container_manager = get_container_manager()
            container_name = f"conversation-{agent_id.hex[:8]}-{uuid4().hex[:8]}"
            config = ContainerConfig(
                agent_id=agent_id,
                name=container_name,
                sandbox_type=container_manager.default_sandbox,
                image="python:3.11-bookworm",
                read_only_root=False,
                tmpfs_mounts={"/tmp": "size=1G,mode=1777"},
                volume_mounts={str(workdir): "/workspace"},
                environment={
                    "PIP_CACHE_DIR": "/workspace/.linx_runtime/pip_cache",
                    "LINX_DEP_WORKDIR": "/workspace/.linx_runtime",
                    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "PIP_DEFAULT_TIMEOUT": "120",
                    "PIP_RETRIES": "6",
                    "PIP_TARGET": "/workspace/.linx_runtime/python_deps",
                    "PYTHONPATH": "/workspace/.linx_runtime/python_deps",
                    "PYTHONNOUSERSITE": "1",
                    "PIP_USER": "0",
                },
                labels={
                    "com.linx.runtime_scope": _PERSISTENT_CONVERSATION_SANDBOX_SCOPE,
                    "com.linx.conversation_id": str(conversation_id),
                    "com.linx.runtime_session_id": str(runtime_session_id),
                },
                network_disabled=False,
                network_mode="bridge",
            )
            container_id = container_manager.create_container(agent_id=agent_id, config=config)
            started = container_manager.start_container(container_id)
            if not started:
                container_manager.terminate_container(container_id)
                if not allow_host_execution_fallback():
                    raise RuntimeError(
                        "Failed to start required persistent conversation sandbox "
                        f"(conversation_id={conversation_id})"
                    )
                return None, False
            return container_id, True
        except Exception as exc:
            if not allow_host_execution_fallback():
                raise RuntimeError(
                    "Failed to acquire persistent conversation sandbox "
                    f"(conversation_id={conversation_id}): {exc}"
                ) from exc
            logger.warning("Failed to acquire persistent conversation sandbox: %s", exc)
            return None, False

    def _put_bytes(
        self,
        *,
        bucket_name: str,
        object_key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        minio = get_minio_client()
        minio.client.put_object(
            bucket_name=bucket_name,
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata=metadata,
        )

    def _create_snapshot_record(
        self,
        conversation_id: UUID,
        agent_id: UUID,
        owner_user_id: UUID,
        workdir: Path,
        snapshot_status: str,
        excluded_paths: Optional[set[str]] = None,
        workspace_bytes_estimate: int = 0,
        workspace_file_count_estimate: int = 0,
    ) -> AgentConversationSnapshot:
        minio = get_minio_client()
        bucket_name = minio.buckets["artifacts"]
        manifest_entries = _build_manifest_entries(workdir, excluded_paths=excluded_paths)
        archive_bytes, checksum = _build_archive_bytes(workdir, excluded_paths=excluded_paths)
        manifest_bytes = json.dumps(
            {"entries": manifest_entries, "generated_at": utcnow().isoformat()},
            ensure_ascii=False,
        ).encode("utf-8")

        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                raise ValueError(f"Conversation {conversation_id} not found")

            previous_ready = (
                session.query(AgentConversationSnapshot)
                .filter(AgentConversationSnapshot.conversation_id == conversation_id)
                .filter(AgentConversationSnapshot.snapshot_status == "ready")
                .order_by(AgentConversationSnapshot.generation.desc())
                .first()
            )
            next_generation = int(previous_ready.generation if previous_ready else 0) + 1
            archive_key = f"{agent_id}/{conversation_id}/{next_generation:06d}/workspace.tar.gz"
            manifest_key = f"{agent_id}/{conversation_id}/{next_generation:06d}/manifest.json"

            metadata = {
                "conversation_id": str(conversation_id),
                "agent_id": str(agent_id),
                "owner_user_id": str(owner_user_id),
                "generation": str(next_generation),
            }
            self._put_bytes(
                bucket_name=bucket_name,
                object_key=archive_key,
                data=archive_bytes,
                content_type="application/gzip",
                metadata=metadata,
            )
            self._put_bytes(
                bucket_name=bucket_name,
                object_key=manifest_key,
                data=manifest_bytes,
                content_type="application/json",
                metadata=metadata,
            )

            snapshot = AgentConversationSnapshot(
                conversation_id=conversation_id,
                generation=next_generation,
                archive_ref=_object_ref(bucket_name, archive_key),
                manifest_ref=_object_ref(bucket_name, manifest_key),
                size_bytes=len(archive_bytes),
                checksum=checksum,
                snapshot_status=snapshot_status,
            )
            session.add(snapshot)
            session.flush()

            if snapshot_status == "ready":
                conversation.latest_snapshot_id = snapshot.snapshot_id
                conversation.updated_at = utcnow()
                conversation.workspace_bytes_estimate = int(workspace_bytes_estimate or 0)
                conversation.workspace_file_count_estimate = int(workspace_file_count_estimate or 0)
                conversation.last_workspace_decay_at = utcnow()
                if previous_ready:
                    previous_ready.snapshot_status = "superseded"
            session.commit()
            session.refresh(snapshot)

        if previous_ready:
            for ref in (previous_ready.archive_ref, previous_ready.manifest_ref):
                parsed = minio.parse_object_reference(ref)
                if not parsed:
                    continue
                bucket, key = parsed
                try:
                    minio.delete_file_versions(bucket, key)
                except Exception as exc:
                    logger.warning(
                        "Failed to delete previous snapshot object %s/%s: %s", bucket, key, exc
                    )
        return snapshot

    def _record_failed_snapshot(
        self,
        conversation_id: UUID,
        *,
        error_text: str,
    ) -> AgentConversationSnapshot | None:
        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                return None
            previous = (
                session.query(AgentConversationSnapshot)
                .filter(AgentConversationSnapshot.conversation_id == conversation_id)
                .order_by(AgentConversationSnapshot.generation.desc())
                .first()
            )
            snapshot = AgentConversationSnapshot(
                conversation_id=conversation_id,
                generation=int(previous.generation if previous else 0) + 1,
                archive_ref=None,
                manifest_ref=None,
                size_bytes=0,
                checksum=sha256_text(error_text),
                snapshot_status="failed",
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot


_runtime_service: PersistentConversationRuntimeService | None = None


def get_persistent_conversation_runtime_service() -> PersistentConversationRuntimeService:
    global _runtime_service
    if _runtime_service is None:
        _runtime_service = PersistentConversationRuntimeService(**_load_runtime_service_settings())
    return _runtime_service


async def initialize_persistent_conversation_runtime_service() -> None:
    await get_persistent_conversation_runtime_service().start()


async def shutdown_persistent_conversation_runtime_service() -> None:
    global _runtime_service
    if _runtime_service is not None:
        await _runtime_service.shutdown()
        _runtime_service = None


def build_default_conversation_title(created_at: datetime | None = None) -> str:
    timestamp = (created_at or utcnow()).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"新对话 {timestamp} UTC"


def is_default_conversation_title(title: str) -> bool:
    return _is_default_conversation_title(title)


def maybe_promote_conversation_title(conversation: AgentConversation, first_message: str) -> None:
    if not _is_default_conversation_title(conversation.title):
        return
    conversation.title = _trim_title_from_text(first_message or "")
