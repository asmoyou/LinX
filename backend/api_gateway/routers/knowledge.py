"""Knowledge Base Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.9: Create knowledge endpoints
"""

import asyncio
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, text

from access_control.knowledge_filter import (
    can_access_knowledge_item,
    check_knowledge_delete_permission,
    check_knowledge_write_permission,
    filter_knowledge_query,
)
from access_control.permissions import CurrentUser, get_current_user
from access_control.rbac import Action
from database.connection import get_db_session
from database.models import KnowledgeCollection, KnowledgeItem, User
from shared.config import get_config
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

_DEFAULT_SEARCH_MAX_CONCURRENT_REQUESTS = 4
_DEFAULT_SEARCH_REQUEST_TIMEOUT_SECONDS = 30.0


def _load_search_runtime_limits() -> tuple[int, float]:
    """Load per-process search runtime limits from config."""
    max_concurrent_requests = _DEFAULT_SEARCH_MAX_CONCURRENT_REQUESTS
    request_timeout_seconds = _DEFAULT_SEARCH_REQUEST_TIMEOUT_SECONDS

    try:
        config = get_config()
        kb_config = config.get_section("knowledge_base")
        search_cfg = kb_config.get("search", {})
        max_concurrent_requests = int(
            search_cfg.get("max_concurrent_requests", max_concurrent_requests)
        )
        request_timeout_seconds = float(
            search_cfg.get("request_timeout_seconds", request_timeout_seconds)
        )
    except Exception as e:
        logger.warning(
            f"Failed to load knowledge search runtime limits from config, using defaults: {e}"
        )

    max_concurrent_requests = max(max_concurrent_requests, 1)
    request_timeout_seconds = max(request_timeout_seconds, 1.0)
    return max_concurrent_requests, request_timeout_seconds


_SEARCH_MAX_CONCURRENT_REQUESTS, _SEARCH_REQUEST_TIMEOUT_SECONDS = _load_search_runtime_limits()
_SEARCH_REQUEST_SEMAPHORE = asyncio.Semaphore(_SEARCH_MAX_CONCURRENT_REQUESTS)
_THUMBNAIL_BACKFILL_RETRY_COOLDOWN_SECONDS = 60 * 60
_THUMBNAIL_BACKFILL_ERROR_MAX_LENGTH = 300
_MAX_UPLOAD_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200MB for non-archive uploads
_MAX_UPLOAD_ZIP_SIZE_BYTES = 3 * 1024 * 1024 * 1024  # 3GB for ZIP archives

# MIME type to document category mapping
MIME_TYPE_MAP = {
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
    "application/vnd.ms-excel": "document",
    "text/plain": "document",
    "text/markdown": "document",
    "image/jpeg": "document",
    "image/png": "document",
    "image/gif": "document",
    "audio/mpeg": "document",
    "audio/wav": "document",
    "audio/mp4": "document",
    "audio/x-m4a": "document",
    "audio/m4a": "document",
    "audio/flac": "document",
    "video/mp4": "document",
    "video/x-msvideo": "document",
    "video/quicktime": "document",
    "video/x-matroska": "document",
}

# MIME type to frontend DocumentType mapping
MIME_TO_DOC_TYPE = {
    "application/pdf": "pdf",
    "application/msword": "docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
    "application/vnd.ms-excel": "excel",
    "text/plain": "txt",
    "text/markdown": "md",
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "audio/mp4": "audio",
    "audio/x-m4a": "audio",
    "audio/m4a": "audio",
    "audio/flac": "audio",
    "video/mp4": "video",
    "video/x-msvideo": "video",
    "video/quicktime": "video",
    "video/x-matroska": "video",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
}

# File extension to frontend DocumentType mapping (fallback)
EXT_TO_DOC_TYPE = {
    ".pdf": "pdf",
    ".doc": "docx",
    ".docx": "docx",
    ".pptx": "ppt",
    ".xls": "excel",
    ".xlsx": "excel",
    ".txt": "txt",
    ".md": "md",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".mp4": "video",
    ".avi": "video",
    ".mov": "video",
    ".mkv": "video",
    ".zip": "zip",
}


class KnowledgeItemResponse(BaseModel):
    """Knowledge item response model matching frontend Document type."""

    id: str
    name: str
    type: str
    size: int
    status: str
    uploadedAt: str
    processedAt: Optional[str] = None
    owner: str
    accessLevel: str
    tags: Optional[List[str]] = None
    description: Optional[str] = None
    fileReference: Optional[str] = None
    thumbnailUrl: Optional[str] = None
    departmentId: Optional[str] = None
    collectionId: Optional[str] = None
    chunkCount: Optional[int] = None
    tokenCount: Optional[int] = None
    errorMessage: Optional[str] = None
    processingProgress: Optional[int] = None


class KnowledgeListResponse(BaseModel):
    """Paginated list response."""

    items: List[KnowledgeItemResponse]
    total: int
    page: int
    pageSize: int


class KnowledgeUpdateRequest(BaseModel):
    """Request to update knowledge item metadata."""

    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    access_level: Optional[str] = None
    department_id: Optional[str] = None
    collection_id: Optional[str] = None


class KnowledgeSearchFilters(BaseModel):
    """Semantic search filters."""

    type: Optional[List[str]] = None
    access_level: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    collection_id: Optional[str] = None
    document_ids: Optional[List[str]] = None


class KnowledgeSearchRequest(BaseModel):
    """Semantic search request."""

    query: str
    limit: int = Field(default=10, ge=1, le=100)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    filters: Optional[KnowledgeSearchFilters] = None


class KnowledgeSearchResultItem(BaseModel):
    """Single search result."""

    document_id: str
    document_title: Optional[str] = None
    content: str
    similarity_score: float
    chunk_index: int
    keywords: Optional[List[str]] = None
    summary: Optional[str] = None
    search_method: Optional[str] = None


class KnowledgeSearchResponse(BaseModel):
    """Search results response."""

    results: List[KnowledgeSearchResultItem]
    query: str
    total: int


class ProcessingStatusResponse(BaseModel):
    """Processing job status."""

    job_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    chunk_count: Optional[int] = None
    token_count: Optional[int] = None
    processed_at: Optional[str] = None
    progress_percent: Optional[int] = None


class CollectionCreateRequest(BaseModel):
    """Request to create a knowledge collection."""

    name: str
    description: Optional[str] = None
    access_level: Optional[str] = "private"
    department_id: Optional[str] = None


class CollectionUpdateRequest(BaseModel):
    """Request to update a knowledge collection."""

    name: Optional[str] = None
    description: Optional[str] = None
    access_level: Optional[str] = None
    department_id: Optional[str] = None


class CollectionResponse(BaseModel):
    """Knowledge collection response."""

    id: str
    name: str
    description: Optional[str] = None
    itemCount: int
    owner: str
    accessLevel: str
    departmentId: Optional[str] = None
    createdAt: str
    updatedAt: str


class CollectionListResponse(BaseModel):
    """Paginated collection list response."""

    collections: List[CollectionResponse]
    total: int
    page: int
    pageSize: int


class ZipUploadResponse(BaseModel):
    """Response for ZIP file upload."""

    collection: CollectionResponse
    items: List[KnowledgeItemResponse]
    skipped: List[str]
    errors: List[str]


def _normalize_content_type(content_type: Optional[str]) -> Optional[str]:
    """Normalize content type by dropping params and lower-casing."""
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _get_file_type(filename: str, content_type: Optional[str]) -> str:
    """Determine document type from MIME type or file extension."""
    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type and normalized_content_type in MIME_TO_DOC_TYPE:
        return MIME_TO_DOC_TYPE[normalized_content_type]

    import os

    ext = os.path.splitext(filename)[1].lower()
    return EXT_TO_DOC_TYPE.get(ext, "txt")


def _get_bucket_type(filename: str, content_type: Optional[str]) -> str:
    """Determine MinIO bucket type from MIME type or file extension.

    Maps file to the correct bucket (documents, images, audio, video)
    so MinIO's file type validation passes.
    """
    import os

    # Check MIME type first
    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type:
        if normalized_content_type.startswith("image/"):
            return "images"
        if normalized_content_type.startswith("audio/"):
            return "audio"
        if normalized_content_type.startswith("video/"):
            return "video"

    # Fallback: check file extension
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    image_exts = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
    audio_exts = {"mp3", "wav", "m4a", "flac"}
    video_exts = {"mp4", "avi", "mov", "mkv"}

    if ext in image_exts:
        return "images"
    if ext in audio_exts:
        return "audio"
    if ext in video_exts:
        return "video"

    return "documents"


def _get_content_type_category(filename: str, content_type: Optional[str]) -> str:
    """Map MIME type to knowledge item content_type category."""
    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type and normalized_content_type in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[normalized_content_type]
    return "document"


def _build_thumbnail_url(item_id: str, thumbnail_reference: Optional[str]) -> Optional[str]:
    """Build API thumbnail URL if thumbnail object exists."""
    if thumbnail_reference and str(thumbnail_reference).startswith("minio:"):
        return f"/api/v1/knowledge/{item_id}/thumbnail"
    return None


def _parse_minio_reference(reference: Optional[str]) -> Optional[tuple[str, str]]:
    """Parse `minio:<bucket>:<key>` reference into bucket/key tuple."""
    if not reference or not str(reference).startswith("minio:"):
        return None

    parts = str(reference).split(":", 2)
    if len(parts) != 3:
        return None

    _, bucket_name, object_key = parts
    if not bucket_name or not object_key:
        return None
    return bucket_name, object_key


def _is_legacy_word_doc(filename: str, mime_type: Optional[str]) -> bool:
    """Return True when source file is likely an old binary .doc file."""
    ext = os.path.splitext(filename or "")[1].lower()
    normalized = _normalize_content_type(mime_type)
    if ext == ".doc":
        return True
    return normalized == "application/msword" and ext != ".docx"


def _build_docx_filename(filename: str) -> str:
    """Build target filename for converted DOCX output."""
    stem = Path(filename or "document").stem or "document"
    return f"{stem}.docx"


