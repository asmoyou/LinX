"""Feishu long-connection manager for enterprise self-built apps."""

from __future__ import annotations

import asyncio
import hashlib
import multiprocessing
import os
import queue
import signal
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from database.connection import get_connection_pool, get_db_session
from database.models import AgentChannelPublication
from shared.config import get_config
from shared.logging import get_logger, setup_logging

logger = get_logger(__name__)

_LEADER_LOCK_ID = 8_142_611
_RUNTIME_CONFIG_KEY = "long_connection_runtime"


@dataclass(frozen=True)
class FeishuPublicationTarget:
    publication_id: str
    config_fingerprint: str


@dataclass
class ManagedFeishuWorker:
    publication_id: str
    config_fingerprint: str
    process: multiprocessing.process.BaseProcess


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_runtime_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _build_target_fingerprint(
    publication_id: str,
    *,
    app_id: str,
    app_secret_ciphertext: str,
) -> str:
    raw = f"{publication_id}:{app_id}:{app_secret_ciphertext}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def update_feishu_long_connection_runtime(
    publication_id: str,
    *,
    state: str | None = None,
    last_connected_at: datetime | None = None,
    last_event_at: datetime | None = None,
    last_error_at: datetime | None = None,
    last_error_message: str | None = None,
    clear_last_error: bool = False,
) -> None:
    try:
        publication_uuid = uuid.UUID(str(publication_id))
    except (TypeError, ValueError):
        return

    with get_db_session() as session:
        publication = (
            session.query(AgentChannelPublication)
            .filter(AgentChannelPublication.publication_id == publication_uuid)
            .filter(AgentChannelPublication.channel_type == "feishu")
            .first()
        )
        if publication is None:
            return

        config = (
            dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
        )
        runtime = dict(config.get(_RUNTIME_CONFIG_KEY) or {})
        runtime["updated_at"] = _serialize_runtime_timestamp(_utc_now())

        if state is not None:
            runtime["state"] = state
        if last_connected_at is not None:
            runtime["last_connected_at"] = _serialize_runtime_timestamp(last_connected_at)
        if last_event_at is not None:
            runtime["last_event_at"] = _serialize_runtime_timestamp(last_event_at)
        if last_error_at is not None:
            runtime["last_error_at"] = _serialize_runtime_timestamp(last_error_at)
        if last_error_message is not None:
            runtime["last_error_message"] = last_error_message
        elif clear_last_error:
            runtime.pop("last_error_message", None)
        if clear_last_error:
            runtime.pop("last_error_at", None)

        config[_RUNTIME_CONFIG_KEY] = runtime
        publication.config_json = config
        session.commit()


def _load_published_feishu_targets() -> dict[str, FeishuPublicationTarget]:
    from api_gateway.feishu_publication_helpers import publication_secrets

    with get_db_session() as session:
        rows = (
            session.query(AgentChannelPublication)
            .filter(AgentChannelPublication.channel_type == "feishu")
            .filter(AgentChannelPublication.status == "published")
            .all()
        )

    targets: dict[str, FeishuPublicationTarget] = {}
    for row in rows:
        config = dict(row.config_json or {}) if isinstance(row.config_json, dict) else {}
        decrypted_secrets = publication_secrets(row)
        if not config.get("app_id") or not decrypted_secrets.get("app_secret"):
            update_feishu_long_connection_runtime(
                str(row.publication_id),
                state="error",
                last_error_at=_utc_now(),
                last_error_message=(
                    "Feishu App Secret is missing or cannot be decrypted. "
                    "Re-enter the secret and save again."
                ),
            )
            logger.warning(
                "Skipping Feishu long-connection worker for incomplete publication",
                extra={"publication_id": str(row.publication_id)},
            )
            continue
        publication_id = str(row.publication_id)
        targets[publication_id] = FeishuPublicationTarget(
            publication_id=publication_id,
            config_fingerprint=_build_target_fingerprint(
                publication_id,
                app_id=str(config.get("app_id") or ""),
                app_secret_ciphertext=str(
                    (row.secret_encrypted_json or {}).get("app_secret") or ""
                ),
            ),
        )
    return targets


