"""Mission Orchestrator.

Manages the full mission lifecycle as an async state machine:
DRAFT -> REQUIREMENTS -> PLANNING -> EXECUTING -> REVIEWING -> QA -> COMPLETED

Also supports FAILED and CANCELLED transitions from any state.
Each running mission is tracked as an ``asyncio.Task``.
"""

import asyncio
import hashlib
import json
import logging
import re
import traceback
from collections import Counter, defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from mission_system.agent_factory import create_mission_agent
from mission_system.agent_factory import create_registered_mission_agent
from mission_system.agent_roles import (
    get_leader_config,
    get_qa_config,
    get_supervisor_config,
)
from mission_system.event_emitter import get_event_emitter
from mission_system.exceptions import (
    MissionCancelledException,
    MissionError,
)
from mission_system.mission_repository import (
    assign_agent as assign_mission_agent,
    get_mission,
    prepare_partial_retry_for_failed_tasks,
    update_agent_status as update_mission_agent_status,
    update_mission_fields,
    update_mission_status,
)
from mission_system.workspace_manager import get_workspace_manager

logger = logging.getLogger(__name__)

# Valid status transitions (source -> set of targets)
_TRANSITIONS: Dict[str, set] = {
    "draft": {"requirements", "cancelled"},
    "requirements": {"planning", "failed", "cancelled"},
    "planning": {"executing", "failed", "cancelled"},
    "executing": {"reviewing", "failed", "cancelled"},
    "reviewing": {"executing", "qa", "failed", "cancelled"},
    "qa": {"reviewing", "completed", "failed", "cancelled"},
    "completed": set(),
    "failed": {"executing"},
    "cancelled": {"executing"},
}

MAX_REVIEW_CYCLES = 2
MAX_QA_CYCLES = 1
MAX_ALLOWED_REWORK_CYCLES = 5
MAX_ALLOWED_QA_CYCLES = 5
MIN_TASK_RELEVANCE_SCORE = 0.12
MAX_OFF_TOPIC_TASK_RATIO = 0.5


