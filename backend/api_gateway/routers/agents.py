"""Agent Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.7: Create agent endpoints
"""

import base64
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

import psutil  # For system memory monitoring
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from agent_framework.agent_registry import get_agent_registry
from object_storage.minio_client import get_minio_client
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _resolve_agent_avatar(avatar_ref: Optional[str]) -> Optional[str]:
    """
    Resolve agent avatar reference to a presigned URL.

    Args:
        avatar_ref: Avatar reference (minio:bucket:key format) or legacy URL

    Returns:
        Presigned URL or original URL, or None if reference is empty
    """
    if not avatar_ref:
        return None

    # Check for minio reference format
    if avatar_ref.startswith("minio:"):
        try:
            minio_client = get_minio_client()
            return minio_client.resolve_avatar_url(avatar_ref)
        except Exception as e:
            logger.warning(f"Failed to resolve agent avatar URL: {e}")
            return None

    # Legacy: detect expired presigned MinIO URLs (localhost:9000/bucket/key?X-Amz-...)
    # and auto-convert them to minio: references for fresh presigned URLs
    if "X-Amz-" in avatar_ref and "localhost:9000/" in avatar_ref:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(avatar_ref)
            # path is like /images/agent-id/filename.webp
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if len(path_parts) == 2:
                bucket_name, object_key = path_parts
                minio_ref = f"minio:{bucket_name}:{object_key}"
                minio_client = get_minio_client()
                url = minio_client.resolve_avatar_url(minio_ref)
                if url:
                    # Auto-fix the DB record in background
                    _auto_fix_avatar_ref(avatar_ref, minio_ref)
                    return url
        except Exception as e:
            logger.warning(f"Failed to convert legacy avatar URL: {e}")

    # Legacy: already a URL, return as-is
    return avatar_ref


def _auto_fix_avatar_ref(old_ref: str, new_ref: str):
    """Auto-fix legacy avatar references in the database."""
    try:
        from database.connection import get_db_session
        from database.models import Agent

        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.avatar == old_ref).first()
            if agent:
                agent.avatar = new_ref
                session.commit()
                logger.info(f"Auto-fixed avatar for agent {agent.agent_id}: minio ref")
    except Exception as e:
        logger.warning(f"Failed to auto-fix avatar reference: {e}")


# Agent cache with TTL (Time To Live) and memory-aware sizing
class AgentCacheEntry:
    """Cache entry for an initialized agent with TTL."""

    def __init__(self, agent, llm, ttl_minutes: int = 30):
        self.agent = agent
        self.llm = llm
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.ttl = timedelta(minutes=ttl_minutes)
        self.access_count = 0

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now() - self.last_used > self.ttl

    def touch(self):
        """Update last used timestamp and increment access count."""
        self.last_used = datetime.now()
        self.access_count += 1


# Global cache for initialized agents (cache_key -> CacheEntry)
_agent_cache: Dict[str, AgentCacheEntry] = {}


def get_dynamic_cache_limit() -> int:
    """
    Calculate dynamic cache limit based on available system memory.

    Returns:
        int: Maximum number of agents to cache
    """
    try:
        # Get system memory info
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)  # Convert to GB

        # Conservative estimate: each cached agent uses ~50-100MB
        # Allow caching if we have at least 2GB available
        if available_gb < 2:
            return 10  # Minimal caching
        elif available_gb < 4:
            return 20
        elif available_gb < 8:
            return 30
        elif available_gb < 16:
            return 50
        else:
            return 100  # Maximum caching for systems with plenty of RAM

    except Exception as e:
        logger.warning(f"Failed to get system memory info: {e}, using default limit")
        return 30  # Safe default


def get_cache_stats() -> dict:
    """Get current cache statistics."""
    total_entries = len(_agent_cache)
    expired_entries = sum(1 for entry in _agent_cache.values() if entry.is_expired())

    # Calculate memory usage estimate
    memory_estimate_mb = total_entries * 75  # Rough estimate: 75MB per agent

    # Get system memory
    try:
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        total_gb = memory.total / (1024**3)
        used_percent = memory.percent
    except:
        available_gb = 0
        total_gb = 0
        used_percent = 0

    return {
        "total_entries": total_entries,
        "expired_entries": expired_entries,
        "active_entries": total_entries - expired_entries,
        "memory_estimate_mb": memory_estimate_mb,
        "cache_limit": get_dynamic_cache_limit(),
        "system_memory_available_gb": round(available_gb, 2),
        "system_memory_total_gb": round(total_gb, 2),
        "system_memory_used_percent": round(used_percent, 1),
    }


def clear_agent_cache():
    """Clear the agent cache. Useful after code changes."""
    global _agent_cache
    stats = get_cache_stats()
    _agent_cache.clear()
    logger.info(f"Agent cache cleared: {stats['total_entries']} entries removed")


def cleanup_expired_cache():
    """Remove expired entries from cache and enforce memory limits."""
    global _agent_cache

    # Remove expired entries
    expired_keys = [key for key, entry in _agent_cache.items() if entry.is_expired()]
    for key in expired_keys:
        del _agent_cache[key]
        logger.debug(f"Removed expired cache entry: {key}")

    # Get dynamic cache limit based on available memory
    cache_limit = get_dynamic_cache_limit()

    # If cache is still too large, remove least recently used entries
    if len(_agent_cache) > cache_limit:
        # Sort by last_used time (oldest first)
        sorted_entries = sorted(_agent_cache.items(), key=lambda x: x[1].last_used)
        to_remove = len(_agent_cache) - cache_limit

        for key, entry in sorted_entries[:to_remove]:
            del _agent_cache[key]
            logger.info(
                f"Removed LRU cache entry: {key} "
                f"(last used: {entry.last_used}, access count: {entry.access_count})"
            )

        logger.info(
            f"Cache size reduced from {len(_agent_cache) + to_remove} to {len(_agent_cache)} "
            f"(limit: {cache_limit}, available memory: {get_cache_stats()['system_memory_available_gb']}GB)"
        )


def get_cached_agent(cache_key: str):
    """Get agent from cache if exists and not expired."""
    cleanup_expired_cache()  # Clean up on every access

    if cache_key in _agent_cache:
        entry = _agent_cache[cache_key]
        if not entry.is_expired():
            entry.touch()  # Update last used time and access count
            logger.debug(
                f"Cache hit: {cache_key} "
                f"(access count: {entry.access_count}, age: {(datetime.now() - entry.created_at).seconds}s)"
            )
            return entry.agent, entry.llm
        else:
            # Remove expired entry
            del _agent_cache[cache_key]
            logger.debug(f"Cache expired: {cache_key}")

    logger.debug(f"Cache miss: {cache_key}")
    return None, None


def cache_agent(cache_key: str, agent, llm, ttl_minutes: int = 30):
    """Cache an initialized agent with TTL."""
    global _agent_cache
    cleanup_expired_cache()  # Clean up before adding

    _agent_cache[cache_key] = AgentCacheEntry(agent, llm, ttl_minutes)

    stats = get_cache_stats()
    logger.info(
        f"Cached agent: {cache_key} "
        f"(TTL: {ttl_minutes}min, cache size: {stats['total_entries']}/{stats['cache_limit']}, "
        f"memory estimate: {stats['memory_estimate_mb']}MB, "
        f"available: {stats['system_memory_available_gb']}GB)"
    )


def invalidate_agent_cache(agent_id: str):
    """
    Invalidate all cache entries for a specific agent.

    This removes all cached versions of an agent (different provider/model/capabilities combinations).
    """
    global _agent_cache
    # Match all cache keys that start with agent_id (handles old and new format)
    cache_keys_to_remove = [key for key in _agent_cache.keys() if key.startswith(f"{agent_id}_")]

    for key in cache_keys_to_remove:
        entry = _agent_cache[key]
        del _agent_cache[key]
        logger.info(
            f"Invalidated cache: {key} "
            f"(age: {(datetime.now() - entry.created_at).seconds}s, access count: {entry.access_count})"
        )

    return len(cache_keys_to_remove)