class FeishuLongConnectionManager:
    def __init__(self, *, poll_interval_seconds: int = 5, advisory_lock_id: int = _LEADER_LOCK_ID):
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))
        self.advisory_lock_id = advisory_lock_id
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._reconcile_event = asyncio.Event()
        self._leader_session = None
        self._workers: dict[str, ManagedFeishuWorker] = {}
        self._ctx = multiprocessing.get_context("spawn")

    async def start(self) -> bool:
        if self._task and not self._task.done():
            return True
        self._shutdown = False
        self._reconcile_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Feishu long-connection manager started",
            extra={"poll_interval_seconds": self.poll_interval_seconds},
        )
        return True

    async def stop(self) -> None:
        self._shutdown = True
        self.request_reconcile()
        if self._task and not self._task.done():
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def request_reconcile(self) -> None:
        self._reconcile_event.set()

    async def _run_loop(self) -> None:
        try:
            while not self._shutdown:
                try:
                    if not self._ensure_leader_lock():
                        await self._wait_for_reconcile_or_timeout()
                        continue
                    if not self._leader_session_is_healthy():
                        await asyncio.to_thread(self._stop_all_workers)
                        self._release_leader_lock()
                        await self._wait_for_reconcile_or_timeout()
                        continue

                    desired_targets = _load_published_feishu_targets()
                    await asyncio.to_thread(self._reconcile_workers, desired_targets)
                except Exception as exc:
                    logger.warning(
                        "Feishu long-connection reconciliation failed: %s",
                        exc,
                        exc_info=True,
                    )
                    await asyncio.to_thread(self._stop_all_workers)
                    self._release_leader_lock()
                await self._wait_for_reconcile_or_timeout()
        finally:
            await asyncio.to_thread(self._stop_all_workers)
            self._release_leader_lock()
            logger.info("Feishu long-connection manager stopped")

    async def _wait_for_reconcile_or_timeout(self) -> None:
        if self._shutdown:
            return
        try:
            await asyncio.wait_for(self._reconcile_event.wait(), timeout=self.poll_interval_seconds)
        except asyncio.TimeoutError:
            pass
        finally:
            self._reconcile_event.clear()

    def _ensure_leader_lock(self) -> bool:
        if self._leader_session is not None:
            return True

        session = get_connection_pool().get_raw_session()
        try:
            acquired = bool(
                session.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": self.advisory_lock_id},
                ).scalar()
            )
            if not acquired:
                session.close()
                return False
            self._leader_session = session
            logger.info("Feishu long-connection manager acquired advisory lock")
            return True
        except Exception:
            session.close()
            raise

    def _leader_session_is_healthy(self) -> bool:
        if self._leader_session is None:
            return False
        try:
            self._leader_session.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("Feishu long-connection leader lock session is unhealthy: %s", exc)
            return False

    def _release_leader_lock(self) -> None:
        if self._leader_session is None:
            return
        try:
            self._leader_session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": self.advisory_lock_id},
            )
        except Exception as exc:
            logger.warning("Failed to release Feishu advisory lock cleanly: %s", exc)
        finally:
            self._leader_session.close()
            self._leader_session = None

    def _reconcile_workers(self, desired_targets: dict[str, FeishuPublicationTarget]) -> None:
        desired_ids = set(desired_targets.keys())

        for publication_id in list(self._workers.keys()):
            if publication_id not in desired_ids:
                self._stop_worker(publication_id, reason="publication_unpublished")

        for publication_id, target in desired_targets.items():
            managed = self._workers.get(publication_id)
            if managed is not None:
                if not managed.process.is_alive():
                    self._stop_worker(publication_id, reason="worker_exited")
                    managed = None
                elif managed.config_fingerprint != target.config_fingerprint:
                    self._stop_worker(publication_id, reason="publication_updated")
                    managed = None

            if managed is None:
                self._start_worker(target)

    def _start_worker(self, target: FeishuPublicationTarget) -> None:
        process = self._ctx.Process(
            target=run_feishu_long_connection_worker,
            args=(target.publication_id,),
            daemon=True,
            name=f"feishu-long-connection-{target.publication_id[:8]}",
        )
        process.start()
        self._workers[target.publication_id] = ManagedFeishuWorker(
            publication_id=target.publication_id,
            config_fingerprint=target.config_fingerprint,
            process=process,
        )
        logger.info(
            "Started Feishu long-connection worker",
            extra={
                "publication_id": target.publication_id,
                "pid": process.pid,
            },
        )
        update_feishu_long_connection_runtime(target.publication_id, state="connecting")

    def _stop_worker(self, publication_id: str, *, reason: str) -> None:
        managed = self._workers.pop(publication_id, None)
        if managed is None:
            return

        process = managed.process
        try:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
        except Exception as exc:
            logger.warning(
                "Failed to stop Feishu worker",
                extra={"publication_id": publication_id, "reason": reason, "error": str(exc)},
            )
        if reason == "publication_unpublished":
            update_feishu_long_connection_runtime(
                publication_id,
                state="inactive",
                clear_last_error=True,
            )
        logger.info(
            "Stopped Feishu long-connection worker",
            extra={"publication_id": publication_id, "reason": reason},
        )

    def _stop_all_workers(self) -> None:
        for publication_id in list(self._workers.keys()):
            self._stop_worker(publication_id, reason="manager_shutdown")


