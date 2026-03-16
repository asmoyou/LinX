"""Knowledge storage cleanup helpers and scheduled maintenance."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from sqlalchemy import text

from database.connection import get_db_session
from database.models import KnowledgeItem
from knowledge_base.cancellation_registry import request_document_cancellation
from knowledge_base.vector_collection import KNOWLEDGE_EMBEDDINGS_COLLECTION
from shared.config import Config, get_config

logger = logging.getLogger(__name__)

_CLEANUP_BUCKET_KEYS = ("documents", "audio", "video", "images")


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


@dataclass(frozen=True)
class KnowledgeStorageObjectRef:
    """Resolvable MinIO object reference used by knowledge storage cleanup."""

    bucket_name: str
    object_key: str
    variant: str = "source"


@dataclass(frozen=True)
class KnowledgeStorageCleanupSettings:
    """Configuration for scheduled knowledge storage cleanup."""

    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 300
    interval_seconds: int = 21600
    dry_run: bool = False
    batch_size: int = 500
    compact_on_cycle: bool = True
    purge_minio_versions: bool = True
    advisory_lock_id: int = 73012022
    use_advisory_lock: bool = True

    def with_defaults(self) -> "KnowledgeStorageCleanupSettings":
        return KnowledgeStorageCleanupSettings(
            enabled=self.enabled,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            dry_run=self.dry_run,
            batch_size=self.batch_size,
            compact_on_cycle=self.compact_on_cycle,
            purge_minio_versions=self.purge_minio_versions,
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
        )


def load_knowledge_storage_cleanup_settings(
    config: Optional[Config] = None,
) -> KnowledgeStorageCleanupSettings:
    """Load settings from ``knowledge_base.cleanup``."""

    cfg = config or get_config()
    raw = cfg.get("knowledge_base.cleanup", {}) or {}
    settings = KnowledgeStorageCleanupSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 300, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 21600, minimum=60),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        batch_size=_cfg_int(raw.get("batch_size"), 500, minimum=1, maximum=5000),
        compact_on_cycle=_cfg_bool(raw.get("compact_on_cycle"), True),
        purge_minio_versions=_cfg_bool(raw.get("purge_minio_versions"), True),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012022),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    )
    return settings.with_defaults()


def build_knowledge_storage_object_metadata(knowledge_id: str, variant: str) -> Dict[str, str]:
    """Build ASCII-only MinIO metadata for knowledge-base managed objects."""

    return {
        "storage_scope": "knowledge_base",
        "knowledge_id": str(knowledge_id),
        "storage_variant": str(variant),
    }


def _normalize_user_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in dict(metadata or {}).items():
        normalized[str(key).strip().lower()] = str(value or "").strip()
    return normalized


def _try_parse_minio_reference(
    reference: Optional[str],
    *,
    minio_client: Optional[Any] = None,
    fallback_bucket_name: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    value = str(reference or "").strip()
    if not value:
        return None

    client = minio_client
    if client is None:
        from object_storage.minio_client import get_minio_client

        client = get_minio_client()

    parsed = client.parse_object_reference(value)
    if parsed:
        return parsed

    if fallback_bucket_name and "://" not in value and not value.startswith("minio:"):
        return fallback_bucket_name, value
    return None


def collect_knowledge_object_refs(
    *,
    file_reference: Optional[str],
    metadata: Optional[Mapping[str, Any]],
    minio_client: Optional[Any] = None,
) -> List[KnowledgeStorageObjectRef]:
    """Collect all MinIO objects owned by one knowledge item."""

    item_metadata = dict(metadata or {})
    refs: List[KnowledgeStorageObjectRef] = []
    seen: Set[Tuple[str, str, str]] = set()

    for variant, reference, fallback_bucket in (
        (
            "source",
            file_reference,
            str(item_metadata.get("storage_bucket") or "documents") or "documents",
        ),
        (
            "thumbnail",
            item_metadata.get("thumbnail_reference"),
            item_metadata.get("thumbnail_bucket"),
        ),
    ):
        parsed = _try_parse_minio_reference(
            reference,
            minio_client=minio_client,
            fallback_bucket_name=fallback_bucket or None,
        )
        if not parsed:
            continue
        key = (parsed[0], parsed[1], variant)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            KnowledgeStorageObjectRef(
                bucket_name=parsed[0],
                object_key=parsed[1],
                variant=variant,
            )
        )
    return refs


def purge_minio_object_refs(
    refs: Iterable[KnowledgeStorageObjectRef],
    *,
    minio_client: Optional[Any] = None,
    purge_versions: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Delete one or more MinIO object refs, optionally purging all versions."""

    client = minio_client
    if client is None:
        from object_storage.minio_client import get_minio_client

        client = get_minio_client()

    targets: List[KnowledgeStorageObjectRef] = []
    seen: Set[Tuple[str, str]] = set()
    for ref in refs:
        key = (str(ref.bucket_name), str(ref.object_key))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        targets.append(ref)

    deleted_objects = 0
    deleted_versions = 0
    errors: List[str] = []

    for ref in targets:
        try:
            if dry_run:
                deleted_objects += 1
                continue
            if purge_versions:
                deleted_versions += int(
                    client.delete_file_versions(ref.bucket_name, ref.object_key)
                )
            else:
                client.delete_file(ref.bucket_name, ref.object_key)
            deleted_objects += 1
        except Exception as exc:
            logger.warning(
                "Failed to delete MinIO object during knowledge cleanup",
                extra={
                    "bucket_name": ref.bucket_name,
                    "object_key": ref.object_key,
                    "variant": ref.variant,
                    "error": str(exc),
                },
            )
            errors.append(f"{ref.bucket_name}/{ref.object_key}: {exc}")

    return {
        "deleted_objects": deleted_objects,
        "deleted_versions": deleted_versions,
        "errors": errors,
    }