class CreateAgentRequest(BaseModel):
    """Create agent request."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=100)  # template type
    template_id: Optional[str] = None
    avatar: Optional[str] = None
    systemPrompt: Optional[str] = None
    skills: List[str] = []
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(default=2000, ge=1, le=8000)
    topP: Optional[float] = Field(default=0.9, ge=0.0, le=1.0)
    accessLevel: Optional[str] = Field(default="private")
    allowedKnowledge: List[str] = []
    allowedMemory: List[str] = []


class UpdateAgentRequest(BaseModel):
    """Update agent request."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    avatar: Optional[str] = None
    systemPrompt: Optional[str] = None
    skills: Optional[List[str]] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(None, ge=1, le=8000)
    topP: Optional[float] = Field(None, ge=0.0, le=1.0)
    accessLevel: Optional[str] = None
    allowedKnowledge: Optional[List[str]] = None
    allowedMemory: Optional[List[str]] = None
    # Knowledge Base Configuration
    embeddingModel: Optional[str] = None
    embeddingProvider: Optional[str] = None
    vectorDimension: Optional[int] = Field(None, ge=128, le=4096)
    topK: Optional[int] = Field(None, ge=1, le=20)
    similarityThreshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    # Department
    department_id: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent response model."""

    id: str
    name: str
    type: str
    avatar: Optional[str] = None
    status: str
    currentTask: Optional[str] = None
    tasksCompleted: int = 0
    uptime: str = "0h 0m"
    systemPrompt: Optional[str] = None
    skills: List[str] = []
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: float = 0.7
    maxTokens: int = 2000
    topP: float = 0.9
    accessLevel: str = "private"
    allowedKnowledge: List[str] = []
    allowedMemory: List[str] = []
    # Knowledge Base Configuration
    embeddingModel: Optional[str] = None
    embeddingProvider: Optional[str] = None
    vectorDimension: Optional[int] = None
    topK: Optional[int] = None
    similarityThreshold: Optional[float] = None
    departmentId: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class AvailableProvidersResponse(BaseModel):
    """Available LLM providers and models for agent configuration."""

    providers: Dict[str, List[str]]  # provider_name -> list of model names


@router.get("/available-providers", response_model=AvailableProvidersResponse)
async def get_available_providers(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get available LLM providers and their models for agent configuration.

    Returns only enabled providers from database with their available models.
    This endpoint is used by the agent configuration UI to populate provider/model dropdowns.
    """
    try:
        from database.connection import get_db_session
        from llm_providers.db_manager import ProviderDBManager

        providers_dict = {}

        # Get providers directly from database
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            db_providers = db_manager.list_providers()

            logger.info(f"[AVAILABLE-PROVIDERS] Found {len(db_providers)} providers in database")

            for p in db_providers:
                logger.info(
                    f"[AVAILABLE-PROVIDERS] Provider: {p.name}, enabled={p.enabled}, models={len(p.models) if p.models else 0}"
                )
                # Only include enabled providers with models
                if p.enabled and p.models:
                    providers_dict[p.name] = p.models

        logger.info(
            f"[AVAILABLE-PROVIDERS] Returning {len(providers_dict)} providers: {list(providers_dict.keys())}"
        )
        return AvailableProvidersResponse(providers=providers_dict)

    except Exception as e:
        logger.error(f"Failed to get available providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available providers: {str(e)}",
        )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: CreateAgentRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new agent."""
    try:
        registry = get_agent_registry()

        # Register agent in database with LLM configuration
        agent_info = registry.register_agent(
            name=request.name,
            agent_type=request.type,
            owner_user_id=UUID(current_user.user_id),
            capabilities=request.skills or [],
            llm_provider=request.provider,
            llm_model=request.model,
            system_prompt=request.systemPrompt,
            temperature=request.temperature or 0.7,
            max_tokens=request.maxTokens or 2000,
            top_p=request.topP or 0.9,
            access_level=request.accessLevel or "private",
            allowed_knowledge=request.allowedKnowledge or [],
            allowed_memory=request.allowedMemory or [],
        )

        # Update status to idle after creation
        agent_info = registry.update_agent(
            agent_id=agent_info.agent_id,
            status="idle",
        )

        logger.info(
            f"Agent created: {agent_info.name}",
            extra={"agent_id": str(agent_info.agent_id), "user_id": current_user.user_id},
        )

        return AgentResponse(
            id=str(agent_info.agent_id),
            name=agent_info.name,
            type=agent_info.agent_type,
            avatar=_resolve_agent_avatar(agent_info.avatar),
            status=agent_info.status,
            currentTask=None,
            tasksCompleted=0,
            uptime="0h 0m",
            systemPrompt=agent_info.system_prompt,
            skills=agent_info.capabilities,
            model=agent_info.llm_model,
            provider=agent_info.llm_provider,
            temperature=agent_info.temperature,
            maxTokens=agent_info.max_tokens,
            topP=agent_info.top_p,
            accessLevel=agent_info.access_level,
            allowedKnowledge=agent_info.allowed_knowledge,
            allowedMemory=agent_info.allowed_memory,
            embeddingModel=agent_info.embedding_model,
            embeddingProvider=agent_info.embedding_provider,
            vectorDimension=agent_info.vector_dimension,
            topK=agent_info.top_k,
            similarityThreshold=agent_info.similarity_threshold,
            departmentId=str(agent_info.department_id) if agent_info.department_id else None,
            createdAt=agent_info.created_at,
            updatedAt=agent_info.updated_at,
        )
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}",
        )


@router.get("", response_model=List[AgentResponse])
async def list_agents(current_user: CurrentUser = Depends(get_current_user)):
    """List user's agents."""
    try:
        registry = get_agent_registry()

        # Get agents for current user
        agents = registry.list_agents(owner_user_id=UUID(current_user.user_id))

        return [
            AgentResponse(
                id=str(agent.agent_id),
                name=agent.name,
                type=agent.agent_type,
                avatar=_resolve_agent_avatar(agent.avatar),
                status=agent.status,
                currentTask=None,  # TODO: Get from task manager
                tasksCompleted=0,  # TODO: Count from tasks table
                uptime="0h 0m",  # TODO: Calculate from created_at
                systemPrompt=agent.system_prompt,
                skills=agent.capabilities,
                model=agent.llm_model,
                provider=agent.llm_provider,
                temperature=agent.temperature,
                maxTokens=agent.max_tokens,
                topP=agent.top_p,
                accessLevel=agent.access_level,
                allowedKnowledge=agent.allowed_knowledge,
                allowedMemory=agent.allowed_memory,
                embeddingModel=agent.embedding_model,
                embeddingProvider=agent.embedding_provider,
                vectorDimension=agent.vector_dimension,
                topK=agent.top_k,
                similarityThreshold=agent.similarity_threshold,
                departmentId=str(agent.department_id) if agent.department_id else None,
                createdAt=agent.created_at,
                updatedAt=agent.updated_at,
            )
            for agent in agents
        ]

    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get agent details."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this agent",
            )

        return AgentResponse(
            id=str(agent.agent_id),
            name=agent.name,
            type=agent.agent_type,
            avatar=_resolve_agent_avatar(agent.avatar),
            status=agent.status,
            currentTask=None,
            tasksCompleted=0,
            uptime="0h 0m",
            systemPrompt=agent.system_prompt,
            skills=agent.capabilities,
            model=agent.llm_model,
            provider=agent.llm_provider,
            temperature=agent.temperature,
            maxTokens=agent.max_tokens,
            topP=agent.top_p,
            accessLevel=agent.access_level,
            allowedKnowledge=agent.allowed_knowledge,
            allowedMemory=agent.allowed_memory,
            embeddingModel=agent.embedding_model,
            embeddingProvider=agent.embedding_provider,
            vectorDimension=agent.vector_dimension,
            topK=agent.top_k,
            similarityThreshold=agent.similarity_threshold,
            departmentId=str(agent.department_id) if agent.department_id else None,
            createdAt=agent.created_at,
            updatedAt=agent.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent: {str(e)}",
        )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update agent configuration."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent",
            )

        # Update agent with all configuration fields
        updated_agent = registry.update_agent(
            agent_id=UUID(agent_id),
            name=request.name,
            avatar=request.avatar,
            capabilities=request.skills,
            llm_provider=request.provider,
            llm_model=request.model,
            system_prompt=request.systemPrompt,
            temperature=request.temperature,
            max_tokens=request.maxTokens,
            top_p=request.topP,
            access_level=request.accessLevel,
            allowed_knowledge=request.allowedKnowledge,
            allowed_memory=request.allowedMemory,
            embedding_model=request.embeddingModel,
            embedding_provider=request.embeddingProvider,
            vector_dimension=request.vectorDimension,
            top_k=request.topK,
            similarity_threshold=request.similarityThreshold,
            department_id=request.department_id,
        )

        if not updated_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Invalidate cache for this agent (all provider/model combinations)
        invalidated_count = invalidate_agent_cache(agent_id)

        logger.info(
            f"Agent updated: {updated_agent.name} (invalidated {invalidated_count} cache entries)",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )

        return AgentResponse(
            id=str(updated_agent.agent_id),
            name=updated_agent.name,
            type=updated_agent.agent_type,
            avatar=_resolve_agent_avatar(updated_agent.avatar),
            status=updated_agent.status,
            currentTask=None,
            tasksCompleted=0,
            uptime="0h 0m",
            systemPrompt=updated_agent.system_prompt,
            skills=updated_agent.capabilities,
            model=updated_agent.llm_model,
            provider=updated_agent.llm_provider,
            temperature=updated_agent.temperature,
            maxTokens=updated_agent.max_tokens,
            topP=updated_agent.top_p,
            accessLevel=updated_agent.access_level,
            allowedKnowledge=updated_agent.allowed_knowledge,
            allowedMemory=updated_agent.allowed_memory,
            embeddingModel=updated_agent.embedding_model,
            embeddingProvider=updated_agent.embedding_provider,
            vectorDimension=updated_agent.vector_dimension,
            topK=updated_agent.top_k,
            similarityThreshold=updated_agent.similarity_threshold,
            departmentId=str(updated_agent.department_id) if updated_agent.department_id else None,
            createdAt=updated_agent.created_at,
            updatedAt=updated_agent.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}",
        )