def _convert_legacy_doc_bytes_to_docx(source_bytes: bytes, source_filename: str) -> bytes:
    """Convert binary .doc bytes to .docx bytes using host-native converters."""
    if not source_bytes:
        raise ValueError("Source DOC file is empty")

    source_suffix = Path(source_filename or "document.doc").suffix.lower() or ".doc"
    if source_suffix != ".doc":
        source_suffix = ".doc"

    with tempfile.TemporaryDirectory(prefix="kb_doc_to_docx_") as temp_dir:
        source_path = Path(temp_dir) / f"source{source_suffix}"
        source_path.write_bytes(source_bytes)

        output_filename = _build_docx_filename(source_filename)
        preferred_output_path = Path(temp_dir) / output_filename
        soffice_output_path = Path(temp_dir) / f"{source_path.stem}.docx"

        conversion_commands: list[tuple[str, list[str]]] = []
        soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice_bin:
            conversion_commands.append(
                (
                    "soffice",
                    [
                        soffice_bin,
                        "--headless",
                        "--convert-to",
                        "docx",
                        "--outdir",
                        str(temp_dir),
                        str(source_path),
                    ],
                )
            )
        textutil_bin = shutil.which("textutil")
        if textutil_bin:
            conversion_commands.append(
                (
                    "textutil",
                    [
                        textutil_bin,
                        "-convert",
                        "docx",
                        str(source_path),
                        "-output",
                        str(preferred_output_path),
                    ],
                )
            )

        attempts: list[str] = []
        for command_name, command in conversion_commands:
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )

                for candidate_path in (preferred_output_path, soffice_output_path):
                    if candidate_path.exists() and candidate_path.stat().st_size > 0:
                        return candidate_path.read_bytes()

                attempts.append(f"{command_name}: converted without output file")
            except Exception as ex:
                attempts.append(f"{command_name}: {ex}")

        details = "; ".join(attempts) if attempts else "no converter tool available"
        raise ValueError(
            "DOC to DOCX conversion failed. Install LibreOffice (soffice) or textutil. "
            f"Details: {details}"
        )


def _should_attempt_thumbnail_backfill(
    metadata: Dict[str, Any], *, now: Optional[datetime] = None
) -> bool:
    """Throttle repeated thumbnail backfill attempts after recent failures."""
    if metadata.get("thumbnail_reference"):
        return False

    last_error = metadata.get("thumbnail_backfill_last_error")
    if not last_error:
        return True

    raw_last_attempt = metadata.get("thumbnail_backfill_last_attempt_at")
    if not raw_last_attempt:
        return True

    try:
        last_attempt = datetime.fromisoformat(str(raw_last_attempt))
    except ValueError:
        return True

    if last_attempt.tzinfo is None:
        last_attempt = last_attempt.replace(tzinfo=timezone.utc)

    current_time = now or datetime.now(timezone.utc)
    elapsed_seconds = (current_time - last_attempt).total_seconds()
    return elapsed_seconds >= _THUMBNAIL_BACKFILL_RETRY_COOLDOWN_SECONDS


def _record_thumbnail_backfill_attempt(
    item: KnowledgeItem,
    metadata: Dict[str, Any],
    *,
    thumbnail_reference: Optional[str] = None,
    thumbnail_mime_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Persist result of a thumbnail backfill attempt to metadata."""
    updated_metadata: Dict[str, Any] = {
        **metadata,
        "thumbnail_backfill_last_attempt_at": datetime.now(timezone.utc).isoformat(),
    }

    if thumbnail_reference:
        updated_metadata["thumbnail_reference"] = thumbnail_reference
        updated_metadata["thumbnail_mime_type"] = thumbnail_mime_type or "image/jpeg"
        updated_metadata.pop("thumbnail_backfill_last_error", None)
    elif error_message:
        updated_metadata["thumbnail_backfill_last_error"] = str(error_message)[
            :_THUMBNAIL_BACKFILL_ERROR_MAX_LENGTH
        ]

    item.item_metadata = updated_metadata


def _backfill_thumbnail_for_item(item: KnowledgeItem) -> tuple[Optional[str], Optional[str]]:
    """Try generating thumbnail for existing media item when metadata lacks it."""
    metadata = dict(item.item_metadata or {})
    if not _should_attempt_thumbnail_backfill(metadata):
        return None, None

    file_reference_parts = _parse_minio_reference(item.file_reference)
    if not file_reference_parts:
        return None, None

    filename = metadata.get("original_filename") or item.title or "document"
    content_type = metadata.get("mime_type")
    file_type = metadata.get("file_type") or _get_file_type(filename, content_type)
    if file_type not in {"image", "pdf", "video"}:
        return None, None

    try:
        from object_storage.minio_client import get_minio_client

        minio_client = get_minio_client()
        source_bucket, source_key = file_reference_parts
        file_data, _ = minio_client.download_file(source_bucket, source_key)

        thumbnail_reference, thumbnail_mime_type = _upload_thumbnail_if_possible(
            minio_client=minio_client,
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            user_id=str(item.owner_user_id),
        )
        if not thumbnail_reference:
            _record_thumbnail_backfill_attempt(
                item,
                metadata,
                error_message="Thumbnail generation returned empty result",
            )
            return None, None

        _record_thumbnail_backfill_attempt(
            item,
            metadata,
            thumbnail_reference=thumbnail_reference,
            thumbnail_mime_type=thumbnail_mime_type,
        )
        return thumbnail_reference, thumbnail_mime_type
    except Exception as ex:
        _record_thumbnail_backfill_attempt(
            item,
            metadata,
            error_message=str(ex),
        )
        logger.warning(
            "Failed to backfill thumbnail for knowledge item",
            extra={"knowledge_id": str(item.knowledge_id), "error": str(ex)},
        )
        return None, None


def _generate_thumbnail_stream(
    file_data: Any,
    filename: str,
    content_type: Optional[str],
) -> Optional[tuple[io.BytesIO, str]]:
    """Generate a compact JPEG preview for image/pdf/video files."""
    import os
    import shutil
    import tempfile

    doc_type = _get_file_type(filename, content_type)
    if doc_type not in {"image", "pdf", "video"}:
        return None

    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("Pillow is not installed, skip thumbnail generation")
        return None

    thumb = io.BytesIO()
    try:
        file_data.seek(0)
        if doc_type == "image":
            image = Image.open(file_data)
        elif doc_type == "pdf":
            try:
                import fitz  # PyMuPDF
            except ImportError:
                logger.info("PyMuPDF is unavailable, skip PDF thumbnail generation")
                return None

            pdf_bytes = file_data.read()
            if not pdf_bytes:
                return None
            with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
                if pdf_doc.page_count == 0:
                    return None
                page = pdf_doc.load_page(0)
                pix = page.get_pixmap(dpi=120, alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
        else:
            try:
                try:
                    from moviepy.editor import VideoFileClip
                except ModuleNotFoundError:
                    from moviepy import VideoFileClip
            except ModuleNotFoundError:
                logger.info("moviepy is unavailable, skip video thumbnail generation")
                return None

            video_suffix = os.path.splitext(filename)[1] or ".mp4"
            with tempfile.NamedTemporaryFile(suffix=video_suffix, delete=False) as temp_video:
                temp_video_path = temp_video.name
                shutil.copyfileobj(file_data, temp_video)

            try:
                with VideoFileClip(temp_video_path) as video_clip:
                    duration = float(video_clip.duration or 0.0)
                    frame_time = 0.0
                    if duration > 0:
                        frame_time = min(1.0, duration * 0.1)
                        frame_time = min(frame_time, max(duration - 0.001, 0.0))
                    frame = video_clip.get_frame(frame_time)
                image = Image.fromarray(frame)
            finally:
                try:
                    os.remove(temp_video_path)
                except OSError:
                    pass

        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        if image.mode == "L":
            image = image.convert("RGB")
        image.thumbnail((512, 512))
        image.save(thumb, format="JPEG", quality=82, optimize=True)
        thumb.seek(0)
        return thumb, "image/jpeg"
    except Exception as ex:
        logger.warning(f"Failed to generate thumbnail for {filename}: {ex}")
        return None
    finally:
        try:
            file_data.seek(0)
        except Exception:
            pass


def _upload_thumbnail_if_possible(
    minio_client: Any,
    file_data: Any,
    filename: str,
    content_type: Optional[str],
    user_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Generate and upload thumbnail to MinIO images bucket."""
    generated = _generate_thumbnail_stream(
        file_data=file_data,
        filename=filename,
        content_type=content_type,
    )
    if not generated:
        return None, None

    import os

    thumb_stream, thumb_mime_type = generated
    thumb_name = f"{os.path.splitext(filename)[0] or 'preview'}_thumb.jpg"
    try:
        thumb_bucket, thumb_key = minio_client.upload_file(
            bucket_type="images",
            file_data=thumb_stream,
            filename=thumb_name,
            user_id=user_id,
            content_type=thumb_mime_type,
        )
        return f"minio:{thumb_bucket}:{thumb_key}", thumb_mime_type
    except Exception as ex:
        logger.warning(f"Thumbnail upload failed for {filename}: {ex}")
        return None, None


def _build_item_response(item: KnowledgeItem, owner_username: str) -> KnowledgeItemResponse:
    """Convert a KnowledgeItem DB model to an API response."""
    metadata = item.item_metadata or {}
    item_id = str(item.knowledge_id)
    file_size = metadata.get("file_size", 0)
    doc_type = metadata.get("file_type", "txt")
    tags = metadata.get("tags", [])
    description = metadata.get("description")
    thumbnail_reference = metadata.get("thumbnail_reference")
    processing_status = metadata.get("processing_status", "completed")
    chunk_count = metadata.get("chunk_count")
    token_count = metadata.get("token_count")
    error_message = metadata.get("error_message")
    processing_progress = metadata.get("processing_progress")
    if processing_progress is not None:
        try:
            processing_progress = int(processing_progress)
        except (TypeError, ValueError):
            processing_progress = None

    return KnowledgeItemResponse(
        id=item_id,
        name=item.title,
        type=doc_type,
        size=file_size,
        status=processing_status,
        uploadedAt=item.created_at.isoformat() if item.created_at else "",
        processedAt=item.updated_at.isoformat() if item.updated_at else None,
        owner=owner_username,
        accessLevel=_map_access_level(item.access_level),
        tags=tags if tags else None,
        description=description,
        fileReference=item.file_reference,
        thumbnailUrl=_build_thumbnail_url(item_id, thumbnail_reference),
        departmentId=str(item.department_id) if item.department_id else None,
        collectionId=str(item.collection_id) if item.collection_id else None,
        chunkCount=chunk_count,
        tokenCount=token_count,
        errorMessage=error_message,
        processingProgress=processing_progress,
    )


def _map_access_level(level: str) -> str:
    """Map backend access levels to frontend access levels."""
    mapping = {
        "private": "restricted",
        "team": "internal",
        "public": "public",
    }
    return mapping.get(level, level)


def _map_access_level_to_backend(level: str) -> str:
    """Map frontend access levels to backend access levels."""
    mapping = {
        "restricted": "private",
        "confidential": "private",
        "internal": "team",
        "public": "public",
        "private": "private",
        "team": "team",
    }
    return mapping.get(level, "private")


def _build_collection_response(
    collection: KnowledgeCollection, owner_username: str
) -> CollectionResponse:
    """Convert a KnowledgeCollection DB model to an API response."""
    return CollectionResponse(
        id=str(collection.collection_id),
        name=collection.name,
        description=collection.description,
        itemCount=collection.item_count,
        owner=owner_username,
        accessLevel=_map_access_level(collection.access_level),
        departmentId=str(collection.department_id) if collection.department_id else None,
        createdAt=collection.created_at.isoformat() if collection.created_at else "",
        updatedAt=collection.updated_at.isoformat() if collection.updated_at else "",
    )


def _refresh_collection_item_counts(session: Any, collection_ids: List[Optional[UUID]]) -> None:
    """Refresh denormalized item_count for the specified collections."""
    valid_ids = sorted({cid for cid in collection_ids if cid is not None}, key=str)
    if not valid_ids:
        return

    counts = {
        row.collection_id: int(row.item_count)
        for row in (
            session.query(
                KnowledgeItem.collection_id.label("collection_id"),
                func.count(KnowledgeItem.knowledge_id).label("item_count"),
            )
            .filter(KnowledgeItem.collection_id.in_(valid_ids))
            .group_by(KnowledgeItem.collection_id)
            .all()
        )
    }

    collections = (
        session.query(KnowledgeCollection)
        .filter(KnowledgeCollection.collection_id.in_(valid_ids))
        .all()
    )
    for collection in collections:
        collection.item_count = counts.get(collection.collection_id, 0)


def _enqueue_processing(
    item_id: str,
    bucket_name: str,
    object_key: str,
    mime_type: str,
    user_id: str,
) -> None:
    """Enqueue a knowledge item for processing via Redis or background thread."""
    try:
        from knowledge_base.processing_queue import get_processing_queue

        queue = get_processing_queue()
        queue.enqueue(
            document_id=item_id,
            file_key=object_key,
            bucket=bucket_name,
            mime_type=mime_type,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning(f"Redis queue unavailable, using background thread: {e}")
        import threading

        thread = threading.Thread(
            target=_process_document_background,
            args=(item_id, bucket_name, object_key, mime_type, user_id),
            daemon=True,
        )
        thread.start()


def _is_zip_file(filename: str, content_type: Optional[str]) -> bool:
    """Check if the uploaded file is a ZIP archive."""
    import os

    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type in ("application/zip", "application/x-zip-compressed"):
        return True
    ext = os.path.splitext(filename or "")[1].lower()
    return ext == ".zip"


def _get_upload_file_size(file: UploadFile) -> int:
    """Return upload size in bytes without changing final stream position."""
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    return size


def _handle_zip_upload(
    file_data,
    filename: str,
    collection_id_str: str,
    access_level: str,
    department_id_str: str,
    parsed_tags: list,
    description: str,
    current_user: CurrentUser,
) -> ZipUploadResponse:
    """Handle ZIP file upload: extract files, create collection if needed, upload each file."""
    import os

    from knowledge_base.zip_handler import extract_zip

    # Extract ZIP
    result = extract_zip(file_data)

    if not result.extracted_files and result.errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZIP extraction failed: {'; '.join(result.errors)}",
        )

    if not result.extracted_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP archive contains no supported files",
        )

    backend_access_level = _map_access_level_to_backend(access_level)

    # Parse department_id
    parsed_dept_id = None
    if department_id_str and department_id_str.strip():
        try:
            parsed_dept_id = UUID(department_id_str)
        except ValueError:
            pass

    # Parse collection_id
    parsed_collection_id = None
    if collection_id_str and collection_id_str.strip():
        try:
            parsed_collection_id = UUID(collection_id_str)
        except ValueError:
            pass

    with get_db_session() as session:
        # Create or use existing collection
        if parsed_collection_id:
            collection = (
                session.query(KnowledgeCollection)
                .filter(KnowledgeCollection.collection_id == parsed_collection_id)
                .first()
            )
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Collection not found",
                )
            if not check_knowledge_write_permission(
                current_user=current_user,
                owner_user_id=str(collection.owner_user_id),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to add files to this collection",
                )
        else:
            # Auto-create collection named after ZIP file (sans .zip extension)
            collection_name = os.path.splitext(filename)[0] or "Untitled Collection"
            collection = KnowledgeCollection(
                name=collection_name,
                description=description if description else None,
                owner_user_id=UUID(current_user.user_id),
                access_level=backend_access_level,
                department_id=parsed_dept_id,
                item_count=0,
            )
            session.add(collection)
            session.flush()

        items_response = []

        try:
            from object_storage.minio_client import get_minio_client

            minio_client = get_minio_client()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storage service unavailable: {str(e)}",
            )

        for extracted in result.extracted_files:
            processing_started_at = datetime.now(timezone.utc).isoformat()
            file_ext = os.path.splitext(extracted.filename)[1].lower()
            doc_type = EXT_TO_DOC_TYPE.get(file_ext, "txt")
            bucket_type = _get_bucket_type(extracted.filename, None)

            # Guess MIME type
            import mimetypes

            mime_type = mimetypes.guess_type(extracted.filename)[0] or "application/octet-stream"

            # Upload to MinIO
            try:
                extracted.data.seek(0)
                bucket_name, object_key = minio_client.upload_file(
                    bucket_type=bucket_type,
                    file_data=extracted.data,
                    filename=extracted.filename,
                    user_id=current_user.user_id,
                    content_type=mime_type,
                )
                file_reference = f"minio:{bucket_name}:{object_key}"
            except Exception as e:
                logger.warning(f"MinIO upload failed for {extracted.filename}: {e}")
                result.errors.append(f"Upload failed: {extracted.filename}")
                continue

            thumbnail_reference, thumbnail_mime_type = _upload_thumbnail_if_possible(
                minio_client=minio_client,
                file_data=extracted.data,
                filename=extracted.filename,
                content_type=mime_type,
                user_id=current_user.user_id,
            )

            # Create KnowledgeItem
            knowledge_item = KnowledgeItem(
                title=extracted.filename,
                content_type="document",
                file_reference=file_reference,
                owner_user_id=UUID(current_user.user_id),
                access_level=backend_access_level,
                department_id=parsed_dept_id,
                collection_id=collection.collection_id,
                item_metadata={
                    "file_size": extracted.size,
                    "file_type": doc_type,
                    "original_filename": extracted.filename,
                    "mime_type": mime_type,
                    "tags": parsed_tags,
                    "description": None,
                    "thumbnail_reference": thumbnail_reference,
                    "thumbnail_mime_type": thumbnail_mime_type,
                    "processing_status": "processing",
                    "processing_progress": 5,
                    "job_id": str(uuid4()),
                    "created_at": processing_started_at,
                    "started_at": processing_started_at,
                    "completed_at": None,
                },
            )
            session.add(knowledge_item)
            session.flush()

            item_id = str(knowledge_item.knowledge_id)

            # Enqueue processing
            _enqueue_processing(item_id, bucket_name, object_key, mime_type, current_user.user_id)

            items_response.append(
                KnowledgeItemResponse(
                    id=item_id,
                    name=extracted.filename,
                    type=doc_type,
                    size=extracted.size,
                    status="processing",
                    processingProgress=5,
                    uploadedAt=(
                        knowledge_item.created_at.isoformat() if knowledge_item.created_at else ""
                    ),
                    owner=current_user.username,
                    accessLevel=_map_access_level(backend_access_level),
                    tags=parsed_tags if parsed_tags else None,
                    thumbnailUrl=_build_thumbnail_url(item_id, thumbnail_reference),
                    collectionId=str(collection.collection_id),
                )
            )

        _refresh_collection_item_counts(session, [collection.collection_id])
        session.flush()

        # Get owner username for collection response
        owner = session.query(User).filter(User.user_id == collection.owner_user_id).first()
        owner_name = owner.username if owner else current_user.username

        collection_resp = _build_collection_response(collection, owner_name)

    return ZipUploadResponse(
        collection=collection_resp,
        items=items_response,
        skipped=result.skipped_files,
        errors=result.errors,
    )


