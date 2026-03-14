"""Shared API contracts for reset-era memory routes."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentCandidateReviewRequest(BaseModel):
    """Review action for learned skill proposals."""

    action: str = Field(..., pattern=r"^(publish|reject|revise)$")
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    note: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MemoryItemResponse(BaseModel):
    """Shared response model for reset-era user-memory and skill-proposal items."""

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    id: str
    type: str
    content: str
    summary: Optional[str] = None
    agent_id: Optional[str] = Field(None, alias="agentId")
    agent_name: Optional[str] = Field(None, alias="agentName")
    user_id: Optional[str] = Field(None, alias="userId")
    user_name: Optional[str] = Field(None, alias="userName")
    created_at: str = Field(..., alias="createdAt")
    tags: List[str] = Field(default_factory=list)
    relevance_score: Optional[float] = Field(None, alias="relevanceScore")
    metadata: Optional[Dict[str, Any]] = None
    is_shared: bool = Field(False, alias="isShared")
    shared_with: List[str] = Field(default_factory=list, alias="sharedWith")
    shared_with_names: List[str] = Field(default_factory=list, alias="sharedWithNames")
    index_status: Optional[str] = Field(None, alias="indexStatus")
    index_error: Optional[str] = Field(None, alias="indexError")


class MemoryConfigResponse(BaseModel):
    """Reset-era config response for user memory, skill learning, and session ledger."""

    user_memory: dict
    skill_learning: dict
    session_ledger: dict
    runtime_context: dict
    recommended: Optional[dict] = None


class MemoryConfigUpdateRequest(BaseModel):
    """Request payload for reset-era memory pipeline updates."""

    user_memory: Optional[dict] = None
    skill_learning: Optional[dict] = None
    session_ledger: Optional[dict] = None
    runtime_context: Optional[dict] = None