@router.post("/{agent_id}/avatar", response_model=Dict[str, str])
async def upload_agent_avatar(
    agent_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload agent avatar image.

    Accepts image files (JPEG, PNG, WebP) and stores them in MinIO.
    Returns the avatar URL.
    """
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent",
            )

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
            )

        # Read file data
        file_data = await file.read()
        file_stream = io.BytesIO(file_data)

        # Upload to MinIO
        minio_client = get_minio_client()

        # Prepare metadata - only include ASCII-safe values
        upload_metadata = {
            "agent_id": agent_id,
            "type": "agent_avatar",
        }

        # Only add agent_name if it's ASCII-safe
        try:
            agent.name.encode("ascii")
            upload_metadata["agent_name"] = agent.name
        except UnicodeEncodeError:
            # Skip non-ASCII agent names in metadata
            logger.debug(f"Skipping non-ASCII agent name in metadata: {agent.name}")

        bucket_name, object_key = minio_client.upload_file(
            bucket_type="images",
            file_data=file_stream,
            filename=f"avatar_{agent_id}.webp",
            user_id=current_user.user_id,
            task_id=None,
            agent_id=agent_id,
            content_type=file.content_type,
            metadata=upload_metadata,
        )

        # Store avatar reference (not presigned URL) for on-demand URL generation
        avatar_ref = minio_client.create_avatar_reference(bucket_name, object_key)

        # Generate presigned URL for immediate response (valid for 7 days)
        from datetime import timedelta

        avatar_url = minio_client.get_presigned_url(
            bucket_name=bucket_name, object_key=object_key, expires=timedelta(days=7)
        )

        # Update agent with avatar reference (store ref, not URL)
        updated_agent = registry.update_agent(
            agent_id=UUID(agent_id),
            avatar=avatar_ref,
        )

        logger.info(
            f"Avatar uploaded for agent: {agent.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id, "object_key": object_key},
        )

        return {
            "avatar_url": avatar_url,
            "avatar_ref": avatar_ref,
            "bucket": bucket_name,
            "key": object_key,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload avatar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}",
        )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Delete an agent."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this agent",
            )

        # Delete agent
        deleted = registry.delete_agent(UUID(agent_id))

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Invalidate cache for this agent
        invalidated_count = invalidate_agent_cache(agent_id)

        logger.info(
            f"Agent deleted: {agent_id} (invalidated {invalidated_count} cache entries)",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}",
        )


@router.post("/cache/clear", status_code=status.HTTP_200_OK)
async def clear_cache(current_user: CurrentUser = Depends(get_current_user)):
    """
    Clear the agent cache. Useful for debugging or after code changes.

    This will force all agents to be reinitialized on next use.
    """
    try:
        stats_before = get_cache_stats()
        clear_agent_cache()
        stats_after = get_cache_stats()

        logger.info(
            f"Agent cache cleared by user",
            extra={
                "user_id": current_user.user_id,
                "entries_cleared": stats_before["total_entries"],
                "memory_freed_mb": stats_before["memory_estimate_mb"],
            },
        )

        return {
            "message": "Agent cache cleared successfully",
            "entries_cleared": stats_before["total_entries"],
            "memory_freed_mb": stats_before["memory_estimate_mb"],
            "stats_before": stats_before,
            "stats_after": stats_after,
        }

    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}",
        )


@router.get("/cache/stats", status_code=status.HTTP_200_OK)
async def get_cache_statistics(current_user: CurrentUser = Depends(get_current_user)):
    """
    Get current agent cache statistics.

    Returns information about:
    - Number of cached agents
    - Memory usage estimates
    - System memory availability
    - Cache limits
    """
    try:
        stats = get_cache_stats()

        # Add detailed cache entries info
        cache_entries = []
        for key, entry in _agent_cache.items():
            age_seconds = (datetime.now() - entry.created_at).total_seconds()
            idle_seconds = (datetime.now() - entry.last_used).total_seconds()

            cache_entries.append(
                {
                    "key": key,
                    "age_seconds": int(age_seconds),
                    "idle_seconds": int(idle_seconds),
                    "access_count": entry.access_count,
                    "is_expired": entry.is_expired(),
                    "ttl_minutes": int(entry.ttl.total_seconds() / 60),
                }
            )

        # Sort by access count (most used first)
        cache_entries.sort(key=lambda x: x["access_count"], reverse=True)

        return {
            "summary": stats,
            "entries": cache_entries,
            "recommendations": _get_cache_recommendations(stats),
        }

    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache stats: {str(e)}",
        )


def _get_cache_recommendations(stats: dict) -> list:
    """Generate recommendations based on cache statistics."""
    recommendations = []

    # Check memory pressure
    if stats["system_memory_used_percent"] > 90:
        recommendations.append(
            {
                "level": "warning",
                "message": "System memory usage is high (>90%). Consider clearing cache or reducing cache limit.",
            }
        )

    # Check cache utilization
    utilization = stats["active_entries"] / stats["cache_limit"] if stats["cache_limit"] > 0 else 0
    if utilization > 0.9:
        recommendations.append(
            {
                "level": "info",
                "message": f"Cache is {int(utilization * 100)}% full. Old entries will be evicted automatically.",
            }
        )

    # Check expired entries
    if stats["expired_entries"] > stats["active_entries"] * 0.3:
        recommendations.append(
            {
                "level": "info",
                "message": f"{stats['expired_entries']} expired entries detected. They will be cleaned up automatically.",
            }
        )

    # Check available memory
    if stats["system_memory_available_gb"] < 2:
        recommendations.append(
            {
                "level": "warning",
                "message": "Low system memory (<2GB available). Cache limit has been reduced automatically.",
            }
        )

    if not recommendations:
        recommendations.append({"level": "success", "message": "Cache is operating normally."})

    return recommendations


@router.post("/cache/clear", status_code=status.HTTP_200_OK)
async def clear_cache(current_user: CurrentUser = Depends(get_current_user)):
    """Clear the agent cache. Useful after code changes or for troubleshooting."""
    clear_agent_cache()
    return {"message": "Agent cache cleared successfully", "cached_agents": 0}


class TestAgentRequest(BaseModel):
    """Test agent request."""

    message: str = Field(..., min_length=1, max_length=5000)
    history: Optional[List[Dict[str, str]]] = Field(
        default=None, description="Conversation history with role and content"
    )


class FileReference(BaseModel):
    """Reference to an uploaded file."""

    path: str  # MinIO object key
    type: str  # file type: image, document, audio, video, other
    name: str  # original filename
    size: int  # file size in bytes
    content_type: str  # MIME type


@router.post("/{agent_id}/test")
async def test_agent(
    agent_id: str,
    message: str = Body(..., min_length=1, max_length=5000, embed=True),
    history: Optional[str] = Body(None, embed=True),  # JSON string of conversation history
    files: List[UploadFile] = File(default=[]),
    stream: bool = Query(default=True),  # Query parameter to enable/disable streaming
    session_id: Optional[str] = Query(
        None, description="Session ID for persistent execution environment"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Test agent with a message and optional files (streaming SSE response or single response).

    This endpoint tests the full agent capabilities including:
    - System prompt
    - Skills/functions (dynamically loaded)
    - Memory access
    - Real agent execution via AgentExecutor
    - Conversation history support
    - Agent caching for faster subsequent requests
    - File processing via agent skills

    File Processing:
    - Files are processed by agent skills (if available)
    - If agent has 'image_processing' skill: processes images
    - If agent has 'document_processing' skill: processes documents
    - If agent has 'ocr' skill: extracts text from images
    - Without relevant skills: files are skipped, only text is processed
    - Skills are dynamically loaded from skill_library at runtime

    Args:
        agent_id: Agent ID
        message: User message
        history: Optional JSON string of conversation history
        files: Optional list of uploaded files
        stream: Enable streaming (default: True)
        session_id: Optional session ID for persistent execution environment
        current_user: Current authenticated user

    Session Persistence:
        - If session_id is provided, the session's working directory is reused
        - Files created in previous rounds persist across conversation turns
        - Installed dependencies (pip packages) persist within the session
        - A new session is created if session_id is not provided or invalid
        - Session events are emitted: {"type": "session", "session_id": "...", "new_session": true/false}
    """
    import asyncio
    import json
    import queue
    import threading

    from fastapi.responses import StreamingResponse
    from langchain_community.chat_models import ChatOllama

    from agent_framework.agent_executor import ExecutionContext, get_agent_executor
    from agent_framework.base_agent import AgentConfig, BaseAgent
    from llm_providers.custom_openai_provider import CustomOpenAIChat

    try:
        # Parse history from JSON string
        parsed_history = []
        if history:
            try:
                parsed_history = json.loads(history)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse history JSON: {e}")

        # Upload files to MinIO and create file references
        file_refs: List[FileReference] = []
        if files:
            minio_client = get_minio_client()

            for file in files:
                try:
                    # Detect file type
                    content_type = file.content_type or "application/octet-stream"
                    file_type = "other"

                    if content_type.startswith("image/"):
                        file_type = "image"
                        bucket_type = "images"
                    elif content_type in [
                        "application/pdf",
                        "application/msword",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "text/plain",
                    ]:
                        file_type = "document"
                        bucket_type = "documents"
                    elif content_type.startswith("audio/"):
                        file_type = "audio"
                        bucket_type = "audio"
                    elif content_type.startswith("video/"):
                        file_type = "video"
                        bucket_type = "video"
                    else:
                        bucket_type = "documents"  # Default bucket

                    # Read file data
                    file_data = await file.read()
                    file_stream = io.BytesIO(file_data)

                    # Upload to MinIO
                    # Note: MinIO metadata only supports ASCII characters
                    # Store filename in file_ref instead of metadata
                    bucket_name, object_key = minio_client.upload_file(
                        bucket_type=bucket_type,
                        file_data=file_stream,
                        filename=file.filename or "unnamed",
                        user_id=current_user.user_id,
                        task_id=None,
                        agent_id=agent_id,
                        content_type=content_type,
                        metadata={
                            "agent_id": agent_id,
                            "uploaded_by": current_user.user_id,
                            # Don't include filename in metadata to avoid non-ASCII errors
                        },
                    )

                    # Create file reference
                    file_ref = FileReference(
                        path=f"{bucket_name}/{object_key}",
                        type=file_type,
                        name=file.filename or "unnamed",
                        size=len(file_data),
                        content_type=content_type,
                    )
                    file_refs.append(file_ref)

                    logger.info(
                        f"File uploaded for agent test: {file.filename}",
                        extra={
                            "agent_id": agent_id,
                            "file_type": file_type,
                            "size": len(file_data),
                            "object_key": object_key,
                        },
                    )

                except Exception as file_error:
                    logger.error(f"Failed to upload file {file.filename}: {file_error}")
                    # Continue with other files
                    continue

        registry = get_agent_registry()
        agent_info = registry.get_agent(UUID(agent_id))

        if not agent_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to test this agent",
            )

        logger.info(
            f"Testing agent: {agent_info.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )

        async def generate_stream():
            """Generate SSE stream for agent execution with real streaming."""
            try:
                # Track timing and tokens
                import time

                start_time = time.time()
                first_token_time = None
                last_token_time = None
                input_tokens = 0
                output_tokens = 0

                # Session management for persistent execution environment
                from agent_framework.session_manager import get_session_manager

                session_mgr = get_session_manager()
                session, is_new_session = await session_mgr.get_or_create_session(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    session_id=session_id,
                )

                # Emit session event to frontend
                session_event = {
                    "type": "session",
                    "session_id": session.session_id,
                    "new_session": is_new_session,
                    "workdir": str(session.workdir),
                    "use_sandbox": session.use_sandbox,
                    "sandbox_id": session.sandbox_id,
                }
                yield f"data: {json.dumps(session_event)}\n\n"

                logger.info(
                    f"Session {'created' if is_new_session else 'resumed'}: {session.session_id}",
                    extra={
                        "session_id": session.session_id,
                        "agent_id": agent_id,
                        "new_session": is_new_session,
                        "workdir": str(session.workdir),
                        "use_sandbox": session.use_sandbox,
                        "sandbox_id": session.sandbox_id,
                    },
                )

                # Check if agent is already cached
                # Include capabilities in cache key to invalidate when skills change
                # Use v2 prefix to invalidate all old caches
                capabilities_hash = hash(tuple(sorted(agent_info.capabilities or [])))
                cache_key = f"v2_{agent_id}_{agent_info.llm_provider}_{agent_info.llm_model}_{capabilities_hash}"
                agent, llm = get_cached_agent(cache_key)

                if agent is not None and llm is not None:
                    logger.info(f"Reusing cached agent: {agent_info.name}")
                    yield f"data: {json.dumps({'type': 'info', 'content': 'Using cached agent...'})}\n\n"
                else:
                    # Send start event
                    yield f"data: {json.dumps({'type': 'start', 'content': 'Agent execution started'})}\n\n"
                    yield f"data: {json.dumps({'type': 'info', 'content': 'Initializing agent...'})}\n\n"

                    # Create agent config
                    config = AgentConfig(
                        agent_id=UUID(agent_id),
                        name=agent_info.name,
                        agent_type=agent_info.agent_type,
                        owner_user_id=UUID(current_user.user_id),
                        capabilities=agent_info.capabilities or [],
                        llm_model=agent_info.llm_model or "llama3.2:latest",
                        temperature=agent_info.temperature or 0.7,
                        max_iterations=10,
                        system_prompt=agent_info.system_prompt,
                    )

                    # Create agent instance
                    agent = BaseAgent(config)

                    provider_name = agent_info.llm_provider or "ollama"
                    model_name = agent_info.llm_model or "llama3.2:latest"
                    temperature = agent_info.temperature or 0.7

                    # Create LLM instance - only from database
                    llm = None
                    try:
                        from database.connection import get_db_session
                        from llm_providers.db_manager import ProviderDBManager

                        with get_db_session() as db:
                            db_manager = ProviderDBManager(db)
                            db_provider = db_manager.get_provider(provider_name)

                            if db_provider and db_provider.enabled:
                                if db_provider.protocol == "openai_compatible":
                                    api_key = None
                                    if db_provider.api_key_encrypted:
                                        api_key = db_manager._decrypt_api_key(
                                            db_provider.api_key_encrypted
                                        )

                                    # Use CustomOpenAIChat for all OpenAI-compatible providers
                                    # It intelligently handles /v1 suffix in base_url
                                    base_url = db_provider.base_url
                                    llm = CustomOpenAIChat(
                                        base_url=base_url,
                                        model=model_name,
                                        temperature=temperature,
                                        api_key=api_key,
                                        timeout=db_provider.timeout,
                                        max_retries=db_provider.max_retries,
                                        max_tokens=agent_info.max_tokens,
                                        streaming=True,
                                    )
                                    logger.info(
                                        f"[LLM-INIT] Using CustomOpenAIChat: provider={provider_name}, base_url={base_url}"
                                    )

                                elif db_provider.protocol == "ollama":
                                    # Use CustomOpenAIChat for Ollama to support reasoning content streaming
                                    # Ollama provides OpenAI-compatible API at /v1/chat/completions
                                    llm = CustomOpenAIChat(
                                        base_url=db_provider.base_url,
                                        model=model_name,
                                        temperature=temperature,
                                        max_tokens=agent_info.max_tokens,
                                        api_key=None,  # Ollama doesn't require API key
                                        streaming=True,
                                    )
                                    logger.info(
                                        f"[LLM-INIT] Using CustomOpenAIChat for Ollama: {provider_name} at {db_provider.base_url}"
                                    )
                            else:
                                logger.error(
                                    f"Provider '{provider_name}' not found or disabled in database"
                                )

                    except Exception as db_error:
                        logger.error(
                            f"Failed to load provider from database: {db_error}", exc_info=True
                        )

                    if llm is None:
                        raise ValueError(f"Could not create LLM for provider: {provider_name}")

                    agent.llm = llm

                    # Initialize agent (now async)
                    await agent.initialize()

                    # Cache the initialized agent with 30 minute TTL
                    # Use same cache key format (includes capabilities hash)
                    capabilities_hash = hash(tuple(sorted(agent_info.capabilities or [])))
                    cache_key = f"{agent_id}_{agent_info.llm_provider}_{agent_info.llm_model}_{capabilities_hash}"
                    cache_agent(cache_key, agent, llm, ttl_minutes=30)

                model_info = f"{agent_info.llm_model or 'llama3.2:latest'} via {agent_info.llm_provider or 'ollama'}"
                yield f"data: {json.dumps({'type': 'info', 'content': f'Using model: {model_info}'})}\n\n"

                if agent.config.capabilities:
                    yield f"data: {json.dumps({'type': 'info', 'content': f'Available skills: {', '.join(agent.config.capabilities)}'})}\n\n"

                yield f"data: {json.dumps({'type': 'info', 'content': 'Retrieving relevant memories and processing...'})}\n\n"
                logger.debug(
                    "[STREAM] Sent status: type='info', content='Retrieving relevant memories and processing...'"
                )

                # Get memory context
                context = {}
                try:
                    from memory_system.embedding_service import (
                        OllamaEmbeddingService,
                        get_embedding_service,
                        set_embedding_service,
                    )
                    from memory_system.memory_interface import MemoryType, SearchQuery

                    # Check if agent has custom embedding configuration
                    custom_embedding_service = None
                    if agent_info.embedding_provider and agent_info.embedding_model:
                        logger.info(
                            f"Agent {agent_info.name} uses custom embedding: "
                            f"provider={agent_info.embedding_provider}, model={agent_info.embedding_model}"
                        )

                        # Create agent-specific embedding service
                        try:
                            from database.connection import get_db_session
                            from llm_providers.db_manager import ProviderDBManager

                            with get_db_session() as db:
                                db_manager = ProviderDBManager(db)
                                embedding_provider = db_manager.get_provider(
                                    agent_info.embedding_provider
                                )

                                if embedding_provider and embedding_provider.enabled:
                                    # Create custom embedding service with agent's configuration
                                    if embedding_provider.protocol == "ollama":
                                        custom_embedding_service = OllamaEmbeddingService(
                                            base_url=embedding_provider.base_url,
                                            model=agent_info.embedding_model,
                                        )
                                        logger.info(
                                            f"Created custom Ollama embedding service: "
                                            f"{embedding_provider.base_url} / {agent_info.embedding_model}"
                                        )
                                    elif embedding_provider.protocol == "openai_compatible":
                                        # For OpenAI-compatible providers
                                        from memory_system.embedding_service import (
                                            VLLMEmbeddingService,
                                        )

                                        custom_embedding_service = VLLMEmbeddingService(
                                            base_url=embedding_provider.base_url,
                                            model=agent_info.embedding_model,
                                        )
                                        logger.info(
                                            f"Created custom OpenAI-compatible embedding service: "
                                            f"{embedding_provider.base_url} / {agent_info.embedding_model}"
                                        )
                                else:
                                    logger.warning(
                                        f"Embedding provider {agent_info.embedding_provider} not found or disabled"
                                    )
                        except Exception as embed_error:
                            logger.error(
                                f"Failed to create custom embedding service: {embed_error}",
                                exc_info=True,
                            )

                    # If we have a custom embedding service, temporarily set it and create new MemorySystem
                    if custom_embedding_service:
                        # Save original and set custom
                        original_service = get_embedding_service()
                        set_embedding_service(custom_embedding_service)

                        # Create a NEW MemorySystem instance that will use the custom embedding service
                        from memory_system.memory_system import MemorySystem

                        memory_system = MemorySystem()

                        logger.info(f"Using custom embedding service for agent {agent_info.name}")
                    else:
                        # Use default memory system
                        from memory_system.memory_system import get_memory_system

                        memory_system = get_memory_system()
                        original_service = None

                    # Search agent memories
                    agent_query = SearchQuery(
                        query_text=message,
                        agent_id=str(agent_id),
                        memory_type=MemoryType.AGENT,
                        top_k=agent_info.top_k or 5,
                    )
                    agent_memories = memory_system.retrieve_memories(agent_query)
                    context["agent_memories"] = [m.content for m in agent_memories]

                    # Search company memories
                    company_query = SearchQuery(
                        query_text=message,
                        user_id=current_user.user_id,
                        memory_type=MemoryType.COMPANY,
                        top_k=agent_info.top_k or 5,
                    )
                    company_memories = memory_system.retrieve_memories(company_query)
                    context["company_memories"] = [m.content for m in company_memories]

                    # Restore original embedding service if we changed it
                    if original_service is not None:
                        set_embedding_service(original_service)
                        logger.info("Restored original embedding service")

                except Exception as mem_error:
                    logger.error(f"Failed to retrieve memories: {mem_error}", exc_info=True)
                    # Make sure to restore original embedding service even on error
                    if "original_service" in locals() and original_service is not None:
                        try:
                            set_embedding_service(original_service)
                        except:
                            pass

                # Build messages with conversation history
                from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

                system_prompt = agent._create_system_prompt()
                messages = [SystemMessage(content=system_prompt)]

                # Add conversation history if provided
                if parsed_history:
                    for msg in parsed_history:
                        if msg.get("role") == "user":
                            messages.append(HumanMessage(content=msg.get("content", "")))
                        elif msg.get("role") == "assistant":
                            messages.append(AIMessage(content=msg.get("content", "")))

                # Process files with agent skills (if available)
                file_processing_results = []
                if file_refs:
                    yield f"data: {json.dumps({'type': 'info', 'content': f'Processing {len(file_refs)} file(s)...'})}\n\n"

                    # Check agent skills
                    agent_skills = agent_info.capabilities or []
                    has_image_skill = "image_processing" in agent_skills
                    has_doc_skill = "document_processing" in agent_skills
                    has_ocr_skill = "ocr" in agent_skills

                    for file_ref in file_refs:
                        try:
                            if file_ref.type == "image":
                                if has_image_skill:
                                    # TODO: Load and execute image_processing skill
                                    yield f"data: {json.dumps({'type': 'info', 'content': f'Analyzing image: {file_ref.name}'})}\n\n"
                                    file_processing_results.append(
                                        f"[Image: {file_ref.name}] - Image processing skill not yet implemented"
                                    )
                                elif has_ocr_skill:
                                    # TODO: Load and execute OCR skill
                                    yield f"data: {json.dumps({'type': 'info', 'content': f'Extracting text from image: {file_ref.name}'})}\n\n"
                                    file_processing_results.append(
                                        f"[Image: {file_ref.name}] - OCR skill not yet implemented"
                                    )
                                else:
                                    logger.info(
                                        f"Agent {agent_id} lacks image processing skills, skipping image {file_ref.name}"
                                    )
                                    file_processing_results.append(
                                        f"[Image: {file_ref.name}] - Attached (no processing skill available)"
                                    )

                            elif file_ref.type == "document":
                                if has_doc_skill:
                                    # TODO: Load and execute document_processing skill
                                    yield f"data: {json.dumps({'type': 'info', 'content': f'Processing document: {file_ref.name}'})}\n\n"
                                    file_processing_results.append(
                                        f"[Document: {file_ref.name}] - Document processing skill not yet implemented"
                                    )
                                else:
                                    logger.info(
                                        f"Agent {agent_id} lacks document processing skills, skipping document {file_ref.name}"
                                    )
                                    file_processing_results.append(
                                        f"[Document: {file_ref.name}] - Attached (no processing skill available)"
                                    )

                            else:
                                # Other file types
                                file_processing_results.append(
                                    f"[File: {file_ref.name}] - Attached"
                                )

                        except Exception as process_error:
                            logger.error(f"Error processing file {file_ref.name}: {process_error}")
                            file_processing_results.append(
                                f"[File: {file_ref.name}] - Processing failed: {str(process_error)}"
                            )

                # Add current message with file processing results
                user_message = message
                if context:
                    context_info = []
                    if context.get("agent_memories"):
                        context_info.append(
                            f"Relevant memories: {', '.join(context['agent_memories'][:3])}"
                        )
                    if context.get("company_memories"):
                        context_info.append(
                            f"Company knowledge: {', '.join(context['company_memories'][:3])}"
                        )

                    if context_info:
                        user_message = f"{message}\n\nContext:\n" + "\n".join(context_info)

                # Check if model supports vision
                model_supports_vision = False
                try:
                    from database.connection import get_db_session
                    from llm_providers.db_manager import ProviderDBManager
                    from llm_providers.model_metadata import EnhancedModelCapabilityDetector

                    provider_name = agent_info.llm_provider or "ollama"
                    model_name = agent_info.llm_model or "llama3.2:latest"

                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        provider = db_manager.get_provider(provider_name)

                        if (
                            provider
                            and provider.model_metadata
                            and model_name in provider.model_metadata
                        ):
                            # Use stored metadata from database
                            metadata_dict = provider.model_metadata[model_name]
                            model_supports_vision = metadata_dict.get("supports_vision", False)
                            logger.info(
                                f"Model {model_name} vision support from database: {model_supports_vision}"
                            )
                        else:
                            # Generate metadata using detector (same as API endpoint)
                            detector = EnhancedModelCapabilityDetector()
                            metadata = detector.detect_metadata(model_name, provider_name)
                            model_supports_vision = metadata.supports_vision
                            logger.info(
                                f"Model {model_name} vision support from detector: {model_supports_vision}"
                            )

                except Exception as meta_error:
                    logger.error(
                        f"Failed to check model vision support: {meta_error}", exc_info=True
                    )
                    model_supports_vision = False

                # Build message content based on model capabilities
                multimodal_content = None  # Will be passed to agent for vision models
                if model_supports_vision and file_refs:
                    # For vision models, use multimodal content format
                    multimodal_content = []

                    # Add text content
                    if user_message:
                        multimodal_content.append({"type": "text", "text": user_message})

                    # Add image content
                    minio_client = get_minio_client()
                    for file_ref in file_refs:
                        if file_ref.type == "image":
                            try:
                                # Download image from MinIO
                                bucket_name, object_key = file_ref.path.split("/", 1)
                                image_stream, metadata = minio_client.download_file(
                                    bucket_name, object_key
                                )

                                # Read image data
                                image_data = image_stream.read()

                                # Convert to base64
                                import base64

                                image_base64 = base64.b64encode(image_data).decode("utf-8")

                                # Determine image format from content type
                                image_format = "jpeg"  # default
                                if file_ref.content_type:
                                    if "png" in file_ref.content_type:
                                        image_format = "png"
                                    elif "webp" in file_ref.content_type:
                                        image_format = "webp"
                                    elif "gif" in file_ref.content_type:
                                        image_format = "gif"

                                # Add image to message content
                                multimodal_content.append(
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/{image_format};base64,{image_base64}"
                                        },
                                    }
                                )

                                yield f"data: {json.dumps({'type': 'info', 'content': f'Image {file_ref.name} added to message for vision model'})}\n\n"

                            except Exception as img_error:
                                logger.error(f"Failed to load image {file_ref.name}: {img_error}")
                                yield f"data: {json.dumps({'type': 'info', 'content': f'Failed to load image {file_ref.name}'})}\n\n"

                    logger.info(
                        f"Built multimodal content with {len(multimodal_content)} parts "
                        f"for vision model"
                    )

                else:
                    # For non-vision models or no images, use text-only format
                    # Append file processing results to message
                    if file_processing_results:
                        user_message += "\n\nAttached files:\n" + "\n".join(file_processing_results)

                # Send status message before generating content
                yield f"data: {json.dumps({'type': 'info', 'content': 'Generating response...'})}\n\n"
                logger.debug("[STREAM] Sent status: type='info', content='Generating response...'")

                # Use a queue to collect streamed tokens from the agent
                token_queue = queue.Queue()
                error_holder = [None]
                final_response = [""]
                response_metadata = [{}]

                def stream_callback(token_data):
                    """Callback for streaming tokens from agent."""
                    nonlocal first_token_time, last_token_time
                    if first_token_time is None:
                        first_token_time = time.time()
                    last_token_time = time.time()
                    token_queue.put(token_data)

                def execute_agent():
                    """Execute agent in a separate thread."""
                    try:
                        # Use agent.execute_task with streaming callback instead of direct LLM streaming
                        # This ensures tools are executed properly
                        # Pass session workdir for persistent execution environment
                        # Pass container_id for Docker sandbox execution (if session has one)
                        result = agent.execute_task(
                            task_description=user_message,
                            context=context,
                            stream_callback=stream_callback,
                            session_workdir=session.workdir,
                            container_id=session.sandbox_id,  # Docker container for sandbox execution
                            message_content=multimodal_content,
                        )

                        # Store final response
                        final_response[0] = result.get("output", "")

                        # Get metadata if available
                        if result.get("messages"):
                            for msg in reversed(result["messages"]):
                                if hasattr(msg, "response_metadata") and msg.response_metadata:
                                    response_metadata[0] = msg.response_metadata
                                    break

                        # Signal completion
                        token_queue.put(None)

                    except Exception as e:
                        logger.error(f"Agent execution error: {e}", exc_info=True)
                        error_holder[0] = str(e)
                        token_queue.put(None)

                # Start agent execution in background thread
                exec_thread = threading.Thread(target=execute_agent)
                exec_thread.start()

                # Stream tokens as they arrive
                while True:
                    try:
                        # Wait for token with timeout
                        token_data = token_queue.get(timeout=0.1)

                        if token_data is None:
                            # Execution complete
                            break

                        # token_data can be either a string (old format) or tuple (token, type)
                        if isinstance(token_data, tuple):
                            token, content_type = token_data
                        else:
                            token = token_data
                            content_type = "content"

                        # Debug: Log what we're sending
                        logger.debug(
                            f"[STREAM] Sending to frontend: type='{content_type}', length={len(str(token))}"
                        )

                        # Handle round_stats specially - the token is already JSON
                        if content_type == "round_stats":
                            try:
                                stats_data = json.loads(token)
                                stats_data["type"] = "round_stats"
                                yield f"data: {json.dumps(stats_data)}\n\n"
                            except json.JSONDecodeError:
                                logger.warning(f"[STREAM] Invalid round_stats JSON: {token}")
                        else:
                            # Send token to client with type information
                            yield f"data: {json.dumps({'type': content_type, 'content': token})}\n\n"

                    except queue.Empty:
                        # Check if thread is still alive
                        if not exec_thread.is_alive():
                            # Thread finished but no None signal - something went wrong
                            logger.warning(
                                "[STREAM] Thread finished without sending completion signal"
                            )
                            break
                        # No token yet, continue waiting
                        continue

                # Wait for thread to complete (should already be done)
                exec_thread.join(timeout=5)

                # Check if there was an error
                if error_holder[0]:
                    logger.error(f"[STREAM] Agent execution error: {error_holder[0]}")
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {error_holder[0]}'})}\n\n"

                # Calculate statistics
                end_time = time.time()

                # Extract token counts from metadata
                metadata = response_metadata[0]

                # 详细日志：打印完整的metadata结构
                logger.info(
                    f"[TOKEN-STATS] Full metadata structure: {json.dumps(metadata, default=str, ensure_ascii=False)}"
                )

                if "usage" in metadata:
                    usage = metadata["usage"]
                    logger.info(f"[TOKEN-STATS] Found 'usage' field: {usage}")
                    if isinstance(usage, dict):
                        input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0) or usage.get(
                            "output_tokens", 0
                        )
                    else:
                        # usage_metadata object
                        input_tokens = getattr(usage, "input_tokens", 0)
                        output_tokens = getattr(usage, "output_tokens", 0)
                    logger.info(
                        f"[TOKEN-STATS] Extracted from 'usage': input={input_tokens}, output={output_tokens}"
                    )
                elif "token_usage" in metadata:
                    token_usage = metadata["token_usage"]
                    logger.info(f"[TOKEN-STATS] Found 'token_usage' field: {token_usage}")
                    input_tokens = token_usage.get("prompt_tokens", 0)
                    output_tokens = token_usage.get("completion_tokens", 0)
                    logger.info(
                        f"[TOKEN-STATS] Extracted from 'token_usage': input={input_tokens}, output={output_tokens}"
                    )

                # Fallback: estimate if no metadata available
                if input_tokens == 0 and output_tokens == 0:
                    # 流式模式下LLM API通常不返回token统计，需要估算
                    # 改进的估算：中文1字符≈1.5token，英文1字符≈0.25token
                    # 简化：平均1字符≈0.5token（考虑中英文混合）
                    input_chars = 0
                    for msg in messages:
                        if hasattr(msg, "content"):
                            if isinstance(msg.content, str):
                                input_chars += len(msg.content)
                            elif isinstance(msg.content, list):
                                # 多模态内容（图片+文本）
                                for item in msg.content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        input_chars += len(item.get("text", ""))

                    # 改进的token估算：中英文混合平均
                    input_tokens = int(input_chars * 0.5)
                    # 安全处理：如果final_response[0]是None，使用0
                    output_text = final_response[0] if final_response[0] is not None else ""
                    output_tokens = int(len(output_text) * 0.5)

                    logger.info(
                        f"Token estimation (no metadata from streaming API): input={input_tokens} (chars={input_chars}), output={output_tokens} (chars={len(output_text)}), messages_count={len(messages)}"
                    )
                else:
                    logger.info(
                        f"Token from metadata: input={input_tokens}, output={output_tokens}"
                    )

                total_tokens = input_tokens + output_tokens

                # Calculate speeds (only generation time, not initialization)
                time_to_first_token = (first_token_time - start_time) if first_token_time else 0

                # Tokens per second: only count generation time (first token to last token)
                # If no chunks were streamed (chunk_count=0), use total time instead
                if first_token_time and last_token_time and output_tokens > 0:
                    generation_time = last_token_time - first_token_time
                    if generation_time > 0:
                        tokens_per_second = output_tokens / generation_time
                    else:
                        # Fallback: use total time if generation_time is 0
                        total_time = end_time - start_time
                        tokens_per_second = output_tokens / total_time if total_time > 0 else 0
                elif output_tokens > 0:
                    # No streaming happened (chunk_count=0), use total time
                    total_time = end_time - start_time
                    tokens_per_second = output_tokens / total_time if total_time > 0 else 0
                else:
                    tokens_per_second = 0

                # Check for errors
                if error_holder[0]:
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Agent execution failed: {error_holder[0]}'})}\n\n"
                else:
                    # Send statistics
                    stats = {
                        "type": "stats",
                        "timeToFirstToken": round(time_to_first_token, 2),
                        "tokensPerSecond": round(tokens_per_second, 1),
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "totalTokens": total_tokens,
                        "totalTime": round(end_time - start_time, 2),
                    }
                    yield f"data: {json.dumps(stats)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'content': 'Agent execution completed'})}\n\n"

                logger.info(
                    f"Agent test completed: {agent_info.name} (tokens: {input_tokens}/{output_tokens}, speed: {tokens_per_second:.1f} tok/s)"
                )

            except Exception as e:
                logger.error(f"Error during agent test streaming: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"

        if stream:
            # Return streaming response
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )
        else:
            # Non-streaming response - execute and return complete result
            try:
                # Create agent config
                config = AgentConfig(
                    agent_id=UUID(agent_id),
                    name=agent_info.name,
                    agent_type=agent_info.agent_type,
                    owner_user_id=UUID(current_user.user_id),
                    capabilities=agent_info.capabilities or [],
                    llm_model=agent_info.llm_model or "llama3.2:latest",
                    temperature=agent_info.temperature or 0.7,
                    max_iterations=10,
                    system_prompt=agent_info.system_prompt,
                )

                agent = BaseAgent(config)

                provider_name = agent_info.llm_provider or "ollama"
                model_name = agent_info.llm_model or "llama3.2:latest"
                temperature = agent_info.temperature or 0.7

                # Create LLM instance - only from database
                llm = None
                try:
                    from database.connection import get_db_session
                    from llm_providers.db_manager import ProviderDBManager

                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        db_provider = db_manager.get_provider(provider_name)

                        if db_provider and db_provider.enabled:
                            if db_provider.protocol == "openai_compatible":
                                api_key = None
                                if db_provider.api_key_encrypted:
                                    api_key = db_manager._decrypt_api_key(
                                        db_provider.api_key_encrypted
                                    )

                                # Use CustomOpenAIChat for all OpenAI-compatible providers
                                # It intelligently handles /v1 suffix in base_url
                                base_url = db_provider.base_url
                                llm = CustomOpenAIChat(
                                    base_url=base_url,
                                    model=model_name,
                                    temperature=temperature,
                                    api_key=api_key,
                                    timeout=db_provider.timeout,
                                    max_retries=db_provider.max_retries,
                                    max_tokens=agent_info.max_tokens,
                                )
                                logger.info(
                                    f"[LLM-INIT] Using CustomOpenAIChat (non-streaming): provider={provider_name}, base_url={base_url}"
                                )
                            elif db_provider.protocol == "ollama":
                                # Use CustomOpenAIChat for Ollama to support reasoning content
                                llm = CustomOpenAIChat(
                                    base_url=db_provider.base_url,
                                    model=model_name,
                                    temperature=temperature,
                                    max_tokens=agent_info.max_tokens,
                                    api_key=None,  # Ollama doesn't require API key
                                    streaming=False,
                                )
                                logger.info(
                                    f"[LLM-INIT] Using CustomOpenAIChat for Ollama (non-streaming): {provider_name}"
                                )
                        else:
                            logger.error(
                                f"Provider '{provider_name}' not found or disabled in database"
                            )

                except Exception as db_error:
                    logger.error(
                        f"Failed to load provider from database: {db_error}", exc_info=True
                    )

                if llm is None:
                    raise ValueError(f"Could not create LLM for provider: {provider_name}")

                agent.llm = llm
                await agent.initialize()

                # Execute without streaming
                exec_context = ExecutionContext(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    task_description=message,
                )

                executor = get_agent_executor()
                result = await asyncio.to_thread(executor.execute, agent, exec_context)

                return {
                    "success": result.get("success"),
                    "output": result.get("output"),
                    "error": result.get("error"),
                }

            except Exception as e:
                logger.error(f"Non-streaming execution failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Execution failed: {str(e)}",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test agent: {str(e)}",
        )


