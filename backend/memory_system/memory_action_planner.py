"""Memory action planner for explicit write semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from memory_system.memory_repository import MemoryRecordData

DuplicateMatch = Tuple[MemoryRecordData, float, str]


class MemoryAction(str, Enum):
    """Planner actions for memory write execution."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NONE = "NONE"


@dataclass(frozen=True)
class MemoryActionDecision:
    """Planner output used by the action executor."""

    action: MemoryAction
    reason: str
    source: str = "planner"
    confidence: Optional[float] = None
    existing_record: Optional[MemoryRecordData] = None
    similarity: Optional[float] = None
    merge_reason: Optional[str] = None


class MemoryActionPlanner:
    """Deterministic planner for `ADD/UPDATE/DELETE/NONE` decisions."""

    def __init__(self, *, allow_delete: bool = True):
        self._allow_delete = bool(allow_delete)

    @staticmethod
    def _clamp_confidence(raw: object) -> Optional[float]:
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, value))

    def plan(
        self,
        *,
        requested_action: Optional[MemoryAction],
        explicit_target: Optional[MemoryRecordData],
        exact_duplicate: Optional[DuplicateMatch],
        semantic_duplicate: Optional[DuplicateMatch],
    ) -> MemoryActionDecision:
        """Plan one explicit action from optional hints and dedupe candidates."""
        duplicate = exact_duplicate or semantic_duplicate

        if requested_action == MemoryAction.NONE:
            return MemoryActionDecision(
                action=MemoryAction.NONE,
                reason="explicit_none",
                confidence=1.0,
            )

        if requested_action == MemoryAction.DELETE:
            if not self._allow_delete:
                return MemoryActionDecision(
                    action=MemoryAction.NONE,
                    reason="explicit_delete_disabled",
                    confidence=1.0,
                )
            if explicit_target is None:
                return MemoryActionDecision(
                    action=MemoryAction.NONE,
                    reason="explicit_delete_target_missing",
                    confidence=1.0,
                )
            return MemoryActionDecision(
                action=MemoryAction.DELETE,
                reason="explicit_delete_target",
                confidence=1.0,
                existing_record=explicit_target,
                merge_reason="explicit_delete_target",
            )

        if requested_action == MemoryAction.UPDATE:
            if explicit_target is not None:
                return MemoryActionDecision(
                    action=MemoryAction.UPDATE,
                    reason="explicit_update_target",
                    confidence=1.0,
                    existing_record=explicit_target,
                    similarity=1.0,
                    merge_reason="explicit_update_target",
                )
            if duplicate:
                existing, similarity, reason = duplicate
                return MemoryActionDecision(
                    action=MemoryAction.UPDATE,
                    reason=reason or "explicit_update_duplicate",
                    confidence=self._clamp_confidence(similarity),
                    existing_record=existing,
                    similarity=float(similarity),
                    merge_reason=reason or "explicit_update_duplicate",
                )
            return MemoryActionDecision(
                action=MemoryAction.ADD,
                reason="explicit_update_target_missing",
                confidence=0.6,
            )

        if requested_action == MemoryAction.ADD:
            return MemoryActionDecision(
                action=MemoryAction.ADD,
                reason="explicit_add",
                confidence=1.0,
            )

        if duplicate:
            existing, similarity, reason = duplicate
            return MemoryActionDecision(
                action=MemoryAction.UPDATE,
                reason=reason or "dedupe_match",
                confidence=self._clamp_confidence(similarity),
                existing_record=existing,
                similarity=float(similarity),
                merge_reason=reason or "dedupe_match",
            )

        return MemoryActionDecision(
            action=MemoryAction.ADD,
            reason="no_duplicate",
            confidence=0.7,
        )