def _process_document_background(
    document_id: str,
    bucket_name: str,
    object_key: str,
    mime_type: str,
    user_id: str,
    job_id: Optional[str] = None,
    job_created_at: Optional[str] = None,
) -> None:
    """Process document in background thread when Redis queue is unavailable."""
    try:
        from knowledge_base.document_processor_worker import get_processor_worker
        from knowledge_base.processing_queue import JobStatus, ProcessingJob

        worker = get_processor_worker()

        # Create a minimal job-like object for the worker pipeline
        local_job_id = job_id or str(uuid4())
        local_created_at = job_created_at or datetime.now(timezone.utc).isoformat()

        job = ProcessingJob(
            job_id=local_job_id,
            document_id=document_id,
            file_key=object_key,
            bucket=bucket_name,
            mime_type=mime_type,
            user_id=user_id,
            task_id=None,
            status=JobStatus.PROCESSING,
            created_at=local_created_at,
        )
        # Keep metadata timestamps coherent even without Redis queue worker.
        worker._update_knowledge_status(document_id, "processing")

        result_meta = worker._process_document(job)

        # Update status to completed
        worker._update_knowledge_status(
            document_id,
            "completed",
            chunk_count=result_meta.get("chunk_count", 0),
            token_count=result_meta.get("total_tokens", 0),
        )
        logger.info(f"Background processing completed for {document_id}")

    except Exception as ex:
        logger.error(f"Background processing failed for {document_id}: {ex}", exc_info=True)
        try:
            from knowledge_base.document_processor_worker import get_processor_worker

            worker = get_processor_worker()
            worker._update_knowledge_status(document_id, "failed", error_message=str(ex))
        except Exception:
            pass


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_knowledge(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    description: str = Form(default=""),
    tags: str = Form(default="[]"),
    access_level: str = Form(default="private"),
    department_id: str = Form(default=""),
    collection_id: str = Form(default=""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a knowledge document.

    Saves file to MinIO, creates KnowledgeItem record, enqueues processing.
    For ZIP files, extracts contents and creates a collection.
    """
    try:
        # Parse tags
        try:
            parsed_tags = json.loads(tags) if tags and tags != "[]" else []
        except json.JSONDecodeError:
            # Handle comma-separated tags
            parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

        file_size = _get_upload_file_size(file)

        # Check if ZIP file
        if _is_zip_file(file.filename or "", file.content_type):
            if file_size > _MAX_UPLOAD_ZIP_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"ZIP archive size exceeds maximum allowed "
                        f"({_MAX_UPLOAD_ZIP_SIZE_BYTES // (1024 * 1024 * 1024)}GB)"
                    ),
                )
            return _handle_zip_upload(
                file_data=file.file,
                filename=file.filename or "archive.zip",
                collection_id_str=collection_id,
                access_level=access_level,
                department_id_str=department_id,
                parsed_tags=parsed_tags,
                description=description,
                current_user=current_user,
            )

        if file_size > _MAX_UPLOAD_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File size exceeds maximum allowed "
                    f"({_MAX_UPLOAD_FILE_SIZE_BYTES // (1024 * 1024)}MB)"
                ),
            )

        # Use filename as title if not provided
        doc_title = title if title else file.filename or "Untitled"

        # Determine file type and content category
        doc_type = _get_file_type(file.filename or "", file.content_type)
        content_category = _get_content_type_category(file.filename or "", file.content_type)

        # Map access level to backend format
        backend_access_level = _map_access_level_to_backend(access_level)

        # Upload to MinIO
        minio_client = None
        upload_error_message: Optional[str] = None
        try:
            from object_storage.minio_client import get_minio_client

            minio_client = get_minio_client()

            # Determine bucket type based on MIME type / file extension
            bucket_type = _get_bucket_type(file.filename or "", file.content_type)

            bucket_name, object_key = minio_client.upload_file(
                bucket_type=bucket_type,
                file_data=file.file,
                filename=file.filename or "upload",
                user_id=current_user.user_id,
                content_type=file.content_type,
            )

            file_reference = f"minio:{bucket_name}:{object_key}"
        except ValueError as e:
            # File-type and validation errors are user-actionable; return immediately.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e
        except Exception as e:
            logger.warning(f"MinIO upload failed, storing reference only: {e}")
            upload_error_message = f"File storage upload failed: {str(e)}"
            file_reference = None
            bucket_name = ""
            object_key = ""

        thumbnail_reference = None
        thumbnail_mime_type = None
        if minio_client:
            thumbnail_reference, thumbnail_mime_type = _upload_thumbnail_if_possible(
                minio_client=minio_client,
                file_data=file.file,
                filename=file.filename or doc_title,
                content_type=file.content_type,
                user_id=current_user.user_id,
            )

        # Parse department_id
        parsed_dept_id = None
        if department_id and department_id.strip():
            try:
                parsed_dept_id = UUID(department_id)
            except ValueError:
                pass

        # Parse collection_id
        parsed_collection_id = None
        if collection_id and collection_id.strip():
            try:
                parsed_collection_id = UUID(collection_id)
            except ValueError:
                pass

        # Create database record
        with get_db_session() as session:
            if parsed_collection_id:
                collection = (
                    session.query(KnowledgeCollection)
                    .filter(KnowledgeCollection.collection_id == parsed_collection_id)
                    .first()
                )
                if not collection:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Collection not found",
                    )
                if not check_knowledge_write_permission(
                    current_user=current_user,
                    owner_user_id=str(collection.owner_user_id),
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to add files to this collection",
                    )

            knowledge_item = KnowledgeItem(
                title=doc_title,
                content_type=content_category,
                file_reference=file_reference,
                owner_user_id=UUID(current_user.user_id),
                access_level=backend_access_level,
                department_id=parsed_dept_id,
                collection_id=parsed_collection_id,
                item_metadata={
                    "file_size": file_size,
                    "file_type": doc_type,
                    "original_filename": file.filename,
                    "mime_type": file.content_type,
                    "tags": parsed_tags,
                    "description": description if description else None,
                    "thumbnail_reference": thumbnail_reference,
                    "thumbnail_mime_type": thumbnail_mime_type,
                    "processing_status": "uploading",
                    "processing_progress": 0,
                },
            )
            session.add(knowledge_item)
            session.flush()

            item_id = str(knowledge_item.knowledge_id)

            # Enqueue processing if MinIO upload succeeded
            if file_reference:
                try:
                    from knowledge_base.processing_queue import get_processing_queue

                    queue = get_processing_queue()
                    queue_job = queue.enqueue(
                        document_id=item_id,
                        file_key=object_key,
                        bucket=bucket_name,
                        mime_type=file.content_type or "application/octet-stream",
                        user_id=current_user.user_id,
                    )
                    now_iso = datetime.now(timezone.utc).isoformat()
                    # Update status to processing
                    knowledge_item.item_metadata = {
                        **knowledge_item.item_metadata,
                        "processing_status": "processing",
                        "processing_progress": 5,
                        "job_id": queue_job.job_id,
                        "created_at": queue_job.created_at,
                        "started_at": queue_job.started_at or now_iso,
                        "completed_at": None,
                    }
                except Exception as e:
                    logger.warning(f"Redis queue unavailable, falling back to sync processing: {e}")
                    fallback_started_at = datetime.now(timezone.utc).isoformat()
                    fallback_job_id = str(uuid4())
                    knowledge_item.item_metadata = {
                        **knowledge_item.item_metadata,
                        "processing_status": "processing",
                        "processing_progress": 5,
                        "job_id": fallback_job_id,
                        "created_at": fallback_started_at,
                        "started_at": fallback_started_at,
                        "completed_at": None,
                    }
                    # Flush to save the "processing" status before starting background work
                    session.flush()

                    # Start background processing thread
                    import threading

                    thread = threading.Thread(
                        target=_process_document_background,
                        args=(
                            item_id,
                            bucket_name,
                            object_key,
                            file.content_type or "application/octet-stream",
                            current_user.user_id,
                            fallback_job_id,
                            fallback_started_at,
                        ),
                        daemon=True,
                    )
                    thread.start()
            else:
                knowledge_item.item_metadata = {
                    **knowledge_item.item_metadata,
                    "processing_status": "failed",
                    "error_message": upload_error_message
                    or "File storage unavailable: upload failed",
                }

            _refresh_collection_item_counts(session, [parsed_collection_id])
            session.flush()

            response = KnowledgeItemResponse(
                id=item_id,
                name=doc_title,
                type=doc_type,
                size=file_size,
                status=knowledge_item.item_metadata.get("processing_status", "completed"),
                processingProgress=knowledge_item.item_metadata.get("processing_progress"),
                uploadedAt=(
                    knowledge_item.created_at.isoformat() if knowledge_item.created_at else ""
                ),
                owner=current_user.username,
                accessLevel=_map_access_level(backend_access_level),
                tags=parsed_tags if parsed_tags else None,
                description=description if description else None,
                fileReference=file_reference,
                thumbnailUrl=_build_thumbnail_url(item_id, thumbnail_reference),
                departmentId=department_id if department_id and department_id.strip() else None,
                collectionId=collection_id if collection_id and collection_id.strip() else None,
            )

        logger.info(
            f"Knowledge item created: {item_id}",
            extra={"user_id": current_user.user_id, "original_filename": file.filename},
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}",
        )


@router.get("", response_model=KnowledgeListResponse)
async def list_knowledge(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    access_level: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    collection_id: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List accessible knowledge items with filtering and pagination.

    collection_id filter:
      - Not provided: return all items (backward compatible)
      - "none": return only root-level items (no collection)
      - UUID: return items in that specific collection
    """
    try:
        with get_db_session() as session:
            query = session.query(KnowledgeItem)

            # Apply permission filtering
            user_attributes = {"department_id": department_id} if department_id else {}
            query = filter_knowledge_query(query, current_user, user_attributes=user_attributes)

            # Apply collection filter
            if collection_id is not None:
                if collection_id == "none":
                    query = query.filter(KnowledgeItem.collection_id.is_(None))
                else:
                    try:
                        coll_uuid = UUID(collection_id)
                        query = query.filter(KnowledgeItem.collection_id == coll_uuid)
                    except ValueError:
                        pass

            # Apply type filter
            if type_filter:
                query = query.filter(KnowledgeItem.content_type == type_filter)

            # Apply access level filter
            if access_level:
                backend_level = _map_access_level_to_backend(access_level)
                query = query.filter(KnowledgeItem.access_level == backend_level)

            # Apply department filter
            if department_id:
                try:
                    dept_uuid = UUID(department_id)
                    query = query.filter(KnowledgeItem.department_id == dept_uuid)
                except ValueError:
                    pass

            # Apply search filter (title search)
            if search:
                query = query.filter(KnowledgeItem.title.ilike(f"%{search}%"))

            # Get total count
            total = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            items = (
                query.order_by(KnowledgeItem.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )

            # Build owner username cache
            owner_ids = {item.owner_user_id for item in items}
            owners = {}
            if owner_ids:
                users = session.query(User).filter(User.user_id.in_(owner_ids)).all()
                owners = {str(u.user_id): u.username for u in users}

            # Build response
            response_items = []
            for item in items:
                owner_name = owners.get(str(item.owner_user_id), "Unknown")
                response_items.append(_build_item_response(item, owner_name))

            return KnowledgeListResponse(
                items=response_items,
                total=total,
                page=page,
                pageSize=page_size,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list knowledge items: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}",
        )


class KBConfigResponse(BaseModel):
    """Knowledge base pipeline configuration."""

    processing: dict
    chunking: dict
    parsing: dict
    enrichment: dict
    embedding: dict
    search: dict
    recommended: Optional[dict] = None


class KBConfigUpdateRequest(BaseModel):
    """Request to update KB pipeline configuration."""

    processing: Optional[dict] = None
    chunking: Optional[dict] = None
    parsing: Optional[dict] = None
    enrichment: Optional[dict] = None
    embedding: Optional[dict] = None
    search: Optional[dict] = None


_KB_RECOMMENDED_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "processing": {
        "transcription": {
            "enabled": True,
            "engine": "funasr",
            "model": "iic/SenseVoiceSmall",
            "provider": "",
            "language": "auto",
            "funasr_service_url": "http://127.0.0.1:10095",
            "funasr_service_timeout_seconds": 300,
            "funasr_service_api_key": "",
        },
    },
    "chunking": {
        "strategy": "semantic",
        "chunk_token_num": 512,
        "overlap_percent": 10,
    },
    "parsing": {
        "method": "auto",
        "output_language": "zh-CN",
    },
    "enrichment": {
        "enabled": True,
        "keywords_topn": 5,
        "questions_topn": 3,
        "generate_summary": True,
        "temperature": 0.2,
        "batch_size": 5,
        "max_tokens": 0,
    },
    "embedding": {
        "dimension": 1024,
    },
    "search": {
        "max_concurrent_requests": 4,
        "request_timeout_seconds": 30,
        "enable_semantic": True,
        "enable_fulltext": True,
        "combine_results": True,
        "semantic_weight": 0.7,
        "fulltext_weight": 0.3,
        "fusion_method": "rrf",
        "rrf_k": 60,
        "min_relevance_score": 0.3,
        "hybrid_score_scale": 0.02,
        "keyword_min_rank": 4.0,
        "keyword_max_terms": 16,
        "semantic_timeout_seconds": 8,
        "embedding_failure_backoff_seconds": 30,
        "rerank_enabled": True,
        "rerank_weight": 0.85,
        "rerank_top_k": 30,
        "rerank_timeout_seconds": 10,
        "rerank_failure_backoff_seconds": 60,
        "rerank_doc_max_chars": 1600,
        "cross_language_expansion_enabled": True,
        "cross_language_languages": ["en", "zh-CN"],
        "cross_language_provider": "",
        "cross_language_model": "",
        "cross_language_timeout_seconds": 4,
        "cross_language_failure_backoff_seconds": 60,
        "cross_language_max_expansions": 2,
        "cross_language_max_queries": 3,
    },
}


def _normalize_processing_config(processing_section: dict) -> dict:
    """Normalize legacy transcription config values for UI/runtime consistency."""
    normalized = dict(processing_section or {})
    transcription = dict(normalized.get("transcription", {}))

    raw_engine = str(transcription.get("engine", "funasr")).strip().lower()
    engine_aliases = {
        "local": "funasr",
        "local_funasr": "funasr",
        "whisper": "funasr",
        "local_whisper": "funasr",
        "openai": "openai_compatible",
        "remote": "openai_compatible",
        "llm": "openai_compatible",
    }
    effective_engine = engine_aliases.get(raw_engine, raw_engine or "funasr")
    transcription["engine"] = effective_engine

    if effective_engine == "funasr":
        whisper_models = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}
        raw_model = str(transcription.get("model", "")).strip()
        alias_models = {"funaudiollm/sensevoicesmall", "sensevoicesmall"}
        if (
            raw_engine in {"whisper", "local_whisper"}
            or not raw_model
            or raw_model in whisper_models
            or raw_model.lower() in alias_models
        ):
            transcription["model"] = "iic/SenseVoiceSmall"
        transcription["provider"] = str(transcription.get("provider", "")).strip()
        transcription["funasr_service_url"] = str(
            transcription.get("funasr_service_url", "http://127.0.0.1:10095")
        ).strip()
        transcription["funasr_service_api_key"] = str(
            transcription.get("funasr_service_api_key", "")
        ).strip()
        try:
            timeout_value = int(transcription.get("funasr_service_timeout_seconds", 300))
        except (TypeError, ValueError):
            timeout_value = 300
        transcription["funasr_service_timeout_seconds"] = max(5, timeout_value)
    elif effective_engine == "openai_compatible":
        transcription["model"] = (
            str(transcription.get("model", "FunAudioLLM/SenseVoiceSmall")).strip()
            or "FunAudioLLM/SenseVoiceSmall"
        )

    normalized["transcription"] = transcription
    return normalized