@router.delete("/{agent_id}/sessions/{session_id}")
async def end_agent_session(
    agent_id: str,
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    End an agent session and clean up its resources.

    This endpoint explicitly ends a conversation session, cleaning up:
    - Working directory and all files created during the session
    - Sandbox container (if sandbox mode was enabled)
    - Any cached state associated with the session

    The session is also automatically cleaned up after TTL expiration (default: 30 minutes
    of inactivity), so this endpoint is optional but recommended for explicit cleanup
    when the user closes the test dialog.

    Args:
        agent_id: Agent ID
        session_id: Session ID to end
        current_user: Current authenticated user

    Returns:
        Success message with session details
    """
    try:
        from agent_framework.session_manager import get_session_manager

        session_mgr = get_session_manager()
        session = session_mgr.get_session(session_id)

        if not session:
            # Session already gone (expired or cleaned up) — desired state achieved.
            # DELETE is idempotent: return success, not 404.
            logger.info(
                f"Session {session_id} already ended (not found)",
                extra={"session_id": session_id, "agent_id": agent_id},
            )
            return {
                "message": "Session already ended",
                "session_id": session_id,
                "agent_id": agent_id,
            }

        # Verify the session belongs to the requesting user
        if session.user_id != UUID(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to end this session",
            )

        # Verify the session is for the correct agent
        if str(session.agent_id) != agent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_id} does not belong to agent {agent_id}",
            )

        # End the session
        ended = await session_mgr.end_session(session_id, UUID(current_user.user_id))

        if ended:
            logger.info(
                f"Session ended by user: {session_id}",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "user_id": current_user.user_id,
                },
            )
            return {
                "message": "Session ended successfully",
                "session_id": session_id,
                "agent_id": agent_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to end session",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end session: {str(e)}",
        )


@router.get("/{agent_id}/sessions")
async def get_agent_sessions(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get all active sessions for an agent.

    Returns information about all sessions the current user has for the specified agent.
    This is useful for debugging and monitoring session state.

    Args:
        agent_id: Agent ID
        current_user: Current authenticated user

    Returns:
        List of session information
    """
    try:
        from agent_framework.session_manager import get_session_manager

        session_mgr = get_session_manager()
        user_sessions = session_mgr.get_user_sessions(UUID(current_user.user_id))

        # Filter to sessions for this agent
        agent_sessions = [
            {
                "session_id": s.session_id,
                "agent_id": str(s.agent_id),
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "remaining_ttl_seconds": s.remaining_ttl_seconds(),
                "use_sandbox": s.use_sandbox,
                "workdir": str(s.workdir),
            }
            for s in user_sessions
            if str(s.agent_id) == agent_id
        ]

        return {
            "agent_id": agent_id,
            "sessions": agent_sessions,
            "total_count": len(agent_sessions),
        }

    except Exception as e:
        logger.error(f"Failed to get sessions for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sessions: {str(e)}",
        )


# ============================================================================
# Agent Skills Configuration Endpoints
# ============================================================================


class AgentSkillsResponse(BaseModel):
    """Response model for agent skills configuration."""

    agent_id: str
    configured_skills: List[str] = Field(
        description="List of skill names configured for this agent"
    )
    available_skills: List[Dict[str, str]] = Field(description="List of all available skills")


@router.get("/{agent_id}/skills", response_model=AgentSkillsResponse)
async def get_agent_skills(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get agent's configured skills and available skills.

    Returns:
        - configured_skills: Skills currently configured for this agent (in capabilities)
        - available_skills: All skills available in the system
    """
    try:
        agent_uuid = UUID(agent_id)
        registry = get_agent_registry()

        # Get agent info
        agent_info = registry.get_agent(agent_uuid)
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this agent")

        # Get all available skills from database
        from database.connection import get_db_session
        from database.models import Skill

        available_skills = []
        with get_db_session() as session:
            skills = session.query(Skill).filter(Skill.is_active == True).order_by(Skill.name).all()

            for skill in skills:
                available_skills.append(
                    {
                        "skill_id": str(skill.skill_id),
                        "name": skill.name,
                        "description": skill.description,
                        "skill_type": skill.skill_type,
                        "version": skill.version,
                    }
                )

        return AgentSkillsResponse(
            agent_id=agent_id,
            configured_skills=agent_info.capabilities or [],
            available_skills=available_skills,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get agent skills: {str(e)}")


class UpdateAgentSkillsRequest(BaseModel):
    """Request model for updating agent skills."""

    skill_names: List[str] = Field(description="List of skill names to configure for this agent")


@router.put("/{agent_id}/skills", response_model=AgentResponse)
async def update_agent_skills(
    agent_id: str,
    request: UpdateAgentSkillsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update agent's configured skills.

    This updates the agent's capabilities list with the selected skills.
    The agent will load these skills on next initialization.
    """
    try:
        agent_uuid = UUID(agent_id)
        registry = get_agent_registry()

        # Get agent info
        agent_info = registry.get_agent(agent_uuid)
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this agent")

        # Validate that all skill names exist
        from database.connection import get_db_session
        from database.models import Skill

        with get_db_session() as session:
            for skill_name in request.skill_names:
                skill = (
                    session.query(Skill)
                    .filter(Skill.name == skill_name, Skill.is_active == True)
                    .first()
                )

                if not skill:
                    raise HTTPException(
                        status_code=400, detail=f"Skill '{skill_name}' not found or not active"
                    )

        # Update agent capabilities
        updated_agent = registry.update_agent(agent_uuid, capabilities=request.skill_names)

        if not updated_agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Clear agent from cache to force reload with new skills
        cache_key = f"{agent_id}:{current_user.user_id}"
        if cache_key in _agent_cache:
            del _agent_cache[cache_key]
            logger.info(f"Cleared agent cache after skills update: {agent_id}")

        logger.info(
            f"Updated agent skills: {agent_id}",
            extra={
                "agent_id": agent_id,
                "skill_count": len(request.skill_names),
                "skills": request.skill_names,
            },
        )

        # Return updated agent info
        return AgentResponse(
            agent_id=str(updated_agent.agent_id),
            name=updated_agent.name,
            agent_type=updated_agent.agent_type,
            avatar=_resolve_agent_avatar(updated_agent.avatar),
            owner_user_id=str(updated_agent.owner_user_id),
            capabilities=updated_agent.capabilities,
            status=updated_agent.status,
            llm_provider=updated_agent.llm_provider,
            llm_model=updated_agent.llm_model,
            system_prompt=updated_agent.system_prompt,
            temperature=updated_agent.temperature,
            max_tokens=updated_agent.max_tokens,
            top_p=updated_agent.top_p,
            access_level=updated_agent.access_level,
            allowed_knowledge=updated_agent.allowed_knowledge,
            allowed_memory=updated_agent.allowed_memory,
            embedding_model=updated_agent.embedding_model,
            embedding_provider=updated_agent.embedding_provider,
            vector_dimension=updated_agent.vector_dimension,
            top_k=updated_agent.top_k,
            similarity_threshold=updated_agent.similarity_threshold,
            created_at=updated_agent.created_at,
            updated_at=updated_agent.updated_at,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update agent skills: {str(e)}")
