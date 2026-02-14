"""Background cleanup for orphan Milvus vectors.

This module provides:
- A production-safe full scan utility based on Milvus query iterators
- PostgreSQL advisory-lock guarded cleanup runs (cross-process safe)
- An async scheduler for periodic orphan cleanup
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text

from memory_system.collections import CollectionName
from memory_system.memory_repository import get_memory_repository
from memory_system.milvus_connection import get_milvus_connection
from shared.config import Config, get_config

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTIONS = [
    CollectionName.AGENT_MEMORIES.value,
    CollectionName.COMPANY_MEMORIES.value,
]


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


def _normalize_collections(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return list(_DEFAULT_COLLECTIONS)

    valid_names = {item.value for item in CollectionName}
    parsed: List[str] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if candidate in valid_names:
            parsed.append(candidate)

    if not parsed:
        return list(_DEFAULT_COLLECTIONS)
    return parsed


def _chunked(values: List[int], size: int) -> Iterable[List[int]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


@dataclass(frozen=True)
class OrphanCleanupSettings:
    """Configuration for automatic orphan vector cleanup."""

    enabled: bool = False
    run_on_startup: bool = True
    startup_delay_seconds: int = 120
    interval_seconds: int = 21600
    batch_size: int = 1000
    query_timeout_seconds: int = 10
    dry_run: bool = False
    max_scan_per_collection: int = 200000
    max_delete_per_collection: int = 20000
    collections: Optional[List[str]] = None
    advisory_lock_id: int = 73012019
    use_advisory_lock: bool = True

    def with_defaults(self) -> "OrphanCleanupSettings":
        """Return a settings object with mutable defaults normalized."""
        return OrphanCleanupSettings(
            enabled=self.enabled,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            batch_size=self.batch_size,
            query_timeout_seconds=self.query_timeout_seconds,
            dry_run=self.dry_run,
            max_scan_per_collection=self.max_scan_per_collection,
            max_delete_per_collection=self.max_delete_per_collection,
            collections=list(self.collections or _DEFAULT_COLLECTIONS),
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
        )


def load_orphan_cleanup_settings(config: Optional[Config] = None) -> OrphanCleanupSettings:
    """Load cleanup settings from ``memory.cleanup_orphans``."""
    cfg = config or get_config()
    raw = cfg.get("memory.cleanup_orphans", {}) or {}

    settings = OrphanCleanupSettings(
        enabled=_cfg_bool(raw.get("enabled"), False),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 120, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 21600, minimum=60),
        batch_size=_cfg_int(raw.get("batch_size"), 1000, minimum=100, maximum=10000),
        query_timeout_seconds=_cfg_int(raw.get("query_timeout_seconds"), 10, minimum=1),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        max_scan_per_collection=_cfg_int(
            raw.get("max_scan_per_collection"),
            200000,
            minimum=1000,
        ),
        max_delete_per_collection=_cfg_int(
            raw.get("max_delete_per_collection"),
            20000,
            minimum=100,
        ),
        collections=_normalize_collections(raw.get("collections")),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012019),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    )
    return settings.with_defaults()


def _acquire_advisory_lock(lock_id: int):
    """Acquire PostgreSQL advisory lock; returns held session or ``None``."""
    from database.connection import get_connection_pool

    session = get_connection_pool().get_raw_session()
    try:
        acquired = bool(
            session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id})
            .scalar()
        )
        if not acquired:
            session.close()
            return None
        return session
    except Exception:
        session.close()
        raise


def _release_advisory_lock(lock_id: int, session) -> None:
    """Release PostgreSQL advisory lock and close lock session."""
    try:
        session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    except Exception as exc:
        logger.warning("Failed to release advisory lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


def scan_orphan_vectors(
    collection_name: str,
    *,
    batch_size: int = 1000,
    dry_run: bool = True,
    max_scan: Optional[int] = None,
    max_delete: Optional[int] = None,
    query_timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Scan one Milvus collection and optionally delete orphan vectors."""
    started = time.monotonic()
    repo = get_memory_repository()
    milvus = get_milvus_connection()

    try:
        collection = milvus.get_collection(collection_name)
    except Exception as exc:
        return {"collection": collection_name, "error": f"Failed to get collection: {exc}"}

    scanned = 0
    orphan_count = 0
    orphan_preview: List[int] = []
    delete_candidates: List[int] = []
    max_scan_limit = max_scan if max_scan and max_scan > 0 else None
    max_delete_limit = max_delete if max_delete and max_delete > 0 else None

    iterator = None
    try:
        iterator_limit = max_scan_limit if max_scan_limit is not None else -1
        iterator = collection.query_iterator(
            batch_size=batch_size,
            limit=iterator_limit,
            expr="id >= 0",
            output_fields=["id"],
            timeout=query_timeout_seconds,
        )

        while True:
            rows = iterator.next()
            if not rows:
                break

            batch_ids: List[int] = []
            for row in rows:
                mid = row.get("id")
                if mid is None:
                    continue
                batch_ids.append(int(mid))
            if not batch_ids:
                continue

            scanned += len(batch_ids)
            existing = repo.get_by_milvus_ids(batch_ids)
            for mid in batch_ids:
                if mid in existing:
                    continue
                orphan_count += 1
                if len(orphan_preview) < 50:
                    orphan_preview.append(mid)
                if max_delete_limit is None or len(delete_candidates) < max_delete_limit:
                    delete_candidates.append(mid)

            if max_scan_limit is not None and scanned >= max_scan_limit:
                break
    except Exception as exc:
        return {
            "collection": collection_name,
            "scanned": scanned,
            "orphan_count": orphan_count,
            "orphan_ids": orphan_preview,
            "deleted": 0,
            "dry_run": dry_run,
            "error": f"Scan failed: {exc}",
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if iterator is not None:
            try:
                iterator.close()
            except Exception:
                pass

    deleted = 0
    delete_error: Optional[str] = None
    if not dry_run and delete_candidates:
        try:
            for chunk in _chunked(delete_candidates, batch_size):
                collection.delete(expr=f"id in {chunk}")
                deleted += len(chunk)
        except Exception as exc:
            delete_error = str(exc)

    result: Dict[str, Any] = {
        "collection": collection_name,
        "scanned": scanned,
        "orphan_count": orphan_count,
        "orphan_ids": orphan_preview,
        "deleted": deleted,
        "dry_run": dry_run,
        "max_scan_reached": bool(max_scan_limit and scanned >= max_scan_limit),
        "delete_capped": bool(max_delete_limit and orphan_count > len(delete_candidates)),
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
    }
    if delete_error:
        result["error"] = f"Delete failed: {delete_error}"
    return result


def run_orphan_cleanup_once(
    settings: Optional[OrphanCleanupSettings] = None,
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one full cleanup cycle across configured collections."""
    cfg = (settings or load_orphan_cleanup_settings()).with_defaults()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "collections": [],
            "total_scanned": 0,
            "total_orphans": 0,
            "total_deleted": 0,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }

    lock_session = None
    if cfg.use_advisory_lock:
        try:
            lock_session = _acquire_advisory_lock(cfg.advisory_lock_id)
        except Exception as exc:
            return {
                "status": "error",
                "reason": reason,
                "error": f"Advisory lock failed: {exc}",
                "dry_run": cfg.dry_run,
                "collections": [],
                "total_scanned": 0,
                "total_orphans": 0,
                "total_deleted": 0,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "skip_reason": "lock_not_acquired",
                "dry_run": cfg.dry_run,
                "collections": [],
                "total_scanned": 0,
                "total_orphans": 0,
                "total_deleted": 0,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }

    try:
        results: List[Dict[str, Any]] = []
        for coll_name in cfg.collections:
            result = scan_orphan_vectors(
                coll_name,
                batch_size=cfg.batch_size,
                dry_run=cfg.dry_run,
                max_scan=cfg.max_scan_per_collection,
                max_delete=cfg.max_delete_per_collection,
                query_timeout_seconds=cfg.query_timeout_seconds,
            )
            results.append(result)

        total_scanned = sum(int(item.get("scanned", 0) or 0) for item in results)
        total_orphans = sum(int(item.get("orphan_count", 0) or 0) for item in results)
        total_deleted = sum(int(item.get("deleted", 0) or 0) for item in results)
        status = "ok"
        if any(item.get("error") for item in results):
            status = "partial_error"

        return {
            "status": status,
            "reason": reason,
            "dry_run": cfg.dry_run,
            "collections": results,
            "total_scanned": total_scanned,
            "total_orphans": total_orphans,
            "total_deleted": total_deleted,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class OrphanVectorCleanupManager:
    """Periodic cleanup scheduler for orphan Milvus vectors."""

    def __init__(self, settings: Optional[OrphanCleanupSettings] = None):
        self.settings = (settings or load_orphan_cleanup_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start scheduled cleanup when enabled."""
        if not self.settings.enabled:
            logger.info("Milvus orphan cleanup is disabled by config")
            return False
        if self._task and not self._task.done():
            return True

        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Milvus orphan cleanup manager started",
            extra={
                "interval_seconds": self.settings.interval_seconds,
                "batch_size": self.settings.batch_size,
                "dry_run": self.settings.dry_run,
                "collections": self.settings.collections,
                "max_scan_per_collection": self.settings.max_scan_per_collection,
                "max_delete_per_collection": self.settings.max_delete_per_collection,
            },
        )
        return True

    async def stop(self) -> None:
        """Stop scheduled cleanup."""
        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Milvus orphan cleanup manager stopped")

    async def run_once(self, *, reason: str = "manual") -> Dict[str, Any]:
        """Run one cleanup cycle in a worker thread."""
        async with self._run_lock:
            result = await asyncio.to_thread(run_orphan_cleanup_once, self.settings, reason=reason)
            level = logging.INFO if result.get("status") in {"ok", "disabled", "skipped"} else logging.WARNING
            logger.log(
                level,
                "Milvus orphan cleanup cycle finished",
                extra={
                    "status": result.get("status"),
                    "reason": reason,
                    "total_scanned": result.get("total_scanned"),
                    "total_orphans": result.get("total_orphans"),
                    "total_deleted": result.get("total_deleted"),
                    "duration_ms": result.get("duration_ms"),
                    "dry_run": result.get("dry_run"),
                    "skip_reason": result.get("skip_reason"),
                    "error": result.get("error"),
                },
            )
            return result

    async def _sleep_or_stop(self, seconds: int) -> bool:
        """Return ``True`` if shutdown requested during wait."""
        if seconds <= 0:
            return self._shutdown
        try:
            await asyncio.sleep(seconds)
            return self._shutdown
        except asyncio.CancelledError:
            return True

    async def _run_loop(self) -> None:
        """Background loop for periodic cleanup."""
        if self.settings.startup_delay_seconds > 0:
            should_stop = await self._sleep_or_stop(self.settings.startup_delay_seconds)
            if should_stop:
                return

        if self.settings.run_on_startup and not self._shutdown:
            try:
                await self.run_once(reason="startup")
            except Exception as exc:
                logger.warning("Startup orphan cleanup cycle failed: %s", exc)

        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled orphan cleanup cycle failed: %s", exc)


_cleanup_manager: Optional[OrphanVectorCleanupManager] = None
_cleanup_manager_lock = threading.Lock()


def get_orphan_cleanup_manager() -> OrphanVectorCleanupManager:
    """Return global orphan cleanup manager singleton."""
    global _cleanup_manager
    with _cleanup_manager_lock:
        if _cleanup_manager is None:
            _cleanup_manager = OrphanVectorCleanupManager()
        return _cleanup_manager


async def initialize_orphan_cleanup_manager() -> Optional[OrphanVectorCleanupManager]:
    """Initialize and start orphan cleanup manager if enabled."""
    manager = get_orphan_cleanup_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_orphan_cleanup_manager() -> None:
    """Shutdown orphan cleanup manager singleton."""
    global _cleanup_manager
    with _cleanup_manager_lock:
        manager = _cleanup_manager
        _cleanup_manager = None

    if manager is not None:
        await manager.stop()