def _merge_kb_section_with_recommended(
    section_name: str,
    current_section: Optional[dict],
) -> dict:
    """Merge current config with recommended defaults for stable first-run experience."""
    defaults = dict(_KB_RECOMMENDED_DEFAULTS.get(section_name, {}))
    current = dict(current_section or {})

    def _deep_merge(base: dict, override: dict) -> dict:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    merged = _deep_merge(defaults, current)
    if section_name == "processing":
        return _normalize_processing_config(merged)
    return merged


@router.get("/config", response_model=KBConfigResponse)
async def get_kb_config(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get knowledge base pipeline configuration."""
    try:
        from shared.config import get_config

        config = get_config()
        kb_section = config.get_section("knowledge_base")

        return KBConfigResponse(
            processing=_merge_kb_section_with_recommended(
                "processing", kb_section.get("processing", {})
            ),
            chunking=_merge_kb_section_with_recommended("chunking", kb_section.get("chunking", {})),
            parsing=_merge_kb_section_with_recommended("parsing", kb_section.get("parsing", {})),
            enrichment=_merge_kb_section_with_recommended(
                "enrichment", kb_section.get("enrichment", {})
            ),
            embedding=_merge_kb_section_with_recommended(
                "embedding", kb_section.get("embedding", {})
            ),
            search=_merge_kb_section_with_recommended("search", kb_section.get("search", {})),
            recommended=_KB_RECOMMENDED_DEFAULTS,
        )
    except Exception as e:
        logger.error(f"Failed to get KB config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get configuration: {str(e)}",
        )


@router.put("/config", response_model=KBConfigResponse)
async def update_kb_config(
    update_data: KBConfigUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update knowledge base pipeline configuration. Requires admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update pipeline configuration",
        )

    try:
        import os

        import yaml

        from shared.config import reload_config

        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
        config_path = os.path.abspath(config_path)

        # Read current config file
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        kb = raw_config.setdefault("knowledge_base", {})

        # Merge updates into existing config
        if update_data.processing is not None:
            current_processing = dict(kb.get("processing", {}))
            for key, value in update_data.processing.items():
                if isinstance(value, dict) and isinstance(current_processing.get(key), dict):
                    current_processing[key] = {**current_processing.get(key, {}), **value}
                else:
                    current_processing[key] = value
            kb["processing"] = current_processing
        if update_data.chunking is not None:
            kb["chunking"] = {**kb.get("chunking", {}), **update_data.chunking}
        if update_data.parsing is not None:
            kb["parsing"] = {**kb.get("parsing", {}), **update_data.parsing}
        if update_data.enrichment is not None:
            kb["enrichment"] = {**kb.get("enrichment", {}), **update_data.enrichment}
        if update_data.embedding is not None:
            kb["embedding"] = {**kb.get("embedding", {}), **update_data.embedding}
        if update_data.search is not None:
            kb["search"] = {**kb.get("search", {}), **update_data.search}

        # Write back
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Reload config singleton
        config = reload_config(config_path)
        updated = config.get_section("knowledge_base")

        return KBConfigResponse(
            processing=_merge_kb_section_with_recommended(
                "processing", updated.get("processing", {})
            ),
            chunking=_merge_kb_section_with_recommended("chunking", updated.get("chunking", {})),
            parsing=_merge_kb_section_with_recommended("parsing", updated.get("parsing", {})),
            enrichment=_merge_kb_section_with_recommended(
                "enrichment", updated.get("enrichment", {})
            ),
            embedding=_merge_kb_section_with_recommended("embedding", updated.get("embedding", {})),
            search=_merge_kb_section_with_recommended("search", updated.get("search", {})),
            recommended=_KB_RECOMMENDED_DEFAULTS,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update KB config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}",
        )


# ============================================================
# Collection endpoints
# ============================================================


@router.post("/collections", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new knowledge collection."""
    try:
        backend_access_level = _map_access_level_to_backend(data.access_level or "private")

        parsed_dept_id = None
        if data.department_id:
            try:
                parsed_dept_id = UUID(data.department_id)
            except ValueError:
                pass

        with get_db_session() as session:
            collection = KnowledgeCollection(
                name=data.name,
                description=data.description,
                owner_user_id=UUID(current_user.user_id),
                access_level=backend_access_level,
                department_id=parsed_dept_id,
                item_count=0,
            )
            session.add(collection)
            session.flush()

            return _build_collection_response(collection, current_user.username)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create collection: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create collection: {str(e)}",
        )