def _load_worker_credentials(publication_id: str) -> tuple[str, str]:
    from api_gateway.feishu_publication_helpers import (
        load_publication_or_raise,
        publication_secrets,
    )

    with get_db_session() as session:
        publication = load_publication_or_raise(session, publication_id)
        if publication.status != "published":
            raise RuntimeError(f"Feishu publication {publication_id} is not published")

        config = (
            dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
        )
        secrets = publication_secrets(publication)
        app_id = str(config.get("app_id") or "").strip()
        app_secret = str(secrets.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            raise RuntimeError(f"Feishu publication {publication_id} has incomplete credentials")
        return app_id, app_secret


def _normalize_optional_config_text(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("${") and text.endswith("}"):
        return ""
    return text


def _resolve_feishu_long_connection_proxy() -> tuple[str, str | bool | None]:
    config = get_config()
    proxy_mode = (
        _normalize_optional_config_text(os.getenv("FEISHU_LONG_CONNECTION_PROXY_MODE"))
        or _normalize_optional_config_text(
            config.get("integrations.feishu.long_connection.proxy_mode", "system")
        )
        or "system"
    ).lower()
    proxy_url = _normalize_optional_config_text(
        os.getenv("FEISHU_LONG_CONNECTION_PROXY_URL")
    ) or _normalize_optional_config_text(
        config.get("integrations.feishu.long_connection.proxy_url", "")
    )

    if proxy_mode == "direct":
        return proxy_mode, None
    if proxy_mode == "system":
        return proxy_mode, True
    if proxy_mode == "explicit":
        if not proxy_url:
            raise RuntimeError(
                "Feishu long-connection proxy_url is required when proxy_mode=explicit"
            )
        return proxy_mode, proxy_url

    raise RuntimeError(
        "Unsupported Feishu long-connection proxy_mode. Use one of: direct, system, explicit."
    )


def _run_worker_message_consumer(
    *,
    publication_id: str,
    event_queue: queue.Queue[dict[str, str | None]],
    stop_event: threading.Event,
) -> None:
    from api_gateway.feishu_publication_helpers import resolve_public_web_base_url

    base_url = resolve_public_web_base_url()
    process_feishu_publication_message = None
    while not stop_event.is_set():
        try:
            message = event_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            if process_feishu_publication_message is None:
                from api_gateway.routers.integrations import (
                    process_feishu_publication_message as _process_feishu_publication_message,
                )

                process_feishu_publication_message = _process_feishu_publication_message
            asyncio.run(
                process_feishu_publication_message(
                    publication_id,
                    message,
                    base_url=base_url,
                )
            )
        except Exception as exc:
            logger.warning(
                "Feishu worker message processing failed: %s",
                exc,
                exc_info=True,
            )
        finally:
            event_queue.task_done()


def run_feishu_long_connection_worker(publication_id: str) -> None:
    from api_gateway.feishu_publication_helpers import (
        extract_feishu_message_from_long_connection_event,
    )
    import lark_oapi as lark
    import lark_oapi.ws.client as lark_ws_client
    from urllib.parse import parse_qs, urlparse

    import websockets

    config = get_config()
    setup_logging(config)

    stop_event = threading.Event()
    event_queue: queue.Queue[dict[str, str | None]] = queue.Queue(maxsize=256)

    def _handle_exit(signum, _frame) -> None:
        logger.info(
            "Received signal for Feishu long-connection worker shutdown",
            extra={"publication_id": publication_id, "signal": signum},
        )
        stop_event.set()
        raise SystemExit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_exit)

    consumer_thread = threading.Thread(
        target=_run_worker_message_consumer,
        kwargs={
            "publication_id": publication_id,
            "event_queue": event_queue,
            "stop_event": stop_event,
        },
        daemon=True,
        name=f"feishu-consumer-{publication_id[:8]}",
    )
    consumer_thread.start()

    try:
        update_feishu_long_connection_runtime(publication_id, state="connecting")

        app_id, app_secret = _load_worker_credentials(publication_id)
        proxy_mode, proxy = _resolve_feishu_long_connection_proxy()

        def on_message(event: lark.im.v1.P2ImMessageReceiveV1) -> None:
            message = extract_feishu_message_from_long_connection_event(event)
            if message is None:
                return
            update_feishu_long_connection_runtime(
                publication_id,
                state="connected",
                last_event_at=_utc_now(),
                clear_last_error=True,
            )
            try:
                event_queue.put_nowait(message)
            except queue.Full:
                logger.warning(
                    "Feishu worker queue is full; dropping event",
                    extra={"publication_id": publication_id, "event_id": message.get("event_id")},
                )

        class TrackingWsClient(lark.ws.Client):
            def __init__(
                self, *args, publication_id: str, stop_event: threading.Event, **kwargs
            ) -> None:
                super().__init__(*args, **kwargs)
                self._publication_id = publication_id
                self._stop_event = stop_event

            async def _connect(self) -> None:
                await self._lock.acquire()
                if self._conn is not None:
                    self._lock.release()
                    return

                update_feishu_long_connection_runtime(
                    self._publication_id,
                    state="connecting",
                )
                try:
                    conn_url = self._get_conn_url()
                    parsed = urlparse(conn_url)
                    query = parse_qs(parsed.query)
                    conn_id = query[lark_ws_client.DEVICE_ID][0]
                    service_id = query[lark_ws_client.SERVICE_ID][0]

                    conn = await websockets.connect(conn_url, proxy=proxy)
                    self._conn = conn
                    self._conn_url = conn_url
                    self._conn_id = conn_id
                    self._service_id = service_id

                    lark_ws_client.logger.info(self._fmt_log("connected to {}", conn_url))
                    lark_ws_client.loop.create_task(self._receive_message_loop())
                except websockets.InvalidStatusCode as exc:
                    update_feishu_long_connection_runtime(
                        self._publication_id,
                        state="error",
                        last_error_at=_utc_now(),
                        last_error_message=str(exc),
                    )
                    lark_ws_client._parse_ws_conn_exception(exc)
                except Exception as exc:
                    update_feishu_long_connection_runtime(
                        self._publication_id,
                        state="error",
                        last_error_at=_utc_now(),
                        last_error_message=str(exc),
                    )
                    raise
                else:
                    update_feishu_long_connection_runtime(
                        self._publication_id,
                        state="connected",
                        last_connected_at=_utc_now(),
                        clear_last_error=True,
                    )
                finally:
                    self._lock.release()

            async def _disconnect(self):
                had_connection = self._conn is not None
                await super()._disconnect()
                if self._stop_event.is_set() or not had_connection:
                    return
                update_feishu_long_connection_runtime(
                    self._publication_id,
                    state="connecting",
                )

        logger.info(
            "Starting Feishu long-connection worker",
            extra={
                "publication_id": publication_id,
                "app_id": app_id,
                "proxy_mode": proxy_mode,
                "proxy": (
                    proxy if isinstance(proxy, str) else ("system" if proxy is True else "direct")
                ),
            },
        )

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        client = TrackingWsClient(
            app_id,
            app_secret,
            publication_id=publication_id,
            stop_event=stop_event,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        client.start()
    except SystemExit:
        raise
    except Exception as exc:
        update_feishu_long_connection_runtime(
            publication_id,
            state="error",
            last_error_at=_utc_now(),
            last_error_message=str(exc),
        )
        raise


_manager: FeishuLongConnectionManager | None = None


def get_feishu_long_connection_manager() -> FeishuLongConnectionManager:
    global _manager
    if _manager is None:
        poll_interval_seconds = int(
            get_config().get("integrations.feishu.long_connection.poll_interval_seconds", 5) or 5
        )
        _manager = FeishuLongConnectionManager(poll_interval_seconds=poll_interval_seconds)
    return _manager


async def initialize_feishu_long_connection_manager() -> FeishuLongConnectionManager:
    manager = get_feishu_long_connection_manager()
    await manager.start()
    return manager


async def shutdown_feishu_long_connection_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.stop()
        _manager = None
