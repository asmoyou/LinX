"""Shared storage cleanup helpers for persistent conversations."""

from __future__ import annotations

import gzip
import io
import json
import logging
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from database.models import (
    AgentConversationMessage,
    AgentConversationMessageArchive,
    AgentConversationSnapshot,
)
from object_storage.minio_client import get_minio_client

logger = logging.getLogger(__name__)


def extract_attachment_storage_refs(attachments_json: Any) -> set[str]:
    refs: set[str] = set()
    if not isinstance(attachments_json, list):
        return refs
    for item in attachments_json:
        if not isinstance(item, dict):
            continue
        storage_ref = str(item.get("storage_ref") or "").strip()
        if storage_ref:
            refs.add(storage_ref)
    return refs


def _extract_archive_attachment_storage_refs(archive_ref: str) -> set[str]:
    minio = get_minio_client()
    parsed = minio.parse_object_reference(archive_ref)
    if not parsed:
        return set()

    bucket_name, object_key = parsed
    refs: set[str] = set()
    try:
        archive_stream, _ = minio.download_file(bucket_name, object_key)
        payload = archive_stream.read()
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            for raw_line in stream:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse compacted archive line for %s/%s",
                        bucket_name,
                        object_key,
                    )
                    continue
                refs.update(
                    extract_attachment_storage_refs(
                        record.get("attachments_json") or record.get("attachments")
                    )
                )
    except Exception as exc:
        logger.warning(
            "Failed to inspect compacted archive attachments for %s/%s: %s",
            bucket_name,
            object_key,
            exc,
        )
    return refs


def collect_conversation_storage_refs(
    session: Session,
    conversation_id: UUID,
) -> dict[str, set[str]]:
    snapshot_refs: set[str] = set()
    archive_refs: set[str] = set()
    attachment_refs: set[str] = set()

    snapshot_rows = (
        session.query(AgentConversationSnapshot.archive_ref, AgentConversationSnapshot.manifest_ref)
        .filter(AgentConversationSnapshot.conversation_id == conversation_id)
        .all()
    )
    for archive_ref, manifest_ref in snapshot_rows:
        if archive_ref:
            snapshot_refs.add(str(archive_ref))
        if manifest_ref:
            snapshot_refs.add(str(manifest_ref))

    attachment_rows = (
        session.query(AgentConversationMessage.attachments_json)
        .filter(AgentConversationMessage.conversation_id == conversation_id)
        .all()
    )
    for row in attachment_rows:
        attachments_json = row[0] if isinstance(row, tuple) else row
        attachment_refs.update(extract_attachment_storage_refs(attachments_json))

    archive_rows = (
        session.query(AgentConversationMessageArchive.archive_ref)
        .filter(AgentConversationMessageArchive.conversation_id == conversation_id)
        .all()
    )
    for row in archive_rows:
        archive_ref = row[0] if isinstance(row, tuple) else row
        if not archive_ref:
            continue
        archive_ref_text = str(archive_ref)
        archive_refs.add(archive_ref_text)
        attachment_refs.update(_extract_archive_attachment_storage_refs(archive_ref_text))

    return {
        "snapshot_refs": snapshot_refs,
        "archive_refs": archive_refs,
        "attachment_refs": attachment_refs,
    }


def delete_object_references(object_refs: Iterable[str]) -> dict[str, int]:
    minio = get_minio_client()
    deleted = 0
    failed = 0
    for ref in sorted({str(item).strip() for item in object_refs if str(item).strip()}):
        parsed = minio.parse_object_reference(ref)
        if not parsed:
            continue
        bucket_name, object_key = parsed
        try:
            minio.delete_file_versions(bucket_name, object_key)
            deleted += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "Failed to delete conversation object %s/%s: %s",
                bucket_name,
                object_key,
                exc,
            )
    return {"deleted": deleted, "failed": failed}


__all__ = [
    "collect_conversation_storage_refs",
    "delete_object_references",
    "extract_attachment_storage_refs",
]