def request_knowledge_processing_cancellation(
    *,
    knowledge_id: str,
    metadata: Optional[Mapping[str, Any]] = None,
    cancel_message: str = "Processing cancelled by user.",
) -> Dict[str, Any]:
    """Register cancellation for one knowledge item and notify the Redis queue when possible."""

    request_document_cancellation(knowledge_id)

    job_id = str((metadata or {}).get("job_id") or "").strip()
    queue_cancel_signal_sent = False
    queue_error: Optional[str] = None

    if job_id and not job_id.startswith("local-"):
        try:
            from knowledge_base.processing_queue import get_processing_queue

            queue = get_processing_queue()
            queue_cancel_signal_sent = bool(
                queue.request_cancel(job_id, error_message=cancel_message)
            )
        except Exception as exc:
            queue_error = str(exc)
            logger.warning(
                "Failed to request queue cancellation during knowledge cleanup",
                extra={
                    "knowledge_id": knowledge_id,
                    "job_id": job_id,
                    "error": queue_error,
                },
            )

    return {
        "job_id": job_id or None,
        "queue_cancel_signal_sent": queue_cancel_signal_sent,
        "queue_error": queue_error,
        "document_cancel_registered": True,
    }


def delete_knowledge_vectors(
    *,
    knowledge_id: str,
    milvus_conn: Optional[Any] = None,
    dry_run: bool = False,
    force_refresh: bool = True,
) -> Dict[str, Any]:
    """Delete all Milvus vectors for one knowledge item."""

    connection = milvus_conn
    if connection is None:
        from memory_system.milvus_connection import get_milvus_connection

        connection = get_milvus_connection()

    if not connection.collection_exists(KNOWLEDGE_EMBEDDINGS_COLLECTION):
        return {"attempted": False, "deleted": False, "error": None}

    try:
        collection = connection.get_collection(
            KNOWLEDGE_EMBEDDINGS_COLLECTION,
            force_refresh=force_refresh,
        )
        if not dry_run:
            collection.delete(f'knowledge_id == "{knowledge_id}"')
        return {"attempted": True, "deleted": True, "error": None}
    except Exception as exc:
        logger.warning(
            "Failed to delete Milvus vectors during knowledge cleanup",
            extra={"knowledge_id": knowledge_id, "error": str(exc)},
        )
        return {"attempted": True, "deleted": False, "error": str(exc)}