@router.get("/collections", response_model=CollectionListResponse)
async def list_collections(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    department_id: Optional[str] = Query(default=None),
    access_level: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List accessible knowledge collections with filtering and pagination."""
    try:
        with get_db_session() as session:
            query = session.query(KnowledgeCollection)

            # Apply permission filtering (reuse same pattern as knowledge items)
            from access_control.rbac import ResourceType, Role, check_permission

            try:
                role = Role(current_user.role)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")

            # Admins see all, others see own + public + team
            if not check_permission(role, ResourceType.KNOWLEDGE, Action.READ, None):
                from sqlalchemy import or_

                conditions = [
                    KnowledgeCollection.owner_user_id == UUID(current_user.user_id),
                    KnowledgeCollection.access_level == "public",
                ]
                if department_id:
                    conditions.append(
                        (KnowledgeCollection.access_level == "team")
                        & (KnowledgeCollection.department_id == UUID(department_id))
                    )
                query = query.filter(or_(*conditions))

            # Apply filters
            if search:
                query = query.filter(KnowledgeCollection.name.ilike(f"%{search}%"))

            if department_id:
                try:
                    dept_uuid = UUID(department_id)
                    query = query.filter(KnowledgeCollection.department_id == dept_uuid)
                except ValueError:
                    pass

            if access_level:
                backend_level = _map_access_level_to_backend(access_level)
                query = query.filter(KnowledgeCollection.access_level == backend_level)

            total = query.count()

            offset = (page - 1) * page_size
            collections = (
                query.order_by(KnowledgeCollection.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )

            # Build owner username cache
            owner_ids = {c.owner_user_id for c in collections}
            owners = {}
            if owner_ids:
                users = session.query(User).filter(User.user_id.in_(owner_ids)).all()
                owners = {str(u.user_id): u.username for u in users}

            response_items = []
            for c in collections:
                owner_name = owners.get(str(c.owner_user_id), "Unknown")
                response_items.append(_build_collection_response(c, owner_name))

            return CollectionListResponse(
                collections=response_items,
                total=total,
                page=page,
                pageSize=page_size,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list collections: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {str(e)}",
        )


@router.get("/collections/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a single collection by ID."""
    try:
        with get_db_session() as session:
            try:
                cid = UUID(collection_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid collection ID format"
                )

            collection = (
                session.query(KnowledgeCollection)
                .filter(KnowledgeCollection.collection_id == cid)
                .first()
            )
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
                )

            owner = session.query(User).filter(User.user_id == collection.owner_user_id).first()
            owner_name = owner.username if owner else "Unknown"

            return _build_collection_response(collection, owner_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection: {str(e)}",
        )


