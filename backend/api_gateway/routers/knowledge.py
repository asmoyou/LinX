"""Knowledge Base Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.9: Create knowledge endpoints
"""

import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from access_control.knowledge_filter import (
    can_access_knowledge_item,
    check_knowledge_delete_permission,
    check_knowledge_write_permission,
    filter_knowledge_query,
)
from access_control.permissions import CurrentUser, get_current_user
from access_control.rbac import Action
from database.connection import get_db_session
from database.models import KnowledgeItem, User
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# MIME type to document category mapping
MIME_TYPE_MAP = {
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "text/plain": "document",
    "text/markdown": "document",
    "image/jpeg": "document",
    "image/png": "document",
    "image/gif": "document",
    "audio/mpeg": "document",
    "audio/wav": "document",
    "video/mp4": "document",
    "video/x-msvideo": "document",
}

# MIME type to frontend DocumentType mapping
MIME_TO_DOC_TYPE = {
    "application/pdf": "pdf",
    "application/msword": "docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "video/mp4": "video",
    "video/x-msvideo": "video",
}

# File extension to frontend DocumentType mapping (fallback)
EXT_TO_DOC_TYPE = {
    ".pdf": "pdf",
    ".doc": "docx",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".mp4": "video",
    ".avi": "video",
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
    departmentId: Optional[str] = None
    chunkCount: Optional[int] = None
    tokenCount: Optional[int] = None
    errorMessage: Optional[str] = None


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


class KnowledgeSearchRequest(BaseModel):
    """Semantic search request."""

    query: str
    limit: int = Field(default=10, ge=1, le=100)
    filters: Optional[dict] = None


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


def _get_file_type(filename: str, content_type: Optional[str]) -> str:
    """Determine document type from MIME type or file extension."""
    if content_type and content_type in MIME_TO_DOC_TYPE:
        return MIME_TO_DOC_TYPE[content_type]

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
    if content_type:
        if content_type.startswith("image/"):
            return "images"
        if content_type.startswith("audio/"):
            return "audio"
        if content_type.startswith("video/"):
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
    if content_type and content_type in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[content_type]
    return "document"


def _build_item_response(item: KnowledgeItem, owner_username: str) -> KnowledgeItemResponse:
    """Convert a KnowledgeItem DB model to an API response."""
    metadata = item.item_metadata or {}
    file_size = metadata.get("file_size", 0)
    doc_type = metadata.get("file_type", "txt")
    tags = metadata.get("tags", [])
    description = metadata.get("description")
    processing_status = metadata.get("processing_status", "completed")
    chunk_count = metadata.get("chunk_count")
    token_count = metadata.get("token_count")
    error_message = metadata.get("error_message")

    return KnowledgeItemResponse(
        id=str(item.knowledge_id),
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
        departmentId=str(item.department_id) if item.department_id else None,
        chunkCount=chunk_count,
        tokenCount=token_count,
        errorMessage=error_message,
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


def _process_document_background(
    document_id: str,
    bucket_name: str,
    object_key: str,
    mime_type: str,
    user_id: str,
) -> None:
    """Process document in background thread when Redis queue is unavailable."""
    try:
        from knowledge_base.document_processor_worker import get_processor_worker
        from knowledge_base.processing_queue import JobStatus, ProcessingJob

        worker = get_processor_worker()

        # Create a minimal job-like object for the worker pipeline
        import uuid
        from datetime import datetime

        job = ProcessingJob(
            job_id=str(uuid.uuid4()),
            document_id=document_id,
            file_key=object_key,
            bucket=bucket_name,
            mime_type=mime_type,
            user_id=user_id,
            task_id=None,
            status=JobStatus.PROCESSING,
            created_at=datetime.utcnow().isoformat(),
        )

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
            worker._update_knowledge_status(
                document_id, "failed", error_message=str(ex)
            )
        except Exception:
            pass


@router.post("", response_model=KnowledgeItemResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    description: str = Form(default=""),
    tags: str = Form(default="[]"),
    access_level: str = Form(default="private"),
    department_id: str = Form(default=""),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a knowledge document.

    Saves file to MinIO, creates KnowledgeItem record, enqueues processing.
    """
    try:
        # Parse tags
        try:
            parsed_tags = json.loads(tags) if tags and tags != "[]" else []
        except json.JSONDecodeError:
            # Handle comma-separated tags
            parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

        # Use filename as title if not provided
        doc_title = title if title else file.filename or "Untitled"

        # Determine file type and content category
        doc_type = _get_file_type(file.filename or "", file.content_type)
        content_category = _get_content_type_category(file.filename or "", file.content_type)

        # Map access level to backend format
        backend_access_level = _map_access_level_to_backend(access_level)

        # Upload to MinIO
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
        except Exception as e:
            logger.warning(f"MinIO upload failed, storing reference only: {e}")
            file_reference = None
            bucket_name = ""
            object_key = ""

        # Get file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        # Parse department_id
        parsed_dept_id = None
        if department_id and department_id.strip():
            try:
                parsed_dept_id = UUID(department_id)
            except ValueError:
                pass

        # Create database record
        with get_db_session() as session:
            knowledge_item = KnowledgeItem(
                title=doc_title,
                content_type=content_category,
                file_reference=file_reference,
                owner_user_id=UUID(current_user.user_id),
                access_level=backend_access_level,
                department_id=parsed_dept_id,
                item_metadata={
                    "file_size": file_size,
                    "file_type": doc_type,
                    "original_filename": file.filename,
                    "mime_type": file.content_type,
                    "tags": parsed_tags,
                    "description": description if description else None,
                    "processing_status": "uploading",
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
                    queue.enqueue(
                        document_id=item_id,
                        file_key=object_key,
                        bucket=bucket_name,
                        mime_type=file.content_type or "application/octet-stream",
                        user_id=current_user.user_id,
                    )
                    # Update status to processing
                    knowledge_item.item_metadata = {
                        **knowledge_item.item_metadata,
                        "processing_status": "processing",
                    }
                except Exception as e:
                    logger.warning(
                        f"Redis queue unavailable, falling back to sync processing: {e}"
                    )
                    knowledge_item.item_metadata = {
                        **knowledge_item.item_metadata,
                        "processing_status": "processing",
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
                        ),
                        daemon=True,
                    )
                    thread.start()
            else:
                knowledge_item.item_metadata = {
                    **knowledge_item.item_metadata,
                    "processing_status": "failed",
                    "error_message": "File storage unavailable: upload failed",
                }

            response = KnowledgeItemResponse(
                id=item_id,
                name=doc_title,
                type=doc_type,
                size=file_size,
                status=knowledge_item.item_metadata.get("processing_status", "completed"),
                uploadedAt=knowledge_item.created_at.isoformat()
                if knowledge_item.created_at
                else "",
                owner=current_user.username,
                accessLevel=_map_access_level(backend_access_level),
                tags=parsed_tags if parsed_tags else None,
                description=description if description else None,
                fileReference=file_reference,
                departmentId=department_id if department_id and department_id.strip() else None,
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
    current_user: CurrentUser = Depends(get_current_user),
):
    """List accessible knowledge items with filtering and pagination."""
    try:
        with get_db_session() as session:
            query = session.query(KnowledgeItem)

            # Apply permission filtering
            user_attributes = {"department_id": department_id} if department_id else {}
            query = filter_knowledge_query(query, current_user, user_attributes=user_attributes)

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

    chunking: dict
    parsing: dict
    enrichment: dict
    embedding: dict
    search: dict


class KBConfigUpdateRequest(BaseModel):
    """Request to update KB pipeline configuration."""

    chunking: Optional[dict] = None
    parsing: Optional[dict] = None
    enrichment: Optional[dict] = None
    embedding: Optional[dict] = None
    search: Optional[dict] = None


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
            chunking=kb_section.get("chunking", {}),
            parsing=kb_section.get("parsing", {}),
            enrichment=kb_section.get("enrichment", {}),
            embedding=kb_section.get("embedding", {}),
            search=kb_section.get("search", {}),
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

        from shared.config import get_config, reload_config

        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
        config_path = os.path.abspath(config_path)

        # Read current config file
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        kb = raw_config.setdefault("knowledge_base", {})

        # Merge updates into existing config
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
            chunking=updated.get("chunking", {}),
            parsing=updated.get("parsing", {}),
            enrichment=updated.get("enrichment", {}),
            embedding=updated.get("embedding", {}),
            search=updated.get("search", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update KB config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}",
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
            metadata = item.item_metadata or {}
            mime_type = metadata.get("mime_type", "application/octet-stream")

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
                from pymilvus import Collection, utility

                if utility.has_collection("knowledge_embeddings"):
                    collection = Collection("knowledge_embeddings")
                    collection.delete(f'document_id == "{knowledge_id}"')
            except Exception as e:
                logger.warning(f"Failed to delete old Milvus embeddings: {e}")

            # Reset status to processing
            metadata["processing_status"] = "processing"
            metadata.pop("error_message", None)
            metadata.pop("chunk_count", None)
            metadata.pop("token_count", None)
            item.item_metadata = metadata
            session.flush()

            item_id = str(item.knowledge_id)

            # Try Redis queue first, fallback to background thread
            try:
                from knowledge_base.processing_queue import get_processing_queue

                queue = get_processing_queue()
                queue.enqueue(
                    document_id=item_id,
                    file_key=object_key,
                    bucket=bucket_name,
                    mime_type=mime_type,
                    user_id=current_user.user_id,
                )
            except Exception as e:
                logger.warning(f"Redis queue unavailable, using background thread: {e}")
                import threading

                thread = threading.Thread(
                    target=_process_document_background,
                    args=(item_id, bucket_name, object_key, mime_type, current_user.user_id),
                    daemon=True,
                )
                thread.start()

            # Get owner username
            owner = session.query(User).filter(User.user_id == item.owner_user_id).first()
            owner_name = owner.username if owner else "Unknown"

            return _build_item_response(item, owner_name)

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

                query = (
                    session.query(KnowledgeChunk)
                    .filter(KnowledgeChunk.knowledge_id == kid)
                    .order_by(KnowledgeChunk.chunk_index)
                )
                total = query.count()

                offset = (page - 1) * page_size
                chunks = query.offset(offset).limit(page_size).all()

                chunk_list = []
                for c in chunks:
                    chunk_list.append({
                        "chunk_id": str(c.chunk_id),
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "keywords": c.keywords,
                        "questions": c.questions,
                        "summary": c.summary,
                        "token_count": c.token_count,
                    })

                return {"chunks": chunk_list, "total": total}

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
async def get_knowledge(
    knowledge_id: str, current_user: CurrentUser = Depends(get_current_user)
):
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

            # Update fields
            if update_data.title is not None:
                item.title = update_data.title

            if update_data.access_level is not None:
                item.access_level = _map_access_level_to_backend(update_data.access_level)

            if update_data.department_id is not None:
                try:
                    item.department_id = UUID(update_data.department_id) if update_data.department_id else None
                except ValueError:
                    pass

            # Update metadata fields
            metadata = item.item_metadata or {}
            if update_data.tags is not None:
                metadata["tags"] = update_data.tags
            if update_data.description is not None:
                metadata["description"] = update_data.description
            item.item_metadata = metadata

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

            # 1. Delete from Milvus (vector embeddings)
            try:
                from pymilvus import Collection, utility

                if utility.has_collection("knowledge_embeddings"):
                    collection = Collection("knowledge_embeddings")
                    collection.delete(f'document_id == "{knowledge_id}"')
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


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    search_data: KnowledgeSearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Semantic search across knowledge base using vector embeddings."""
    try:
        from knowledge_base.knowledge_search import SearchFilter, get_knowledge_search

        search_service = get_knowledge_search()

        search_filter = SearchFilter(
            user_id=current_user.user_id,
            top_k=search_data.limit,
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
                    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

                    items = (
                        session.query(
                            KnowledgeItem.knowledge_id, KnowledgeItem.title
                        )
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

    except Exception as e:
        logger.warning(f"Knowledge search failed (Milvus may be unavailable): {e}")
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
            chunk_count = metadata.get("chunk_count")
            token_count = metadata.get("token_count")
            error_message = metadata.get("error_message")
            processed_at = item.updated_at.isoformat() if item.updated_at else None

        # Try to get job status from processing queue
        try:
            from knowledge_base.processing_queue import get_processing_queue

            queue = get_processing_queue()
            # Search for job by document_id (iterate recent jobs)
            # The queue doesn't have a lookup by document_id, so use stored status
            return ProcessingStatusResponse(
                status=stored_status,
                chunk_count=chunk_count,
                token_count=token_count,
                error_message=error_message,
                processed_at=processed_at,
            )
        except Exception:
            return ProcessingStatusResponse(
                status=stored_status,
                chunk_count=chunk_count,
                token_count=token_count,
                error_message=error_message,
                processed_at=processed_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get processing status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get processing status: {str(e)}",
        )


@router.get("/{knowledge_id}/download")
async def download_knowledge(
    knowledge_id: str,
    inline: bool = Query(default=False),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download knowledge item file from MinIO.

    Args:
        inline: If True, set Content-Disposition to inline (for preview).
    """
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
                    detail="You do not have access to download this file",
                )

            if not item.file_reference or not item.file_reference.startswith("minio:"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not available for download",
                )

            # Parse file reference
            parts = item.file_reference.split(":", 2)
            if len(parts) != 3:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid file reference format",
                )

            _, bucket_name, object_key = parts
            metadata = item.item_metadata or {}
            original_filename = metadata.get("original_filename", item.title)
            mime_type = metadata.get("mime_type", "application/octet-stream")

        # Stream from MinIO
        from object_storage.minio_client import get_minio_client

        minio_client = get_minio_client()
        stream, file_metadata = minio_client.download_file_streaming(bucket_name, object_key)

        # Encode filename for Content-Disposition header (RFC 5987)
        import urllib.parse

        encoded_filename = urllib.parse.quote(original_filename)

        disposition = "inline" if inline else "attachment"

        return StreamingResponse(
            stream,
            media_type=mime_type,
            headers={
                "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
                "Content-Length": str(file_metadata.get("size", 0)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download knowledge item: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {str(e)}",
        )