def trigger_knowledge_collection_compaction(
    *,
    milvus_conn: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Trigger Milvus compaction for the knowledge embeddings collection."""

    connection = milvus_conn
    if connection is None:
        from memory_system.milvus_connection import get_milvus_connection

        connection = get_milvus_connection()

    if not connection.collection_exists(KNOWLEDGE_EMBEDDINGS_COLLECTION):
        return {"attempted": False, "triggered": False, "error": None}

    try:
        collection = connection.get_collection(
            KNOWLEDGE_EMBEDDINGS_COLLECTION,
            force_refresh=False,
        )
        if not dry_run:
            collection.compact()
        return {"attempted": True, "triggered": True, "error": None}
    except Exception as exc:
        logger.warning(
            "Failed to trigger Milvus compaction for knowledge embeddings",
            extra={"error": str(exc)},
        )
        return {"attempted": True, "triggered": False, "error": str(exc)}


def cleanup_knowledge_item_storage(
    item: Any,
    *,
    cancel_processing: bool = True,
    purge_minio_versions: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Best-effort cleanup of all external storage owned by one knowledge item."""

    metadata = dict(getattr(item, "item_metadata", None) or {})
    knowledge_id = str(getattr(item, "knowledge_id", "") or "")
    cancel_result = None
    if cancel_processing and knowledge_id:
        cancel_result = request_knowledge_processing_cancellation(
            knowledge_id=knowledge_id,
            metadata=metadata,
        )

    minio_client = None
    try:
        from object_storage.minio_client import get_minio_client

        minio_client = get_minio_client()
    except Exception as exc:
        logger.warning("Failed to get MinIO client for knowledge cleanup: %s", exc)

    refs = collect_knowledge_object_refs(
        file_reference=getattr(item, "file_reference", None),
        metadata=metadata,
        minio_client=minio_client,
    )
    minio_result = (
        purge_minio_object_refs(
            refs,
            minio_client=minio_client,
            purge_versions=purge_minio_versions,
            dry_run=dry_run,
        )
        if refs and minio_client is not None
        else {"deleted_objects": 0, "deleted_versions": 0, "errors": []}
    )

    vector_result = (
        delete_knowledge_vectors(
            knowledge_id=knowledge_id,
            dry_run=dry_run,
        )
        if knowledge_id
        else {"attempted": False, "deleted": False, "error": None}
    )
    return {
        "knowledge_id": knowledge_id,
        "cancel": cancel_result,
        "minio": minio_result,
        "vectors": vector_result,
    }


def _acquire_advisory_lock(lock_id: int):
    """Acquire PostgreSQL advisory lock; returns held session or ``None``."""

    from database.connection import get_connection_pool

    session = get_connection_pool().get_raw_session()
    try:
        acquired = bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
            ).scalar()
        )
        if not acquired:
            session.close()
            return None
        return session
    except Exception:
        session.close()
        raise