@router.put("/collections/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: str,
    update_data: CollectionUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a collection's metadata."""
    try:
        with get_db_session() as session:
            try:
                cid = UUID(collection_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid collection ID format"
                )

            collection = (
                session.query(KnowledgeCollection)
                .filter(KnowledgeCollection.collection_id == cid)
                .first()
            )
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
                )

            # Check ownership or admin
            if not check_knowledge_write_permission(
                current_user=current_user,
                owner_user_id=str(collection.owner_user_id),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to update this collection",
                )

            if update_data.name is not None:
                collection.name = update_data.name
            if update_data.description is not None:
                collection.description = update_data.description
            if update_data.access_level is not None:
                collection.access_level = _map_access_level_to_backend(update_data.access_level)
            if update_data.department_id is not None:
                try:
                    collection.department_id = (
                        UUID(update_data.department_id) if update_data.department_id else None
                    )
                except ValueError:
                    pass

            session.flush()

            owner = session.query(User).filter(User.user_id == collection.owner_user_id).first()
            owner_name = owner.username if owner else "Unknown"

            return _build_collection_response(collection, owner_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update collection: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update collection: {str(e)}",
        )


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a collection and all its items (cascade)."""
    try:
        with get_db_session() as session:
            try:
                cid = UUID(collection_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid collection ID format"
                )

            collection = (
                session.query(KnowledgeCollection)
                .filter(KnowledgeCollection.collection_id == cid)
                .first()
            )
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
                )

            if not check_knowledge_delete_permission(
                current_user=current_user,
                owner_user_id=str(collection.owner_user_id),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to delete this collection",
                )

            # Get all items in collection for cleanup
            items = session.query(KnowledgeItem).filter(KnowledgeItem.collection_id == cid).all()

            for item in items:
                kid = str(item.knowledge_id)

                # Delete Milvus embeddings
                try:
                    from memory_system.milvus_connection import get_milvus_connection

                    milvus = get_milvus_connection()
                    if milvus.collection_exists("knowledge_embeddings"):
                        milvus_coll = milvus.get_collection(
                            "knowledge_embeddings",
                            force_refresh=True,
                        )
                        milvus_coll.delete(f'knowledge_id == "{kid}"')
                except Exception as e:
                    logger.warning(f"Failed to delete Milvus embeddings for {kid}: {e}")

                # Delete chunks
                try:
                    session.execute(
                        text("DELETE FROM knowledge_chunks WHERE knowledge_id = :kid"),
                        {"kid": kid},
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete chunks for {kid}: {e}")

                # Delete MinIO file
                if item.file_reference and item.file_reference.startswith("minio:"):
                    try:
                        from object_storage.minio_client import get_minio_client

                        minio_client = get_minio_client()
                        parts = item.file_reference.split(":", 2)
                        if len(parts) == 3:
                            _, bucket_name, object_key = parts
                            minio_client.delete_file(bucket_name, object_key)
                    except Exception as e:
                        logger.warning(f"Failed to delete MinIO file for {kid}: {e}")

            # Delete collection (cascades to items)
            session.delete(collection)

        logger.info(
            f"Collection deleted: {collection_id} ({len(items)} items)",
            extra={"user_id": current_user.user_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete collection: {str(e)}",
        )


@router.get("/collections/{collection_id}/items", response_model=KnowledgeListResponse)
async def list_collection_items(
    collection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List items in a specific collection."""
    try:
        with get_db_session() as session:
            try:
                cid = UUID(collection_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid collection ID format"
                )

            # Verify collection exists
            collection = (
                session.query(KnowledgeCollection)
                .filter(KnowledgeCollection.collection_id == cid)
                .first()
            )
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
                )

            query = session.query(KnowledgeItem).filter(KnowledgeItem.collection_id == cid)

            # Apply permission filtering
            query = filter_knowledge_query(query, current_user)

            total = query.count()

            offset = (page - 1) * page_size
            items = (
                query.order_by(KnowledgeItem.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )

            # Build owner username cache
            owner_ids = {item.owner_user_id for item in items}
            owners = {}
            if owner_ids:
                users = session.query(User).filter(User.user_id.in_(owner_ids)).all()
                owners = {str(u.user_id): u.username for u in users}

            response_items = []
            for item in items:
                owner_name = owners.get(str(item.owner_user_id), "Unknown")
                response_items.append(_build_item_response(item, owner_name))

            return KnowledgeListResponse(
                items=response_items,
                total=total,
                page=page,
                pageSize=page_size,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list collection items: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collection items: {str(e)}",
        )


@router.post("/{knowledge_id}/reprocess", response_model=KnowledgeItemResponse)
async def reprocess_knowledge(
    knowledge_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reprocess a failed or completed knowledge item.

    Resets processing status and re-triggers the pipeline.
    """
    try:
        enqueue_payload = None
        response_payload = None

        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            # Check write permission
            if not check_knowledge_write_permission(
                current_user=current_user,
                knowledge_id=knowledge_id,
                owner_user_id=str(item.owner_user_id),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to reprocess this item",
                )

            if not item.file_reference or not item.file_reference.startswith("minio:"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File not available for reprocessing",
                )

            # Parse file reference
            parts = item.file_reference.split(":", 2)
            if len(parts) != 3:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid file reference format",
                )

            _, bucket_name, object_key = parts
            metadata = dict(item.item_metadata or {})
            mime_type = metadata.get("mime_type", "application/octet-stream")
            reprocess_started_at = datetime.now(timezone.utc).isoformat()
            reprocess_job_id = str(uuid4())

            # Delete old chunks
            try:
                session.execute(
                    text("DELETE FROM knowledge_chunks WHERE knowledge_id = :kid"),
                    {"kid": str(kid)},
                )
            except Exception as e:
                logger.warning(f"Failed to delete old chunks: {e}")

            # Delete old Milvus embeddings
            try:
                from memory_system.milvus_connection import get_milvus_connection

                milvus = get_milvus_connection()
                if milvus.collection_exists("knowledge_embeddings"):
                    collection = milvus.get_collection(
                        "knowledge_embeddings",
                        force_refresh=True,
                    )
                    collection.delete(f'knowledge_id == "{knowledge_id}"')
            except Exception as e:
                logger.warning(f"Failed to delete old Milvus embeddings: {e}")

            # Reset status to processing
            metadata["processing_status"] = "processing"
            metadata["processing_progress"] = 5
            metadata["job_id"] = reprocess_job_id
            metadata["created_at"] = reprocess_started_at
            metadata["started_at"] = reprocess_started_at
            metadata["completed_at"] = None
            metadata.pop("error_message", None)
            metadata.pop("chunk_count", None)
            metadata.pop("token_count", None)
            item.item_metadata = metadata
            session.flush()

            item_id = str(item.knowledge_id)

            # Get owner username
            owner = session.query(User).filter(User.user_id == item.owner_user_id).first()
            owner_name = owner.username if owner else "Unknown"
            response_payload = _build_item_response(item, owner_name)

            enqueue_payload = {
                "document_id": item_id,
                "bucket_name": bucket_name,
                "object_key": object_key,
                "mime_type": mime_type,
                "job_id": reprocess_job_id,
                "job_created_at": reprocess_started_at,
            }

        # Enqueue only after transaction commit, so status/chunk cleanup is visible immediately.
        if enqueue_payload is None or response_payload is None:
            raise RuntimeError("Reprocess payload preparation failed")
        try:
            from knowledge_base.processing_queue import get_processing_queue

            queue = get_processing_queue()
            queue_job = queue.enqueue(
                document_id=enqueue_payload["document_id"],
                file_key=enqueue_payload["object_key"],
                bucket=enqueue_payload["bucket_name"],
                mime_type=enqueue_payload["mime_type"],
                user_id=current_user.user_id,
            )
            # Update to real queue job metadata (fallback values were written pre-commit).
            with get_db_session() as session:
                item = (
                    session.query(KnowledgeItem)
                    .filter(KnowledgeItem.knowledge_id == UUID(enqueue_payload["document_id"]))
                    .first()
                )
                if item:
                    meta = dict(item.item_metadata or {})
                    now_iso = datetime.now(timezone.utc).isoformat()
                    meta["job_id"] = queue_job.job_id
                    meta["created_at"] = queue_job.created_at
                    meta["started_at"] = queue_job.started_at or meta.get("started_at") or now_iso
                    meta["completed_at"] = queue_job.completed_at
                    item.item_metadata = meta
                    session.commit()
        except Exception as e:
            logger.warning(f"Redis queue unavailable, using background thread: {e}")
            import threading

            thread = threading.Thread(
                target=_process_document_background,
                args=(
                    enqueue_payload["document_id"],
                    enqueue_payload["bucket_name"],
                    enqueue_payload["object_key"],
                    enqueue_payload["mime_type"],
                    current_user.user_id,
                    enqueue_payload["job_id"],
                    enqueue_payload["job_created_at"],
                ),
                daemon=True,
            )
            thread.start()

        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document: {str(e)}",
        )


@router.get("/{knowledge_id}/chunks")
async def get_knowledge_chunks(
    knowledge_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get chunks for a knowledge item with pagination."""
    try:
        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            # Check access
            has_access = can_access_knowledge_item(
                current_user=current_user,
                action=Action.READ,
                owner_user_id=str(item.owner_user_id),
                access_level=item.access_level,
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this knowledge item",
                )

            # Query chunks
            try:
                from database.models import KnowledgeChunk
                from memory_system.embedding_service import resolve_embedding_settings

                query = (
                    session.query(KnowledgeChunk)
                    .filter(KnowledgeChunk.knowledge_id == kid)
                    .order_by(KnowledgeChunk.chunk_index)
                )
                total = query.count()

                offset = (page - 1) * page_size
                chunks = query.offset(offset).limit(page_size).all()

                # Resolve effective embedding config for frontend diagnostics.
                embedding_settings: Dict[str, Any] = {}
                try:
                    embedding_settings = resolve_embedding_settings(scope="knowledge_base")
                except Exception as embed_cfg_err:
                    logger.warning(
                        "Failed to resolve embedding settings for chunks view: " f"{embed_cfg_err}"
                    )

                # Best-effort Milvus lookup to show whether page chunks are indexed.
                indexed_chunk_indices: set[int] = set()
                vector_lookup_attempted = False
                vector_lookup_error: Optional[str] = None

                try:
                    chunk_indexes = sorted(
                        {int(c.chunk_index) for c in chunks if c.chunk_index is not None}
                    )
                    if chunk_indexes:
                        from memory_system.milvus_connection import get_milvus_connection

                        milvus = get_milvus_connection()
                        if milvus.collection_exists("knowledge_embeddings"):
                            collection = milvus.get_collection("knowledge_embeddings")
                            index_expr = ", ".join(str(idx) for idx in chunk_indexes)
                            expr = f'knowledge_id == "{kid}" and ' f"chunk_index in [{index_expr}]"
                            rows = collection.query(
                                expr=expr,
                                output_fields=["chunk_index"],
                                limit=max(len(chunk_indexes), 1),
                            )
                            indexed_chunk_indices = {
                                int(row["chunk_index"])
                                for row in rows
                                if isinstance(row, dict) and row.get("chunk_index") is not None
                            }
                        vector_lookup_attempted = True
                except Exception as vector_err:
                    vector_lookup_attempted = True
                    vector_lookup_error = str(vector_err)
                    logger.warning(
                        "Failed to query chunk vector index status",
                        extra={
                            "knowledge_id": str(kid),
                            "error": vector_lookup_error,
                        },
                    )

                chunk_list = []
                for c in chunks:
                    keywords = c.keywords or []
                    questions = c.questions or []
                    summary_text = (c.summary or "").strip()
                    enrichment_applied = bool(keywords or questions or summary_text)

                    if c.chunk_index is not None:
                        is_indexed = int(c.chunk_index) in indexed_chunk_indices
                    else:
                        is_indexed = False

                    if is_indexed:
                        embedding_status = "indexed"
                    elif item.status == "failed":
                        embedding_status = "failed"
                    elif item.status == "completed":
                        embedding_status = "missing" if vector_lookup_attempted else "unknown"
                    else:
                        embedding_status = "pending"

                    chunk_list.append(
                        {
                            "chunk_id": str(c.chunk_id),
                            "chunk_index": c.chunk_index,
                            "content": c.content,
                            "keywords": keywords,
                            "questions": questions,
                            "summary": c.summary,
                            "token_count": c.token_count,
                            "chunk_metadata": c.chunk_metadata,
                            "enrichment_applied": enrichment_applied,
                            "enrichment": {
                                "applied": enrichment_applied,
                                "keywords_count": len(keywords),
                                "questions_count": len(questions),
                                "has_summary": bool(summary_text),
                            },
                            "embedding": {
                                "status": embedding_status,
                                "indexed": is_indexed,
                                "provider": embedding_settings.get("provider"),
                                "model": embedding_settings.get("model"),
                                "dimension": embedding_settings.get("dimension"),
                            },
                        }
                    )

                return {
                    "chunks": chunk_list,
                    "total": total,
                    "embedding_config": {
                        "provider": embedding_settings.get("provider"),
                        "model": embedding_settings.get("model"),
                        "dimension": embedding_settings.get("dimension"),
                        "provider_source": embedding_settings.get("provider_source"),
                        "model_source": embedding_settings.get("model_source"),
                        "dimension_source": embedding_settings.get("dimension_source"),
                    },
                    "vector_index_lookup": {
                        "attempted": vector_lookup_attempted,
                        "error": vector_lookup_error,
                    },
                }

            except Exception as e:
                logger.warning(f"Failed to query chunks (table may not exist): {e}")
                return {"chunks": [], "total": 0}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge chunks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chunks: {str(e)}",
        )


@router.get("/{knowledge_id}", response_model=KnowledgeItemResponse)
async def get_knowledge(knowledge_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get knowledge item details."""
    try:
        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            # Check access
            has_access = can_access_knowledge_item(
                current_user=current_user,
                action=Action.READ,
                owner_user_id=str(item.owner_user_id),
                access_level=item.access_level,
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this knowledge item",
                )

            # Get owner username
            owner = session.query(User).filter(User.user_id == item.owner_user_id).first()
            owner_name = owner.username if owner else "Unknown"

            return _build_item_response(item, owner_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get document: {str(e)}",
        )


@router.put("/{knowledge_id}", response_model=KnowledgeItemResponse)
async def update_knowledge(
    knowledge_id: str,
    update_data: KnowledgeUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update knowledge item metadata."""
    try:
        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            # Check write permission
            if not check_knowledge_write_permission(
                current_user=current_user,
                knowledge_id=knowledge_id,
                owner_user_id=str(item.owner_user_id),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to update this knowledge item",
                )

            original_collection_id = item.collection_id

            # Update fields
            if update_data.title is not None:
                item.title = update_data.title

            if update_data.access_level is not None:
                item.access_level = _map_access_level_to_backend(update_data.access_level)

            if update_data.department_id is not None:
                try:
                    item.department_id = (
                        UUID(update_data.department_id) if update_data.department_id else None
                    )
                except ValueError:
                    pass

            if update_data.collection_id is not None:
                target_collection_id: Optional[UUID] = None
                if update_data.collection_id:
                    try:
                        target_collection_id = UUID(update_data.collection_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid collection ID format",
                        )

                    target_collection = (
                        session.query(KnowledgeCollection)
                        .filter(KnowledgeCollection.collection_id == target_collection_id)
                        .first()
                    )
                    if not target_collection:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collection not found",
                        )

                    if not check_knowledge_write_permission(
                        current_user=current_user,
                        owner_user_id=str(target_collection.owner_user_id),
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have permission to move item into this collection",
                        )

                item.collection_id = target_collection_id

            # Update metadata fields
            metadata = dict(item.item_metadata or {})
            if update_data.tags is not None:
                metadata["tags"] = update_data.tags
            if update_data.description is not None:
                metadata["description"] = update_data.description
            item.item_metadata = metadata

            session.flush()
            if original_collection_id != item.collection_id:
                _refresh_collection_item_counts(
                    session, [original_collection_id, item.collection_id]
                )
                session.flush()

            # Get owner username
            owner = session.query(User).filter(User.user_id == item.owner_user_id).first()
            owner_name = owner.username if owner else "Unknown"

            return _build_item_response(item, owner_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document: {str(e)}",
        )


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    knowledge_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Delete knowledge item from database and MinIO."""
    try:
        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            # Check delete permission
            if not check_knowledge_delete_permission(
                current_user=current_user,
                owner_user_id=str(item.owner_user_id),
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to delete this knowledge item",
                )

            original_collection_id = item.collection_id

            # 1. Delete from Milvus (vector embeddings)
            try:
                from memory_system.milvus_connection import get_milvus_connection

                milvus = get_milvus_connection()
                if milvus.collection_exists("knowledge_embeddings"):
                    collection = milvus.get_collection(
                        "knowledge_embeddings",
                        force_refresh=True,
                    )
                    collection.delete(f'knowledge_id == "{knowledge_id}"')
                    logger.info(f"Deleted Milvus embeddings for {knowledge_id}")
            except Exception as e:
                logger.warning(f"Failed to delete from Milvus: {e}")

            # 2. Delete knowledge_chunks (if table exists)
            try:
                session.execute(
                    text("DELETE FROM knowledge_chunks WHERE knowledge_id = :kid"),
                    {"kid": str(kid)},
                )
            except Exception as e:
                logger.warning(f"Failed to delete knowledge_chunks: {e}")
                session.rollback()

            # 3. Delete from MinIO if file reference exists
            if item.file_reference and item.file_reference.startswith("minio:"):
                try:
                    from object_storage.minio_client import get_minio_client

                    minio_client = get_minio_client()
                    parts = item.file_reference.split(":", 2)
                    if len(parts) == 3:
                        _, bucket_name, object_key = parts
                        minio_client.delete_file(bucket_name, object_key)
                except Exception as e:
                    logger.warning(f"Failed to delete file from MinIO: {e}")

            # 4. Delete knowledge item from database
            session.delete(item)
            session.flush()
            _refresh_collection_item_counts(session, [original_collection_id])

        logger.info(
            f"Knowledge item deleted: {knowledge_id}",
            extra={"user_id": current_user.user_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}",
        )


def _search_knowledge_sync(
    search_data: KnowledgeSearchRequest,
    current_user: CurrentUser,
) -> KnowledgeSearchResponse:
    """Synchronous knowledge retrieval chain executed in threadpool."""
    from knowledge_base.knowledge_search import SearchFilter, get_knowledge_search

    search_service = get_knowledge_search()
    candidate_document_ids: Optional[List[str]] = None

    has_explicit_filters = bool(
        search_data.filters
        and any(
            [
                search_data.filters.collection_id,
                search_data.filters.document_ids,
            ]
        )
    )

    if has_explicit_filters:
        with get_db_session() as session:
            query = session.query(KnowledgeItem.knowledge_id)
            query = filter_knowledge_query(query, current_user)

            if search_data.filters.collection_id:
                if search_data.filters.collection_id == "none":
                    query = query.filter(KnowledgeItem.collection_id.is_(None))
                else:
                    try:
                        collection_uuid = UUID(search_data.filters.collection_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid collection_id in search filters",
                        )
                    query = query.filter(KnowledgeItem.collection_id == collection_uuid)

            if search_data.filters.document_ids:
                parsed_doc_ids = []
                for doc_id in search_data.filters.document_ids:
                    try:
                        parsed_doc_ids.append(UUID(doc_id))
                    except ValueError:
                        continue

                if not parsed_doc_ids:
                    return KnowledgeSearchResponse(
                        results=[],
                        query=search_data.query,
                        total=0,
                    )

                query = query.filter(KnowledgeItem.knowledge_id.in_(parsed_doc_ids))

            candidate_document_ids = [str(item[0]) for item in query.all()]

        if not candidate_document_ids:
            return KnowledgeSearchResponse(
                results=[],
                query=search_data.query,
                total=0,
            )

    search_filter = SearchFilter(
        user_id=current_user.user_id,
        user_role=current_user.role,
        document_ids=candidate_document_ids,
        top_k=search_data.limit,
        min_relevance_score=search_data.min_score,
    )

    results = search_service.search(
        query=search_data.query,
        search_filter=search_filter,
    )

    # Batch-fetch document titles
    doc_ids = list({r.document_id for r in results})
    doc_titles = {}
    if doc_ids:
        try:
            with get_db_session() as session:
                items = (
                    session.query(KnowledgeItem.knowledge_id, KnowledgeItem.title)
                    .filter(KnowledgeItem.knowledge_id.in_(doc_ids))
                    .all()
                )
                doc_titles = {str(i.knowledge_id): i.title for i in items}
        except Exception as e:
            logger.warning(f"Failed to fetch document titles: {e}")

    response_results = [
        KnowledgeSearchResultItem(
            document_id=r.document_id,
            document_title=doc_titles.get(r.document_id),
            content=r.content,
            similarity_score=r.similarity_score,
            chunk_index=r.chunk_index,
            keywords=r.keywords,
            summary=r.summary,
            search_method=r.search_method,
        )
        for r in results
    ]

    return KnowledgeSearchResponse(
        results=response_results,
        query=search_data.query,
        total=len(response_results),
    )


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    search_data: KnowledgeSearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Semantic search across knowledge base using vector embeddings."""
    request_start = time.perf_counter()
    try:
        async with _SEARCH_REQUEST_SEMAPHORE:
            semaphore_acquired_at = time.perf_counter()
            result = await asyncio.wait_for(
                asyncio.to_thread(_search_knowledge_sync, search_data, current_user),
                timeout=_SEARCH_REQUEST_TIMEOUT_SECONDS,
            )
            completed_at = time.perf_counter()
            logger.info(
                "Knowledge search request executed",
                extra={
                    "queue_wait_ms": round((semaphore_acquired_at - request_start) * 1000.0, 2),
                    "execution_ms": round((completed_at - semaphore_acquired_at) * 1000.0, 2),
                    "total_ms": round((completed_at - request_start) * 1000.0, 2),
                    "query_length": len(search_data.query or ""),
                    "user_id": current_user.user_id,
                },
            )
            return result
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        timeout_at = time.perf_counter()
        logger.warning(
            "Knowledge search timed out",
            extra={
                "timeout_seconds": _SEARCH_REQUEST_TIMEOUT_SECONDS,
                "user_id": current_user.user_id,
                "query_length": len(search_data.query or ""),
                "total_ms": round((timeout_at - request_start) * 1000.0, 2),
            },
        )
        return KnowledgeSearchResponse(
            results=[],
            query=search_data.query,
            total=0,
        )
    except Exception as e:
        logger.error(f"Knowledge search failed (Milvus may be unavailable): {e}", exc_info=True)
        # Gracefully degrade - return empty results if Milvus is unavailable
        return KnowledgeSearchResponse(
            results=[],
            query=search_data.query,
            total=0,
        )


@router.get("/{knowledge_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    knowledge_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    """Get processing status for a knowledge item."""
    try:
        # First check the item exists and user has access
        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            metadata = item.item_metadata or {}
            stored_status = metadata.get("processing_status", "completed")
            if stored_status == "queued":
                stored_status = "processing"
            job_id = metadata.get("job_id")
            if not job_id:
                # Keep response fields stable even for legacy rows created before job_id existed.
                job_id = f"local-{knowledge_id}"
            created_at = metadata.get("created_at")
            started_at = metadata.get("started_at")
            completed_at = metadata.get("completed_at")
            chunk_count = metadata.get("chunk_count")
            token_count = metadata.get("token_count")
            error_message = metadata.get("error_message")
            processed_at = metadata.get("processed_at")
            progress_percent = metadata.get("processing_progress")
            if progress_percent is not None:
                try:
                    progress_percent = int(progress_percent)
                except (TypeError, ValueError):
                    progress_percent = None
            if processed_at is None and item.updated_at:
                processed_at = item.updated_at.isoformat()
            if created_at is None and item.created_at:
                created_at = item.created_at.isoformat()

            # Metadata and chunk rows can briefly diverge during reprocess retries.
            # Reconcile here so clients don't stop polling on stale "completed" states.
            if stored_status == "completed":
                from database.models import KnowledgeChunk

                actual_chunk_count = (
                    session.query(KnowledgeChunk).filter(KnowledgeChunk.knowledge_id == kid).count()
                )
                metadata_chunk_count = None
                if chunk_count is not None:
                    try:
                        metadata_chunk_count = int(chunk_count)
                    except (TypeError, ValueError):
                        metadata_chunk_count = None

                if metadata_chunk_count is None:
                    chunk_count = actual_chunk_count
                elif metadata_chunk_count != actual_chunk_count:
                    if metadata_chunk_count > 0 and actual_chunk_count == 0:
                        logger.warning(
                            "Completed status had stale chunk_count; returning processing status",
                            extra={
                                "knowledge_id": knowledge_id,
                                "metadata_chunk_count": metadata_chunk_count,
                                "actual_chunk_count": actual_chunk_count,
                            },
                        )
                        stored_status = "processing"
                        chunk_count = None
                        token_count = None
                        error_message = None
                    else:
                        chunk_count = actual_chunk_count

        # Provide best-effort progress timestamps even when queue metadata is unavailable.
        if started_at is None and stored_status in {"processing", "completed", "failed"}:
            started_at = processed_at or created_at
        if completed_at is None and stored_status in {"completed", "failed"}:
            completed_at = processed_at

        # Try to get richer job status from processing queue (when available).
        try:
            if job_id and not str(job_id).startswith("local-"):
                from knowledge_base.processing_queue import get_processing_queue

                queue = get_processing_queue()
                queue_job = queue.get_job(job_id)
                if queue_job:
                    stored_status = queue_job.status.value
                    if stored_status == "queued":
                        # Frontend status model does not expose queued; treat as early processing.
                        stored_status = "processing"
                    created_at = queue_job.created_at or created_at
                    started_at = queue_job.started_at or started_at
                    completed_at = queue_job.completed_at or completed_at
                    error_message = queue_job.error_message or error_message
        except Exception:
            pass

        # Backfill progress for legacy rows and keep stage status coherent.
        if progress_percent is None:
            if stored_status == "uploading":
                progress_percent = 0
            elif stored_status == "processing":
                progress_percent = 50
            elif stored_status in {"completed", "failed"}:
                progress_percent = 100
        else:
            progress_percent = max(0, min(100, progress_percent))
            if stored_status == "completed":
                progress_percent = 100
            elif stored_status == "processing" and progress_percent >= 100:
                progress_percent = 99

        return ProcessingStatusResponse(
            job_id=job_id,
            status=stored_status,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            chunk_count=chunk_count,
            token_count=token_count,
            error_message=error_message,
            processed_at=processed_at,
            progress_percent=progress_percent,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get processing status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get processing status: {str(e)}",
        )


@router.get("/{knowledge_id}/thumbnail")
async def get_knowledge_thumbnail(
    knowledge_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a generated thumbnail image for a knowledge item."""
    try:
        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            has_access = can_access_knowledge_item(
                current_user=current_user,
                action=Action.READ,
                owner_user_id=str(item.owner_user_id),
                access_level=item.access_level,
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this thumbnail",
                )

            metadata = item.item_metadata or {}
            thumbnail_reference = metadata.get("thumbnail_reference")
            thumbnail_mime_type = metadata.get("thumbnail_mime_type", "image/jpeg")
            thumbnail_parts = _parse_minio_reference(thumbnail_reference)
            if not thumbnail_parts:
                generated_reference, generated_mime_type = _backfill_thumbnail_for_item(item)
                if generated_reference:
                    thumbnail_reference = generated_reference
                    thumbnail_mime_type = generated_mime_type or "image/jpeg"
                    thumbnail_parts = _parse_minio_reference(thumbnail_reference)
                    session.flush()

            if not thumbnail_parts:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Thumbnail not available",
                )

            bucket_name, object_key = thumbnail_parts

        from object_storage.minio_client import get_minio_client

        minio_client = get_minio_client()
        stream, file_metadata = minio_client.download_file_streaming(bucket_name, object_key)

        cache_headers = {
            "Content-Length": str(file_metadata.get("size", 0)),
            "Cache-Control": "private, max-age=86400, stale-while-revalidate=3600",
            "Vary": "Authorization",
        }

        etag = str(file_metadata.get("etag", "")).strip()
        normalized_etag = etag.strip('"') if etag else ""
        if normalized_etag:
            cache_headers["ETag"] = f'"{normalized_etag}"'

        last_modified = file_metadata.get("last_modified")
        if last_modified:
            cache_headers["Last-Modified"] = str(last_modified)

        if_none_match = request.headers.get("if-none-match")
        if if_none_match and normalized_etag:
            etag_tokens = [token.strip().strip('"') for token in if_none_match.split(",")]
            if "*" in etag_tokens or normalized_etag in etag_tokens:
                cache_headers.pop("Content-Length", None)
                return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)

        if_modified_since = request.headers.get("if-modified-since")
        if if_modified_since and last_modified:
            try:
                ims_dt = parsedate_to_datetime(if_modified_since)
                lm_dt = parsedate_to_datetime(str(last_modified))
                if ims_dt and lm_dt and lm_dt <= ims_dt:
                    cache_headers.pop("Content-Length", None)
                    return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)
            except Exception:
                pass

        return StreamingResponse(
            stream,
            media_type=thumbnail_mime_type,
            headers=cache_headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge thumbnail: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get thumbnail: {str(e)}",
        )