class MissionOrchestrator:
    """Singleton orchestrator for mission lifecycle management."""

    def __init__(self) -> None:
        self._active_missions: Dict[UUID, asyncio.Task] = {}
        self._clarification_events: Dict[UUID, asyncio.Event] = {}
        self._clarification_responses: Dict[UUID, str] = {}
        self._emitter = get_event_emitter()
        self._workspace = get_workspace_manager()
        logger.info("MissionOrchestrator initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_mission(self, mission_id: UUID, user_id: UUID) -> None:
        """Launch a mission as a background asyncio.Task.

        Args:
            mission_id: Mission to start.
            user_id: User who triggered the start.
        """
        if mission_id in self._active_missions:
            raise MissionError(mission_id, "Mission is already running")

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        task = asyncio.create_task(
            self._run_mission(mission_id, user_id),
            name=f"mission-{mission_id}",
        )
        self._active_missions[mission_id] = task

        self._emitter.emit(
            mission_id=mission_id,
            event_type="MISSION_STARTED",
            message=f"Mission started by user {user_id}",
        )

    async def retry_failed_parts(self, mission_id: UUID, user_id: UUID) -> None:
        """Retry only unfinished parts of a failed/cancelled mission."""
        if mission_id in self._active_missions:
            raise MissionError(mission_id, "Mission is already running")

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        if mission.status not in {"failed", "cancelled"}:
            raise MissionError(
                mission_id,
                "Only failed or cancelled missions can retry failed parts",
            )

        retry_summary = prepare_partial_retry_for_failed_tasks(mission_id)
        self._emitter.emit(
            mission_id=mission_id,
            event_type="MISSION_PARTIAL_RETRY_REQUESTED",
            data=retry_summary,
            message=(
                "Partial retry requested: "
                f"{retry_summary.get('retried_tasks', 0)} task(s) reset to pending"
            ),
        )

        task = asyncio.create_task(
            self._run_partial_retry(mission_id, user_id),
            name=f"mission-partial-retry-{mission_id}",
        )
        self._active_missions[mission_id] = task

    async def cancel_mission(self, mission_id: UUID) -> None:
        """Cancel a running mission and clean up resources."""
        task = self._active_missions.get(mission_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Mission %s raised while cancelling", mission_id)

        self._active_missions.pop(mission_id, None)

        try:
            update_mission_status(mission_id, "cancelled")
        except ValueError:
            # The mission may already have been deleted after cancellation.
            logger.info("Mission %s not found while setting cancelled status", mission_id)
        except Exception:
            logger.exception("Failed to update cancelled status for %s", mission_id)

        self._cleanup(mission_id)
        self._emitter.emit(
            mission_id=mission_id,
            event_type="MISSION_CANCELLED",
            message="Mission cancelled by user",
        )

    async def cancel_all_active_missions(self) -> Dict[str, int]:
        """Best-effort cancel all active missions.

        Used during API shutdown/reload so mission status does not stay in
        executing/reviewing/qa when the process is restarted.
        """
        active_ids = list(self._active_missions.keys())
        if not active_ids:
            return {"active": 0, "cancelled": 0, "failed": 0}

        cancelled = 0
        failed = 0
        for mission_id in active_ids:
            try:
                await self.cancel_mission(mission_id)
                cancelled += 1
            except Exception:
                failed += 1
                logger.exception("Failed to cancel mission %s during shutdown", mission_id)

        return {"active": len(active_ids), "cancelled": cancelled, "failed": failed}

    def provide_clarification(self, mission_id: UUID, response: str) -> None:
        """Supply a user clarification response for a blocked requirements phase."""
        self._clarification_responses[mission_id] = response
        event = self._clarification_events.get(mission_id)
        if event:
            event.set()

    def get_active_mission_ids(self):
        """Return a list of currently running mission IDs."""
        return list(self._active_missions.keys())

    # ------------------------------------------------------------------
    # Mission lifecycle
    # ------------------------------------------------------------------

    async def _run_mission(self, mission_id: UUID, user_id: UUID) -> None:
        """Execute all mission phases sequentially."""
        try:
            await self._phase_requirements(mission_id)
            await self._phase_planning(mission_id)
            await self._phase_execution(mission_id)
            await self._phase_review(mission_id)
            await self._phase_qa(mission_id)
            await self._phase_complete(mission_id)
        except asyncio.CancelledError:
            logger.info("Mission %s was cancelled", mission_id)
            try:
                self._snapshot_deliverables(mission_id)
                update_mission_status(mission_id, "cancelled")
            except Exception:
                logger.exception("Failed to set cancelled status for mission %s", mission_id)
            raise
        except MissionCancelledException:
            logger.info("Mission %s cancelled via exception", mission_id)
            self._snapshot_deliverables(mission_id)
            update_mission_status(mission_id, "cancelled")
        except Exception as exc:
            trace = traceback.format_exc()
            mission_snapshot = get_mission(mission_id)
            failed_phase = mission_snapshot.status if mission_snapshot else "unknown"
            exec_cfg = self._get_execution_config(mission_snapshot) if mission_snapshot else {}
            debug_mode = self._coerce_bool(exec_cfg.get("debug_mode", False), default=False)
            failure_data: Dict[str, Any] = {
                "error": str(exc),
                "error_type": exc.__class__.__name__,
                "phase": failed_phase,
            }
            if debug_mode:
                failure_data["traceback"] = trace
            logger.exception("Mission %s failed: %s", mission_id, exc)
            self._snapshot_deliverables(mission_id)
            try:
                self._sync_mission_task_counters(
                    mission_id,
                    fallback_total=mission_snapshot.total_tasks if mission_snapshot else 0,
                )
            except Exception:
                logger.exception("Failed to sync mission counters for %s", mission_id)
            update_mission_status(mission_id, "failed", error_message=str(exc))
            self._emitter.emit(
                mission_id=mission_id,
                event_type="PHASE_FAILED",
                data=failure_data,
                message=f"Mission phase failed: {failed_phase}",
            )
            self._emitter.emit(
                mission_id=mission_id,
                event_type="MISSION_FAILED",
                data=failure_data,
                message=str(exc),
            )
        finally:
            self._active_missions.pop(mission_id, None)
            self._cleanup(mission_id)

    async def _run_partial_retry(self, mission_id: UUID, user_id: UUID) -> None:
        """Resume a mission from execution/review/qa without rebuilding plan."""
        _ = user_id
        try:
            mission = get_mission(mission_id)
            if mission is None:
                raise MissionError(mission_id, "Mission not found")
            self._prepare_workspace(mission_id, mission)

            await self._phase_execution(mission_id)
            await self._phase_review(mission_id)
            await self._phase_qa(mission_id)
            await self._phase_complete(mission_id)
        except asyncio.CancelledError:
            logger.info("Mission %s partial retry was cancelled", mission_id)
            try:
                self._snapshot_deliverables(mission_id)
                update_mission_status(mission_id, "cancelled")
            except Exception:
                logger.exception("Failed to set cancelled status for mission %s", mission_id)
            raise
        except MissionCancelledException:
            logger.info("Mission %s partial retry cancelled via exception", mission_id)
            self._snapshot_deliverables(mission_id)
            update_mission_status(mission_id, "cancelled")
        except Exception as exc:
            trace = traceback.format_exc()
            mission_snapshot = get_mission(mission_id)
            failed_phase = mission_snapshot.status if mission_snapshot else "unknown"
            exec_cfg = self._get_execution_config(mission_snapshot) if mission_snapshot else {}
            debug_mode = self._coerce_bool(exec_cfg.get("debug_mode", False), default=False)
            failure_data: Dict[str, Any] = {
                "error": str(exc),
                "error_type": exc.__class__.__name__,
                "phase": failed_phase,
                "mode": "partial_retry",
            }
            if debug_mode:
                failure_data["traceback"] = trace
            logger.exception("Mission %s partial retry failed: %s", mission_id, exc)
            self._snapshot_deliverables(mission_id)
            try:
                self._sync_mission_task_counters(
                    mission_id,
                    fallback_total=mission_snapshot.total_tasks if mission_snapshot else 0,
                )
            except Exception:
                logger.exception("Failed to sync mission counters for %s", mission_id)
            update_mission_status(mission_id, "failed", error_message=str(exc))
            self._emitter.emit(
                mission_id=mission_id,
                event_type="PHASE_FAILED",
                data=failure_data,
                message=f"Mission phase failed: {failed_phase}",
            )
            self._emitter.emit(
                mission_id=mission_id,
                event_type="MISSION_FAILED",
                data=failure_data,
                message=str(exc),
            )
        finally:
            self._active_missions.pop(mission_id, None)
            self._cleanup(mission_id)

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _get_llm_config(self, mission: Any, role: str) -> Dict[str, Any]:
        """Extract LLM config for a role from mission_config.

        Supports two key formats:
        - Settings-merged: {"leader_config": {"llm_provider": "ollama", ...}}
        - Legacy: {"leader": {"provider": "ollama", "model": "..."}}

        Falls back to top-level defaults then hardcoded defaults.
        """
        cfg = getattr(mission, "mission_config", None) or {}
        # Try settings-merged format first (e.g. "leader_config"), then legacy (e.g. "leader")
        role_cfg = cfg.get(f"{role}_config", cfg.get(role, {}))
        inherited_cfg: Dict[str, Any] = {}
        if role == "temporary_worker":
            inherited_cfg = cfg.get("leader_config", cfg.get("leader", {})) or {}
            if not role_cfg:
                execution_cfg = cfg.get("execution_config", {})
                if isinstance(execution_cfg, dict):
                    nested_tmp_cfg = execution_cfg.get("temporary_worker_config")
                    if isinstance(nested_tmp_cfg, dict):
                        role_cfg = nested_tmp_cfg

        def _resolve_value(keys: tuple[str, ...], default: Any) -> Any:
            for source in (role_cfg, inherited_cfg, cfg):
                if not isinstance(source, dict):
                    continue
                for key in keys:
                    if key in source and source[key] is not None:
                        return source[key]
            return default

        return {
            "llm_provider": _resolve_value(("llm_provider", "provider"), "ollama"),
            "llm_model": _resolve_value(("llm_model", "model"), "qwen2.5:14b"),
            "temperature": float(_resolve_value(("temperature",), 0.7)),
            "max_tokens": int(_resolve_value(("max_tokens",), 4096)),
        }

    @staticmethod
    def _get_execution_config(mission: Any) -> Dict[str, Any]:
        """Extract execution config, supporting nested and legacy top-level keys."""
        cfg = getattr(mission, "mission_config", None) or {}
        exec_cfg = cfg.get("execution_config", {})
        if not isinstance(exec_cfg, dict):
            exec_cfg = {}

        merged = dict(exec_cfg)
        for key in (
            "max_retries",
            "task_timeout_s",
            "max_rework_cycles",
            "max_concurrent_tasks",
            "max_qa_cycles",
            "debug_mode",
            "require_dependency_review_pass",
            "enable_team_blueprint",
            "prefer_existing_agents",
            "allow_temporary_workers",
            "auto_select_temp_skills",
            "temp_worker_skill_limit",
            "temp_worker_memory_scopes",
            "temp_worker_knowledge_strategy",
            "temp_worker_knowledge_limit",
        ):
            if key in cfg:
                merged[key] = cfg[key]
        if "network_access" in cfg:
            merged["network_access"] = cfg["network_access"]
        elif "network_access" not in merged and "network_enabled" in cfg:
            merged["network_access"] = bool(cfg["network_enabled"])
        merged["debug_mode"] = MissionOrchestrator._coerce_bool(
            merged.get("debug_mode", False), default=False
        )
        return merged

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        """Best-effort bool coercion for mixed config payloads."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on", "enabled"}:
                return True
            if lowered in {"0", "false", "no", "off", "disabled"}:
                return False
        return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """Best-effort int coercion for mission config values."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _get_task_review_status(task_metadata: Any) -> str:
        """Normalize review_status from task metadata."""
        if not isinstance(task_metadata, dict):
            return ""
        return str(task_metadata.get("review_status") or "").strip().lower()

    @staticmethod
    def _normalize_agent_result(result: Any) -> Dict[str, Any]:
        """Normalize different agent return formats to a dict payload."""
        if isinstance(result, dict):
            return result
        return {
            "success": True,
            "output": "" if result is None else str(result),
        }

    @staticmethod
    def _extract_agent_output(result: Any, context: str) -> str:
        """Extract output from agent response and raise on explicit failures."""
        payload = MissionOrchestrator._normalize_agent_result(result)
        if payload.get("success") is False:
            error_message = payload.get("error") or "Unknown agent execution error"
            raise RuntimeError(f"{context}: {error_message}")
        output = payload.get("output")
        return "" if output is None else str(output)

    @staticmethod
    def _append_attempt_to_result(
        existing_result: Any,
        attempt_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Append attempt metadata to task result while preserving existing fields."""
        result = dict(existing_result) if isinstance(existing_result, dict) else {}
        attempts = result.get("attempts")
        if not isinstance(attempts, list):
            attempts = []
        attempts.append(attempt_record)
        result["attempts"] = attempts[-50:]
        return result

    @staticmethod
    def _build_text_signature(content: Any) -> str:
        """Build a stable signature for text-like content."""
        text = "" if content is None else str(content)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _detect_instruction_language(text: str) -> str:
        """Detect a preferred response language from mission instructions."""
        if not text:
            return "English"
        if re.search(r"[\u4e00-\u9fff]", text):
            return "Simplified Chinese"
        if re.search(r"[\u3040-\u30ff]", text):
            return "Japanese"
        if re.search(r"[\uac00-\ud7af]", text):
            return "Korean"
        return "English"

    @staticmethod
    def _build_temporary_agent_name(task_title: str, task_id: UUID) -> str:
        """Build a stable, readable temporary worker name for a task."""
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", task_title).strip("-").lower()
        if not slug:
            slug = "task"
        return f"temp-worker-{slug[:24]}-{str(task_id)[:8]}"

    @staticmethod
    def _truncate_prompt_text(text: Any, limit: int = 600) -> str:
        """Normalize and truncate free-form text before injecting into system prompts."""
        if text is None:
            return ""
        normalized = str(text).strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "..."

    @staticmethod
    def _sanitize_generated_mission_title(raw_title: Any, fallback: str) -> str:
        """Normalize model output into a single-line mission title."""
        candidate = "" if raw_title is None else str(raw_title)
        candidate = candidate.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", candidate).strip()
            candidate = re.sub(r"\n?```$", "", candidate).strip()

        lines = [line.strip() for line in candidate.splitlines() if line.strip()]
        if lines:
            candidate = lines[0]

        candidate = re.sub(
            r"^(title|mission title|标题)\s*[:：\-]\s*",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()
        candidate = candidate.strip("`\"' ")
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if len(candidate) > 120:
            candidate = candidate[:120].rstrip(" ,;:：。.!?、")
        if candidate:
            return candidate
        return (fallback or "Untitled Mission").strip() or "Untitled Mission"

    def _build_temporary_worker_system_prompt(self, mission: Any, task_obj: Any) -> str:
        """Build a task-specific SOP prompt for temporary workers.

        Temporary workers are intentionally created without pre-bound skills/capabilities,
        but they should still have role-specific behavior. This prompt injects task context
        so each temporary worker follows a differentiated SOP.
        """
        task_metadata = task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
        task_title = task_metadata.get("title", "Untitled")
        mission_title = getattr(mission, "title", "Untitled Mission")

        mission_instruction_snippet = self._truncate_prompt_text(
            getattr(mission, "instructions", ""),
            limit=700,
        )
        task_instruction_snippet = self._truncate_prompt_text(
            getattr(task_obj, "goal_text", ""),
            limit=900,
        )
        acceptance_criteria_snippet = self._truncate_prompt_text(
            getattr(task_obj, "acceptance_criteria", ""),
            limit=900,
        )
        dependency_titles = task_metadata.get("dependencies", [])
        if isinstance(dependency_titles, list):
            dependency_text = ", ".join(str(item) for item in dependency_titles[:10]) or "None"
        else:
            dependency_text = "None"
        owner_role = str(
            task_metadata.get("owner_role_name")
            or task_metadata.get("owner_role")
            or task_metadata.get("role_name")
            or ""
        ).strip()
        role_required_capabilities = self._coerce_string_list(
            task_metadata.get("role_required_capabilities")
        )
        role_sop_hint = str(task_metadata.get("role_sop_hint") or "").strip()

        preferred_language = self._detect_instruction_language(
            "\n".join(
                [
                    str(getattr(mission, "instructions", "") or ""),
                    str(task_title or ""),
                    str(getattr(task_obj, "goal_text", "") or ""),
                ]
            )
        )

        return (
            "You are a temporary specialist worker created for exactly one mission task.\n"
            "Your behavior must be task-specific, evidence-driven, and output-oriented.\n\n"
            "## Mission Context\n"
            f"- Mission: {mission_title}\n"
            f"- Task ID: {task_obj.task_id}\n"
            f"- Task Title: {task_title}\n"
            f"- Preferred response language: {preferred_language}\n"
            f"- Declared dependencies: {dependency_text}\n\n"
            "## Mission Instructions Snapshot\n"
            f"{mission_instruction_snippet or 'N/A'}\n\n"
            "## Task Instructions Snapshot\n"
            f"{task_instruction_snippet or 'N/A'}\n\n"
            "## Acceptance Criteria Snapshot\n"
            f"{acceptance_criteria_snippet or 'N/A'}\n\n"
            "## Assigned Role Context\n"
            f"- Role: {owner_role or 'N/A'}\n"
            "- Role required capabilities: "
            f"{', '.join(role_required_capabilities) if role_required_capabilities else 'N/A'}\n"
            f"- Role SOP hint: {role_sop_hint or 'N/A'}\n\n"
            "## Task-Specific SOP\n"
            "1. Restate the concrete deliverable and constraints before execution.\n"
            "2. Respect dependencies. If blocked, explicitly report the blocker.\n"
            "3. Produce real artifacts in workspace files, not just explanations.\n"
            "4. Self-check each acceptance criterion and fix gaps before finalizing.\n"
            "5. Return a concise completion report containing:\n"
            "   - files changed/created,\n"
            "   - acceptance checklist,\n"
            "   - remaining risks/assumptions.\n\n"
            "## Output Location Policy\n"
            "- Put final user-facing deliverables under `/workspace/output`.\n"
            "- Intermediate notes/logs/scripts can stay under `/workspace/shared` or `/workspace/tasks`.\n"
            "- Avoid placing final deliverables in `/workspace` root.\n\n"
            "Do not output tool placeholders as final answer. Deliver completed work."
        )

    @staticmethod
    def _coerce_string_list(value: Any, max_items: int = 32) -> List[str]:
        """Best-effort normalize list-like values to non-empty unique strings."""
        if not isinstance(value, list):
            return []
        normalized: List[str] = []
        for raw in value[:max_items]:
            text = str(raw or "").strip()
            if not text:
                continue
            if text not in normalized:
                normalized.append(text)
        return normalized

    @staticmethod
    def _normalize_role_key(value: Any) -> str:
        """Normalize role identifiers to stable matching keys."""
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", raw).strip("_")
        return key

    @staticmethod
    def _tokenize_for_match(*parts: Any) -> set[str]:
        """Tokenize free text for lightweight lexical matching."""
        text = " ".join(str(part or "") for part in parts).lower()
        if not text.strip():
            return set()
        return set(re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", text))

    @classmethod
    def _evaluate_task_plan_relevance(
        cls,
        task_list: List[Dict[str, Any]],
        anchor_text: str,
    ) -> Dict[str, Any]:
        """Evaluate whether generated tasks are semantically tied to mission anchors."""
        anchor_tokens = cls._tokenize_for_match(anchor_text)
        if not task_list:
            return {"scores": [], "off_topic_indices": []}
        if not anchor_tokens:
            return {"scores": [1.0] * len(task_list), "off_topic_indices": []}

        scores: List[float] = []
        off_topic_indices: List[int] = []
        for idx, task_def in enumerate(task_list):
            requirement_refs = cls._coerce_string_list(task_def.get("requirement_refs"))
            task_tokens = cls._tokenize_for_match(
                task_def.get("title", ""),
                task_def.get("instructions", ""),
                task_def.get("acceptance_criteria", ""),
                " ".join(requirement_refs),
            )
            if not task_tokens:
                score = 0.0
            else:
                overlap = len(task_tokens & anchor_tokens)
                score = overlap / max(1, min(24, len(task_tokens)))
            scores.append(score)
            if score < MIN_TASK_RELEVANCE_SCORE:
                off_topic_indices.append(idx)

        return {"scores": scores, "off_topic_indices": off_topic_indices}

    @classmethod
    def _build_task_key(
        cls,
        candidate: Any,
        index: int,
        existing_keys: set[str],
    ) -> str:
        """Build a unique stable task key for planning/execution references."""
        raw = str(candidate or "").strip()
        base = cls._normalize_role_key(raw)
        if not base:
            base = f"task_{index + 1}"
        if base[0].isdigit():
            base = f"task_{base}"

        key = base
        suffix = 2
        while key in existing_keys:
            key = f"{base}_{suffix}"
            suffix += 1

        existing_keys.add(key)
        return key

    @classmethod
    def _resolve_task_dependency_keys(
        cls,
        dependency_tokens: List[str],
        *,
        title_to_key: Dict[str, str],
        normalized_title_to_key: Dict[str, str],
        task_keys: set[str],
    ) -> List[str]:
        """Resolve dependency references from mixed task titles/keys to task keys."""
        resolved: List[str] = []
        for token in dependency_tokens:
            dep = str(token or "").strip()
            if not dep:
                continue

            matched_key = ""
            if dep in task_keys:
                matched_key = dep
            elif dep in title_to_key:
                matched_key = title_to_key[dep]
            else:
                normalized_dep = cls._normalize_role_key(dep)
                if normalized_dep and normalized_dep in task_keys:
                    matched_key = normalized_dep
                elif normalized_dep and normalized_dep in normalized_title_to_key:
                    matched_key = normalized_title_to_key[normalized_dep]
                elif normalized_dep:
                    # Lightweight fuzzy fallback for minor wording drift.
                    for normalized_title, candidate_key in normalized_title_to_key.items():
                        if normalized_dep in normalized_title or normalized_title in normalized_dep:
                            matched_key = candidate_key
                            break

            if matched_key and matched_key not in resolved:
                resolved.append(matched_key)

        return resolved

    @staticmethod
    def _compute_dependency_levels(task_defs: List[Dict[str, Any]]) -> Dict[str, int]:
        """Compute dependency wave/level per task_key (0-based)."""
        dependency_map: Dict[str, List[str]] = {}
        for task_def in task_defs:
            task_key = str(task_def.get("task_key") or "").strip()
            if not task_key:
                continue
            deps = [
                dep
                for dep in MissionOrchestrator._coerce_string_list(task_def.get("dependency_keys"))
                if dep and dep != task_key
            ]
            dependency_map[task_key] = deps

        levels: Dict[str, int] = {}
        visiting: set[str] = set()

        def dfs(task_key: str) -> int:
            if task_key in levels:
                return levels[task_key]
            if task_key in visiting:
                # Cycle guard; keep wave stable and let topological sorter raise later.
                return 0

            visiting.add(task_key)
            max_dep_level = -1
            for dep_key in dependency_map.get(task_key, []):
                if dep_key not in dependency_map:
                    continue
                max_dep_level = max(max_dep_level, dfs(dep_key))
            visiting.discard(task_key)

            level = max_dep_level + 1
            levels[task_key] = max(0, level)
            return levels[task_key]

        for key in dependency_map:
            dfs(key)

        return levels

    @staticmethod
    def _render_execution_plan_markdown(
        mission: Any,
        task_plan_rows: List[Dict[str, Any]],
        role_assignments: Dict[str, Dict[str, Any]],
        assignment_summary: Dict[str, int],
    ) -> str:
        """Render a human-readable execution plan similar to Plan mode output."""
        lines: List[str] = [
            "# Mission Execution Plan",
            "",
            "## Summary",
            f"- Mission: {getattr(mission, 'title', 'Untitled Mission')}",
            f"- Planned tasks: {len(task_plan_rows)}",
            f"- Team roles: {len(role_assignments)}",
            f"- Existing agent assigned tasks: {assignment_summary.get('assigned_existing', 0)}",
            (
                "- Temporary fallback tasks: "
                f"{assignment_summary.get('temporary_fallback_pending', 0)}"
            ),
            f"- Explicitly unassigned tasks: {assignment_summary.get('unassigned', 0)}",
            "",
        ]

        if role_assignments:
            lines.extend(
                [
                    "## Team Blueprint",
                    "| Role Key | Role Name | Required Capabilities | Assigned Agent |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for role in role_assignments.values():
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(role.get("role_key") or "-"),
                            str(role.get("role_name") or "-"),
                            ", ".join(role.get("required_capabilities") or []) or "-",
                            str(role.get("assigned_agent_name") or "Temporary fallback"),
                        ]
                    )
                    + " |"
                )
            lines.append("")

        wave_groups: Dict[int, List[str]] = {}
        for row in task_plan_rows:
            wave = max(0, int(row.get("dependency_level", 0)))
            wave_groups.setdefault(wave, []).append(f"[{row.get('task_key')}] {row.get('title')}")
        if wave_groups:
            lines.extend(["## Execution Waves", "Dependency-safe execution order:", ""])
            for wave in sorted(wave_groups):
                lines.append(f"- Wave {wave + 1}: {', '.join(wave_groups[wave])}")
            lines.append("")

        lines.extend(
            [
                "## Task Breakdown",
                "Dependencies reference task keys to preserve deterministic execution order.",
                "",
            ]
        )
        for index, row in enumerate(task_plan_rows, start=1):
            dependencies = row.get("dependency_keys") or []
            requirement_refs = row.get("requirement_refs") or []
            lines.extend(
                [
                    f"{index}. [{row.get('task_key')}] {row.get('title')}",
                    f"   - Owner role: {row.get('owner_role_name') or row.get('owner_role') or 'N/A'}",
                    (
                        "   - Assigned agent: "
                        f"{row.get('assigned_agent_name') or 'Temporary fallback'} "
                        f"({row.get('assignment_source')})"
                    ),
                    ("   - Assignment reason: " f"{row.get('assignment_reason_code') or 'n/a'}"),
                    f"   - Execution wave: {int(row.get('dependency_level', 0)) + 1}",
                    ("   - Dependencies: " + (", ".join(dependencies) if dependencies else "None")),
                    (
                        "   - Requirement refs: "
                        + ("; ".join(requirement_refs) if requirement_refs else "N/A")
                    ),
                    f"   - Acceptance criteria: {row.get('acceptance_criteria') or 'N/A'}",
                    "",
                ]
            )

        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _resolve_temporary_worker_memory_scopes(exec_cfg: Dict[str, Any]) -> List[str]:
        """Resolve temporary worker memory scopes with sane defaults.

        `task_context` is always enabled for temporary workers because
        mission tasks rely on task-scoped context continuity.
        """
        raw_scopes = exec_cfg.get("temp_worker_memory_scopes")
        normalized: List[str] = []
        if isinstance(raw_scopes, list):
            for scope in raw_scopes:
                candidate = str(scope or "").strip().lower()
                if candidate in {"agent", "company", "user_context", "task_context"}:
                    if candidate not in normalized:
                        normalized.append(candidate)
        if not normalized:
            normalized = ["agent", "company", "user_context"]
        if "task_context" not in normalized:
            normalized.append("task_context")
        return normalized

    def _select_temporary_worker_skills(
        self,
        mission: Any,
        task_obj: Any,
        exec_cfg: Dict[str, Any],
    ) -> List[str]:
        """Auto-select relevant skills for temporary workers based on task context."""
        if not self._coerce_bool(exec_cfg.get("auto_select_temp_skills", True), default=True):
            return []

        limit = max(0, min(self._coerce_int(exec_cfg.get("temp_worker_skill_limit", 3), 3), 8))
        if limit == 0:
            return []

        task_metadata = task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
        task_text = "\n".join(
            [
                str(task_metadata.get("title", "") or ""),
                str(getattr(task_obj, "goal_text", "") or ""),
                str(getattr(task_obj, "acceptance_criteria", "") or ""),
                " ".join(self._coerce_string_list(task_metadata.get("role_required_capabilities"))),
            ]
        )
        task_tokens = self._tokenize_for_match(task_text)
        if not task_tokens:
            return []

        try:
            from database.connection import get_db_session
            from database.models import Skill

            with get_db_session() as session:
                candidates = (
                    session.query(Skill)
                    .filter(Skill.is_active.is_(True))
                    .order_by(Skill.created_at.desc())
                    .limit(500)
                    .all()
                )
        except Exception:
            logger.exception(
                "Failed to load skill candidates for temporary worker",
                extra={"mission_id": str(getattr(mission, "mission_id", ""))},
            )
            return []

        scored: List[tuple[float, str]] = []
        task_lower = task_text.lower()
        for skill in candidates:
            skill_name = str(getattr(skill, "name", "") or "").strip()
            if not skill_name:
                continue
            skill_desc = str(getattr(skill, "description", "") or "").strip()
            skill_tokens = self._tokenize_for_match(skill_name, skill_desc)
            overlap = len(task_tokens.intersection(skill_tokens))

            name_in_task = skill_name.lower() in task_lower
            # Only keep skills with at least one direct relevance signal.
            if overlap <= 0 and not name_in_task:
                continue

            score = float(overlap * 2)
            if name_in_task:
                score += 6.0
            if getattr(skill, "skill_type", "") == "agent_skill":
                score += 0.2

            if score > 0:
                scored.append((score, skill_name))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected: List[str] = []
        for _, skill_name in scored:
            if skill_name in selected:
                continue
            selected.append(skill_name)
            if len(selected) >= limit:
                break
        return selected

    def _select_temporary_worker_knowledge_collections(
        self,
        mission: Any,
        task_obj: Any,
        exec_cfg: Dict[str, Any],
    ) -> List[str]:
        """Select knowledge collections for temporary workers.

        Strategies:
        - manual_only: attach none (only manually configured agents can use KB).
        - all_owner: attach latest owner collections up to limit.
        - owner_accessible (default): choose owner collections lexically relevant to task.
        """
        strategy = str(exec_cfg.get("temp_worker_knowledge_strategy", "owner_accessible")).strip()
        strategy = strategy.lower() or "owner_accessible"
        limit = max(
            0,
            min(
                self._coerce_int(exec_cfg.get("temp_worker_knowledge_limit", 6), 6),
                20,
            ),
        )
        if limit == 0:
            return []
        if strategy in {"manual_only", "manual", "none"}:
            return []

        try:
            from database.connection import get_db_session
            from database.models import KnowledgeCollection

            with get_db_session() as session:
                collections = (
                    session.query(KnowledgeCollection)
                    .filter(KnowledgeCollection.owner_user_id == mission.created_by_user_id)
                    .order_by(KnowledgeCollection.updated_at.desc())
                    .limit(200)
                    .all()
                )
        except Exception:
            logger.exception(
                "Failed to load owner knowledge collections for temporary worker",
                extra={"mission_id": str(getattr(mission, "mission_id", ""))},
            )
            return []

        if not collections:
            return []
        if strategy in {"all_owner", "owner_all"}:
            return [str(item.collection_id) for item in collections[:limit]]

        # owner_accessible: rank with lexical overlap against task context.
        task_metadata = task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
        task_tokens = self._tokenize_for_match(
            task_metadata.get("title", ""),
            getattr(task_obj, "goal_text", ""),
            getattr(task_obj, "acceptance_criteria", ""),
        )
        if not task_tokens:
            return [str(item.collection_id) for item in collections[:limit]]

        scored: List[tuple[int, Any]] = []
        for item in collections:
            tokens = self._tokenize_for_match(item.name, item.description)
            score = len(task_tokens.intersection(tokens))
            scored.append((score, item))

        scored.sort(key=lambda row: row[0], reverse=True)
        positive = [item for score, item in scored if score > 0]
        selected = positive[:limit] if positive else collections[:limit]
        return [str(item.collection_id) for item in selected]

    def _resolve_blueprint_role_assignments(
        self,
        team_blueprint: List[Dict[str, Any]],
        available_agents: List[Any],
        allow_temporary_workers: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """Resolve role-to-agent assignments from team blueprint and platform agents."""
        if not team_blueprint:
            return {}

        agent_by_id = {str(agent.agent_id): agent for agent in available_agents}
        used_agent_ids: set[str] = set()
        role_map: Dict[str, Dict[str, Any]] = {}

        for index, role in enumerate(team_blueprint):
            if not isinstance(role, dict):
                continue

            role_name = str(
                role.get("role_name") or role.get("name") or role.get("role") or f"role_{index+1}"
            ).strip()
            if not role_name:
                role_name = f"role_{index+1}"
            role_key = self._normalize_role_key(role.get("role_key") or role_name)
            if not role_key:
                role_key = f"role_{index+1}"

            required_capabilities = self._coerce_string_list(
                role.get("required_capabilities") or role.get("skills")
            )
            preferred_agent_id = str(role.get("preferred_agent_id") or "").strip()

            assigned_agent_id = ""
            assigned_agent_name = ""
            required_caps = {
                str(capability).strip().lower()
                for capability in required_capabilities
                if str(capability).strip()
            }

            if preferred_agent_id and preferred_agent_id in agent_by_id:
                preferred = agent_by_id[preferred_agent_id]
                assigned_agent_id = str(preferred.agent_id)
                assigned_agent_name = preferred.name
                used_agent_ids.add(assigned_agent_id)
            else:
                best_candidate: Optional[Any] = None
                best_score = -1.0
                for candidate in available_agents:
                    candidate_id = str(candidate.agent_id)
                    candidate_caps = {
                        str(capability).strip().lower()
                        for capability in (candidate.capabilities or [])
                        if str(capability).strip()
                    }
                    if required_caps:
                        score = len(candidate_caps.intersection(required_caps)) / len(required_caps)
                    else:
                        score = 0.0
                    if candidate_id in used_agent_ids:
                        score -= 0.15
                    if score > best_score:
                        best_score = score
                        best_candidate = candidate

                should_assign_existing = False
                if best_candidate is not None:
                    if not allow_temporary_workers:
                        # Temporary workers disabled: keep execution possible even with weak matches.
                        should_assign_existing = best_score >= 0
                    elif required_caps:
                        # Temporary workers enabled: require meaningful capability fit.
                        should_assign_existing = best_score >= 0.35

                if best_candidate is not None and should_assign_existing:
                    assigned_agent_id = str(best_candidate.agent_id)
                    assigned_agent_name = best_candidate.name
                    used_agent_ids.add(assigned_agent_id)

            role_map[role_key] = {
                "role_key": role_key,
                "role_name": role_name,
                "responsibilities": self._coerce_string_list(role.get("responsibilities")),
                "required_capabilities": required_capabilities,
                "preferred_agent_id": preferred_agent_id or "",
                "assigned_agent_id": assigned_agent_id,
                "assigned_agent_name": assigned_agent_name,
                "memory_scopes": self._coerce_string_list(role.get("memory_scopes")),
                "knowledge_collection_ids": self._coerce_string_list(
                    role.get("knowledge_collection_ids")
                ),
                "sop_hint": str(role.get("sop_hint") or "").strip(),
            }

        return role_map

    def _select_platform_agent_for_task(
        self,
        task_obj: Any,
        available_agents: List[Any],
    ) -> Optional[Dict[str, Any]]:
        """Pick the best existing platform agent for a task, if relevance exists.

        This matcher intentionally requires at least one direct relevance signal
        (capability overlap or lexical overlap). Otherwise it returns None so the
        orchestrator can create a temporary specialist as fallback.
        """
        if not available_agents:
            return None

        task_metadata = task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
        role_required_caps = {
            capability.strip().lower()
            for capability in self._coerce_string_list(
                task_metadata.get("role_required_capabilities")
            )
            if capability.strip()
        }
        task_text = "\n".join(
            [
                str(task_metadata.get("title", "") or ""),
                str(getattr(task_obj, "goal_text", "") or ""),
                str(getattr(task_obj, "acceptance_criteria", "") or ""),
                " ".join(sorted(role_required_caps)),
            ]
        )
        task_tokens = self._tokenize_for_match(task_text)

        best_agent: Optional[Any] = None
        best_score = float("-inf")
        best_capability_overlap = 0
        best_lexical_overlap = 0

        for candidate in available_agents:
            if getattr(candidate, "agent_type", "") == "mission_temp_worker":
                # Ignore temporary workers from prior runs; prefer manually curated agents.
                continue

            candidate_capabilities = {
                str(capability).strip().lower()
                for capability in (getattr(candidate, "capabilities", None) or [])
                if str(capability).strip()
            }
            candidate_tokens = self._tokenize_for_match(
                getattr(candidate, "name", ""),
                " ".join(sorted(candidate_capabilities)),
            )

            capability_overlap = len(role_required_caps.intersection(candidate_capabilities))
            lexical_overlap = len(task_tokens.intersection(candidate_tokens))

            # Hard guard: weak lexical matches are too noisy for auto-assignment.
            min_lexical_overlap = 3 if len(task_tokens) >= 6 else 2
            if capability_overlap <= 0 and lexical_overlap < min_lexical_overlap:
                continue

            score = float(capability_overlap * 4 + lexical_overlap * 1.2)

            candidate_status = str(getattr(candidate, "status", "") or "").lower()
            if candidate_status == "idle":
                score += 0.6
            elif candidate_status == "active":
                score += 0.2

            if score > best_score:
                best_score = score
                best_agent = candidate
                best_capability_overlap = capability_overlap
                best_lexical_overlap = lexical_overlap

        if best_agent is None:
            return None

        return {
            "agent_id": str(best_agent.agent_id),
            "agent_name": str(getattr(best_agent, "name", "worker") or "worker"),
            "match_score": best_score,
            "capability_overlap": best_capability_overlap,
            "lexical_overlap": best_lexical_overlap,
            "match_summary": (
                f"capability_overlap={best_capability_overlap}, "
                f"lexical_overlap={best_lexical_overlap}, "
                f"score={best_score:.2f}"
            ),
        }

    def _provision_temporary_worker_agent(
        self,
        mission_id: UUID,
        mission: Any,
        task_obj: Any,
        llm_cfg: Dict[str, Any],
    ) -> UUID:
        """Register and assign a temporary platform agent for a task."""
        from agent_framework.agent_registry import AgentRegistry
        from database.connection import get_db_session
        from database.models import Task

        task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
        exec_cfg = self._get_execution_config(mission)
        selected_skills = self._select_temporary_worker_skills(
            mission=mission,
            task_obj=task_obj,
            exec_cfg=exec_cfg,
        )
        selected_knowledge = self._select_temporary_worker_knowledge_collections(
            mission=mission,
            task_obj=task_obj,
            exec_cfg=exec_cfg,
        )
        memory_scopes = self._resolve_temporary_worker_memory_scopes(exec_cfg)
        worker_system_prompt = self._build_temporary_worker_system_prompt(mission, task_obj)
        registry = AgentRegistry()
        temp_agent = registry.register_agent(
            name=self._build_temporary_agent_name(task_title, task_obj.task_id),
            agent_type="mission_temp_worker",
            owner_user_id=mission.created_by_user_id,
            capabilities=selected_skills,
            llm_provider=llm_cfg.get("llm_provider"),
            llm_model=llm_cfg.get("llm_model"),
            temperature=float(llm_cfg.get("temperature", 0.7)),
            max_tokens=int(llm_cfg.get("max_tokens", 4096)),
            access_level="private",
            system_prompt=worker_system_prompt,
            allowed_knowledge=selected_knowledge,
            allowed_memory=memory_scopes,
        )

        try:
            assign_mission_agent(
                mission_id=mission_id,
                agent_id=temp_agent.agent_id,
                role="worker",
                is_temporary=True,
            )
        except Exception:
            logger.debug(
                "Mission temporary worker assignment already exists",
                extra={"mission_id": str(mission_id), "agent_id": str(temp_agent.agent_id)},
            )

        with get_db_session() as session:
            task = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
            if task:
                task.assigned_agent_id = temp_agent.agent_id
                metadata = dict(task.task_metadata or {})
                metadata["assigned_agent_name"] = temp_agent.name
                metadata["assigned_agent_temporary"] = True
                metadata["assignment_reason_code"] = "temporary_worker_provisioned"
                metadata["assignment_reason"] = (
                    "Temporary worker provisioned based on assignment policy."
                )
                metadata["temporary_agent_prompt_mode"] = "task_specific_sop"
                metadata["temporary_agent_skills"] = selected_skills
                metadata["temporary_agent_memory_scopes"] = memory_scopes
                metadata["temporary_agent_knowledge_collections"] = selected_knowledge
                task.task_metadata = metadata

        task_obj.assigned_agent_id = temp_agent.agent_id
        task_metadata = dict(task_obj.task_metadata or {})
        task_metadata["assigned_agent_name"] = temp_agent.name
        task_metadata["assigned_agent_temporary"] = True
        task_metadata["assignment_reason_code"] = "temporary_worker_provisioned"
        task_metadata["assignment_reason"] = (
            "Temporary worker provisioned based on assignment policy."
        )
        task_metadata["temporary_agent_prompt_mode"] = "task_specific_sop"
        task_metadata["temporary_agent_skills"] = selected_skills
        task_metadata["temporary_agent_memory_scopes"] = memory_scopes
        task_metadata["temporary_agent_knowledge_collections"] = selected_knowledge
        task_obj.task_metadata = task_metadata

        self._emitter.emit(
            mission_id=mission_id,
            event_type="TASK_AGENT_ASSIGNED",
            task_id=task_obj.task_id,
            agent_id=temp_agent.agent_id,
            data={
                "title": task_title,
                "agent_id": str(temp_agent.agent_id),
                "agent_name": temp_agent.name,
                "is_temporary": True,
                "prompt_mode": "task_specific_sop",
                "skills": selected_skills,
                "memory_scopes": memory_scopes,
                "knowledge_collections": selected_knowledge,
            },
            message=f"Temporary worker assigned: {temp_agent.name}",
        )
        return temp_agent.agent_id

    @staticmethod
    async def _execute_agent_task(
        agent: Any,
        prompt: str,
        *,
        container_id: Optional[str] = None,
        code_execution_network_access: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Run blocking agent calls in a worker thread.

        For task execution with a workspace container, pass a no-op stream callback so
        code blocks/tool loops are enabled and executed against that container.
        """

        def _noop_stream_callback(_chunk: Any) -> None:
            return None

        if not container_id:
            return await asyncio.to_thread(agent.execute_task, prompt)

        return await asyncio.to_thread(
            agent.execute_task,
            task_description=prompt,
            stream_callback=_noop_stream_callback,
            container_id=container_id,
            code_execution_network_access=code_execution_network_access,
        )

    async def _execute_phase_prompt_with_retry(
        self,
        mission_id: UUID,
        mission: Any,
        phase: str,
        step: str,
        agent: Any,
        prompt: str,
        error_context: str,
    ) -> str:
        """Execute a non-task phase prompt with retry and structured failure telemetry."""
        exec_cfg = self._get_execution_config(mission)
        max_retries = max(0, self._coerce_int(exec_cfg.get("max_retries", 2), 2))
        debug_mode = self._coerce_bool(exec_cfg.get("debug_mode", False), default=False)
        total_attempts = max_retries + 1

        for attempt in range(total_attempts):
            try:
                result = await self._execute_agent_task(agent, prompt)
                return self._extract_agent_output(result, error_context)
            except Exception as exc:
                backoff = 2**attempt if attempt < max_retries else None
                trace = traceback.format_exc() if debug_mode else None
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="PHASE_ATTEMPT_FAILED",
                    data={
                        "phase": phase,
                        "step": step,
                        "attempt": attempt + 1,
                        "max_attempts": total_attempts,
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                        "will_retry": attempt < max_retries,
                        "backoff_s": backoff,
                        "traceback": trace,
                    },
                    message=(
                        f"{phase} step failed (attempt {attempt + 1}/{total_attempts}): {step}"
                    ),
                )
                if attempt < max_retries:
                    assert backoff is not None
                    await asyncio.sleep(backoff)
                    continue
                raise

    def _prepare_workspace(self, mission_id: UUID, mission: Any) -> None:
        """Create mission workspace container and mount mission attachments."""
        self._workspace.create_workspace(
            mission_id,
            config=mission.mission_config or {},
        )

        if not getattr(mission, "attachments", None):
            return

        attachment_dicts = [
            {
                "bucket_name": (
                    att.file_reference.split("/")[0]
                    if "/" in att.file_reference
                    else "documents"
                ),
                "object_key": (
                    att.file_reference.split("/", 1)[1]
                    if "/" in att.file_reference
                    else att.file_reference
                ),
                "filename": att.filename,
            }
            for att in mission.attachments
        ]
        self._workspace.setup_attachments(mission_id, attachment_dicts)

    async def _phase_requirements(self, mission_id: UUID) -> None:
        """Leader analyses instructions and gathers requirements."""
        self._transition(mission_id, "requirements")
        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_STARTED",
            data={"phase": "requirements"},
            message="Requirements gathering started",
        )

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        self._prepare_workspace(mission_id, mission)

        # Build leader agent
        llm_cfg = self._get_llm_config(mission, "leader")
        leader_config = get_leader_config(
            owner_user_id=mission.created_by_user_id,
            temperature=llm_cfg["temperature"],
        )
        leader = await create_mission_agent(agent_config=leader_config, **llm_cfg)

        # Build task prompt
        attachment_names = (
            ", ".join(att.filename for att in mission.attachments)
            if mission.attachments
            else "None"
        )
        response_language = self._detect_instruction_language(mission.instructions)
        task_prompt = (
            "Analyse the following mission instructions and produce a structured "
            "requirements document.\n\n"
            f"## Mission Instructions\n{mission.instructions}\n\n"
            f"## Attached Files\n{attachment_names}\n\n"
            f"Respond in {response_language}.\n"
            "If anything is ambiguous or unclear, list specific clarifying questions "
            "prefixed with 'CLARIFICATION:' (keep this prefix in English exactly). "
            f"Write the question content in {response_language}. "
            f"Otherwise produce the full requirements in {response_language}."
        )

        output = await self._execute_phase_prompt_with_retry(
            mission_id=mission_id,
            mission=mission,
            phase="requirements",
            step="generate_requirements",
            agent=leader,
            prompt=task_prompt,
            error_context="Requirements generation failed",
        )

        # Handle clarification loop
        if "CLARIFICATION:" in output:
            clarification_questions = output
            self._emitter.emit(
                mission_id=mission_id,
                event_type="USER_CLARIFICATION_REQUESTED",
                data={"questions": clarification_questions},
                message="Leader requests clarification from user",
            )

            # Wait for user response
            event = asyncio.Event()
            self._clarification_events[mission_id] = event
            await event.wait()

            user_response = self._clarification_responses.pop(mission_id, "")
            self._clarification_events.pop(mission_id, None)

            # Re-invoke with user answers
            followup_prompt = (
                "Rebuild the requirements with the original mission context and the user's "
                "clarification answers.\n\n"
                f"## Original Mission Instructions\n{mission.instructions}\n\n"
                f"## Attached Files\n{attachment_names}\n\n"
                f"## Clarification Questions\n{clarification_questions}\n\n"
                f"## User Answers\n{user_response}\n\n"
                "Requirements must stay tightly aligned to the original mission objective. "
                "Do not introduce unrelated goals.\n"
                f"Produce the full requirements document in {response_language}."
            )
            output = await self._execute_phase_prompt_with_retry(
                mission_id=mission_id,
                mission=mission,
                phase="requirements",
                step="regenerate_after_clarification",
                agent=leader,
                prompt=followup_prompt,
                error_context="Requirements regeneration failed",
            )

        # Persist requirements
        requirements_doc = output
        update_mission_fields(mission_id, requirements_doc=requirements_doc)
        self._workspace.write_file(mission_id, "shared/requirements.md", requirements_doc)

        mission_config = mission.mission_config if isinstance(mission.mission_config, dict) else {}
        should_auto_generate_title = self._coerce_bool(
            mission_config.get("auto_generate_title"),
            default=False,
        )
        if should_auto_generate_title:
            try:
                title_prompt = (
                    "Generate a concise mission title based on the mission instructions and "
                    "requirements below.\n\n"
                    "Rules:\n"
                    "- Return ONLY title text.\n"
                    "- No quotes, no markdown, no numbering.\n"
                    "- Keep it specific and action-oriented.\n"
                    "- Prefer <= 24 Chinese characters, or <= 70 English characters.\n\n"
                    f"Respond in {response_language}.\n\n"
                    "## Mission Instructions\n"
                    f"{mission.instructions}\n\n"
                    "## Requirements Summary\n"
                    f"{self._truncate_prompt_text(requirements_doc, limit=2000)}"
                )
                generated_title_output = await self._execute_phase_prompt_with_retry(
                    mission_id=mission_id,
                    mission=mission,
                    phase="requirements",
                    step="generate_mission_title",
                    agent=leader,
                    prompt=title_prompt,
                    error_context="Mission title generation failed",
                )
                generated_title = self._sanitize_generated_mission_title(
                    generated_title_output,
                    fallback=str(mission.title or "Untitled Mission"),
                )
                config_update = dict(mission_config)
                config_update["auto_generate_title"] = False
                config_update["auto_generated_title"] = generated_title
                fields_to_update: Dict[str, Any] = {"mission_config": config_update}
                if generated_title != str(mission.title or "").strip():
                    fields_to_update["title"] = generated_title
                    self._emitter.emit(
                        mission_id=mission_id,
                        event_type="MISSION_TITLE_UPDATED",
                        data={"title": generated_title, "auto_generated": True},
                        message=f"Mission title generated: {generated_title}",
                    )
                update_mission_fields(mission_id, **fields_to_update)
            except Exception:
                logger.warning(
                    "Mission %s auto title generation failed, fallback title retained",
                    mission_id,
                    exc_info=True,
                )

        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_COMPLETED",
            data={"phase": "requirements"},
            message="Requirements gathering completed",
        )

    async def _phase_planning(self, mission_id: UUID) -> None:
        """Leader decomposes requirements into tasks and assigns agents."""
        self._transition(mission_id, "planning")
        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_STARTED",
            data={"phase": "planning"},
            message="Task planning started",
        )

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        # Build leader agent
        llm_cfg = self._get_llm_config(mission, "leader")
        leader_config = get_leader_config(
            owner_user_id=mission.created_by_user_id,
            temperature=llm_cfg["temperature"],
        )
        leader = await create_mission_agent(agent_config=leader_config, **llm_cfg)

        # Build available platform agent catalog so planning can assign real workers.
        from agent_framework.agent_registry import AgentRegistry

        registry = AgentRegistry()
        available_agents = [
            agent
            for agent in registry.list_agents(owner_user_id=mission.created_by_user_id, limit=500)
            if agent.status in {"active", "idle", "initializing"}
        ]
        agent_id_map = {str(agent.agent_id): agent for agent in available_agents}
        agent_catalog = (
            "\n".join(
                (
                    f"- id={agent.agent_id}, name={agent.name}, "
                    f"capabilities={','.join(agent.capabilities or []) or 'general'}"
                )
                for agent in available_agents
            )
            or "No pre-registered platform agents available."
        )

        requirements_doc = mission.requirements_doc or mission.instructions
        response_language = self._detect_instruction_language(
            f"{mission.instructions}\n{requirements_doc}"
        )
        exec_cfg = self._get_execution_config(mission)
        enable_team_blueprint = self._coerce_bool(
            exec_cfg.get("enable_team_blueprint", True),
            default=True,
        )
        prefer_existing_agents = self._coerce_bool(
            exec_cfg.get("prefer_existing_agents", True),
            default=True,
        )
        allow_temporary_workers = self._coerce_bool(
            exec_cfg.get("allow_temporary_workers", True),
            default=True,
        )

        from database.connection import get_db_session
        from database.models import KnowledgeCollection, Task

        with get_db_session() as session:
            knowledge_collections = (
                session.query(KnowledgeCollection)
                .filter(KnowledgeCollection.owner_user_id == mission.created_by_user_id)
                .order_by(KnowledgeCollection.updated_at.desc())
                .limit(80)
                .all()
            )
        knowledge_catalog = (
            "\n".join(
                f"- id={collection.collection_id}, name={collection.name}, "
                f"description={collection.description or ''}"
                for collection in knowledge_collections
            )
            or "No owner knowledge collections available."
        )

        if available_agents:
            if prefer_existing_agents and allow_temporary_workers:
                assignment_instruction = (
                    "Prefer assigning existing platform agents via `assigned_agent_id`. "
                    "Leave `assigned_agent_id` empty only when no suitable existing agent exists, "
                    "so execution can fallback to temporary workers."
                )
            elif prefer_existing_agents and not allow_temporary_workers:
                assignment_instruction = (
                    "You must assign existing platform agents via `assigned_agent_id`. "
                    "Do not leave `assigned_agent_id` empty because temporary workers are disabled."
                )
            elif not prefer_existing_agents and allow_temporary_workers:
                assignment_instruction = (
                    "You may leave `assigned_agent_id` empty to prefer temporary workers. "
                    "Use `assigned_agent_id` only when an existing platform agent is clearly better."
                )
            else:
                assignment_instruction = (
                    "Assign existing platform agents via `assigned_agent_id`. "
                    "Temporary workers are disabled."
                )
        else:
            assignment_instruction = (
                "No platform agents are available. Keep `assigned_agent_id` empty."
                if allow_temporary_workers
                else "No platform agents are available and temporary workers are disabled. "
                "Planning should still return tasks, but execution will fail until agents are created."
            )
        if enable_team_blueprint:
            task_prompt = (
                "Design an execution team and task plan from the mission requirements.\n\n"
                "Return ONLY JSON inside a ```json code block with this exact shape:\n"
                "{\n"
                '  "team_blueprint": [\n'
                "    {\n"
                '      "role_key": "frontend_lead",\n'
                '      "role_name": "Frontend Lead",\n'
                '      "responsibilities": ["..."],\n'
                '      "required_capabilities": ["skill_a", "skill_b"],\n'
                '      "preferred_agent_id": "",\n'
                '      "memory_scopes": ["agent","company","user_context"],\n'
                '      "knowledge_collection_ids": ["<collection_id>"],\n'
                '      "sop_hint": "short SOP hint"\n'
                "    }\n"
                "  ],\n"
                '  "tasks": [\n'
                "    {\n"
                '      "task_key": "build_api_contract",\n'
                '      "title": "Task title",\n'
                '      "instructions": "Detailed instructions",\n'
                '      "acceptance_criteria": "Testable criteria",\n'
                '      "requirement_refs": ["quote 1", "quote 2"],\n'
                '      "dependencies": ["other_task_key"],\n'
                '      "priority": 0,\n'
                '      "owner_role": "frontend_lead",\n'
                '      "assigned_agent_id": ""\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                f"{assignment_instruction}\n\n"
                "Role guidance:\n"
                "- Keep team roles minimal and explicit.\n"
                "- required_capabilities should use existing platform skill names when possible.\n"
                "- If a role should use existing knowledge collections, reference IDs from catalog.\n"
                "- `task_key` must be unique and stable (snake_case).\n"
                "- `dependencies` must reference `task_key` values (not free-form titles).\n"
                "- Every task MUST be directly traceable to mission requirements.\n"
                "- `requirement_refs` must quote exact requirement fragments from the requirements section.\n"
                "- Do NOT add unrelated optimization, platform migration, or speculative tasks.\n\n"
                f"Respond in {response_language}.\n\n"
                "## Original Mission Instructions\n"
                f"{mission.instructions}\n\n"
                f"## Available Platform Agents\n{agent_catalog}\n\n"
                f"## Available Owner Knowledge Collections\n{knowledge_catalog}\n\n"
                f"## Requirements\n{requirements_doc}"
            )
        else:
            task_prompt = (
                "Decompose the following requirements into an ordered list of tasks "
                "with acceptance criteria. Return them as a JSON array where each "
                "element has keys: task_key, title, instructions, acceptance_criteria, "
                "requirement_refs (list of exact requirement snippets), "
                "dependencies (list of task_key values), priority (integer 0-10), "
                "assigned_agent_id (string UUID or empty string).\n\n"
                "Rules:\n"
                "- `task_key` must be unique and stable (snake_case).\n"
                "- `dependencies` must use `task_key` values.\n"
                "- Every task must map directly to requirement content.\n"
                "- `requirement_refs` cannot be empty.\n"
                "- Reject off-topic ideas and avoid speculative tasks.\n\n"
                f"{assignment_instruction}\n\n"
                f"Respond in {response_language}.\n\n"
                "## Original Mission Instructions\n"
                f"{mission.instructions}\n\n"
                f"## Available Platform Agents\n{agent_catalog}\n\n"
                "Return ONLY the JSON array inside a ```json code block.\n\n"
                f"## Requirements\n{requirements_doc}"
            )

        output = await self._execute_phase_prompt_with_retry(
            mission_id=mission_id,
            mission=mission,
            phase="planning",
            step="decompose_tasks",
            agent=leader,
            prompt=task_prompt,
            error_context="Task planning failed",
        )

        def _parse_plan_payload(payload: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
            parsed_tasks: List[Dict[str, Any]] = []
            parsed_roles: List[Dict[str, Any]] = []
            if enable_team_blueprint:
                parsed_object = self._extract_json_object(payload)
                raw_tasks = parsed_object.get("tasks") if isinstance(parsed_object, dict) else None
                raw_roles = (
                    parsed_object.get("team_blueprint") if isinstance(parsed_object, dict) else None
                )
                if isinstance(raw_tasks, list):
                    parsed_tasks = [item for item in raw_tasks if isinstance(item, dict)]
                if isinstance(raw_roles, list):
                    parsed_roles = [item for item in raw_roles if isinstance(item, dict)]
            if not parsed_tasks:
                parsed_tasks = self._extract_json_array(payload)
            return parsed_tasks, parsed_roles

        # Parse JSON task list and optional team blueprint.
        task_list, raw_team_blueprint = _parse_plan_payload(output)

        if not task_list:
            raise MissionError(
                mission_id,
                "Leader failed to produce a valid task plan",
            )

        relevance_anchor = f"{mission.instructions}\n{requirements_doc}"
        relevance_report = self._evaluate_task_plan_relevance(task_list, relevance_anchor)
        off_topic_indices = relevance_report["off_topic_indices"]
        off_topic_ratio = len(off_topic_indices) / max(1, len(task_list))

        if off_topic_ratio > MAX_OFF_TOPIC_TASK_RATIO:
            problematic_titles = [
                str(task_list[idx].get("title") or f"Task {idx + 1}")
                for idx in off_topic_indices[:8]
            ]
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_PLAN_LOW_RELEVANCE",
                data={
                    "off_topic_count": len(off_topic_indices),
                    "task_count": len(task_list),
                    "off_topic_titles": problematic_titles,
                },
                message="Task plan weakly aligned with mission requirements, regenerating plan",
            )

            regenerate_prompt = (
                "Your previous plan had too many off-topic tasks. Regenerate from scratch.\n"
                "Strict constraints:\n"
                "1. Every task must map directly to mission requirements.\n"
                "2. `requirement_refs` must cite exact snippets from requirements.\n"
                "3. `task_key` values must be unique and stable.\n"
                "4. `dependencies` must reference `task_key` values.\n"
                "5. Do not add unrelated tasks.\n\n"
                f"Respond in {response_language}.\n\n"
                "## Original Mission Instructions\n"
                f"{mission.instructions}\n\n"
                "## Requirements\n"
                f"{requirements_doc}\n\n"
                "## Previous Plan (for correction)\n"
                f"{output}\n\n"
                "Return only corrected JSON in the same schema."
            )
            output = await self._execute_phase_prompt_with_retry(
                mission_id=mission_id,
                mission=mission,
                phase="planning",
                step="decompose_tasks_rebuild",
                agent=leader,
                prompt=regenerate_prompt,
                error_context="Task planning relevance correction failed",
            )
            task_list, raw_team_blueprint = _parse_plan_payload(output)
            if not task_list:
                raise MissionError(
                    mission_id, "Leader failed to produce a valid corrected task plan"
                )

            relevance_report = self._evaluate_task_plan_relevance(task_list, relevance_anchor)
            off_topic_ratio = len(relevance_report["off_topic_indices"]) / max(1, len(task_list))
            if off_topic_ratio > MAX_OFF_TOPIC_TASK_RATIO:
                raise MissionError(
                    mission_id,
                    "Task plan remains weakly aligned with mission objective after regeneration",
                )

        role_assignments = self._resolve_blueprint_role_assignments(
            team_blueprint=raw_team_blueprint,
            available_agents=available_agents,
            allow_temporary_workers=allow_temporary_workers,
        )

        normalized_task_defs: List[Dict[str, Any]] = []
        used_task_keys: set[str] = set()
        title_to_task_key: Dict[str, str] = {}
        normalized_title_to_task_key: Dict[str, str] = {}
        for idx, raw_task_def in enumerate(task_list):
            task_def = dict(raw_task_def or {})
            title = str(task_def.get("title") or f"Task {idx + 1}").strip() or f"Task {idx + 1}"
            task_key = self._build_task_key(
                task_def.get("task_key") or task_def.get("id") or title,
                idx,
                used_task_keys,
            )
            task_def["title"] = title
            task_def["task_key"] = task_key
            normalized_task_defs.append(task_def)
            title_to_task_key[title] = task_key
            normalized_title_to_task_key[self._normalize_role_key(title)] = task_key

        task_keys = set(used_task_keys)
        for task_def in normalized_task_defs:
            dependency_tokens = self._coerce_string_list(task_def.get("dependencies"))
            dependency_keys = self._resolve_task_dependency_keys(
                dependency_tokens,
                title_to_key=title_to_task_key,
                normalized_title_to_key=normalized_title_to_task_key,
                task_keys=task_keys,
            )
            task_def["dependency_keys"] = [
                key for key in dependency_keys if key != task_def.get("task_key")
            ]

        # Replace with normalized task payload (task_key/dependency_keys resolved).
        task_list = normalized_task_defs
        dependency_levels = self._compute_dependency_levels(task_list)

        task_key_to_id: Dict[str, UUID] = {}
        used_agent_ids: set[UUID] = set()
        assignment_summary: Dict[str, int] = {
            "assigned_existing": 0,
            "temporary_fallback_pending": 0,
            "unassigned": 0,
        }
        task_plan_rows: List[Dict[str, Any]] = []
        unassigned_without_temp_titles: List[str] = []
        with get_db_session() as session:
            for idx, task_def in enumerate(task_list):
                from uuid import uuid4
                from types import SimpleNamespace

                task_id = uuid4()
                title = str(task_def.get("title") or f"Task {idx + 1}")
                task_key = str(task_def.get("task_key") or f"task_{idx + 1}")
                task_key_to_id[task_key] = task_id

                owner_role_key = self._normalize_role_key(
                    task_def.get("owner_role")
                    or task_def.get("role_key")
                    or task_def.get("role")
                    or ""
                )
                role_context = role_assignments.get(owner_role_key, {})

                assigned_agent_id: Optional[UUID] = None
                assignment_source = "unassigned"
                assignment_reason_code = "unassigned"
                assignment_reason = ""
                assigned_agent_raw = str(task_def.get("assigned_agent_id") or "").strip()
                if assigned_agent_raw and assigned_agent_raw in agent_id_map:
                    assigned_agent_id = agent_id_map[assigned_agent_raw].agent_id
                    assignment_source = "leader_assigned"
                    assignment_reason_code = "leader_assigned"
                    assignment_reason = "Planner explicitly assigned an existing platform agent."
                elif role_context.get("assigned_agent_id"):
                    role_agent_id = str(role_context.get("assigned_agent_id"))
                    if role_agent_id in agent_id_map:
                        assigned_agent_id = agent_id_map[role_agent_id].agent_id
                        assignment_source = "team_blueprint_assigned"
                        assignment_reason_code = "team_blueprint_assigned"
                        assignment_reason = (
                            "Team blueprint role resolved to an existing platform agent."
                        )
                    else:
                        assignment_reason_code = "team_blueprint_agent_not_found"
                        assignment_reason = (
                            "Team blueprint preferred agent is unavailable; "
                            "falling back to policy-based assignment."
                        )
                elif assigned_agent_raw:
                    assignment_reason_code = "leader_assigned_agent_not_found"
                    assignment_reason = (
                        "Planner-provided assigned_agent_id is unavailable; "
                        "falling back to policy-based assignment."
                    )

                if assigned_agent_id is None and prefer_existing_agents and available_agents:
                    selection_probe = SimpleNamespace(
                        task_metadata={
                            "title": title,
                            "role_required_capabilities": self._coerce_string_list(
                                role_context.get("required_capabilities")
                            ),
                        },
                        goal_text=task_def.get("instructions", title),
                        acceptance_criteria=task_def.get("acceptance_criteria"),
                    )
                    selected_platform = self._select_platform_agent_for_task(
                        task_obj=selection_probe,
                        available_agents=available_agents,
                    )
                    if selected_platform:
                        candidate_agent_id = str(selected_platform["agent_id"])
                        if candidate_agent_id in agent_id_map:
                            assigned_agent_id = agent_id_map[candidate_agent_id].agent_id
                            assignment_source = "platform_auto_match_planning"
                            assignment_reason_code = "platform_auto_match_planning"
                            assignment_reason = str(
                                selected_platform.get("match_summary")
                                or "Matched by platform auto-assignment."
                            )
                    elif not assignment_reason:
                        assignment_reason_code = "no_suitable_existing_agent"
                        assignment_reason = (
                            "No suitable existing platform agent matched task capabilities/context."
                        )

                if assigned_agent_id:
                    used_agent_ids.add(assigned_agent_id)
                    assignment_summary["assigned_existing"] += 1
                elif allow_temporary_workers:
                    assignment_source = "temporary_fallback_pending"
                    if not assignment_reason:
                        if not available_agents:
                            assignment_reason_code = "no_available_platform_agents"
                            assignment_reason = "No platform agents are currently available."
                        elif not prefer_existing_agents:
                            assignment_reason_code = "prefer_temporary_workers_policy"
                            assignment_reason = (
                                "Execution policy allows temporary workers first for this task."
                            )
                        else:
                            assignment_reason_code = "temporary_fallback_pending"
                            assignment_reason = (
                                "Existing platform match not confident; temporary worker "
                                "will be provisioned at execution."
                            )
                    assignment_summary["temporary_fallback_pending"] += 1
                else:
                    assignment_reason_code = "temporary_workers_disabled"
                    assignment_reason = (
                        "Temporary workers are disabled and no existing agent was selected."
                    )
                    assignment_summary["unassigned"] += 1
                    unassigned_without_temp_titles.append(title)

                role_required_capabilities = self._coerce_string_list(
                    role_context.get("required_capabilities")
                )
                role_memory_scopes = self._coerce_string_list(role_context.get("memory_scopes"))
                role_knowledge_collections = self._coerce_string_list(
                    role_context.get("knowledge_collection_ids")
                )
                role_sop_hint = str(role_context.get("sop_hint") or "").strip()
                dependency_keys = self._coerce_string_list(task_def.get("dependency_keys"))
                requirement_refs = self._coerce_string_list(task_def.get("requirement_refs"))
                assigned_agent_name: Optional[str] = (
                    agent_id_map[str(assigned_agent_id)].name
                    if assigned_agent_id and str(assigned_agent_id) in agent_id_map
                    else None
                )
                dependency_level = dependency_levels.get(task_key, 0)
                if assignment_source == "temporary_fallback_pending" and not assigned_agent_name:
                    assigned_agent_name = "Temporary worker (pending)"

                task = Task(
                    task_id=task_id,
                    goal_text=task_def.get("instructions", title),
                    status="pending",
                    priority=int(task_def.get("priority", idx)),
                    created_by_user_id=mission.created_by_user_id,
                    mission_id=mission_id,
                    assigned_agent_id=assigned_agent_id,
                    acceptance_criteria=task_def.get("acceptance_criteria"),
                    task_metadata={
                        "title": title,
                        "task_key": task_key,
                        "dependencies": dependency_keys,
                        "dependency_keys": dependency_keys,
                        "owner_role": owner_role_key or None,
                        "owner_role_name": role_context.get("role_name"),
                        "role_required_capabilities": role_required_capabilities,
                        "role_memory_scopes": role_memory_scopes,
                        "role_knowledge_collections": role_knowledge_collections,
                        "role_sop_hint": role_sop_hint,
                        "requirement_refs": requirement_refs,
                        "assigned_agent_name": assigned_agent_name,
                        "assignment_source": assignment_source,
                        "assignment_reason_code": assignment_reason_code,
                        "assignment_reason": assignment_reason,
                        "dependency_level": dependency_level,
                    },
                )
                session.add(task)
                task_plan_rows.append(
                    {
                        "task_id": task_id,
                        "task_key": task_key,
                        "title": title,
                        "instructions": task_def.get("instructions", title),
                        "acceptance_criteria": task_def.get("acceptance_criteria"),
                        "priority": int(task_def.get("priority", idx)),
                        "owner_role": owner_role_key or None,
                        "owner_role_name": role_context.get("role_name"),
                        "dependency_keys": dependency_keys,
                        "requirement_refs": requirement_refs,
                        "assigned_agent_id": str(assigned_agent_id) if assigned_agent_id else "",
                        "assigned_agent_name": assigned_agent_name or "",
                        "assignment_source": assignment_source,
                        "assignment_reason_code": assignment_reason_code,
                        "assignment_reason": assignment_reason,
                        "dependency_level": dependency_level,
                    }
                )

            if unassigned_without_temp_titles:
                raise MissionError(
                    mission_id,
                    "Tasks without assigned existing agents while temporary workers are disabled: "
                    + ", ".join(unassigned_without_temp_titles[:10]),
                )

            session.flush()

            # Resolve dependency keys to task_id arrays.
            tasks_in_session = session.query(Task).filter(Task.mission_id == mission_id).all()
            for t in tasks_in_session:
                dep_keys = self._coerce_string_list((t.task_metadata or {}).get("dependency_keys"))
                dep_ids = [
                    str(task_key_to_id[dep_key])
                    for dep_key in dep_keys
                    if dep_key in task_key_to_id and str(task_key_to_id[dep_key]) != str(t.task_id)
                ]
                t.dependencies = dep_ids

        for worker_agent_id in used_agent_ids:
            try:
                assign_mission_agent(
                    mission_id=mission_id,
                    agent_id=worker_agent_id,
                    role="worker",
                    is_temporary=False,
                )
            except Exception:
                # MissionAgent has a unique (mission_id, agent_id) constraint; duplicates are benign.
                logger.debug(
                    "Mission worker assignment already exists",
                    extra={
                        "mission_id": str(mission_id),
                        "agent_id": str(worker_agent_id),
                    },
                )

        # Update mission counters
        update_mission_fields(mission_id, total_tasks=len(task_list))

        # Emit per-task events
        for row in task_plan_rows:
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_DECOMPOSED",
                task_id=row["task_id"],
                data={"title": row["title"], "task_key": row["task_key"]},
                message=f"Task created: {row['title']}",
            )
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_ASSIGNMENT_DECIDED",
                task_id=row["task_id"],
                data={
                    "title": row["title"],
                    "task_key": row["task_key"],
                    "dependency_level": row.get("dependency_level"),
                    "assignment_source": row["assignment_source"],
                    "assignment_reason_code": row.get("assignment_reason_code"),
                    "assignment_reason": row.get("assignment_reason"),
                    "assigned_agent_id": row.get("assigned_agent_id"),
                    "assigned_agent_name": row.get("assigned_agent_name"),
                },
                message=(
                    f"Assignment decided: {row['title']} -> "
                    f"{row.get('assigned_agent_name') or row['assignment_source']}"
                ),
            )

        self._emitter.emit(
            mission_id=mission_id,
            event_type="TASK_ASSIGNMENT_PLANNED",
            data={
                **assignment_summary,
                "task_count": len(task_list),
                "prefer_existing_agents": prefer_existing_agents,
                "allow_temporary_workers": allow_temporary_workers,
            },
            message=(
                "Task assignment planned: "
                f"{assignment_summary['assigned_existing']} existing, "
                f"{assignment_summary['temporary_fallback_pending']} temporary fallback"
            ),
        )

        # Save plan to workspace
        self._workspace.write_file(
            mission_id,
            "shared/task_plan.json",
            json.dumps(
                [{**row, "task_id": str(row.get("task_id"))} for row in task_plan_rows],
                indent=2,
                ensure_ascii=False,
            ),
        )
        self._workspace.write_file(
            mission_id,
            "shared/execution_plan.md",
            self._render_execution_plan_markdown(
                mission=mission,
                task_plan_rows=task_plan_rows,
                role_assignments=role_assignments,
                assignment_summary=assignment_summary,
            ),
        )
        if role_assignments:
            self._workspace.write_file(
                mission_id,
                "shared/team_blueprint.json",
                json.dumps(
                    {
                        "team_blueprint": list(role_assignments.values()),
                        "tasks": [
                            {**row, "task_id": str(row.get("task_id"))} for row in task_plan_rows
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TEAM_BLUEPRINT_CREATED",
                data={
                    "role_count": len(role_assignments),
                    "assigned_role_count": len(
                        [
                            role
                            for role in role_assignments.values()
                            if role.get("assigned_agent_id")
                        ]
                    ),
                },
                message=f"Team blueprint created with {len(role_assignments)} roles",
            )

        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_COMPLETED",
            data={
                "phase": "planning",
                "task_count": len(task_list),
                "role_count": len(role_assignments),
            },
            message=f"Task planning completed: {len(task_list)} tasks created",
        )

    async def _phase_execution(self, mission_id: UUID) -> None:
        """Execute tasks respecting dependency ordering."""
        self._transition(mission_id, "executing")
        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_STARTED",
            data={"phase": "executing"},
            message="Task execution started",
        )

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")
        mission_total_tasks = self._coerce_int(getattr(mission, "total_tasks", 0), 0)

        from agent_framework.agent_registry import AgentRegistry

        registry = AgentRegistry()
        available_platform_agents = [
            agent
            for agent in registry.list_agents(owner_user_id=mission.created_by_user_id, limit=500)
            if str(getattr(agent, "status", "")).lower() in {"active", "idle", "initializing"}
        ]

        # Fetch pending/failed tasks for this mission.
        # Failed tasks are reset to pending at the start of each execution phase so
        # dependency checks don't use stale failed states from the previous review loop.
        from database.connection import get_db_session
        from database.models import Task

        with get_db_session() as session:
            tasks = (
                session.query(Task)
                .filter(
                    Task.mission_id == mission_id,
                    Task.status.in_(["pending", "failed"]),
                )
                .all()
            )
            for task in tasks:
                if task.status == "failed":
                    task.status = "pending"
                    task.completed_at = None
            # Detach for use outside session
            task_data = []
            for t in tasks:
                session.expunge(t)
                task_data.append(t)

        if not task_data:
            logger.info("No tasks to execute for mission %s", mission_id)
            self._emitter.emit(
                mission_id=mission_id,
                event_type="PHASE_COMPLETED",
                data={"phase": "executing"},
                message="Task execution completed (no pending tasks)",
            )
            return

        # Topological sort
        sorted_tasks = self._topological_sort(task_data)

        # Execute with concurrency limiter from execution config
        exec_cfg = self._get_execution_config(mission)
        max_concurrent = max(1, self._coerce_int(exec_cfg.get("max_concurrent_tasks", 3), 3))
        require_dependency_review_pass = self._coerce_bool(
            exec_cfg.get("require_dependency_review_pass", True),
            default=True,
        )
        semaphore = asyncio.Semaphore(max_concurrent)
        dependency_review_locks: Dict[str, asyncio.Lock] = {}
        dependency_supervisor: Optional[Any] = None
        dependency_supervisor_lock = asyncio.Lock()

        async def _get_dependency_supervisor() -> Any:
            nonlocal dependency_supervisor
            if dependency_supervisor is not None:
                return dependency_supervisor

            async with dependency_supervisor_lock:
                if dependency_supervisor is None:
                    supervisor_llm_cfg = self._get_llm_config(mission, "supervisor")
                    supervisor_config = get_supervisor_config(
                        owner_user_id=mission.created_by_user_id,
                        temperature=supervisor_llm_cfg["temperature"],
                    )
                    dependency_supervisor = await create_mission_agent(
                        agent_config=supervisor_config,
                        **supervisor_llm_cfg,
                    )

            return dependency_supervisor

        async def _execute_single(task_obj: Any) -> None:
            async with semaphore:
                # Wait for dependencies to complete
                dep_ids = task_obj.dependencies or []
                while dep_ids:
                    with get_db_session() as session:
                        dep_rows = session.query(Task).filter(Task.task_id.in_(dep_ids)).all()
                        dep_statuses = {str(t.task_id): t.status for t in dep_rows}
                        dep_review_statuses = {
                            str(t.task_id): self._get_task_review_status(t.task_metadata)
                            for t in dep_rows
                        }

                    missing_deps = [dep_id for dep_id in dep_ids if dep_id not in dep_statuses]
                    if missing_deps:
                        with get_db_session() as session:
                            t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                            if t:
                                t.status = "failed"
                                t.result = {
                                    "error": f"Missing dependencies: {', '.join(missing_deps)}"
                                }
                        counter_snapshot = self._safe_sync_mission_task_counters(
                            mission_id,
                            fallback_total=mission_total_tasks,
                        )
                        self._emitter.emit(
                            mission_id=mission_id,
                            event_type="TASK_FAILED",
                            task_id=task_obj.task_id,
                            data={
                                "title": (task_obj.task_metadata or {}).get("title", "Untitled"),
                                "error": f"Missing dependencies: {', '.join(missing_deps)}",
                                **counter_snapshot,
                            },
                            message="Task failed due to missing dependencies",
                        )
                        return

                    all_done = all(dep_statuses.get(dep_id) == "completed" for dep_id in dep_ids)
                    if all_done:
                        if require_dependency_review_pass:
                            blocked_by_review_deps = [
                                dep_id
                                for dep_id in dep_ids
                                if dep_review_statuses.get(dep_id)
                                in {"rework_required", "blocked_by_dependency"}
                            ]
                            if blocked_by_review_deps:
                                with get_db_session() as session:
                                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                                    if t:
                                        t.status = "failed"
                                        t.result = {
                                            "error": (
                                                "Blocked by review-failed dependencies: "
                                                f"{', '.join(blocked_by_review_deps)}"
                                            )
                                        }
                                counter_snapshot = self._safe_sync_mission_task_counters(
                                    mission_id,
                                    fallback_total=mission_total_tasks,
                                )
                                self._emitter.emit(
                                    mission_id=mission_id,
                                    event_type="TASK_FAILED",
                                    task_id=task_obj.task_id,
                                    data={
                                        "title": (task_obj.task_metadata or {}).get("title", "Untitled"),
                                        "error": (
                                            "Blocked by review-failed dependencies: "
                                            f"{', '.join(blocked_by_review_deps)}"
                                        ),
                                        **counter_snapshot,
                                    },
                                    message="Task failed due to review-failed dependencies",
                                )
                                return

                            dependencies_pending_review = [
                                dep_id
                                for dep_id in dep_ids
                                if dep_review_statuses.get(dep_id) != "approved"
                            ]
                            if dependencies_pending_review:
                                for dep_id in dependencies_pending_review:
                                    dep_lock = dependency_review_locks.setdefault(dep_id, asyncio.Lock())
                                    async with dep_lock:
                                        try:
                                            dep_uuid = UUID(dep_id)
                                        except (TypeError, ValueError):
                                            continue

                                        with get_db_session() as session:
                                            dep_task = (
                                                session.query(Task)
                                                .filter(Task.task_id == dep_uuid)
                                                .first()
                                            )
                                            if dep_task is None:
                                                continue
                                            dep_status = str(dep_task.status or "").strip().lower()
                                            dep_review_status = self._get_task_review_status(
                                                dep_task.task_metadata
                                            )

                                        if dep_status != "completed":
                                            continue
                                        if dep_review_status == "approved":
                                            continue

                                        supervisor = await _get_dependency_supervisor()
                                        await self._review_task_for_dependency_gate(
                                            mission_id=mission_id,
                                            mission=mission,
                                            dependency_task_id=dep_uuid,
                                            supervisor=supervisor,
                                            fallback_total_tasks=mission_total_tasks,
                                        )
                                # Re-evaluate dependency statuses after on-demand review.
                                continue
                        break

                    terminal_statuses = {"completed", "failed", "cancelled"}
                    all_terminal = all(
                        dep_statuses.get(dep_id) in terminal_statuses for dep_id in dep_ids
                    )
                    failed_deps = [
                        dep_id
                        for dep_id in dep_ids
                        if dep_statuses.get(dep_id) in {"failed", "cancelled"}
                    ]
                    if all_terminal and failed_deps:
                        with get_db_session() as session:
                            t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                            if t:
                                t.status = "failed"
                                t.result = {
                                    "error": f"Blocked by failed dependencies: {', '.join(failed_deps)}"
                                }
                        counter_snapshot = self._safe_sync_mission_task_counters(
                            mission_id,
                            fallback_total=mission_total_tasks,
                        )
                        self._emitter.emit(
                            mission_id=mission_id,
                            event_type="TASK_FAILED",
                            task_id=task_obj.task_id,
                            data={
                                "title": (task_obj.task_metadata or {}).get("title", "Untitled"),
                                "error": (
                                    "Blocked by failed dependencies: " f"{', '.join(failed_deps)}"
                                ),
                                **counter_snapshot,
                            },
                            message="Task failed due to failed dependencies",
                        )
                        return
                    await asyncio.sleep(2)

                await self._execute_task_with_retry(
                    mission_id,
                    mission,
                    task_obj,
                    max_retries=max(0, self._coerce_int(exec_cfg.get("max_retries", 2), 2)),
                    available_platform_agents=available_platform_agents,
                )

        await asyncio.gather(
            *[_execute_single(t) for t in sorted_tasks],
            return_exceptions=True,
        )

        counts = self._get_task_status_counts(mission_id)
        completed_count = counts.get("completed", 0)
        failed_count = counts.get("failed", 0)
        total_count = sum(counts.values())

        # Update mission counters based on actual DB task statuses.
        self._sync_mission_task_counters(mission_id, fallback_total=mission_total_tasks)

        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_COMPLETED",
            data={
                "phase": "executing",
                "completed": completed_count,
                "failed": failed_count,
                "total": total_count,
            },
            message=f"Task execution completed: {completed_count} done, {failed_count} failed",
        )

    async def _execute_task_with_retry(
        self,
        mission_id: UUID,
        mission: Any,
        task_obj: Any,
        max_retries: int = 2,
        available_platform_agents: Optional[List[Any]] = None,
    ) -> bool:
        """Execute a single task with exponential backoff retry.

        Returns True on success, False on failure.
        """
        llm_cfg = self._get_llm_config(mission, "temporary_worker")
        exec_cfg = self._get_execution_config(mission)
        debug_mode = self._coerce_bool(exec_cfg.get("debug_mode", False), default=False)
        prefer_existing_agents = self._coerce_bool(
            exec_cfg.get("prefer_existing_agents", True),
            default=True,
        )
        allow_temporary_workers = self._coerce_bool(
            exec_cfg.get("allow_temporary_workers", True),
            default=True,
        )
        task_timeout_s = max(0, self._coerce_int(exec_cfg.get("task_timeout_s", 600), 600))
        task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
        task_metadata = task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
        mission_total_tasks = self._coerce_int(getattr(mission, "total_tasks", 0), 0)
        review_feedback_raw = task_metadata.get("review_feedback")
        review_feedback = (
            review_feedback_raw.strip() if isinstance(review_feedback_raw, str) else ""
        )
        review_cycle = self._coerce_int(task_metadata.get("review_cycle_count", 0), 0)
        assignment_source = str(task_metadata.get("assignment_source") or "").strip().lower()
        planning_prefers_temporary = assignment_source == "temporary_fallback_pending"
        if len(review_feedback) > 4000:
            review_feedback = review_feedback[:4000] + "\n...[truncated]"
        resolved_agent_id: Optional[UUID] = getattr(task_obj, "assigned_agent_id", None)
        skip_existing_selection = False
        # Backward-compat guard:
        # only enforce rework escalation when assignment source is explicit.
        # Legacy rows (without assignment_source) should keep prior behavior.
        force_temporary_for_rework = (
            allow_temporary_workers
            and bool(review_feedback)
            and review_cycle > 0
            and bool(assignment_source)
            and not self._coerce_bool(task_metadata.get("assigned_agent_temporary", False))
        )
        if force_temporary_for_rework and resolved_agent_id is not None:
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_AGENT_ESCALATED",
                task_id=task_obj.task_id,
                agent_id=resolved_agent_id,
                data={
                    "title": task_title,
                    "reason": "review_rework_requires_specialist",
                    "review_cycle": review_cycle,
                    "previous_agent_id": str(resolved_agent_id),
                    "assignment_source": assignment_source or "unknown",
                },
                message=f"Escalating rework to temporary worker: {task_title}",
            )
            resolved_agent_id = None
            # Avoid immediately selecting another broad platform match for rework tasks.
            skip_existing_selection = True
        agent = None
        total_attempts = max_retries + 1

        if resolved_agent_id:
            agent = await create_registered_mission_agent(
                agent_id=resolved_agent_id,
                owner_user_id=mission.created_by_user_id,
            )
            if agent is None:
                logger.warning(
                    "Assigned agent %s unavailable for task %s, creating temporary worker",
                    resolved_agent_id,
                    task_obj.task_id,
                )
                resolved_agent_id = None

        if resolved_agent_id is None and prefer_existing_agents and not skip_existing_selection:
            selected_platform = self._select_platform_agent_for_task(
                task_obj=task_obj,
                available_agents=available_platform_agents or [],
            )

            if selected_platform and planning_prefers_temporary:
                capability_overlap = self._coerce_int(
                    selected_platform.get("capability_overlap"),
                    0,
                )
                match_score = float(selected_platform.get("match_score") or 0.0)
                if capability_overlap <= 0 or match_score < 4.5:
                    self._emitter.emit(
                        mission_id=mission_id,
                        event_type="TASK_AGENT_MATCH_REJECTED",
                        task_id=task_obj.task_id,
                        data={
                            "title": task_title,
                            "reason": "planning_marked_temporary_fallback",
                            "match_score": match_score,
                            "capability_overlap": capability_overlap,
                            "candidate_agent_id": selected_platform.get("agent_id"),
                            "candidate_agent_name": selected_platform.get("agent_name"),
                            "match_summary": selected_platform.get("match_summary"),
                        },
                        message=(
                            f"Platform match rejected for temporary-planned task: {task_title}"
                        ),
                    )
                    selected_platform = None

            if selected_platform:
                candidate_agent_id = UUID(selected_platform["agent_id"])
                candidate = await create_registered_mission_agent(
                    agent_id=candidate_agent_id,
                    owner_user_id=mission.created_by_user_id,
                )
                if candidate is not None:
                    resolved_agent_id = candidate_agent_id
                    agent = candidate

                    from database.connection import get_db_session
                    from database.models import Task

                    with get_db_session() as session:
                        t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                        if t:
                            t.assigned_agent_id = resolved_agent_id
                            meta = dict(t.task_metadata or {})
                            meta["assigned_agent_name"] = selected_platform["agent_name"]
                            meta["assigned_agent_temporary"] = False
                            meta["assignment_source"] = "platform_auto_match"
                            meta["assignment_reason_code"] = "platform_auto_match"
                            meta["assignment_reason"] = str(
                                selected_platform.get("match_summary")
                                or "Matched by platform auto-assignment."
                            )
                            t.task_metadata = meta

                    local_meta = dict(task_obj.task_metadata or {})
                    local_meta["assigned_agent_name"] = selected_platform["agent_name"]
                    local_meta["assigned_agent_temporary"] = False
                    local_meta["assignment_source"] = "platform_auto_match"
                    local_meta["assignment_reason_code"] = "platform_auto_match"
                    local_meta["assignment_reason"] = str(
                        selected_platform.get("match_summary")
                        or "Matched by platform auto-assignment."
                    )
                    task_obj.task_metadata = local_meta
                    task_obj.assigned_agent_id = resolved_agent_id

                    self._emitter.emit(
                        mission_id=mission_id,
                        event_type="TASK_AGENT_ASSIGNED",
                        task_id=task_obj.task_id,
                        agent_id=resolved_agent_id,
                        data={
                            "title": task_title,
                            "agent_id": str(resolved_agent_id),
                            "agent_name": selected_platform["agent_name"],
                            "is_temporary": False,
                            "source": "platform_auto_match",
                            "match_summary": selected_platform.get("match_summary"),
                        },
                        message=f"Platform agent assigned: {selected_platform['agent_name']}",
                    )

        if resolved_agent_id is None and allow_temporary_workers:
            resolved_agent_id = self._provision_temporary_worker_agent(
                mission_id=mission_id,
                mission=mission,
                task_obj=task_obj,
                llm_cfg=llm_cfg,
            )
            agent = await create_registered_mission_agent(
                agent_id=resolved_agent_id,
                owner_user_id=mission.created_by_user_id,
            )
            if agent is None:
                raise MissionError(
                    mission_id,
                    f"Failed to initialize temporary worker agent for task {task_obj.task_id}",
                )

        if resolved_agent_id is None or agent is None:
            no_agent_error = (
                "No suitable existing platform agent was found and temporary workers are disabled."
                if not allow_temporary_workers
                else "Failed to resolve an executable worker agent for this task."
            )
            from database.connection import get_db_session
            from database.models import Task

            with get_db_session() as session:
                t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                if t:
                    t.status = "failed"
                    t.result = {
                        "error": no_agent_error,
                        "last_error": no_agent_error,
                        "attempts": [],
                    }
            counter_snapshot = self._safe_sync_mission_task_counters(
                mission_id,
                fallback_total=mission_total_tasks,
            )
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_FAILED",
                task_id=task_obj.task_id,
                data={
                    "title": task_title,
                    "error": no_agent_error,
                    "prefer_existing_agents": prefer_existing_agents,
                    "allow_temporary_workers": allow_temporary_workers,
                    **counter_snapshot,
                },
                message=f"Task failed: {task_title}",
            )
            return False

        for attempt in range(max_retries + 1):
            try:
                # Update task status
                from database.connection import get_db_session
                from database.models import Task

                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        t.status = "in_progress"
                        t.assigned_agent_id = resolved_agent_id

                update_mission_agent_status(
                    mission_id=mission_id,
                    agent_id=resolved_agent_id,
                    status="active",
                )

                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="TASK_STARTED",
                    task_id=task_obj.task_id,
                    data={
                        "title": task_title,
                        "attempt": attempt + 1,
                        "agent_id": str(resolved_agent_id),
                        "agent_name": getattr(agent, "name", "worker"),
                    },
                    message=f"Executing task: {task_title} (attempt {attempt + 1})",
                )

                review_feedback_section = ""
                if review_feedback:
                    review_feedback_section = (
                        "## Rework Context\n"
                        f"This task is in rework cycle {review_cycle}. "
                        "You must address every review finding below before finishing.\n\n"
                        "## Previous Review Feedback\n"
                        f"{review_feedback}\n\n"
                    )

                mission_context_snippet = self._truncate_prompt_text(
                    getattr(mission, "instructions", ""),
                    limit=1800,
                )
                role_context = str(
                    task_metadata.get("owner_role_name") or task_metadata.get("owner_role") or ""
                ).strip()
                role_required_capabilities = self._coerce_string_list(
                    task_metadata.get("role_required_capabilities")
                )
                role_sop_hint = str(task_metadata.get("role_sop_hint") or "").strip()

                task_prompt = (
                    "Execute the following mission task. Keep your own SOP and specialization, "
                    "while strictly satisfying the task constraints.\n\n"
                    f"## Mission\n{getattr(mission, 'title', 'Untitled Mission')}\n\n"
                    "## Original User Prompt\n"
                    f"{mission_context_snippet or 'N/A'}\n\n"
                    f"## Task: {task_title}\n"
                    f"## Task Role\n{role_context or 'N/A'}\n\n"
                    "## Role Required Capabilities\n"
                    f"{', '.join(role_required_capabilities) if role_required_capabilities else 'N/A'}\n\n"
                    "## Role SOP Hint\n"
                    f"{role_sop_hint or 'N/A'}\n\n"
                    f"## Instructions\n{task_obj.goal_text}\n\n"
                    f"## Acceptance Criteria\n{task_obj.acceptance_criteria or 'None specified'}\n\n"
                    "## Output Location Policy\n"
                    "- Write final user-facing deliverable files to `/workspace/output`.\n"
                    "- Put intermediate/debug artifacts under `/workspace/shared` or `/workspace/tasks`.\n"
                    "- Do not leave final deliverables only in `/workspace` root.\n\n"
                    f"{review_feedback_section}"
                    "Produce the deliverable and confirm completion."
                )

                workspace_container_id: Optional[str] = None
                workspace_manager = getattr(self, "_workspace", None)
                if workspace_manager is not None:
                    try:
                        workspace_container_id = workspace_manager.get_container_id(mission_id)
                    except Exception:
                        workspace_container_id = None
                code_execution_network_access = self._coerce_bool(
                    exec_cfg.get("network_access", False),
                    default=False,
                )
                if task_timeout_s > 0:
                    result = await asyncio.wait_for(
                        self._execute_agent_task(
                            agent,
                            task_prompt,
                            container_id=workspace_container_id,
                            code_execution_network_access=code_execution_network_access,
                        ),
                        timeout=task_timeout_s,
                    )
                else:
                    result = await self._execute_agent_task(
                        agent,
                        task_prompt,
                        container_id=workspace_container_id,
                        code_execution_network_access=code_execution_network_access,
                    )
                output = self._extract_agent_output(
                    result,
                    f"Task execution failed for '{task_title}'",
                )

                # Mark task completed
                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        t.status = "completed"
                        existing_result = dict(t.result) if isinstance(t.result, dict) else {}
                        completion_payload: Dict[str, Any] = {"output": output}
                        attempts = existing_result.get("attempts")
                        if isinstance(attempts, list) and attempts:
                            completion_payload["attempts"] = attempts
                        if debug_mode:
                            completion_payload["successful_attempt"] = attempt + 1
                        t.result = completion_payload
                        task_meta = dict(getattr(t, "task_metadata", None) or {})
                        if isinstance(task_meta.get("review_feedback"), str):
                            task_meta["last_review_feedback"] = task_meta.get("review_feedback")
                            task_meta.pop("review_feedback", None)
                        task_meta["review_status"] = "pending"
                        task_meta.pop("review_output_signature", None)
                        t.task_metadata = task_meta
                        t.completed_at = datetime.utcnow()
                        local_meta = dict(task_obj.task_metadata or {})
                        if isinstance(local_meta.get("review_feedback"), str):
                            local_meta["last_review_feedback"] = local_meta.get("review_feedback")
                            local_meta.pop("review_feedback", None)
                        local_meta["review_status"] = "pending"
                        local_meta.pop("review_output_signature", None)
                        task_obj.task_metadata = local_meta

                counter_snapshot = self._safe_sync_mission_task_counters(
                    mission_id,
                    fallback_total=mission_total_tasks,
                )
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="TASK_COMPLETED",
                    task_id=task_obj.task_id,
                    data={"title": task_title, **counter_snapshot},
                    message=f"Task completed: {task_title}",
                )
                update_mission_agent_status(
                    mission_id=mission_id,
                    agent_id=resolved_agent_id,
                    status="idle",
                )
                return True

            except Exception as exc:
                is_timeout = isinstance(exc, asyncio.TimeoutError)
                if is_timeout:
                    error_message = (
                        "Task execution exceeded configured timeout "
                        f"({task_timeout_s}s) and was aborted"
                    )
                    error_type = "TaskTimeoutError"
                else:
                    error_message = str(exc)
                    error_type = exc.__class__.__name__
                trace = traceback.format_exc() if debug_mode else None
                backoff = 2**attempt if attempt < max_retries else None

                logger.warning(
                    "Task %s attempt %d failed: %s",
                    task_obj.task_id,
                    attempt + 1,
                    exc,
                )

                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        attempt_record: Dict[str, Any] = {
                            "attempt": attempt + 1,
                            "max_attempts": total_attempts,
                            "error": error_message,
                            "error_type": error_type,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "will_retry": attempt < max_retries,
                        }
                        if backoff is not None:
                            attempt_record["backoff_s"] = backoff
                        if is_timeout and task_timeout_s > 0:
                            attempt_record["timeout_s"] = task_timeout_s
                        if trace:
                            attempt_record["traceback"] = trace
                        result_payload = self._append_attempt_to_result(
                            existing_result=t.result,
                            attempt_record=attempt_record,
                        )
                        result_payload["last_error"] = error_message
                        result_payload["last_error_type"] = error_type
                        if trace:
                            result_payload["last_traceback"] = trace
                        if attempt >= max_retries:
                            t.status = "failed"
                            t.completed_at = None
                        t.result = result_payload

                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="TASK_ATTEMPT_FAILED",
                    task_id=task_obj.task_id,
                    data={
                        "title": task_title,
                        "attempt": attempt + 1,
                        "max_attempts": total_attempts,
                        "error": error_message,
                        "error_type": error_type,
                        "will_retry": attempt < max_retries,
                        "backoff_s": backoff,
                        "agent_id": str(resolved_agent_id),
                        "agent_name": getattr(agent, "name", "worker"),
                        "timeout_s": task_timeout_s if is_timeout and task_timeout_s > 0 else None,
                        "traceback": trace,
                    },
                    message=(f"Task attempt {attempt + 1}/{total_attempts} failed: {task_title}"),
                )

                if attempt < max_retries:
                    assert backoff is not None
                    await asyncio.sleep(backoff)
                else:
                    # Final failure
                    counter_snapshot = self._safe_sync_mission_task_counters(
                        mission_id,
                        fallback_total=mission_total_tasks,
                    )
                    self._emitter.emit(
                        mission_id=mission_id,
                        event_type="TASK_FAILED",
                        task_id=task_obj.task_id,
                        data={
                            "title": task_title,
                            "error": error_message,
                            "error_type": error_type,
                            "attempt": attempt + 1,
                            "max_attempts": total_attempts,
                            "agent_id": str(resolved_agent_id),
                            "agent_name": getattr(agent, "name", "worker"),
                            "timeout_s": task_timeout_s if is_timeout and task_timeout_s > 0 else None,
                            **counter_snapshot,
                        },
                        message=f"Task failed: {task_title}",
                    )
                    update_mission_agent_status(
                        mission_id=mission_id,
                        agent_id=resolved_agent_id,
                        status="failed",
                    )
                    return False

        return False

    async def _review_task_for_dependency_gate(
        self,
        mission_id: UUID,
        mission: Any,
        dependency_task_id: UUID,
        *,
        supervisor: Any,
        fallback_total_tasks: int = 0,
    ) -> bool:
        """Review a completed dependency task before unblocking downstream execution."""
        from database.connection import get_db_session
        from database.models import Task

        with get_db_session() as session:
            dep_task = session.query(Task).filter(Task.task_id == dependency_task_id).first()
            if dep_task is None:
                return False

            if str(dep_task.status or "").strip().lower() != "completed":
                return False

            dep_meta = dict(dep_task.task_metadata or {})
            dep_title = str(dep_meta.get("title") or "Untitled")
            dep_output = (dep_task.result or {}).get("output", "No output")
            dep_output_signature = self._build_text_signature(dep_output)
            if (
                self._get_task_review_status(dep_meta) == "approved"
                and str(dep_meta.get("review_output_signature") or "") == dep_output_signature
            ):
                return True

            dep_goal = dep_task.goal_text
            dep_acceptance = dep_task.acceptance_criteria or "None specified"

        review_prompt = (
            "Review the following task output against its acceptance criteria.\n\n"
            f"## Task: {dep_title}\n"
            f"## Instructions\n{dep_goal}\n\n"
            f"## Acceptance Criteria\n{dep_acceptance}\n\n"
            f"## Task Output\n{dep_output}\n\n"
            "Respond with PASS or FAIL followed by your reasoning. "
            "If FAIL, provide specific actionable feedback."
        )
        review_output = await self._execute_phase_prompt_with_retry(
            mission_id=mission_id,
            mission=mission,
            phase="reviewing",
            step=f"dependency_gate_review:{dependency_task_id}",
            agent=supervisor,
            prompt=review_prompt,
            error_context=f"Dependency review failed for task {dependency_task_id}",
        )
        verdict = self._extract_binary_verdict(review_output)
        self._emitter.emit(
            mission_id=mission_id,
            event_type="TASK_REVIEWED",
            task_id=dependency_task_id,
            data={
                "title": dep_title,
                "verdict": verdict,
                "reason": "dependency_gate",
            },
            message=f"Task review: {dep_title} -> {verdict} (dependency gate)",
        )

        if verdict == "FAIL":
            with get_db_session() as session:
                dep_task = session.query(Task).filter(Task.task_id == dependency_task_id).first()
                if dep_task:
                    dep_task.status = "failed"
                    dep_meta = dict(dep_task.task_metadata or {})
                    dep_meta["review_feedback"] = review_output
                    dep_meta["review_status"] = "rework_required"
                    dep_meta["review_cycle_count"] = (
                        self._coerce_int(dep_meta.get("review_cycle_count", 0), 0) + 1
                    )
                    dep_meta.pop("review_output_signature", None)
                    dep_task.task_metadata = dep_meta
                    dep_task.completed_at = None

            counter_snapshot = self._safe_sync_mission_task_counters(
                mission_id,
                fallback_total=fallback_total_tasks,
            )
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_FAILED",
                task_id=dependency_task_id,
                data={
                    "title": dep_title,
                    "error": "Dependency review failed; task returned to rework.",
                    "reason": "dependency_review_failed",
                    **counter_snapshot,
                },
                message=f"Task failed due to dependency review rejection: {dep_title}",
            )
            return False

        with get_db_session() as session:
            dep_task = session.query(Task).filter(Task.task_id == dependency_task_id).first()
            if dep_task:
                dep_meta = dict(dep_task.task_metadata or {})
                dep_meta["review_status"] = "approved"
                dep_meta["review_output_signature"] = dep_output_signature
                dep_meta.pop("review_feedback", None)
                dep_meta.pop("blocked_by_failed_dependencies", None)
                dep_task.task_metadata = dep_meta

        return True

    async def _phase_review(self, mission_id: UUID) -> None:
        """Supervisor reviews outputs against acceptance criteria."""
        self._transition(mission_id, "reviewing")
        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_STARTED",
            data={"phase": "reviewing"},
            message="Supervisor review started",
        )

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        # Create supervisor agent
        llm_cfg = self._get_llm_config(mission, "supervisor")
        supervisor_config = get_supervisor_config(
            owner_user_id=mission.created_by_user_id,
            temperature=llm_cfg["temperature"],
        )
        supervisor = await create_mission_agent(agent_config=supervisor_config, **llm_cfg)

        # Fetch all mission tasks so incomplete tasks are also considered failures.
        from database.connection import get_db_session
        from database.models import Task

        with get_db_session() as session:
            tasks = session.query(Task).filter(Task.mission_id == mission_id).all()
            task_data = []
            for t in tasks:
                session.expunge(t)
                task_data.append(t)
        task_title_by_id = {
            str(task.task_id): (task.task_metadata or {}).get("title", "Untitled")
            for task in task_data
        }

        failed_tasks: List[UUID] = []
        failed_task_ids: set[str] = set()
        tasks_in_review_order = self._topological_sort(task_data)

        def _mark_task_review_failed(
            task_obj: Any,
            *,
            reason: str,
            feedback: str,
            increment_cycle: bool,
            blocked_by: Optional[List[str]] = None,
        ) -> None:
            task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
            with get_db_session() as session:
                t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                if t:
                    t.status = "failed"
                    meta = dict(t.task_metadata or {})
                    review_cycle = self._coerce_int(meta.get("review_cycle_count", 0), 0)
                    if increment_cycle:
                        review_cycle += 1
                        meta["review_cycle_count"] = review_cycle
                    meta["review_feedback"] = feedback
                    meta["review_status"] = (
                        "rework_required" if increment_cycle else "blocked_by_dependency"
                    )
                    if blocked_by:
                        meta["blocked_by_failed_dependencies"] = blocked_by
                    else:
                        meta.pop("blocked_by_failed_dependencies", None)
                    meta.pop("review_output_signature", None)
                    t.task_metadata = meta
                    t.completed_at = None

            local_meta = dict(task_obj.task_metadata or {})
            if increment_cycle:
                local_meta["review_cycle_count"] = (
                    self._coerce_int(local_meta.get("review_cycle_count", 0), 0) + 1
                )
            local_meta["review_feedback"] = feedback
            local_meta["review_status"] = (
                "rework_required" if increment_cycle else "blocked_by_dependency"
            )
            if blocked_by:
                local_meta["blocked_by_failed_dependencies"] = blocked_by
            else:
                local_meta.pop("blocked_by_failed_dependencies", None)
            local_meta.pop("review_output_signature", None)
            task_obj.task_metadata = local_meta
            task_obj.status = "failed"

            failed_tasks.append(task_obj.task_id)
            failed_task_ids.add(str(task_obj.task_id))
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_REVIEWED",
                task_id=task_obj.task_id,
                data={
                    "title": task_title,
                    "verdict": "FAIL",
                    "reason": reason,
                    "blocked_by": blocked_by or [],
                },
                message=f"Task review: {task_title} -> FAIL ({reason})",
            )

        for task_obj in tasks_in_review_order:
            task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
            dependency_ids = [
                dep_id for dep_id in (task_obj.dependencies or []) if dep_id in task_title_by_id
            ]
            failed_dependencies = [dep_id for dep_id in dependency_ids if dep_id in failed_task_ids]

            if failed_dependencies:
                blocked_titles = [
                    task_title_by_id.get(dep_id, dep_id) for dep_id in failed_dependencies
                ]
                _mark_task_review_failed(
                    task_obj,
                    reason="dependency_review_failed",
                    feedback=(
                        "Blocked by review-failed dependencies: " + ", ".join(blocked_titles)
                    ),
                    increment_cycle=False,
                    blocked_by=failed_dependencies,
                )
                continue

            if task_obj.status != "completed":
                task_meta_current = (
                    task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
                )
                existing_feedback = str(task_meta_current.get("review_feedback") or "").strip()
                existing_review_status = str(task_meta_current.get("review_status") or "").strip()
                if existing_feedback and existing_review_status == "rework_required":
                    _mark_task_review_failed(
                        task_obj,
                        reason="qa_rework_required",
                        feedback=existing_feedback,
                        increment_cycle=False,
                    )
                    continue
                _mark_task_review_failed(
                    task_obj,
                    reason="task_not_completed",
                    feedback=(
                        f"Task status is '{task_obj.status}', expected 'completed' before review."
                    ),
                    increment_cycle=True,
                )
                continue

            task_output = (task_obj.result or {}).get("output", "No output")
            task_meta = dict(task_obj.task_metadata or {})
            output_signature = self._build_text_signature(task_output)
            if (
                task_meta.get("review_status") == "approved"
                and str(task_meta.get("review_output_signature") or "") == output_signature
            ):
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="TASK_REVIEWED",
                    task_id=task_obj.task_id,
                    data={
                        "title": task_title,
                        "verdict": "PASS",
                        "reason": "reuse_previous_pass",
                    },
                    message=f"Task review: {task_title} -> PASS (cached)",
                )
                continue

            review_prompt = (
                "Review the following task output against its acceptance criteria.\n\n"
                f"## Task: {task_title}\n"
                f"## Instructions\n{task_obj.goal_text}\n\n"
                f"## Acceptance Criteria\n{task_obj.acceptance_criteria or 'None specified'}\n\n"
                f"## Task Output\n{task_output}\n\n"
                "Respond with PASS or FAIL followed by your reasoning. "
                "If FAIL, provide specific actionable feedback."
            )

            review_output = await self._execute_phase_prompt_with_retry(
                mission_id=mission_id,
                mission=mission,
                phase="reviewing",
                step=f"review_task:{task_obj.task_id}",
                agent=supervisor,
                prompt=review_prompt,
                error_context="Supervisor review failed",
            )

            verdict = self._extract_binary_verdict(review_output)
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_REVIEWED",
                task_id=task_obj.task_id,
                data={"title": task_title, "verdict": verdict},
                message=f"Task review: {task_title} -> {verdict}",
            )

            if verdict == "FAIL":
                _mark_task_review_failed(
                    task_obj,
                    reason="review_rejected",
                    feedback=review_output,
                    increment_cycle=True,
                )
                continue

            with get_db_session() as session:
                t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                if t:
                    meta = dict(t.task_metadata or {})
                    meta["review_status"] = "approved"
                    meta["review_output_signature"] = output_signature
                    meta.pop("review_feedback", None)
                    meta.pop("blocked_by_failed_dependencies", None)
                    t.task_metadata = meta
            local_meta = dict(task_obj.task_metadata or {})
            local_meta["review_status"] = "approved"
            local_meta["review_output_signature"] = output_signature
            local_meta.pop("review_feedback", None)
            local_meta.pop("blocked_by_failed_dependencies", None)
            task_obj.task_metadata = local_meta

        exec_cfg = self._get_execution_config(mission)
        configured_max_rework_cycles = self._coerce_int(
            exec_cfg.get("max_rework_cycles", MAX_REVIEW_CYCLES),
            MAX_REVIEW_CYCLES,
        )
        max_rework_cycles = max(
            0,
            min(configured_max_rework_cycles, MAX_ALLOWED_REWORK_CYCLES),
        )
        if configured_max_rework_cycles != max_rework_cycles:
            self._emitter.emit(
                mission_id=mission_id,
                event_type="REVIEW_CYCLE_LIMIT_ADJUSTED",
                data={
                    "configured": configured_max_rework_cycles,
                    "effective": max_rework_cycles,
                },
                message=(
                    "Review cycle limit capped to avoid runaway retries: "
                    f"{configured_max_rework_cycles} -> {max_rework_cycles}"
                ),
            )

        # If there are failed tasks and we haven't exceeded review cycles, loop back
        if failed_tasks:
            # Check the max review cycle across failed tasks
            with get_db_session() as session:
                max_cycle = 0
                for tid in failed_tasks:
                    t = session.query(Task).filter(Task.task_id == tid).first()
                    if t:
                        cycle = self._coerce_int(
                            (t.task_metadata or {}).get("review_cycle_count", 0),
                            0,
                        )
                        max_cycle = max(max_cycle, cycle)

            if max_cycle <= max_rework_cycles:
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="REVIEW_CYCLE_RETRY",
                    data={
                        "failed_count": len(failed_tasks),
                        "cycle": max_cycle,
                        "max_rework_cycles": max_rework_cycles,
                        "failed_task_ids": [str(task_id) for task_id in failed_tasks],
                        "failed_task_titles": [
                            task_title_by_id.get(str(task_id), "Untitled")
                            for task_id in failed_tasks
                        ],
                    },
                    message=f"Review found {len(failed_tasks)} failures, retrying execution",
                )
                # Transition back to executing for retry is handled in _phase_execution.
                await self._phase_execution(mission_id)
                # Re-enter review after re-execution
                await self._phase_review(mission_id)
                return
            counts = self._get_task_status_counts(mission_id)
            update_mission_fields(
                mission_id,
                completed_tasks=counts.get("completed", 0),
                failed_tasks=counts.get("failed", 0),
                total_tasks=max(mission.total_tasks, sum(counts.values())),
            )
            raise MissionError(
                mission_id,
                (
                    f"Review failed after {max_cycle} cycle(s); configured max_rework_cycles="
                    f"{max_rework_cycles}, unresolved tasks={len(failed_tasks)}"
                ),
            )

        counts = self._get_task_status_counts(mission_id)
        update_mission_fields(
            mission_id,
            completed_tasks=counts.get("completed", 0),
            failed_tasks=counts.get("failed", 0),
            total_tasks=max(mission.total_tasks, sum(counts.values())),
        )

        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_COMPLETED",
            data={"phase": "reviewing", "failed_count": len(failed_tasks)},
            message="Supervisor review completed",
        )

    async def _phase_qa(self, mission_id: UUID) -> None:
        """QA auditor performs final quality and security checks."""
        self._transition(mission_id, "qa")
        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_STARTED",
            data={"phase": "qa"},
            message="QA audit started",
        )

        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        # Create QA agent
        llm_cfg = self._get_llm_config(mission, "qa")
        qa_config = get_qa_config(
            owner_user_id=mission.created_by_user_id,
            temperature=llm_cfg["temperature"],
        )
        qa_agent = await create_mission_agent(agent_config=qa_config, **llm_cfg)

        # Gather all task outputs for audit
        from database.connection import get_db_session
        from database.models import Task

        with get_db_session() as session:
            tasks = session.query(Task).filter(Task.mission_id == mission_id).all()
            task_summaries = []
            for t in tasks:
                title = (t.task_metadata or {}).get("title", "Untitled")
                output = (t.result or {}).get("output", "No output")
                task_summaries.append(
                    f"### {title} (status: {t.status})\n"
                    f"**Acceptance Criteria**: {t.acceptance_criteria or 'None'}\n"
                    f"**Output**: {output[:2000]}\n"
                )

        audit_prompt = (
            "Perform a comprehensive quality and security audit of this mission.\n\n"
            f"## Mission: {mission.title}\n"
            f"## Original Instructions\n{mission.instructions}\n\n"
            f"## Requirements\n{mission.requirements_doc or 'N/A'}\n\n"
            f"## Task Deliverables\n{'---'.join(task_summaries)}\n\n"
            "Produce a structured audit report. End with a clear PASS or FAIL verdict."
        )

        qa_output = await self._execute_phase_prompt_with_retry(
            mission_id=mission_id,
            mission=mission,
            phase="qa",
            step="audit_deliverables",
            agent=qa_agent,
            prompt=audit_prompt,
            error_context="QA audit failed",
        )

        # Persist QA report regardless of verdict so failures remain debuggable.
        self._workspace.write_file(mission_id, "shared/qa_report.md", qa_output)
        verdict = self._extract_binary_verdict(qa_output)
        qa_details = self._extract_qa_audit_details(qa_output, verdict=verdict)
        qa_event_data = self._build_qa_verdict_event_data(verdict=verdict, qa_details=qa_details)

        self._emitter.emit(
            mission_id=mission_id,
            event_type="QA_VERDICT",
            data=qa_event_data,
            message=f"QA audit verdict: {verdict}",
        )

        if verdict == "FAIL":
            # Check QA cycle count
            mission = get_mission(mission_id)
            cfg = mission.mission_config or {} if mission else {}
            exec_cfg = self._get_execution_config(mission) if mission else {}
            configured_max_qa_cycles = self._coerce_int(
                exec_cfg.get("max_qa_cycles", MAX_QA_CYCLES),
                MAX_QA_CYCLES,
            )
            max_qa_cycles = max(0, min(configured_max_qa_cycles, MAX_ALLOWED_QA_CYCLES))
            qa_cycle = self._coerce_int(cfg.get("qa_cycle_count", 0), 0) + 1

            # Persist cycle count for observability and retry tracking
            update_mission_fields(
                mission_id,
                mission_config={**cfg, "qa_cycle_count": qa_cycle},
            )
            if configured_max_qa_cycles != max_qa_cycles:
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="QA_CYCLE_LIMIT_ADJUSTED",
                    data={
                        "configured": configured_max_qa_cycles,
                        "effective": max_qa_cycles,
                    },
                    message=(
                        "QA cycle limit capped to avoid runaway retries: "
                        f"{configured_max_qa_cycles} -> {max_qa_cycles}"
                    ),
                )
            if qa_cycle <= max_qa_cycles:
                rework_seeded_tasks = self._seed_tasks_for_qa_rework(
                    mission_id=mission_id,
                    qa_details=qa_details,
                )
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="QA_REWORK_SEEDED",
                    data={
                        "cycle": qa_cycle,
                        "rework_seeded_tasks": rework_seeded_tasks,
                    },
                    message=(
                        "QA feedback seeded into task rework context: "
                        f"{rework_seeded_tasks} task(s)"
                    ),
                )
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="QA_CYCLE_RETRY",
                    data={
                        **qa_event_data,
                        "cycle": qa_cycle,
                        "max_qa_cycles": max_qa_cycles,
                        "rework_seeded_tasks": rework_seeded_tasks,
                    },
                    message="QA failed, routing back to review",
                )
                # Transition back to reviewing is handled in _phase_review.
                await self._phase_review(mission_id)
                await self._phase_qa(mission_id)
                return
            failure_summary = str(qa_details.get("summary") or "").strip()
            if len(failure_summary) > 180:
                failure_summary = failure_summary[:180] + "..."
            reason_suffix = f"; summary={failure_summary}" if failure_summary else ""
            raise MissionError(
                mission_id,
                (
                    f"QA audit failed after {qa_cycle} cycle(s); configured max_qa_cycles="
                    f"{max_qa_cycles}{reason_suffix}"
                ),
            )

        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_COMPLETED",
            data={"phase": "qa", "verdict": verdict},
            message="QA audit completed",
        )

    async def _phase_complete(self, mission_id: UUID) -> None:
        """Collect deliverables and finalise."""
        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        counts = self._get_task_status_counts(mission_id)
        total_tasks = sum(counts.values())
        completed_count = counts.get("completed", 0)
        failed_count = counts.get("failed", 0)
        unfinished_count = total_tasks - completed_count - failed_count

        if total_tasks > 0 and (unfinished_count > 0 or failed_count > 0):
            raise MissionError(
                mission_id,
                (
                    "Mission cannot be completed while tasks remain unfinished "
                    f"(completed={completed_count}, failed={failed_count}, unfinished={unfinished_count})"
                ),
            )

        deliverables = self._workspace.collect_deliverables(mission_id)
        update_mission_fields(
            mission_id,
            result={"deliverables": [d.__dict__ for d in deliverables]},
            total_tasks=max(mission.total_tasks, total_tasks),
            completed_tasks=completed_count,
            failed_tasks=failed_count,
        )
        update_mission_status(mission_id, "completed")
        self._emitter.emit(
            mission_id=mission_id,
            event_type="MISSION_COMPLETED",
            data={"deliverable_count": len(deliverables)},
            message="Mission completed successfully",
        )

    def _snapshot_deliverables(self, mission_id: UUID) -> None:
        """Best-effort snapshot of artifacts before workspace cleanup."""
        try:
            deliverables = self._workspace.collect_deliverables(mission_id)
        except Exception:
            # Workspace may not exist (e.g. failed before requirements phase).
            return
        if not deliverables:
            return

        try:
            mission = get_mission(mission_id)
            existing_result = dict(mission.result or {}) if mission else {}
            existing_result["deliverables"] = [d.__dict__ for d in deliverables]
            update_mission_fields(mission_id, result=existing_result)
        except Exception:
            logger.exception("Failed to persist deliverable snapshot for mission %s", mission_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_qa_verdict_event_data(verdict: str, qa_details: Dict[str, Any]) -> Dict[str, Any]:
        """Build a stable payload schema for QA verdict events."""
        normalized_verdict = str(verdict or qa_details.get("verdict") or "").strip().upper()
        if normalized_verdict not in {"PASS", "FAIL"}:
            normalized_verdict = "FAIL"

        summary = str(qa_details.get("summary") or "").strip()

        raw_issues = qa_details.get("issues")
        issues: List[str] = []
        if isinstance(raw_issues, list):
            for item in raw_issues:
                issue = str(item or "").strip()
                if issue:
                    issues.append(issue)

        issues_count = qa_details.get("issues_count")
        if not isinstance(issues_count, int):
            issues_count = len(issues)
        issues_count = max(issues_count, len(issues))

        raw_recommendations = qa_details.get("recommendations")
        recommendations: List[str] = []
        if isinstance(raw_recommendations, list):
            for item in raw_recommendations:
                recommendation = str(item or "").strip()
                if recommendation:
                    recommendations.append(recommendation)

        report_format = str(qa_details.get("report_format") or "plain_text").strip()
        if not report_format:
            report_format = "plain_text"

        return {
            "schema_version": "qa_verdict.v2",
            "verdict": normalized_verdict,
            "summary": summary,
            "issues_count": issues_count,
            "issues": issues[:8],
            "recommendations": recommendations[:8],
            "report_format": report_format,
        }

    @staticmethod
    def _build_qa_rework_feedback(qa_details: Dict[str, Any]) -> str:
        """Compose deterministic rework feedback from QA findings."""
        summary = str(qa_details.get("summary") or "").strip()
        issues = qa_details.get("issues")
        recommendations = qa_details.get("recommendations")

        normalized_issues: List[str] = []
        if isinstance(issues, list):
            for issue in issues:
                value = str(issue or "").strip()
                if value:
                    normalized_issues.append(value)

        normalized_recommendations: List[str] = []
        if isinstance(recommendations, list):
            for recommendation in recommendations:
                value = str(recommendation or "").strip()
                if value:
                    normalized_recommendations.append(value)

        lines: List[str] = [
            "QA audit failed. Address every finding below before marking the task complete.",
        ]
        if summary:
            lines.append(f"Summary: {summary}")
        if normalized_issues:
            lines.append("Key QA findings:")
            lines.extend(f"{idx + 1}. {issue}" for idx, issue in enumerate(normalized_issues[:8]))
        if normalized_recommendations:
            lines.append("Recommended fixes:")
            lines.extend(
                f"{idx + 1}. {recommendation}"
                for idx, recommendation in enumerate(normalized_recommendations[:8])
            )

        feedback = "\n".join(lines).strip()
        if len(feedback) > 4000:
            feedback = feedback[:4000] + "\n...[truncated]"
        return feedback

    def _seed_tasks_for_qa_rework(self, mission_id: UUID, qa_details: Dict[str, Any]) -> int:
        """Seed task metadata so the next execution loop receives QA rework context."""
        from database.connection import get_db_session
        from database.models import Task

        feedback = self._build_qa_rework_feedback(qa_details)
        seeded = 0

        with get_db_session() as session:
            tasks = session.query(Task).filter(Task.mission_id == mission_id).all()
            for task in tasks:
                if str(task.status or "").lower() == "cancelled":
                    continue

                meta = dict(task.task_metadata or {})
                existing_feedback = meta.get("review_feedback")
                if isinstance(existing_feedback, str) and existing_feedback.strip():
                    meta["last_review_feedback"] = existing_feedback.strip()

                meta["review_cycle_count"] = (
                    self._coerce_int(meta.get("review_cycle_count", 0), 0) + 1
                )
                meta["review_feedback"] = feedback
                meta["review_status"] = "rework_required"
                meta["qa_feedback_cycle"] = (
                    self._coerce_int(meta.get("qa_feedback_cycle", 0), 0) + 1
                )
                meta.pop("review_output_signature", None)

                task.task_metadata = meta
                task.status = "failed"
                task.completed_at = None
                seeded += 1

        return seeded

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        """Extract a JSON object from LLM output, handling markdown code blocks."""
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
        else:
            candidate = text.strip()

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                parsed = json.loads(brace_match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        return {}

    @staticmethod
    def _extract_json_array(text: str) -> List[Dict[str, Any]]:
        """Extract a JSON array from LLM output, handling markdown code blocks."""
        # Try to find a ```json ... ``` block first
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
        else:
            candidate = text.strip()

        # Try to parse as JSON array
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: look for the first [ ... ] in the text
        bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket_match:
            try:
                parsed = json.loads(bracket_match.group(0))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        return []

    @staticmethod
    def _extract_binary_verdict(text: str) -> str:
        """Extract a PASS/FAIL verdict from model output.

        Uses the trailing lines first and defaults to FAIL when ambiguous.
        """
        if not text:
            return "FAIL"

        lines = [line.strip().upper() for line in text.splitlines() if line.strip()]
        recent = lines[-10:] if len(lines) > 10 else lines

        # Prefer explicit verdict lines near the end.
        for line in reversed(recent):
            if re.search(r"\bFAIL\b", line) and ("VERDICT" in line or "FINAL" in line):
                return "FAIL"
            if re.search(r"\bPASS\b", line) and ("VERDICT" in line or "FINAL" in line):
                return "PASS"

        # Fallback to the latest binary signal.
        for line in reversed(recent):
            if re.search(r"\bFAIL\b", line):
                return "FAIL"
            if re.search(r"\bPASS\b", line):
                return "PASS"

        return "FAIL"

    @staticmethod
    def _extract_qa_audit_details(text: str, verdict: str = "") -> Dict[str, Any]:
        """Extract compact QA summary/issues from free-form audit output."""
        if not text:
            return {
                "schema_version": "qa_verdict.v2",
                "summary": "",
                "issues_count": 0,
                "issues": [],
                "recommendations": [],
                "report_format": "empty",
            }

        normalized_verdict = str(verdict or "").strip().upper()

        def _normalize_summary_candidate(value: str) -> str:
            candidate = str(value or "").strip()
            if not candidate:
                return ""
            lowered = candidate.lower()
            if lowered in {"```", "```json", "```markdown", "```md"}:
                return ""
            if lowered in {"pass", "fail"}:
                return ""
            if candidate in {"{", "}", "[", "]"}:
                return ""
            if re.match(r"""^["']?audit_report["']?\s*:\s*\{?\s*$""", candidate, re.IGNORECASE):
                return ""
            return candidate

        lines = []
        for raw_line in str(text).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered in {"```", "```json", "```markdown", "```md"}:
                continue
            lines.append(line)

        summary = ""
        report_format = "plain_text"
        recommendations: List[str] = []

        def _coerce_issue_text(item: Any) -> str:
            if isinstance(item, dict):
                for key in ("issue", "description", "detail", "message", "title"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                return ""
            return str(item or "").strip()

        def _coerce_recommendation_text(item: Any) -> str:
            if isinstance(item, dict):
                for key in ("recommendation", "action", "suggestion", "detail", "message", "title"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                return ""
            return str(item or "").strip()

        def _clean_issue_text(value: str) -> str:
            cleaned = re.sub(r'^"?issue"?\s*[:：]\s*', "", str(value or ""), flags=re.IGNORECASE)
            cleaned = cleaned.strip().strip(",").strip().strip('"').strip("'").strip(",").strip()
            return cleaned

        parsed_obj = MissionOrchestrator._extract_json_object(str(text))
        if isinstance(parsed_obj, dict) and parsed_obj:
            report_obj: Dict[str, Any] = parsed_obj
            nested_report = parsed_obj.get("audit_report")
            if isinstance(nested_report, dict) and nested_report:
                report_obj = nested_report
                report_format = "audit_report_json"
            else:
                report_format = "json"

            for summary_key in (
                "summary",
                "overall",
                "conclusion",
                "details",
                "reason",
                "assessment",
            ):
                raw_summary = report_obj.get(summary_key)
                if isinstance(raw_summary, str) and raw_summary.strip():
                    summary = _normalize_summary_candidate(raw_summary)
                    if not summary:
                        continue
                    break

            issues: List[str] = []
            for issues_key in ("issues", "findings", "risks", "problems", "defects"):
                raw_issues = report_obj.get(issues_key)
                if isinstance(raw_issues, list):
                    for item in raw_issues:
                        issue = _clean_issue_text(_coerce_issue_text(item))
                        if issue and issue not in issues:
                            issues.append(issue[:260])
                    if issues:
                        break

            for recommendation_key in ("recommendations", "actions", "next_steps", "suggestions"):
                raw_recommendations = report_obj.get(recommendation_key)
                if isinstance(raw_recommendations, list):
                    for item in raw_recommendations:
                        recommendation = _coerce_recommendation_text(item).strip()
                        recommendation = recommendation.strip(",").strip('"').strip("'").strip()
                        if recommendation and recommendation not in recommendations:
                            recommendations.append(recommendation[:260])
                    if recommendations:
                        break

            if not summary and issues:
                summary = issues[0]

            if normalized_verdict == "PASS" and not issues:
                return {
                    "schema_version": "qa_verdict.v2",
                    "summary": summary[:260],
                    "issues_count": 0,
                    "issues": [],
                    "recommendations": recommendations[:8],
                    "report_format": report_format,
                }
            if summary or issues:
                return {
                    "schema_version": "qa_verdict.v2",
                    "summary": summary[:260] if summary else "",
                    "issues_count": len(issues),
                    "issues": issues[:8],
                    "recommendations": recommendations[:8],
                    "report_format": report_format,
                }

        summary_patterns = [
            r"^(summary|overall|assessment|结论|总体结论|总体评估|摘要)\s*[:：]\s*(.+)$",
            r"^(final verdict|verdict|最终结论|最终判定)\s*[:：]\s*(.+)$",
        ]
        for line in lines:
            for pattern in summary_patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    summary = _normalize_summary_candidate(match.group(2))
                    break
            if summary:
                break

        if not summary:
            for line in lines:
                upper = line.upper()
                if "PASS" in upper or "FAIL" in upper:
                    continue
                if line in {"{", "}", "[", "]"}:
                    continue
                summary = _normalize_summary_candidate(line)
                break

        if normalized_verdict == "PASS":
            return {
                "schema_version": "qa_verdict.v2",
                "summary": summary[:260] if summary else "",
                "issues_count": 0,
                "issues": [],
                "recommendations": recommendations[:8],
                "report_format": report_format,
            }

        issue_keywords = re.compile(
            r"(issue|risk|defect|problem|gap|missing|error|warning|"
            r"问题|风险|缺陷|不符合|未满足|错误|失败)",
            re.IGNORECASE,
        )
        issues: List[str] = []
        for raw_line in lines:
            line = raw_line.strip()
            if len(line) < 4:
                continue
            if not issue_keywords.search(line):
                continue

            cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
            cleaned = _clean_issue_text(cleaned)
            if not cleaned:
                continue
            if cleaned in issues:
                continue
            issues.append(cleaned[:260])
            if len(issues) >= 8:
                break

        if not summary and issues:
            summary = issues[0]
        if not summary and normalized_verdict == "FAIL":
            summary = "QA reported a failure without structured summary."

        return {
            "schema_version": "qa_verdict.v2",
            "summary": summary[:260] if summary else "",
            "issues_count": len(issues),
            "issues": issues,
            "recommendations": recommendations[:8],
            "report_format": report_format,
        }

    @staticmethod
    def _get_task_status_counts(mission_id: UUID) -> Dict[str, int]:
        """Get per-status task counts for a mission."""
        from database.connection import get_db_session
        from database.models import Task

        with get_db_session() as session:
            statuses = session.query(Task.status).filter(Task.mission_id == mission_id).all()
        counter = Counter(status for (status,) in statuses)
        return dict(counter)

    def _sync_mission_task_counters(
        self,
        mission_id: UUID,
        fallback_total: int = 0,
    ) -> Dict[str, int]:
        """Persist mission task counters from current DB task statuses."""
        counts = self._get_task_status_counts(mission_id)
        total_count = sum(counts.values())
        snapshot = {
            "total_tasks": max(fallback_total, total_count),
            "completed_tasks": counts.get("completed", 0),
            "failed_tasks": counts.get("failed", 0),
        }
        update_mission_fields(
            mission_id,
            **snapshot,
        )
        return snapshot

    def _safe_sync_mission_task_counters(
        self,
        mission_id: UUID,
        fallback_total: int = 0,
    ) -> Dict[str, int]:
        """Best-effort counter sync for non-critical UI snapshots."""
        try:
            return self._sync_mission_task_counters(
                mission_id=mission_id,
                fallback_total=fallback_total,
            )
        except Exception:
            logger.debug(
                "Failed to sync mission counters for snapshot",
                extra={"mission_id": str(mission_id)},
                exc_info=True,
            )
            return {}

    @staticmethod
    def _topological_sort(tasks: List[Any]) -> List[Any]:
        """Topological sort of tasks based on their dependencies.

        Tasks with no dependencies come first. Falls back to priority
        ordering if the graph is not a DAG (cycles are broken).
        """
        task_map = {str(t.task_id): t for t in tasks}
        in_degree: Dict[str, int] = defaultdict(int)
        graph: Dict[str, List[str]] = defaultdict(list)

        for t in tasks:
            tid = str(t.task_id)
            deps = t.dependencies or []
            for dep_id in deps:
                if dep_id in task_map:
                    graph[dep_id].append(tid)
                    in_degree[tid] += 1
            if tid not in in_degree:
                in_degree[tid] = 0

        # Kahn's algorithm
        queue = deque(
            sorted(
                [tid for tid, deg in in_degree.items() if deg == 0],
                key=lambda tid: task_map[tid].priority,
            )
        )
        result: List[Any] = []

        while queue:
            tid = queue.popleft()
            if tid in task_map:
                result.append(task_map[tid])
            for neighbor in graph.get(tid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Add any remaining tasks (cycle-breaking fallback)
        seen = {str(t.task_id) for t in result}
        for t in sorted(tasks, key=lambda x: x.priority):
            if str(t.task_id) not in seen:
                result.append(t)

        return result

    def _transition(self, mission_id: UUID, target_status: str) -> None:
        """Validate and apply a status transition."""
        mission = get_mission(mission_id)
        if mission is None:
            raise MissionError(mission_id, "Mission not found")

        current = mission.status
        if current == target_status:
            # Idempotent transition: retries/re-entrancy may re-request current state.
            return
        allowed = _TRANSITIONS.get(current, set())
        if target_status not in allowed:
            raise MissionError(
                mission_id,
                f"Invalid transition: {current} -> {target_status}",
            )
        update_mission_status(mission_id, target_status)

    def _cleanup(self, mission_id: UUID) -> None:
        """Clean up workspace and internal tracking."""
        self._clarification_events.pop(mission_id, None)
        self._clarification_responses.pop(mission_id, None)
        self._cleanup_temporary_agents(mission_id)
        try:
            self._workspace.cleanup_workspace(mission_id)
        except Exception:
            logger.exception("Workspace cleanup failed for mission %s", mission_id)

    def _cleanup_temporary_agents(self, mission_id: UUID) -> None:
        """Delete temporary agents created for a mission."""
        from agent_framework.agent_registry import AgentRegistry
        from mission_system.mission_repository import list_mission_agents

        try:
            mission_agents = list_mission_agents(mission_id)
        except Exception:
            logger.exception("Failed to list mission agents during cleanup for %s", mission_id)
            return

        registry = AgentRegistry()
        for mission_agent in mission_agents:
            if not getattr(mission_agent, "is_temporary", False):
                continue
            try:
                deleted = registry.delete_agent(mission_agent.agent_id)
                if deleted:
                    logger.info(
                        "Deleted temporary agent %s for mission %s",
                        mission_agent.agent_id,
                        mission_id,
                    )
            except Exception:
                logger.exception(
                    "Failed to delete temporary agent %s for mission %s",
                    mission_agent.agent_id,
                    mission_id,
                )


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: Optional[MissionOrchestrator] = None


def get_orchestrator() -> MissionOrchestrator:
    """Get or create the global MissionOrchestrator singleton."""
    global _instance
    if _instance is None:
        _instance = MissionOrchestrator()
    return _instance