def _release_advisory_lock(lock_id: int, session) -> None:
    """Release PostgreSQL advisory lock and close the lock session."""

    try:
        session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    except Exception as exc:
        logger.warning("Failed to release knowledge cleanup lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


def _load_live_knowledge_ids() -> Set[str]:
    live_ids: Set[str] = set()
    with get_db_session() as session:
        query = session.query(KnowledgeItem.knowledge_id).yield_per(1000)
        for row in query:
            knowledge_id = row[0] if isinstance(row, tuple) else getattr(row, "knowledge_id", row)
            if knowledge_id is not None:
                live_ids.add(str(knowledge_id))
    return live_ids


def _chunked(values: Sequence[str], batch_size: int) -> Iterable[List[str]]:
    size = max(int(batch_size), 1)
    for idx in range(0, len(values), size):
        yield list(values[idx : idx + size])


def cleanup_orphaned_knowledge_vectors(
    *,
    live_knowledge_ids: Set[str],
    batch_size: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Remove Milvus vectors whose ``knowledge_id`` no longer exists in PostgreSQL."""

    from memory_system.milvus_connection import get_milvus_connection

    connection = get_milvus_connection()
    if not connection.collection_exists(KNOWLEDGE_EMBEDDINGS_COLLECTION):
        return {
            "scanned_rows": 0,
            "orphaned_knowledge_ids": 0,
            "deleted_knowledge_ids": 0,
            "errors": [],
        }

    collection = connection.get_collection(KNOWLEDGE_EMBEDDINGS_COLLECTION, force_refresh=True)
    iterator = collection.query_iterator(
        batch_size=max(int(batch_size), 1),
        expr=None,
        output_fields=["knowledge_id"],
    )

    scanned_rows = 0
    orphaned_ids: Set[str] = set()
    errors: List[str] = []
    try:
        while True:
            rows = iterator.next()
            if not rows:
                break
            scanned_rows += len(rows)
            for row in rows:
                knowledge_id = str((row or {}).get("knowledge_id") or "").strip()
                if knowledge_id and knowledge_id not in live_knowledge_ids:
                    orphaned_ids.add(knowledge_id)
    finally:
        iterator.close()

    deleted_count = 0
    orphaned_id_list = sorted(orphaned_ids)
    for batch in _chunked(orphaned_id_list, batch_size):
        quoted = ", ".join(f'"{knowledge_id}"' for knowledge_id in batch)
        try:
            if not dry_run:
                collection.delete(f"knowledge_id in [{quoted}]")
            deleted_count += len(batch)
        except Exception as exc:
            logger.warning(
                "Failed to delete orphaned Milvus knowledge vectors",
                extra={"knowledge_ids": batch, "error": str(exc)},
            )
            errors.append(str(exc))

    return {
        "scanned_rows": scanned_rows,
        "orphaned_knowledge_ids": len(orphaned_id_list),
        "deleted_knowledge_ids": deleted_count,
        "errors": errors,
    }


def cleanup_orphaned_knowledge_objects(
    *,
    live_knowledge_ids: Set[str],
    purge_minio_versions: bool,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Remove tagged MinIO knowledge objects whose ``knowledge_id`` no longer exists."""

    from object_storage.minio_client import get_minio_client

    client = get_minio_client()
    bucket_names = [
        str(client.buckets.get(bucket_key) or "")
        for bucket_key in _CLEANUP_BUCKET_KEYS
        if client.buckets.get(bucket_key)
    ]

    tagged_versions = 0
    orphan_targets: Set[Tuple[str, str]] = set()
    errors: List[str] = []

    for bucket_name in bucket_names:
        try:
            objects = client.list_objects(
                bucket_name,
                recursive=True,
                include_user_meta=True,
                include_version=True,
            )
        except Exception as exc:
            logger.warning(
                "Failed to list MinIO objects during knowledge cleanup",
                extra={"bucket_name": bucket_name, "error": str(exc)},
            )
            errors.append(f"{bucket_name}: {exc}")
            continue

        for obj in objects:
            metadata = _normalize_user_metadata(obj.get("metadata"))
            if metadata.get("storage_scope") != "knowledge_base":
                continue
            tagged_versions += 1
            knowledge_id = metadata.get("knowledge_id", "")
            object_key = str(obj.get("object_key") or "").strip()
            if not object_key or not knowledge_id or knowledge_id in live_knowledge_ids:
                continue
            orphan_targets.add((bucket_name, object_key))

    deleted_objects = 0
    deleted_versions = 0
    for bucket_name, object_key in sorted(orphan_targets):
        try:
            if dry_run:
                deleted_objects += 1
                continue
            if purge_minio_versions:
                deleted_versions += int(client.delete_file_versions(bucket_name, object_key))
            else:
                client.delete_file(bucket_name, object_key)
            deleted_objects += 1
        except Exception as exc:
            logger.warning(
                "Failed to purge orphaned MinIO knowledge object",
                extra={"bucket_name": bucket_name, "object_key": object_key, "error": str(exc)},
            )
            errors.append(f"{bucket_name}/{object_key}: {exc}")

    return {
        "scanned_tagged_versions": tagged_versions,
        "orphaned_objects": len(orphan_targets),
        "deleted_objects": deleted_objects,
        "deleted_versions": deleted_versions,
        "errors": errors,
    }


def run_knowledge_storage_cleanup_once(
    settings: Optional[KnowledgeStorageCleanupSettings] = None,
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one knowledge storage cleanup cycle."""

    cfg = (settings or load_knowledge_storage_cleanup_settings()).with_defaults()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "cleanup": None,
        }

    lock_session = None
    if cfg.use_advisory_lock:
        try:
            lock_session = _acquire_advisory_lock(cfg.advisory_lock_id)
        except Exception as exc:
            return {
                "status": "error",
                "reason": reason,
                "dry_run": cfg.dry_run,
                "error": f"Advisory lock failed: {exc}",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "cleanup": None,
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "dry_run": cfg.dry_run,
                "skip_reason": "lock_not_acquired",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "cleanup": None,
            }

    try:
        live_ids = _load_live_knowledge_ids()
        vector_cleanup = cleanup_orphaned_knowledge_vectors(
            live_knowledge_ids=live_ids,
            batch_size=cfg.batch_size,
            dry_run=cfg.dry_run,
        )
        object_cleanup = cleanup_orphaned_knowledge_objects(
            live_knowledge_ids=live_ids,
            purge_minio_versions=cfg.purge_minio_versions,
            dry_run=cfg.dry_run,
        )
        compaction = {"attempted": False, "triggered": False, "error": None}
        if cfg.compact_on_cycle:
            compaction = trigger_knowledge_collection_compaction(dry_run=cfg.dry_run)

        cleanup = {
            "live_knowledge_ids": len(live_ids),
            "vector_cleanup": vector_cleanup,
            "object_cleanup": object_cleanup,
            "compaction": compaction,
        }
        return {
            "status": "ok",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "cleanup": cleanup,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class KnowledgeStorageCleanupManager:
    """Periodic scheduler for knowledge storage maintenance."""

    def __init__(self, settings: Optional[KnowledgeStorageCleanupSettings] = None):
        self.settings = (settings or load_knowledge_storage_cleanup_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()

    async def start(self) -> bool:
        if not self.settings.enabled:
            logger.info("Knowledge storage cleanup is disabled by config")
            return False
        if self._task and not self._task.done():
            return True

        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Knowledge storage cleanup manager started",
            extra={
                "interval_seconds": self.settings.interval_seconds,
                "batch_size": self.settings.batch_size,
                "dry_run": self.settings.dry_run,
                "compact_on_cycle": self.settings.compact_on_cycle,
            },
        )
        return True

    async def stop(self) -> None:
        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Knowledge storage cleanup manager stopped")

    async def run_once(self, *, reason: str = "manual") -> Dict[str, Any]:
        async with self._run_lock:
            result = await asyncio.to_thread(
                run_knowledge_storage_cleanup_once,
                self.settings,
                reason=reason,
            )
            level = (
                logging.INFO
                if result.get("status") in {"ok", "disabled", "skipped"}
                else logging.WARNING
            )
            cleanup = result.get("cleanup") or {}
            vector_cleanup = cleanup.get("vector_cleanup") or {}
            object_cleanup = cleanup.get("object_cleanup") or {}
            logger.log(
                level,
                "Knowledge storage cleanup cycle finished",
                extra={
                    "status": result.get("status"),
                    "reason": reason,
                    "dry_run": result.get("dry_run"),
                    "live_knowledge_ids": cleanup.get("live_knowledge_ids"),
                    "orphaned_vector_ids": vector_cleanup.get("orphaned_knowledge_ids"),
                    "deleted_vector_ids": vector_cleanup.get("deleted_knowledge_ids"),
                    "orphaned_minio_objects": object_cleanup.get("orphaned_objects"),
                    "deleted_minio_objects": object_cleanup.get("deleted_objects"),
                    "deleted_minio_versions": object_cleanup.get("deleted_versions"),
                    "duration_ms": result.get("duration_ms"),
                    "skip_reason": result.get("skip_reason"),
                    "error": result.get("error"),
                },
            )
            return result

    async def _sleep_or_stop(self, seconds: int) -> bool:
        if seconds <= 0:
            return self._shutdown
        try:
            await asyncio.sleep(seconds)
            return self._shutdown
        except asyncio.CancelledError:
            return True

    async def _run_loop(self) -> None:
        if self.settings.startup_delay_seconds > 0:
            should_stop = await self._sleep_or_stop(self.settings.startup_delay_seconds)
            if should_stop:
                return

        if self.settings.run_on_startup and not self._shutdown:
            try:
                await self.run_once(reason="startup")
            except Exception as exc:
                logger.warning("Startup knowledge storage cleanup cycle failed: %s", exc)

        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled knowledge storage cleanup cycle failed: %s", exc)


_knowledge_storage_cleanup_manager: Optional[KnowledgeStorageCleanupManager] = None
_knowledge_storage_cleanup_manager_lock = threading.Lock()


def get_knowledge_storage_cleanup_manager() -> KnowledgeStorageCleanupManager:
    """Return the global knowledge storage cleanup manager singleton."""

    global _knowledge_storage_cleanup_manager
    with _knowledge_storage_cleanup_manager_lock:
        if _knowledge_storage_cleanup_manager is None:
            _knowledge_storage_cleanup_manager = KnowledgeStorageCleanupManager()
        return _knowledge_storage_cleanup_manager


async def initialize_knowledge_storage_cleanup_manager() -> (
    Optional[KnowledgeStorageCleanupManager]
):
    """Initialize and start the knowledge storage cleanup manager if enabled."""

    manager = get_knowledge_storage_cleanup_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_knowledge_storage_cleanup_manager() -> None:
    """Shutdown the knowledge storage cleanup manager singleton."""

    global _knowledge_storage_cleanup_manager
    with _knowledge_storage_cleanup_manager_lock:
        manager = _knowledge_storage_cleanup_manager
        _knowledge_storage_cleanup_manager = None

    if manager is not None:
        await manager.stop()