@router.get("/{knowledge_id}/download")
async def download_knowledge(
    knowledge_id: str,
    request: Request,
    inline: bool = Query(default=False),
    convert_to: Optional[str] = Query(
        default=None, description="Optional format conversion target"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download knowledge item file from MinIO."""
    try:
        if convert_to not in {None, "docx"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported convert_to value. Supported values: docx",
            )

        with get_db_session() as session:
            try:
                kid = UUID(knowledge_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid knowledge ID format"
                )

            item = session.query(KnowledgeItem).filter(KnowledgeItem.knowledge_id == kid).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found"
                )

            # Check access
            has_access = can_access_knowledge_item(
                current_user=current_user,
                action=Action.READ,
                owner_user_id=str(item.owner_user_id),
                access_level=item.access_level,
            )
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to download this file",
                )

            if not item.file_reference or not item.file_reference.startswith("minio:"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not available for download",
                )

            file_reference_parts = _parse_minio_reference(item.file_reference)
            if not file_reference_parts:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid file reference format",
                )

            bucket_name, object_key = file_reference_parts
            metadata = item.item_metadata or {}
            original_filename = metadata.get("original_filename", item.title)
            mime_type = metadata.get("mime_type", "application/octet-stream")
            should_convert_to_docx = convert_to == "docx" and _is_legacy_word_doc(
                original_filename, mime_type
            )

        # Stream from MinIO (or convert legacy DOC on demand)
        from object_storage.minio_client import get_minio_client

        minio_client = get_minio_client()
        if should_convert_to_docx:
            downloaded_stream, _ = minio_client.download_file(bucket_name, object_key)
            doc_bytes = downloaded_stream.read()
            converted_bytes = _convert_legacy_doc_bytes_to_docx(doc_bytes, original_filename)
            stream = io.BytesIO(converted_bytes)
            file_metadata = {"size": len(converted_bytes), "etag": "", "last_modified": None}
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            original_filename = _build_docx_filename(original_filename)
        else:
            stream, file_metadata = minio_client.download_file_streaming(bucket_name, object_key)

        # Encode filename for Content-Disposition header (RFC 5987)
        import urllib.parse

        encoded_filename = urllib.parse.quote(original_filename)

        disposition = "inline" if inline else "attachment"
        cache_headers = {
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(file_metadata.get("size", 0)),
            "Cache-Control": (
                "private, max-age=300"
                if should_convert_to_docx
                else "private, max-age=3600, stale-while-revalidate=120"
            ),
            "Vary": "Authorization",
        }

        etag = str(file_metadata.get("etag", "")).strip()
        if etag:
            normalized_etag = etag.strip('"')
            cache_headers["ETag"] = f'"{normalized_etag}"'
        else:
            normalized_etag = ""

        last_modified = file_metadata.get("last_modified")
        if last_modified:
            cache_headers["Last-Modified"] = str(last_modified)

        # Conditional request support to avoid sending full payload repeatedly.
        if request is not None:
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and normalized_etag:
                etag_tokens = [token.strip().strip('"') for token in if_none_match.split(",")]
                if "*" in etag_tokens or normalized_etag in etag_tokens:
                    cache_headers.pop("Content-Length", None)
                    return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)

            if_modified_since = request.headers.get("if-modified-since")
            if if_modified_since and last_modified:
                try:
                    ims_dt = parsedate_to_datetime(if_modified_since)
                    lm_dt = parsedate_to_datetime(str(last_modified))
                    if ims_dt and lm_dt and lm_dt <= ims_dt:
                        cache_headers.pop("Content-Length", None)
                        return Response(
                            status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers
                        )
                except Exception:
                    # Invalid date headers should not fail downloads.
                    pass

        return StreamingResponse(
            stream,
            media_type=mime_type,
            headers=cache_headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {str(e)}",
        )
