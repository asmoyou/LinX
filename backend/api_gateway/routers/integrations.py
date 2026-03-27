"""External channel webhook endpoints."""

from __future__ import annotations

import asyncio
import atexit
import heapq
import io
import json
import mimetypes
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.datastructures import Headers

from access_control.permissions import CurrentUser
from agent_framework.conversation_execution import build_conversation_execution_principal
from agent_framework.persistent_conversations import (
    build_default_conversation_title,
    get_persistent_conversation_runtime_service,
)
from api_gateway.feishu_publication_helpers import extract_feishu_message as _extract_feishu_message
from api_gateway.feishu_publication_helpers import (
    extract_feishu_message_from_long_connection_event as _extract_feishu_message_from_long_connection_event,
)
from api_gateway.feishu_publication_helpers import (
    load_publication_or_raise as _load_publication_or_raise,
)
from api_gateway.feishu_publication_helpers import publication_secrets as _publication_secrets
from api_gateway.feishu_publication_helpers import (
    resolve_public_web_base_url as _resolve_public_web_base_url,
)
from api_gateway.routers import agents as agents_router
from api_gateway.routers.agent_conversations import execute_persistent_conversation_turn
from database.connection import get_db_session
from database.models import (
    Agent,
    AgentChannelPublication,
    AgentConversation,
    AgentConversationMessage,
    ExternalConversationLink,
    User,
    UserBindingCode,
    UserExternalBinding,
)
from shared.binding_codes import hash_user_binding_code, normalize_user_binding_code
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

_FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
_TENANT_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}
_FEISHU_MAX_DIRECT_FILE_MESSAGES = 3
_FEISHU_MAX_DIRECT_FILE_SIZE_BYTES = 30 * 1024 * 1024
_FEISHU_FILE_DELIVERY_QUEUE_MAX_ATTEMPTS = 3
_FEISHU_FILE_DELIVERY_BASE_BACKOFF_SECONDS = 0.5
_FEISHU_FILE_DELIVERY_QUEUE_MAX_PENDING = 128
_FEISHU_IGNORED_ARTIFACT_ROOTS = {"input", "logs", "tasks"}
_FEISHU_IGNORED_ARTIFACT_NAMES = {
    ".linx_runtime",
    ".skills",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
_FEISHU_PROCESSING_REACTION_EMOJI_TYPES = ("EYES", "SMILE")
_FEISHU_EXECUTION_FAILURE_TEXT = "抱歉，刚才处理这条消息时失败了，请稍后重试。"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeishuApiError(RuntimeError):
    """Structured Feishu API failure with response context for retry and logging."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: int | None = None,
        log_id: str | None = None,
        response_preview: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.log_id = log_id
        self.response_preview = response_preview


@dataclass
class _QueuedFeishuFileDelivery:
    publication_id: str
    conversation_id: str
    chat_id: str
    artifact_path: str
    file_name: str
    file_bytes: bytes
    attempt: int = 1
    max_attempts: int = _FEISHU_FILE_DELIVERY_QUEUE_MAX_ATTEMPTS


@dataclass
class _PreparedFeishuExecutionInput:
    message_text: str
    files: list[UploadFile] = field(default_factory=list)
    input_message_text: str | None = None
    input_message_content_json: dict[str, Any] | None = None
    execution_task_text: str | None = None
    execution_intent_text: str | None = None
    title_seed_text: str | None = None
    direct_reply_text: str | None = None
    skip_execution_reason: str | None = None


class FeishuFileDeliveryRetryService:
    """Background retry queue for transient Feishu file delivery failures."""

    def __init__(self, *, max_pending: int = _FEISHU_FILE_DELIVERY_QUEUE_MAX_PENDING) -> None:
        self.max_pending = max(1, int(max_pending))
        self._condition = threading.Condition()
        self._pending: list[tuple[float, int, _QueuedFeishuFileDelivery]] = []
        self._sequence = 0
        self._shutdown = False
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        with self._condition:
            if self._worker and self._worker.is_alive():
                return
            self._shutdown = False
            self._worker = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="feishu-file-delivery-retry",
            )
            self._worker.start()
        logger.info("Feishu file delivery retry service started")

    def stop(self) -> None:
        worker: threading.Thread | None = None
        with self._condition:
            self._shutdown = True
            self._condition.notify_all()
            worker = self._worker
            self._worker = None
        if worker and worker.is_alive():
            worker.join(timeout=5)
        logger.info("Feishu file delivery retry service stopped")

    def enqueue(
        self,
        job: _QueuedFeishuFileDelivery,
        *,
        delay_seconds: float = 0.0,
    ) -> bool:
        self.start()
        run_at = time.monotonic() + max(0.0, float(delay_seconds))
        with self._condition:
            if len(self._pending) >= self.max_pending:
                return False
            self._sequence += 1
            heapq.heappush(self._pending, (run_at, self._sequence, job))
            self._condition.notify_all()
            return True

    def _run_loop(self) -> None:
        while True:
            job: _QueuedFeishuFileDelivery | None = None
            with self._condition:
                while not self._shutdown:
                    if not self._pending:
                        self._condition.wait()
                        continue
                    run_at, _, next_job = self._pending[0]
                    delay = run_at - time.monotonic()
                    if delay > 0:
                        self._condition.wait(timeout=delay)
                        continue
                    heapq.heappop(self._pending)
                    job = next_job
                    break
                if self._shutdown:
                    return

            if job is None:
                continue
            self._process_job(job)

    def _process_job(self, job: _QueuedFeishuFileDelivery) -> None:
        try:
            publication = _load_feishu_publication_for_retry(job.publication_id)
            if publication is None:
                logger.warning(
                    "Discarding queued Feishu file delivery because publication is unavailable",
                    extra={
                        "publication_id": job.publication_id,
                        "conversation_id": job.conversation_id,
                        "artifact_path": job.artifact_path,
                        "attempt": job.attempt,
                    },
                )
                return

            _send_feishu_file_bytes_message(
                publication,
                chat_id=job.chat_id,
                file_bytes=job.file_bytes,
                file_name=job.file_name,
            )
            logger.info(
                "Queued Feishu file delivery succeeded",
                extra={
                    "publication_id": job.publication_id,
                    "conversation_id": job.conversation_id,
                    "artifact_path": job.artifact_path,
                    "attempt": job.attempt,
                },
            )
        except Exception as exc:
            retryable = _is_retryable_feishu_file_delivery_error(exc)
            can_retry = retryable and job.attempt < job.max_attempts
            log_extra = {
                "publication_id": job.publication_id,
                "conversation_id": job.conversation_id,
                "artifact_path": job.artifact_path,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
                **_build_feishu_file_delivery_log_extra(exc),
            }
            if can_retry:
                next_attempt = _QueuedFeishuFileDelivery(
                    publication_id=job.publication_id,
                    conversation_id=job.conversation_id,
                    chat_id=job.chat_id,
                    artifact_path=job.artifact_path,
                    file_name=job.file_name,
                    file_bytes=job.file_bytes,
                    attempt=job.attempt + 1,
                    max_attempts=job.max_attempts,
                )
                delay_seconds = _get_feishu_file_delivery_retry_delay(job.attempt)
                if self.enqueue(next_attempt, delay_seconds=delay_seconds):
                    logger.warning(
                        "Queued Feishu file delivery failed; scheduled another retry: %s",
                        exc,
                        extra={
                            **log_extra,
                            "retry_delay_seconds": delay_seconds,
                        },
                    )
                    return
                logger.warning(
                    "Queued Feishu file delivery failed and retry queue is full: %s",
                    exc,
                    extra=log_extra,
                )
                return

            logger.warning(
                "Queued Feishu file delivery failed permanently: %s",
                exc,
                extra=log_extra,
            )


_feishu_file_delivery_retry_service: FeishuFileDeliveryRetryService | None = None


def _normalize_feishu_response_preview(value: str | None, *, max_chars: int = 240) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 1].rstrip()}…"


def _extract_feishu_log_id(response: requests.Response) -> str | None:
    return (
        str(response.headers.get("X-Tt-Logid") or response.headers.get("x-tt-logid") or "").strip()
        or None
    )


def _build_feishu_error_message(
    base_message: str,
    *,
    status_code: int | None,
    log_id: str | None,
    response_preview: str | None = None,
) -> str:
    details: list[str] = []
    if status_code is not None:
        details.append(f"http_status={status_code}")
    if log_id:
        details.append(f"log_id={log_id}")
    if response_preview:
        details.append(f"response={response_preview}")
    if not details:
        return base_message
    return f"{base_message} ({'; '.join(details)})"


def _format_feishu_api_error(payload: dict[str, Any], *, default_error: str) -> str:
    message = str(payload.get("msg") or "").strip()
    details: list[str] = []

    code = payload.get("code")
    if code not in (None, ""):
        details.append(f"code={code}")

    error = payload.get("error")
    if isinstance(error, dict):
        permission_violations = error.get("permission_violations")
        if isinstance(permission_violations, list):
            scopes = sorted(
                {
                    str(item.get("subject") or "").strip()
                    for item in permission_violations
                    if isinstance(item, dict) and str(item.get("subject") or "").strip()
                }
            )
            if scopes:
                details.append(f"missing_scopes={','.join(scopes)}")

    summary = f"{default_error}: {message}" if message else default_error
    if details:
        summary = f"{summary} ({'; '.join(details)})"
    return summary


def _parse_feishu_json_response(
    response: requests.Response,
    *,
    default_error: str,
) -> dict[str, Any]:
    status_code = response.status_code
    log_id = _extract_feishu_log_id(response)
    response_preview = _normalize_feishu_response_preview(getattr(response, "text", None))

    try:
        payload = response.json()
    except ValueError:
        raise FeishuApiError(
            _build_feishu_error_message(
                default_error,
                status_code=status_code,
                log_id=log_id,
                response_preview=response_preview,
            ),
            status_code=status_code,
            log_id=log_id,
            response_preview=response_preview,
        )

    if not isinstance(payload, dict):
        raise FeishuApiError(
            _build_feishu_error_message(
                default_error,
                status_code=status_code,
                log_id=log_id,
                response_preview=response_preview,
            ),
            status_code=status_code,
            log_id=log_id,
            response_preview=response_preview,
        )

    if status_code >= 400 or int(payload.get("code", 0) or 0) != 0:
        raise FeishuApiError(
            _build_feishu_error_message(
                _format_feishu_api_error(payload, default_error=default_error),
                status_code=status_code,
                log_id=log_id,
            ),
            status_code=status_code,
            error_code=int(payload.get("code", 0) or 0) or None,
            log_id=log_id,
            response_preview=response_preview,
        )

    return payload


def _is_retryable_feishu_status_code(status_code: int | None) -> bool:
    return status_code in {408, 429} or bool(status_code and status_code >= 500)


def _is_retryable_feishu_file_delivery_error(exc: Exception) -> bool:
    if isinstance(exc, FeishuApiError):
        return _is_retryable_feishu_status_code(exc.status_code)
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.RequestException):
        status_code = getattr(exc.response, "status_code", None)
        return _is_retryable_feishu_status_code(status_code)
    return False


def _get_feishu_file_delivery_retry_delay(attempt: int) -> float:
    return _FEISHU_FILE_DELIVERY_BASE_BACKOFF_SECONDS * (2 ** max(0, attempt - 1))


def get_feishu_file_delivery_retry_service() -> FeishuFileDeliveryRetryService:
    global _feishu_file_delivery_retry_service
    if _feishu_file_delivery_retry_service is None:
        _feishu_file_delivery_retry_service = FeishuFileDeliveryRetryService()
    return _feishu_file_delivery_retry_service


async def initialize_feishu_file_delivery_retry_service() -> FeishuFileDeliveryRetryService:
    service = get_feishu_file_delivery_retry_service()
    await asyncio.to_thread(service.start)
    return service


async def shutdown_feishu_file_delivery_retry_service() -> None:
    global _feishu_file_delivery_retry_service
    service = _feishu_file_delivery_retry_service
    if service is None:
        return
    await asyncio.to_thread(service.stop)
    _feishu_file_delivery_retry_service = None


def _stop_feishu_file_delivery_retry_service_at_exit() -> None:
    service = _feishu_file_delivery_retry_service
    if service is not None:
        try:
            service.stop()
        except Exception:
            pass


atexit.register(_stop_feishu_file_delivery_retry_service_at_exit)


def _build_feishu_file_delivery_log_extra(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, FeishuApiError):
        return {
            "feishu_http_status": exc.status_code,
            "feishu_error_code": exc.error_code,
            "feishu_log_id": exc.log_id,
            "feishu_response_preview": exc.response_preview,
            "feishu_retryable": _is_retryable_feishu_file_delivery_error(exc),
        }

    response = getattr(exc, "response", None)
    return {
        "feishu_http_status": getattr(response, "status_code", None),
        "feishu_log_id": (
            getattr(response, "headers", {}).get("X-Tt-Logid") if response is not None else None
        ),
        "feishu_retryable": _is_retryable_feishu_file_delivery_error(exc),
    }


def _classify_feishu_file_delivery_error(exc: Exception) -> str | None:
    message = str(exc)
    error_code = exc.error_code if isinstance(exc, FeishuApiError) else None
    status_code = exc.status_code if isinstance(exc, FeishuApiError) else None
    if (
        "im:resource:upload" in message
        or "missing_scopes=im:resource,im:resource:upload" in message
    ):
        return "当前飞书应用未开通文件上传权限，已改为发送文本结果和网页链接。"
    if error_code == 234006 or "file size exceed the max value" in message.lower():
        return "文件超过飞书 30MB 限制，已改为发送文本结果和网页链接。"
    if error_code == 234010 or "size can't be 0" in message.lower():
        return "文件为空，已改为发送文本结果和网页链接。"
    if error_code in {230013, 230017, 230027, 230035}:
        return "当前飞书会话不允许直接发送文件，已改为发送文本结果和网页链接。"
    if (status_code is not None and _is_retryable_feishu_status_code(status_code)) or isinstance(
        exc, (requests.Timeout, requests.ConnectionError)
    ):
        return "飞书文件接口暂时不可用，多次重试后仍失败，已改为发送文本结果和网页链接。"
    return None


def _queued_feishu_file_delivery_note() -> str:
    return "飞书文件接口暂时不可用，系统会在后台继续重试发送；当前先发送文本结果和网页链接。"


def _validate_feishu_verification_token(
    payload: dict[str, Any],
    publication: AgentChannelPublication,
) -> None:
    secrets = _publication_secrets(publication)
    expected_token = secrets.get("verification_token")
    if not expected_token:
        return
    received_token = payload.get("token") or (payload.get("header") or {}).get("token")
    if str(received_token or "") != expected_token:
        raise HTTPException(status_code=403, detail="Invalid Feishu verification token")


def _get_feishu_tenant_access_token(publication: AgentChannelPublication) -> str:
    cache_key = str(publication.publication_id)
    cached = _TENANT_TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > _utc_now():
        return cached[0]

    config = (
        dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
    )
    secrets = _publication_secrets(publication)
    app_id = str(config.get("app_id") or "").strip()
    app_secret = str(secrets.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("Feishu app credentials are incomplete")

    response = requests.post(
        f"{_FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    payload = _parse_feishu_json_response(
        response,
        default_error="Failed to fetch Feishu tenant access token",
    )

    token = str(payload.get("tenant_access_token") or "").strip()
    expire_seconds = int(payload.get("expire", 7200) or 7200)
    if not token:
        raise RuntimeError("Feishu tenant access token is missing")

    _TENANT_TOKEN_CACHE[cache_key] = (
        token,
        _utc_now() + timedelta(seconds=max(expire_seconds - 120, 60)),
    )
    return token


def _send_feishu_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    msg_type: str,
    content: str,
    default_error: str,
) -> None:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        json={
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": content,
        },
        timeout=20,
    )
    _parse_feishu_json_response(response, default_error=default_error)


def _send_feishu_text_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    text: str,
) -> None:
    _send_feishu_message(
        publication,
        chat_id=chat_id,
        msg_type="text",
        content=json.dumps({"text": text}, ensure_ascii=False),
        default_error="Failed to send Feishu message",
    )


def _normalize_feishu_card_markdown(markdown_text: str) -> str:
    normalized = str(markdown_text or "").strip()
    if not normalized:
        return ""

    def _normalize_table_line(line: str) -> str:
        stripped_line = line.strip()
        if stripped_line.count("|") < 2:
            return line
        if re.fullmatch(r"\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)*\s*\|?", stripped_line):
            return stripped_line

        cells = [cell.strip() for cell in stripped_line.strip("|").split("|")]
        cleaned_cells = []
        for cell in cells:
            cleaned = re.sub(r"`([^`]+)`", r"\1", cell)
            cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
            cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
            cleaned_cells.append(cleaned.strip())
        return f"| {' | '.join(cleaned_cells)} |"

    normalized = re.sub(
        r"(?m)^网页查看对话与工作区:\s*(https?://\S+)\s*$",
        lambda match: f"[网页查看对话与工作区]({match.group(1)})",
        normalized,
    )
    normalized_lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = str(raw_line or "").rstrip()
        stripped = line.strip()
        if not stripped:
            normalized_lines.append("")
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            normalized_lines.append("<hr>")
            continue
        banner_match = re.fullmatch(
            r"(?:[\W_]+?\s*)?\*\*(.+?)\*\*",
            stripped,
        )
        if banner_match and not stripped.startswith("#") and "|" not in stripped:
            normalized_lines.append(f"# {banner_match.group(1).strip()}")
            continue
        if stripped.count("|") >= 2:
            normalized_lines.append(_normalize_table_line(stripped))
            continue
        normalized_lines.append(line)

    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _is_feishu_markdown_table_separator(line: str) -> bool:
    stripped = str(line or "").strip()
    return bool(re.fullmatch(r"\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)+\s*\|?", stripped))


def _is_feishu_markdown_table_row(line: str) -> bool:
    stripped = str(line or "").strip()
    return stripped.count("|") >= 2 and not stripped.startswith("```")


def _split_feishu_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in str(line or "").strip().strip("|").split("|")]


def _flatten_feishu_markdown_tables(markdown_text: str) -> str:
    lines = str(markdown_text or "").splitlines()
    flattened: list[str] = []
    index = 0
    in_code_block = False

    while index < len(lines):
        line = lines[index]
        stripped = str(line or "").strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            flattened.append(line)
            index += 1
            continue

        if (
            not in_code_block
            and index + 1 < len(lines)
            and _is_feishu_markdown_table_row(line)
            and _is_feishu_markdown_table_separator(lines[index + 1])
        ):
            headers = _split_feishu_markdown_table_row(line)
            index += 2
            converted_rows: list[str] = []
            while index < len(lines) and _is_feishu_markdown_table_row(lines[index]):
                cells = _split_feishu_markdown_table_row(lines[index])
                if len(headers) == 2 and len(cells) >= 2:
                    converted_rows.append(f"- {cells[0]}: {cells[1]}")
                else:
                    pairs = []
                    for cell_index, cell in enumerate(cells):
                        if not cell:
                            continue
                        header = (
                            headers[cell_index]
                            if cell_index < len(headers)
                            else f"列{cell_index + 1}"
                        )
                        pairs.append(f"{header}: {cell}")
                    if pairs:
                        converted_rows.append(f"- {'；'.join(pairs)}")
                index += 1
            flattened.extend(converted_rows or [line])
            if flattened and flattened[-1] != "":
                flattened.append("")
            continue

        flattened.append(line)
        index += 1

    return re.sub(r"\n{3,}", "\n\n", "\n".join(flattened)).strip()


def _is_feishu_card_table_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    error_code = exc.error_code if isinstance(exc, FeishuApiError) else None
    return error_code == 230099 or "card table number over limit" in message


def _build_feishu_markdown_card_content(
    *,
    markdown_text: str,
) -> str:
    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": [
                {
                    "tag": "markdown",
                    "content": _normalize_feishu_card_markdown(markdown_text),
                    "text_align": "left",
                    "text_size": "normal",
                    "margin": "0px 0px 0px 0px",
                }
            ],
        },
    }
    return json.dumps(card, ensure_ascii=False)


def _send_feishu_markdown_card_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    markdown_text: str,
) -> None:
    normalized_markdown = _normalize_feishu_card_markdown(markdown_text)

    def _send_card(content_markdown: str) -> None:
        _send_feishu_message(
            publication,
            chat_id=chat_id,
            msg_type="interactive",
            content=_build_feishu_markdown_card_content(
                markdown_text=content_markdown,
            ),
            default_error="Failed to send Feishu message card",
        )

    try:
        _send_card(normalized_markdown)
    except FeishuApiError as exc:
        if not _is_feishu_card_table_limit_error(exc):
            raise
        flattened_markdown = _flatten_feishu_markdown_tables(normalized_markdown)
        if flattened_markdown == normalized_markdown:
            raise
        logger.warning(
            "Feishu card hit table limit; retrying with flattened markdown tables",
            extra={
                "publication_id": str(publication.publication_id),
                "chat_id": chat_id,
                "feishu_error_code": exc.error_code,
                "feishu_http_status": exc.status_code,
                "feishu_log_id": exc.log_id,
            },
        )
        _send_card(flattened_markdown)


def _send_feishu_file_bytes_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    file_bytes: bytes,
    file_name: str,
) -> None:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    upload_response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/files",
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        data={"file_type": "stream", "file_name": file_name},
        files={
            "file": (
                file_name,
                io.BytesIO(file_bytes),
                mimetypes.guess_type(file_name)[0] or "application/octet-stream",
            )
        },
        timeout=120,
    )
    upload_payload = _parse_feishu_json_response(
        upload_response,
        default_error="Failed to upload Feishu file",
    )

    file_key = (
        str((upload_payload.get("data") or {}).get("file_key") or "").strip()
        or str(upload_payload.get("file_key") or "").strip()
    )
    if not file_key:
        raise RuntimeError("Feishu file upload succeeded but file_key is missing")

    send_response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        json={
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
        },
        timeout=20,
    )
    _parse_feishu_json_response(send_response, default_error="Failed to send Feishu file message")


def _send_feishu_file_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    file_path: Path,
    file_name: str,
) -> None:
    _send_feishu_file_bytes_message(
        publication,
        chat_id=chat_id,
        file_bytes=file_path.read_bytes(),
        file_name=file_name,
    )


def _send_feishu_message_reaction(
    publication: AgentChannelPublication,
    *,
    message_id: str,
    emoji_type: str,
) -> None:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/messages/{message_id}/reactions",
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        json={"reaction_type": {"emoji_type": emoji_type}},
        timeout=20,
    )
    _parse_feishu_json_response(response, default_error="Failed to add Feishu message reaction")


def _try_add_feishu_processing_reaction(
    publication: AgentChannelPublication,
    *,
    message_id: str | None,
) -> None:
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        return

    for emoji_type in _FEISHU_PROCESSING_REACTION_EMOJI_TYPES:
        try:
            _send_feishu_message_reaction(
                publication,
                message_id=normalized_message_id,
                emoji_type=emoji_type,
            )
            return
        except Exception as exc:
            logger.debug(
                "Failed to add Feishu processing reaction",
                extra={
                    "message_id": normalized_message_id,
                    "emoji_type": emoji_type,
                    "error": str(exc),
                },
            )


def _user_can_access_agent(agent: Agent, user: User) -> bool:
    from access_control.agent_access import build_agent_access_context_for_user_id, can_read_agent

    with get_db_session() as session:
        context = build_agent_access_context_for_user_id(
            session=session,
            user_id=str(user.user_id),
            role=str(user.role or ""),
        )
        return can_read_agent(agent, context)


def _find_external_binding(
    session,
    *,
    publication_id: UUID,
    open_id: str | None,
    external_user_id: str | None,
    union_id: str | None,
) -> UserExternalBinding | None:
    query = session.query(UserExternalBinding).filter(
        UserExternalBinding.publication_id == publication_id
    )
    if open_id:
        row = query.filter(UserExternalBinding.external_open_id == open_id).first()
        if row:
            return row
    if external_user_id:
        row = query.filter(UserExternalBinding.external_user_id == external_user_id).first()
        if row:
            return row
    if union_id:
        row = query.filter(UserExternalBinding.external_union_id == union_id).first()
        if row:
            return row
    return None


def _load_feishu_publication_for_retry(publication_id: str) -> AgentChannelPublication | None:
    try:
        publication_uuid = UUID(str(publication_id))
    except (TypeError, ValueError):
        return None

    with get_db_session() as session:
        return (
            session.query(AgentChannelPublication)
            .filter(AgentChannelPublication.publication_id == publication_uuid)
            .filter(AgentChannelPublication.channel_type == "feishu")
            .filter(AgentChannelPublication.status == "published")
            .first()
        )


def _enqueue_feishu_file_delivery_retry(
    *,
    publication: AgentChannelPublication,
    conversation: AgentConversation,
    chat_id: str,
    artifact_path: str,
    local_path: Path,
) -> bool:
    try:
        file_bytes = local_path.read_bytes()
    except Exception as exc:
        logger.warning(
            "Failed to snapshot Feishu artifact for async retry: %s",
            exc,
            extra={
                "publication_id": str(publication.publication_id),
                "conversation_id": str(conversation.conversation_id),
                "artifact_path": artifact_path,
            },
        )
        return False

    job = _QueuedFeishuFileDelivery(
        publication_id=str(publication.publication_id),
        conversation_id=str(conversation.conversation_id),
        chat_id=chat_id,
        artifact_path=artifact_path,
        file_name=local_path.name,
        file_bytes=file_bytes,
    )
    queued = get_feishu_file_delivery_retry_service().enqueue(
        job,
        delay_seconds=_get_feishu_file_delivery_retry_delay(0),
    )
    if queued:
        logger.info(
            "Queued Feishu file delivery retry",
            extra={
                "publication_id": str(publication.publication_id),
                "conversation_id": str(conversation.conversation_id),
                "artifact_path": artifact_path,
                "initial_delay_seconds": _get_feishu_file_delivery_retry_delay(0),
                "max_attempts": job.max_attempts,
            },
        )
        return True

    logger.warning(
        "Feishu file delivery retry queue is full; skipping async retry",
        extra={
            "publication_id": str(publication.publication_id),
            "conversation_id": str(conversation.conversation_id),
            "artifact_path": artifact_path,
        },
    )
    return False


def _bind_user_from_code(
    session,
    *,
    publication: AgentChannelPublication,
    message_text: str,
    open_id: str | None,
    external_user_id: str | None,
    union_id: str | None,
    tenant_key: str | None,
) -> UserExternalBinding | None:
    normalized_code = normalize_user_binding_code(message_text)
    if not normalized_code:
        return None

    binding_code = (
        session.query(UserBindingCode)
        .filter(UserBindingCode.code_hash == hash_user_binding_code(normalized_code))
        .filter(UserBindingCode.status == "active")
        .first()
    )
    if binding_code is None:
        return None

    user = session.query(User).filter(User.user_id == binding_code.user_id).first()
    agent = session.query(Agent).filter(Agent.agent_id == publication.agent_id).first()
    if user is None or agent is None:
        return None
    if not _user_can_access_agent(agent, user):
        return None

    existing = _find_external_binding(
        session,
        publication_id=publication.publication_id,
        open_id=open_id,
        external_user_id=external_user_id,
        union_id=union_id,
    )
    now = _utc_now()
    if existing is None:
        existing = UserExternalBinding(
            user_id=user.user_id,
            channel_type="feishu",
            publication_id=publication.publication_id,
            external_user_id=external_user_id,
            external_open_id=open_id,
            external_union_id=union_id,
            tenant_key=tenant_key,
            metadata_json={"bound_via": "binding_code"},
            created_at=now,
            last_seen_at=now,
        )
        session.add(existing)
    else:
        existing.user_id = user.user_id
        existing.external_user_id = external_user_id
        existing.external_open_id = open_id
        existing.external_union_id = union_id
        existing.tenant_key = tenant_key
        existing.last_seen_at = now

    binding_code.last_used_at = now
    return existing


def _get_or_create_external_conversation(
    session,
    *,
    publication: AgentChannelPublication,
    binding: UserExternalBinding,
    chat_key: str,
    thread_key: str,
) -> AgentConversation:
    link = (
        session.query(ExternalConversationLink)
        .filter(ExternalConversationLink.publication_id == publication.publication_id)
        .filter(ExternalConversationLink.external_chat_key == chat_key)
        .filter(ExternalConversationLink.external_thread_key == thread_key)
        .first()
    )
    if link is not None:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == link.conversation_id)
            .first()
        )
        if conversation is not None:
            return conversation

    conversation = AgentConversation(
        agent_id=publication.agent_id,
        owner_user_id=binding.user_id,
        title=build_default_conversation_title(),
        status="active",
        source="feishu",
    )
    session.add(conversation)
    session.flush()

    session.add(
        ExternalConversationLink(
            publication_id=publication.publication_id,
            conversation_id=conversation.conversation_id,
            external_chat_key=chat_key,
            external_thread_key=thread_key,
        )
    )
    return conversation


def _conversation_already_processed(
    session,
    *,
    conversation_id: UUID,
    external_event_id: str | None,
) -> bool:
    if not external_event_id:
        return False
    row = (
        session.query(AgentConversationMessage)
        .filter(AgentConversationMessage.conversation_id == conversation_id)
        .filter(AgentConversationMessage.external_event_id == external_event_id)
        .first()
    )
    return row is not None


def _is_feishu_deliverable_artifact(entry: dict[str, Any]) -> bool:
    if not _is_feishu_sendable_artifact(entry, allow_input=False):
        return False

    path = str(entry.get("path") or "").strip().strip("/")
    parts = [part for part in path.split("/") if part]

    # Default auto-delivery should only send direct final files from /workspace/output.
    # Nested output trees often contain process artifacts (repos, temp assets, exports).
    return len(parts) == 2 and parts[0] == "output"


def _is_feishu_sendable_artifact(
    entry: dict[str, Any],
    *,
    allow_input: bool,
) -> bool:
    if bool(entry.get("is_directory") or entry.get("is_dir")):
        return False

    path = str(entry.get("path") or "").strip().strip("/")
    if not path:
        return False
    if agents_router._is_internal_workspace_path(path):
        return False

    parts = [part for part in path.split("/") if part]
    if not parts:
        return False

    if parts[0] in _FEISHU_IGNORED_ARTIFACT_ROOTS and (parts[0] != "input" or not allow_input):
        return False
    if any(part.startswith(".") or part in _FEISHU_IGNORED_ARTIFACT_NAMES for part in parts):
        return False
    return True


def _select_feishu_deliverable_artifacts(
    artifacts: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [entry for entry in (artifacts or []) if _is_feishu_deliverable_artifact(entry)]


def _select_feishu_explicitly_requested_artifacts(
    artifacts: list[dict[str, Any]] | None,
    *texts: str | None,
) -> list[dict[str, Any]]:
    candidates = [
        entry
        for entry in (artifacts or [])
        if _is_feishu_sendable_artifact(entry, allow_input=True)
    ]
    haystack = "\n".join(str(text or "") for text in texts).lower()
    if not haystack.strip():
        return []

    selected: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    by_name: dict[str, list[dict[str, Any]]] = {}
    for artifact in candidates:
        path = str(artifact.get("path") or "").strip()
        if not path:
            continue
        file_name = Path(path).name.lower()
        if file_name:
            by_name.setdefault(file_name, []).append(artifact)

        normalized_path = path.lower()
        if (
            normalized_path in haystack
            or f"/workspace/{normalized_path}" in haystack
            or f"workspace/{normalized_path}" in haystack
        ):
            selected.append(artifact)
            seen_paths.add(path)

    for file_name, matches in by_name.items():
        if len(matches) != 1 or file_name not in haystack:
            continue
        artifact = matches[0]
        path = str(artifact.get("path") or "").strip()
        if not path or path in seen_paths:
            continue
        selected.append(artifact)
        seen_paths.add(path)

    return selected


def _looks_like_feishu_file_send_request(text: str | None) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    has_send_intent = any(
        token in normalized
        for token in (
            "发我",
            "发给我",
            "给我发",
            "发送",
            "给我文件",
            "把文件给我",
            "download",
            "send me",
            "attach",
            "附件",
        )
    )
    has_file_hint = (
        bool(
            re.search(
                r"(/workspace/|workspace/|output/|shared/|input/|[\w.-]+\.(md|txt|pdf|docx?|xlsx?|pptx?|html|csv|json|zip))",
                normalized,
            )
        )
        or "文件" in normalized
        or "file" in normalized
    )
    return has_send_intent and has_file_hint


def _resolve_feishu_artifact_file_paths(
    conversation: AgentConversation,
    artifacts: list[dict[str, Any]] | None,
) -> list[tuple[dict[str, Any], Path]]:
    runtime = get_persistent_conversation_runtime_service().get_active_runtime(
        conversation.conversation_id
    )
    if runtime is None:
        return []

    resolved: list[tuple[dict[str, Any], Path]] = []
    for artifact in artifacts or []:
        artifact_path = str(artifact.get("path") or "").strip()
        if not artifact_path:
            continue
        try:
            local_path, _ = agents_router._resolve_safe_workspace_path(
                Path(runtime.workdir), artifact_path
            )
        except HTTPException:
            continue
        if not local_path.exists() or not local_path.is_file():
            continue
        resolved.append((artifact, local_path))
    return resolved


def _guess_feishu_attachment_filename(
    message: dict[str, Any], fallback_suffix: str = ".bin"
) -> str:
    content_payload = (
        dict(message.get("content_payload") or {})
        if isinstance(message.get("content_payload"), dict)
        else {}
    )
    for field_name in ("file_name", "audio_file_name", "name", "title"):
        value = str(content_payload.get(field_name) or "").strip()
        if value:
            return value
    message_id = str(
        message.get("message_id") or message.get("event_id") or "feishu_attachment"
    ).strip()
    return f"{message_id}{fallback_suffix}"


def _download_feishu_message_attachment(
    publication: AgentChannelPublication,
    *,
    message_id: str,
    file_key: str,
    resource_type: str,
) -> tuple[bytes, str | None]:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    response = requests.get(
        f"{_FEISHU_API_BASE}/im/v1/messages/{message_id}/resources/{file_key}",
        params={"type": resource_type},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        timeout=120,
    )
    content_type = str(response.headers.get("Content-Type") or "")
    if content_type.startswith("application/json"):
        _parse_feishu_json_response(
            response,
            default_error="Failed to download Feishu message attachment",
        )
        raise RuntimeError("Feishu attachment download returned JSON unexpectedly")
    response.raise_for_status()

    file_name = None
    content_disposition = str(response.headers.get("Content-Disposition") or "")
    if "filename=" in content_disposition:
        file_name = content_disposition.split("filename=", 1)[1].strip().strip('"')
    return response.content, file_name


def _is_supported_feishu_inbound_message_type(message_type: str | None) -> bool:
    normalized = str(message_type or "").strip().lower()
    return normalized in {"text", "file", "image", "audio"}


def _parse_feishu_message_timestamp(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_text_from_feishu_message_item(item: dict[str, Any]) -> str:
    body = dict(item.get("body") or {}) if isinstance(item.get("body"), dict) else {}
    raw_content = body.get("content") or "{}"
    try:
        parsed_content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except json.JSONDecodeError:
        parsed_content = {}
    if not isinstance(parsed_content, dict):
        return ""
    return str(parsed_content.get("text") or "").strip()


def _list_feishu_chat_messages(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    start_time: int | None = None,
    end_time: int | None = None,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    params: dict[str, Any] = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "sort_type": "ByCreateTimeDesc",
        "page_size": max(1, min(int(page_size), 50)),
    }
    if start_time is not None:
        params["start_time"] = str(start_time)
    if end_time is not None:
        params["end_time"] = str(end_time)

    response = requests.get(
        f"{_FEISHU_API_BASE}/im/v1/messages",
        params=params,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        timeout=30,
    )
    payload = _parse_feishu_json_response(
        response,
        default_error="Failed to list Feishu chat messages",
    )
    data = dict(payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}
    items = data.get("items")
    return list(items) if isinstance(items, list) else []


def _find_nearby_feishu_text_message(
    publication: AgentChannelPublication,
    *,
    message: dict[str, Any],
    window_ms: int = 8_000,
) -> dict[str, Any] | None:
    chat_id = str(message.get("chat_id") or "").strip()
    current_message_id = str(message.get("message_id") or "").strip()
    sender_open_id = str(message.get("open_id") or "").strip()
    current_create_time = _parse_feishu_message_timestamp(message.get("create_time"))
    if not chat_id or not current_message_id or current_create_time is None:
        return None

    items = _list_feishu_chat_messages(
        publication,
        chat_id=chat_id,
        start_time=max(0, current_create_time - window_ms),
        end_time=current_create_time + window_ms,
        page_size=20,
    )

    best_match: dict[str, Any] | None = None
    best_delta: int | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("message_id") or "").strip() == current_message_id:
            continue
        if str(item.get("msg_type") or "").strip().lower() != "text":
            continue

        sender = dict(item.get("sender") or {}) if isinstance(item.get("sender"), dict) else {}
        sender_id = str(sender.get("id") or "").strip()
        sender_type = str(sender.get("sender_type") or "").strip().lower()
        if sender_type != "user":
            continue
        if sender_open_id and sender_id and sender_id != sender_open_id:
            continue

        text = _extract_text_from_feishu_message_item(item)
        if not text:
            continue
        item_create_time = _parse_feishu_message_timestamp(item.get("create_time"))
        if item_create_time is None:
            continue
        delta = abs(item_create_time - current_create_time)
        if delta > window_ms:
            continue
        if best_delta is None or delta < best_delta:
            best_match = {
                "message_id": str(item.get("message_id") or "").strip(),
                "text": text,
                "create_time": item_create_time,
            }
            best_delta = delta

    return best_match


def _resolve_feishu_message_resource(
    message: dict[str, Any],
) -> tuple[str, str, str] | None:
    message_type = str(message.get("message_type") or "").strip().lower()
    content_payload = (
        dict(message.get("content_payload") or {})
        if isinstance(message.get("content_payload"), dict)
        else {}
    )

    resource_type = ""
    fallback_suffix = ".bin"
    candidate_keys: tuple[str, ...] = ()
    if message_type == "image":
        resource_type = "image"
        fallback_suffix = ".png"
        candidate_keys = ("image_key", "resource_key", "file_key")
    elif message_type == "file":
        resource_type = "file"
        fallback_suffix = ".bin"
        candidate_keys = ("file_key", "resource_key")
    elif message_type == "audio":
        # Feishu audio messages still download through the generic file resource endpoint.
        resource_type = "file"
        fallback_suffix = ".m4a"
        candidate_keys = ("audio_key", "file_key", "resource_key")
    else:
        return None

    resource_key = ""
    for key_name in candidate_keys:
        value = str(content_payload.get(key_name) or "").strip()
        if value:
            resource_key = value
            break
    if not resource_key:
        return None

    file_name = _guess_feishu_attachment_filename(message, fallback_suffix=fallback_suffix)
    return resource_type, resource_key, file_name


async def _prepare_feishu_message_uploads(
    *,
    publication: AgentChannelPublication,
    message: dict[str, Any],
) -> list[UploadFile]:
    resource = _resolve_feishu_message_resource(message)
    if resource is None:
        return []
    resource_type, resource_key, file_name = resource
    if resource_type not in {"file", "image"}:
        return []

    message_id = str(message.get("message_id") or "").strip()
    if not message_id:
        return []

    file_bytes, downloaded_name = await asyncio.to_thread(
        _download_feishu_message_attachment,
        publication,
        message_id=message_id,
        file_key=resource_key,
        resource_type=resource_type,
    )
    file_name = downloaded_name or file_name
    content_type = (
        "image/png"
        if resource_type == "image"
        else mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    )

    return [
        UploadFile(
            file=io.BytesIO(file_bytes),
            size=len(file_bytes),
            filename=file_name,
            headers=Headers({"content-type": content_type}),
        )
    ]


async def _transcribe_feishu_audio_message(
    *,
    publication: AgentChannelPublication,
    message: dict[str, Any],
) -> str:
    resource = _resolve_feishu_message_resource(message)
    if resource is None:
        raise RuntimeError("Feishu audio message is missing file_key")

    resource_type, resource_key, file_name = resource
    message_id = str(message.get("message_id") or "").strip()
    if not message_id:
        raise RuntimeError("Feishu audio message is missing message_id")

    audio_bytes, downloaded_name = await asyncio.to_thread(
        _download_feishu_message_attachment,
        publication,
        message_id=message_id,
        file_key=resource_key,
        resource_type=resource_type,
    )
    resolved_name = downloaded_name or file_name
    suffix = Path(resolved_name).suffix.lower() or ".m4a"

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = Path(temp_file.name)

        def _transcribe_audio_file(path: Path) -> str:
            from knowledge_base.audio_processor import get_audio_processor

            transcription = get_audio_processor().transcribe(path)
            return agents_router._sanitize_transcription_text(transcription.text)

        transcript_text = await asyncio.to_thread(_transcribe_audio_file, temp_path)
        if not transcript_text:
            raise RuntimeError("Speech transcription returned empty text")
        return transcript_text
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


async def _prepare_feishu_execution_input(
    *,
    publication: AgentChannelPublication,
    message: dict[str, Any],
) -> _PreparedFeishuExecutionInput:
    message_type = str(message.get("message_type") or "").strip().lower()
    original_text = str(message.get("text") or "").strip()
    if message_type != "audio":
        uploads = await _prepare_feishu_message_uploads(publication=publication, message=message)
        return _PreparedFeishuExecutionInput(message_text=original_text, files=uploads)

    nearby_text_message: dict[str, Any] | None = None
    if not original_text:
        try:
            nearby_text_message = await asyncio.to_thread(
                _find_nearby_feishu_text_message,
                publication,
                message=message,
            )
        except Exception as exc:
            logger.warning(
                "Failed to inspect nearby Feishu text messages for audio event: %s",
                exc,
                extra={
                    "publication_id": str(publication.publication_id),
                    "message_id": str(message.get("message_id") or ""),
                    "chat_id": str(message.get("chat_id") or ""),
                },
            )
        if nearby_text_message:
            logger.info(
                "Skipping Feishu audio event because a nearby text message is present",
                extra={
                    "publication_id": str(publication.publication_id),
                    "message_id": str(message.get("message_id") or ""),
                    "nearby_text_message_id": str(nearby_text_message.get("message_id") or ""),
                    "transcription_status": "skipped_nearby_text",
                },
            )
            return _PreparedFeishuExecutionInput(
                message_text="",
                skip_execution_reason="nearby_text_message_present",
            )

    voice_metadata: dict[str, Any] = {
        "messageType": message_type,
        "originalText": original_text,
        "transcriptText": None,
        "transcriptionStatus": "skipped",
        "transcriptionError": None,
        "contentPayloadKeys": sorted(
            key
            for key in (
                dict(message.get("content_payload") or {})
                if isinstance(message.get("content_payload"), dict)
                else {}
            ).keys()
            if str(key).strip()
        ),
    }

    try:
        transcript_text = await _transcribe_feishu_audio_message(
            publication=publication,
            message=message,
        )
    except Exception as exc:
        error_text = agents_router._trim_process_text(str(exc), max_chars=220)
        voice_metadata["transcriptionStatus"] = "failed"
        voice_metadata["transcriptionError"] = error_text
        logger.warning(
            "Feishu audio transcription failed: %s",
            exc,
            extra={
                "publication_id": str(publication.publication_id),
                "message_id": str(message.get("message_id") or ""),
                "message_type": message_type,
                "has_original_text": bool(original_text),
                "content_payload_keys": voice_metadata["contentPayloadKeys"],
                "transcription_status": "failed",
                "transcription_error": error_text,
            },
        )
        if original_text:
            return _PreparedFeishuExecutionInput(
                message_text=original_text,
                input_message_text=original_text,
                input_message_content_json={"feishuVoice": voice_metadata},
                execution_task_text=original_text,
                execution_intent_text=original_text,
                title_seed_text=original_text,
            )
        return _PreparedFeishuExecutionInput(
            message_text="",
            input_message_content_json={"feishuVoice": voice_metadata},
            direct_reply_text="语音转写失败，请补发文字消息。",
        )

    voice_metadata["transcriptText"] = transcript_text
    voice_metadata["transcriptionStatus"] = "succeeded"
    logger.info(
        "Feishu audio transcription succeeded",
        extra={
            "publication_id": str(publication.publication_id),
            "message_id": str(message.get("message_id") or ""),
            "message_type": message_type,
            "has_original_text": bool(original_text),
            "content_payload_keys": voice_metadata["contentPayloadKeys"],
            "transcription_status": "succeeded",
        },
    )

    if original_text:
        merged_text = f"{original_text}\n\n[语音转写]\n{transcript_text}"
        return _PreparedFeishuExecutionInput(
            message_text=original_text,
            input_message_text=original_text,
            input_message_content_json={"feishuVoice": voice_metadata},
            execution_task_text=merged_text,
            execution_intent_text=original_text,
            title_seed_text=original_text,
        )

    return _PreparedFeishuExecutionInput(
        message_text=transcript_text,
        input_message_text=transcript_text,
        input_message_content_json={"feishuVoice": voice_metadata},
        execution_task_text=transcript_text,
        execution_intent_text=transcript_text,
        title_seed_text=transcript_text,
    )


def _build_feishu_reply_text(
    *,
    agent: Agent,
    conversation: AgentConversation,
    output_text: str,
    request_text: str | None = None,
    delivered_artifacts: list[dict[str, Any]] | None,
    pending_artifacts: list[dict[str, Any]] | None,
    delivery_notes: list[str] | None = None,
    base_url: str | None = None,
) -> str:
    base_text = output_text.strip() or "Agent execution completed."
    delivered_items = [
        item for item in (delivered_artifacts or []) if str(item.get("path") or "").strip()
    ]
    deduped_notes = [note.strip() for note in (delivery_notes or []) if str(note).strip()]
    pending_paths = [
        str(item.get("path") or "").strip()
        for item in (pending_artifacts or [])
        if str(item.get("path") or "").strip()
    ]
    if delivered_items and not pending_paths and not deduped_notes:
        base_text = _sanitize_feishu_reply_for_delivered_files(
            request_text=request_text,
            reply_text=base_text,
            delivered_artifacts=delivered_items,
        )
        if not base_text:
            return ""
    if not pending_paths and not deduped_notes:
        return base_text

    note_block = "\n".join(f"- {note}" for note in deduped_notes[:3])
    more_notes = max(0, len(deduped_notes) - 3)
    if more_notes:
        note_block = f"{note_block}\n- 另外 {more_notes} 条说明"

    pending_labels = "\n".join(f"- {path}" for path in pending_paths[:5])
    more_count = max(0, len(pending_paths) - 5)
    summary_prefix = (
        "本轮还有部分产物未直接发送，可在网页查看："
        if delivered_artifacts
        else "本轮产生了以下文件："
    )
    if more_count:
        pending_labels = f"{pending_labels}\n- 另外 {more_count} 个文件"
    detail_blocks = [block for block in (note_block, pending_labels) if block]
    detail_text = "\n".join(detail_blocks)
    if not base_url:
        return f"{base_text}\n\n{summary_prefix}\n{detail_text}"

    conversation_url = f"{base_url.rstrip('/')}/workforce/{agent.agent_id}/conversations/{conversation.conversation_id}"
    return (
        f"{base_text}\n\n"
        f"{summary_prefix}\n{detail_text}\n\n"
        f"网页查看对话与工作区: {conversation_url}"
    )


def _should_suppress_feishu_file_request_reply(
    *,
    request_text: str | None,
    reply_text: str,
    delivered_artifacts: list[dict[str, Any]],
) -> bool:
    if not _looks_like_feishu_file_send_request(request_text):
        return False

    normalized_reply = str(reply_text or "").strip()
    if not normalized_reply:
        return True

    lowered_reply = normalized_reply.lower()
    if "```" in normalized_reply:
        return True

    artifact_hints: set[str] = set()
    for item in delivered_artifacts:
        path = str(item.get("path") or "").strip().lower()
        if not path:
            continue
        artifact_hints.add(path)
        artifact_hints.add(Path(path).name.lower())

    content_dump_tokens = (
        "完整代码",
        "完整内容",
        "全文如下",
        "代码如下",
        "源代码",
        "full code",
        "full content",
        "source code",
    )
    if any(token in lowered_reply for token in content_dump_tokens):
        return True

    has_artifact_hint = any(hint and hint in lowered_reply for hint in artifact_hints)

    if len(normalized_reply) >= 800 and (has_artifact_hint or normalized_reply.count("\n") >= 12):
        return True

    if has_artifact_hint:
        file_delivery_tokens = (
            "文件位置",
            "路径",
            "已找到",
            "attached",
            "found",
            "located",
        )
        return any(token in lowered_reply for token in file_delivery_tokens)

    return False


def _sanitize_feishu_reply_for_delivered_files(
    *,
    request_text: str | None,
    reply_text: str,
    delivered_artifacts: list[dict[str, Any]],
) -> str:
    normalized_reply = str(reply_text or "").strip()
    if not normalized_reply:
        return ""

    condensed_reply = _condense_feishu_delivered_file_reply(
        normalized_reply,
        delivered_artifacts=delivered_artifacts,
    )
    trimmed_reply = condensed_reply or _trim_feishu_file_content_dump(
        normalized_reply,
        delivered_artifacts=delivered_artifacts,
    )
    if not trimmed_reply:
        return ""

    if _should_suppress_feishu_file_request_reply(
        request_text=request_text,
        reply_text=trimmed_reply,
        delivered_artifacts=delivered_artifacts,
    ) or _should_suppress_feishu_delivery_confirmation(trimmed_reply, delivered_artifacts):
        return ""

    return trimmed_reply


def _condense_feishu_delivered_file_reply(
    text: str,
    *,
    delivered_artifacts: list[dict[str, Any]],
) -> str | None:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    lowered = normalized.lower()
    preview_markers = (
        "文档内容预览",
        "内容预览",
        "文档预览",
        "文件预览",
        "内容概览",
        "文档概览",
        "完整代码",
        "完整内容",
        "全文如下",
        "代码如下",
        "内容如下",
        "preview",
        "full code",
        "full content",
        "source code",
    )
    artifact_hints = {
        hint
        for item in delivered_artifacts
        for hint in (
            str(item.get("path") or "").strip().lower(),
            Path(str(item.get("path") or "").strip()).name.lower(),
        )
        if hint
    }
    heading_count = sum(
        1 for line in normalized.splitlines() if re.match(r"^\s{0,3}#{1,4}\s+\S", line)
    )
    has_preview_marker = "```" in normalized or any(token in lowered for token in preview_markers)
    has_artifact_hint = any(hint in lowered for hint in artifact_hints)
    looks_like_preview = has_preview_marker or (
        len(normalized) >= 600 and heading_count >= 4 and has_artifact_hint
    )
    if not looks_like_preview:
        return None

    intro = _extract_feishu_reply_intro_line(normalized)
    summary_intro = _normalize_feishu_delivery_summary_intro(
        intro,
        delivered_artifacts=delivered_artifacts,
    )
    outline_items = _extract_feishu_outline_items(normalized)
    if outline_items:
        return f"{summary_intro}\n\n内容概览：{'、'.join(outline_items[:5])}。"
    return summary_intro


def _extract_feishu_reply_intro_line(text: str) -> str:
    ignored_tokens = (
        "文件位置",
        "文件信息",
        "文件详情",
        "使用方式",
        "文件已保存到",
        "完整路径",
        "普通版",
        "双语版",
        "完整内容",
        "完整代码",
        "内容预览",
        "内容概览",
        "文档内容预览",
        "文档内容概览",
    )
    for raw_line in str(text or "").splitlines():
        line = _strip_feishu_markdown_text(raw_line)
        if not line or line == "---":
            continue
        if any(token in line for token in ignored_tokens):
            continue
        return line
    return ""


def _normalize_feishu_delivery_summary_intro(
    intro: str,
    *,
    delivered_artifacts: list[dict[str, Any]],
) -> str:
    cleaned = _strip_feishu_markdown_text(intro)
    if cleaned:
        cleaned = re.sub(
            r"(已为你准备好|已准备好|已找到|已创建|已生成|已输出|已完成)", "已发送", cleaned
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.lower() in {"report", "final report", "document", "overview", "preview"}:
        cleaned = ""
    if not cleaned or _is_feishu_delivery_boilerplate_line(cleaned, delivered_artifacts):
        if len(delivered_artifacts) == 1:
            return f"{Path(str(delivered_artifacts[0].get('path') or '')).name} 已发送。"
        return "文件已发送。"
    if not re.search(r"[。！？.!?]$", cleaned):
        cleaned = f"{cleaned}。"
    return cleaned


def _extract_feishu_outline_items(text: str) -> list[str]:
    lines = str(text or "").splitlines()
    items: list[str] = []
    seen: set[str] = set()
    preview_started = False
    preview_tokens = ("预览", "概览", "完整内容", "完整代码", "全文如下", "代码如下", "内容如下")
    ignored_tokens = (
        "文件位置",
        "文件信息",
        "文件详情",
        "使用方式",
        "文件已保存到",
        "完整路径",
        "普通版",
        "双语版",
    )

    for raw_line in lines:
        stripped = raw_line.strip()
        lowered = stripped.lower()
        if not preview_started and (
            "```" in stripped or any(token in stripped for token in preview_tokens)
        ):
            preview_started = True
            continue
        if not preview_started:
            continue

        heading_match = re.match(r"^\s{0,3}(#{1,4})\s+(.+?)\s*$", raw_line)
        numbered_match = re.match(r"^\s*\d+\.\s+(.+?)\s*$", raw_line)
        candidate = ""
        if heading_match:
            level = len(heading_match.group(1))
            if level >= 4:
                continue
            candidate = heading_match.group(2)
        elif numbered_match:
            candidate = numbered_match.group(1)
        else:
            continue

        cleaned = _clean_feishu_outline_item(candidate)
        if not cleaned:
            continue
        if any(token in cleaned for token in ignored_tokens):
            continue
        if any(token in lowered for token in ("```",)):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
        if len(items) >= 5:
            break

    return items


def _clean_feishu_outline_item(value: str) -> str:
    cleaned = _strip_feishu_markdown_text(value)
    if not cleaned:
        return ""
    cleaned = cleaned.split(" - ", 1)[0].strip()
    cleaned = cleaned.split("：", 1)[0].strip()
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.lower() in {"report", "final report", "document", "overview", "preview"}:
        return ""
    if len(cleaned) > 32:
        return ""
    return cleaned


def _strip_feishu_markdown_text(value: str) -> str:
    cleaned = str(value or "")
    cleaned = re.sub(r"[*_`#>\-]+", " ", cleaned)
    cleaned = re.sub(r"^[^\u4e00-\u9fffA-Za-z0-9]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_feishu_delivery_boilerplate_line(
    text: str,
    delivered_artifacts: list[dict[str, Any]],
) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    artifact_hints = {
        hint
        for item in delivered_artifacts
        for hint in (
            str(item.get("path") or "").strip().lower(),
            Path(str(item.get("path") or "").strip()).name.lower(),
        )
        if hint
    }
    boilerplate_tokens = (
        "文件位置",
        "路径",
        "已发送",
        "已找到",
        "attached",
        "found",
        "located",
        "saved",
        "generated",
        "created",
    )
    return any(token in lowered for token in boilerplate_tokens) and any(
        hint and hint in lowered for hint in artifact_hints
    )


def _trim_feishu_file_content_dump(
    text: str,
    *,
    delivered_artifacts: list[dict[str, Any]],
) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    dump_markers = (
        "```",
        "## 完整代码",
        "## 完整内容",
        "## 文档内容预览",
        "## 内容预览",
        "## 文档内容概览",
        "完整代码",
        "完整内容",
        "文档内容预览",
        "内容预览",
        "文档内容概览",
        "全文如下",
        "代码如下",
        "内容如下",
        "full code",
        "full content",
        "source code",
    )
    cut_positions = [
        normalized.find(marker) for marker in dump_markers if normalized.find(marker) >= 0
    ]
    if not cut_positions:
        return normalized

    prefix = normalized[: min(cut_positions)].strip()
    if not prefix:
        return ""

    lowered_prefix = prefix.lower()
    artifact_hints = {
        hint
        for item in delivered_artifacts
        for hint in (
            str(item.get("path") or "").strip().lower(),
            Path(str(item.get("path") or "").strip()).name.lower(),
        )
        if hint
    }
    boilerplate_tokens = (
        "文件位置",
        "路径",
        "已找到",
        "attached",
        "found",
        "located",
    )
    meaningful_tokens = (
        "总结",
        "概览",
        "概述",
        "说明",
        "建议",
        "风险",
        "结论",
        "changes",
        "summary",
        "overview",
        "notes",
    )
    has_boilerplate = any(token in lowered_prefix for token in boilerplate_tokens)
    has_artifact_hint = any(hint in lowered_prefix for hint in artifact_hints)
    has_meaningful_summary = any(token in lowered_prefix for token in meaningful_tokens)
    if has_boilerplate and has_artifact_hint and not has_meaningful_summary:
        return ""

    return prefix


def _should_suppress_feishu_delivery_confirmation(
    text: str,
    delivered_artifacts: list[dict[str, Any]],
) -> bool:
    raw_text = str(text or "").strip().lower()
    normalized = re.sub(r"[*_`#>|]+", " ", raw_text)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    if not normalized:
        return True
    if len(normalized) > 420:
        return False

    completion_tokens = (
        "已创建",
        "已生成",
        "已完成",
        "已输出",
        "已保存",
        "创建完成",
        "生成完成",
        "完成",
        "created",
        "generated",
        "finished",
        "saved",
        "done",
    )
    file_tokens = (
        "文件",
        "文档",
        "报告",
        "附件",
        "file",
        "document",
        "report",
        "attachment",
    )
    if not any(token in normalized for token in completion_tokens):
        return False
    if not any(token in normalized for token in file_tokens):
        return False

    artifact_hints: set[str] = set()
    for item in delivered_artifacts:
        path = str(item.get("path") or "").strip().lower()
        if path:
            artifact_hints.add(path)
            artifact_hints.add(Path(path).name.lower())

    return any(hint and hint in raw_text for hint in artifact_hints)


async def process_feishu_publication_message(
    publication_id: str | UUID,
    message: dict[str, Any],
    *,
    base_url: str | None = None,
) -> dict[str, Any]:
    with get_db_session() as session:
        publication = _load_publication_or_raise(session, str(publication_id))
        if publication.status != "published":
            return {"success": False, "ignored": True, "reason": "publication_inactive"}

        if message.get("chat_type") != "p2p":
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前仅支持飞书单聊接入，请使用单聊继续对话。",
            )
            return {"success": True, "ignored": True}
        message_type = str(message.get("message_type") or "").strip().lower()
        if not _is_supported_feishu_inbound_message_type(message_type):
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前支持文本、语音、图片和文件消息，请直接发送文本、语音或上传文件。",
            )
            return {"success": True, "ignored": True}

        await asyncio.to_thread(
            _try_add_feishu_processing_reaction,
            publication,
            message_id=message.get("message_id"),
        )

        binding = _find_external_binding(
            session,
            publication_id=publication.publication_id,
            open_id=message.get("open_id"),
            external_user_id=message.get("external_user_id"),
            union_id=message.get("union_id"),
        )
        if binding is None:
            binding = _bind_user_from_code(
                session,
                publication=publication,
                message_text=str(message.get("text") or ""),
                open_id=message.get("open_id"),
                external_user_id=message.get("external_user_id"),
                union_id=message.get("union_id"),
                tenant_key=message.get("tenant_key"),
            )
            if binding is None:
                session.commit()
                await asyncio.to_thread(
                    _send_feishu_text_message,
                    publication,
                    chat_id=str(message.get("chat_id") or ""),
                    text="请先发送用户识别码完成绑定。",
                )
                return {"success": True, "bound": False}

            session.commit()
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="绑定成功，后续消息将直接转发给 Agent。",
            )
            return {"success": True, "bound": True}

        binding.last_seen_at = _utc_now()
        user = session.query(User).filter(User.user_id == binding.user_id).first()
        agent = session.query(Agent).filter(Agent.agent_id == publication.agent_id).first()
        if user is None or agent is None:
            raise HTTPException(status_code=404, detail="Bound user or agent no longer exists")
        if not _user_can_access_agent(agent, user):
            session.commit()
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前绑定用户没有访问该 Agent 的权限，请刷新绑定或联系管理员。",
            )
            return {"success": True, "authorized": False}

        conversation = _get_or_create_external_conversation(
            session,
            publication=publication,
            binding=binding,
            chat_key=str(message.get("chat_id") or ""),
            thread_key=str(message.get("thread_key") or ""),
        )
        session.commit()
        session.refresh(conversation)

        if _conversation_already_processed(
            session,
            conversation_id=conversation.conversation_id,
            external_event_id=message.get("event_id"),
        ):
            return {"success": True, "duplicate": True}

        current_user = CurrentUser(
            user_id=str(user.user_id),
            username=user.username,
            role=user.role,
        )

    prepared_input = await _prepare_feishu_execution_input(
        publication=publication,
        message=message,
    )
    if prepared_input.skip_execution_reason:
        return {"success": True, "ignored": True, "reason": prepared_input.skip_execution_reason}
    if prepared_input.direct_reply_text:
        await asyncio.to_thread(
            _send_feishu_text_message,
            publication,
            chat_id=str(message.get("chat_id") or ""),
            text=prepared_input.direct_reply_text,
        )
        return {"success": True, "ignored": True, "reason": "audio_transcription_failed"}

    try:
        result = await execute_persistent_conversation_turn(
            conversation=conversation,
            principal=build_conversation_execution_principal(
                user_id=current_user.user_id,
                role=current_user.role,
                username=current_user.username,
            ),
            message=prepared_input.message_text,
            files=prepared_input.files,
            source="feishu",
            external_event_id=message.get("event_id"),
            input_message_text=prepared_input.input_message_text,
            input_message_content_json=prepared_input.input_message_content_json,
            execution_task_text=prepared_input.execution_task_text,
            execution_intent_text=prepared_input.execution_intent_text,
            title_seed_text=prepared_input.title_seed_text,
        )
        if result.get("duplicate"):
            return {"success": True, "duplicate": True}

        resolved_request_text = str(
            prepared_input.execution_task_text or prepared_input.message_text or ""
        ).strip()
        current_artifacts = list(result.get("artifacts") or [])
        delta_artifacts = _select_feishu_deliverable_artifacts(result.get("artifact_delta") or [])
        requested_artifacts = _select_feishu_explicitly_requested_artifacts(
            current_artifacts,
            resolved_request_text,
            str(result.get("output") or ""),
        )
        deliverable_artifacts: list[dict[str, Any]] = []
        seen_artifact_paths: set[str] = set()
        for artifact in [*delta_artifacts, *requested_artifacts]:
            path = str(artifact.get("path") or "").strip()
            if not path or path in seen_artifact_paths:
                continue
            deliverable_artifacts.append(artifact)
            seen_artifact_paths.add(path)

        resolved_deliverable_files = _resolve_feishu_artifact_file_paths(
            conversation,
            deliverable_artifacts,
        )
        sent_artifacts: list[dict[str, Any]] = []
        pending_artifacts: list[dict[str, Any]] = []
        delivery_notes: list[str] = []
        resolved_paths = {
            str(artifact.get("path") or "").strip() for artifact, _ in resolved_deliverable_files
        }
        pending_artifacts.extend(
            artifact
            for artifact in deliverable_artifacts
            if str(artifact.get("path") or "").strip() not in resolved_paths
        )

        for artifact, local_path in resolved_deliverable_files[:_FEISHU_MAX_DIRECT_FILE_MESSAGES]:
            if local_path.stat().st_size > _FEISHU_MAX_DIRECT_FILE_SIZE_BYTES:
                pending_artifacts.append(artifact)
                continue
            try:
                await asyncio.to_thread(
                    _send_feishu_file_message,
                    publication,
                    chat_id=str(message.get("chat_id") or ""),
                    file_path=local_path,
                    file_name=local_path.name,
                )
                sent_artifacts.append(artifact)
            except Exception as exc:
                logger.warning(
                    "Failed to send Feishu deliverable file: %s",
                    exc,
                    extra={
                        "publication_id": str(publication.publication_id),
                        "conversation_id": str(conversation.conversation_id),
                        "artifact_path": str(artifact.get("path") or ""),
                        **_build_feishu_file_delivery_log_extra(exc),
                    },
                )
                queued_for_retry = False
                if _is_retryable_feishu_file_delivery_error(exc):
                    queued_for_retry = await asyncio.to_thread(
                        _enqueue_feishu_file_delivery_retry,
                        publication=publication,
                        conversation=conversation,
                        chat_id=str(message.get("chat_id") or ""),
                        artifact_path=str(artifact.get("path") or ""),
                        local_path=local_path,
                    )
                if queued_for_retry:
                    delivery_notes.append(_queued_feishu_file_delivery_note())
                else:
                    delivery_note = _classify_feishu_file_delivery_error(exc)
                    if delivery_note:
                        delivery_notes.append(delivery_note)
                pending_artifacts.append(artifact)

        if len(resolved_deliverable_files) > _FEISHU_MAX_DIRECT_FILE_MESSAGES:
            pending_artifacts.extend(
                artifact
                for artifact, _ in resolved_deliverable_files[_FEISHU_MAX_DIRECT_FILE_MESSAGES:]
            )

        deduped_pending: list[dict[str, Any]] = []
        seen_pending_paths: set[str] = set()
        for artifact in pending_artifacts:
            path = str(artifact.get("path") or "").strip()
            if not path or path in seen_pending_paths:
                continue
            deduped_pending.append(artifact)
            seen_pending_paths.add(path)

        if (
            not deliverable_artifacts
            and not deduped_pending
            and not sent_artifacts
            and _looks_like_feishu_file_send_request(resolved_request_text)
        ):
            delivery_notes.append(
                "如果需要发送现有工作区文件，请在消息里写明文件名或路径，例如 output/report.md。"
            )

        reply_text = _build_feishu_reply_text(
            agent=agent,
            conversation=conversation,
            output_text=str(result.get("output") or ""),
            request_text=resolved_request_text,
            delivered_artifacts=sent_artifacts,
            pending_artifacts=deduped_pending,
            delivery_notes=delivery_notes,
            base_url=base_url or _resolve_public_web_base_url(),
        )
        if reply_text.strip():
            await asyncio.to_thread(
                _send_feishu_markdown_card_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                markdown_text=reply_text,
            )
        return {"success": True}
    except Exception as exc:
        log_extra = {
            "publication_id": str(publication.publication_id),
            "conversation_id": str(conversation.conversation_id),
            "agent_id": str(agent.agent_id),
            "event_id": str(message.get("event_id") or ""),
            "chat_id": str(message.get("chat_id") or ""),
        }
        logger.warning(
            "Feishu publication message execution failed: %s",
            exc,
            exc_info=True,
            extra=log_extra,
        )
        try:
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text=_FEISHU_EXECUTION_FAILURE_TEXT,
            )
        except Exception as notify_exc:
            logger.warning(
                "Failed to send Feishu execution failure notice: %s",
                notify_exc,
                exc_info=True,
                extra=log_extra,
            )
        return {"success": False, "error": str(exc)}


@router.post("/feishu/{publication_id}/events")
async def handle_feishu_events(publication_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    with get_db_session() as session:
        publication = _load_publication_or_raise(session, publication_id)
        if publication.status != "published":
            raise HTTPException(status_code=409, detail="Feishu publication is not active")
        _validate_feishu_verification_token(payload, publication)

        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        message = _extract_feishu_message(payload)
        if message is None:
            return {"success": True, "ignored": True}
    return await process_feishu_publication_message(
        publication_id,
        message,
        base_url=_resolve_public_web_base_url(request),
    )
