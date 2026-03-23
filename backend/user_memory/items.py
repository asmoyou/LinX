"""Shared item contracts for reset-era user-memory and skill retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Union


@dataclass(slots=True)
class RetrievedMemoryItem:
    """Normalized retrieval item used by runtime and API adapters."""

    id: Optional[Union[int, str]]
    content: str
    memory_type: str
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    similarity_score: Optional[float] = None
    summary: Optional[str] = None

    def __post_init__(self) -> None:
        self.memory_type = str(self.memory_type or "").strip() or "user_memory"
        self.metadata = dict(self.metadata or {})
        if self.summary is not None:
            self.summary = str(self.summary).strip() or None
        if self.summary and "summary" not in self.metadata:
            self.metadata["summary"] = self.summary
        self.metadata.setdefault("memory_type", self.memory_type)


__all__ = ["RetrievedMemoryItem"]
