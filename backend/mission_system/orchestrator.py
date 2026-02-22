"""Mission Orchestrator.

Manages the full mission lifecycle as an async state machine:
DRAFT -> REQUIREMENTS -> PLANNING -> EXECUTING -> REVIEWING -> QA -> COMPLETED

Also supports FAILED and CANCELLED transitions from any state.
Each running mission is tracked as an ``asyncio.Task``.
"""

import asyncio
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
    "failed": set(),
    "cancelled": set(),
}

MAX_REVIEW_CYCLES = 2
MAX_QA_CYCLES = 1
MAX_ALLOWED_REWORK_CYCLES = 5
MAX_ALLOWED_QA_CYCLES = 5


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
        merged_role_cfg = {**inherited_cfg, **(role_cfg or {})}
        return {
            "llm_provider": merged_role_cfg.get(
                "llm_provider",
                merged_role_cfg.get("provider", cfg.get("provider", "ollama")),
            ),
            "llm_model": merged_role_cfg.get(
                "llm_model",
                merged_role_cfg.get("model", cfg.get("model", "qwen2.5:14b")),
            ),
            "temperature": float(merged_role_cfg.get("temperature", cfg.get("temperature", 0.7))),
            "max_tokens": int(merged_role_cfg.get("max_tokens", cfg.get("max_tokens", 4096))),
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
                    required_caps = {
                        str(capability).strip().lower()
                        for capability in required_capabilities
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

                if best_candidate is not None and best_score >= 0:
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
    ) -> Optional[Dict[str, str]]:
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
            for capability in self._coerce_string_list(task_metadata.get("role_required_capabilities"))
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
                getattr(candidate, "system_prompt", ""),
            )

            capability_overlap = len(role_required_caps.intersection(candidate_capabilities))
            lexical_overlap = len(task_tokens.intersection(candidate_tokens))

            # Hard guard: no overlap means "no reliable match", do not auto-bind.
            if capability_overlap <= 0 and lexical_overlap <= 0:
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

        if best_agent is None:
            return None

        return {
            "agent_id": str(best_agent.agent_id),
            "agent_name": str(getattr(best_agent, "name", "worker") or "worker"),
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
                metadata["temporary_agent_prompt_mode"] = "task_specific_sop"
                metadata["temporary_agent_skills"] = selected_skills
                metadata["temporary_agent_memory_scopes"] = memory_scopes
                metadata["temporary_agent_knowledge_collections"] = selected_knowledge
                task.task_metadata = metadata

        task_obj.assigned_agent_id = temp_agent.agent_id
        task_metadata = dict(task_obj.task_metadata or {})
        task_metadata["assigned_agent_name"] = temp_agent.name
        task_metadata["assigned_agent_temporary"] = True
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
    async def _execute_agent_task(agent: Any, prompt: str) -> Dict[str, Any]:
        """Run blocking agent calls in a worker thread so the event loop stays responsive."""
        return await asyncio.to_thread(agent.execute_task, prompt)

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

        # Create workspace
        self._workspace.create_workspace(
            mission_id,
            config=mission.mission_config or {},
        )

        # Set up attachments if any
        if mission.attachments:
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
            self._emitter.emit(
                mission_id=mission_id,
                event_type="USER_CLARIFICATION_REQUESTED",
                data={"questions": output},
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
                f"The user responded to your clarifications:\n\n{user_response}\n\n"
                f"Now produce the complete requirements document in {response_language}."
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
                '      "title": "Task title",\n'
                '      "instructions": "Detailed instructions",\n'
                '      "acceptance_criteria": "Testable criteria",\n'
                '      "dependencies": ["Other task title"],\n'
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
                "- If a role should use existing knowledge collections, reference IDs from catalog.\n\n"
                f"## Available Platform Agents\n{agent_catalog}\n\n"
                f"## Available Owner Knowledge Collections\n{knowledge_catalog}\n\n"
                f"## Requirements\n{requirements_doc}"
            )
        else:
            task_prompt = (
                "Decompose the following requirements into an ordered list of tasks "
                "with acceptance criteria. Return them as a JSON array where each "
                "element has keys: title, instructions, acceptance_criteria, "
                "dependencies (list of task titles), priority (integer 0-10), "
                "assigned_agent_id (string UUID or empty string).\n\n"
                f"{assignment_instruction}\n\n"
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

        # Parse JSON task list and optional team blueprint.
        task_list: List[Dict[str, Any]] = []
        raw_team_blueprint: List[Dict[str, Any]] = []
        if enable_team_blueprint:
            parsed_object = self._extract_json_object(output)
            raw_tasks = parsed_object.get("tasks") if isinstance(parsed_object, dict) else None
            raw_roles = (
                parsed_object.get("team_blueprint")
                if isinstance(parsed_object, dict)
                else None
            )
            if isinstance(raw_tasks, list):
                task_list = [item for item in raw_tasks if isinstance(item, dict)]
            if isinstance(raw_roles, list):
                raw_team_blueprint = [item for item in raw_roles if isinstance(item, dict)]
        if not task_list:
            task_list = self._extract_json_array(output)

        if not task_list:
            raise MissionError(
                mission_id,
                "Leader failed to produce a valid task plan",
            )

        role_assignments = self._resolve_blueprint_role_assignments(
            team_blueprint=raw_team_blueprint,
            available_agents=available_agents,
        )

        title_to_id: Dict[str, UUID] = {}
        used_agent_ids: set[UUID] = set()
        with get_db_session() as session:
            for idx, task_def in enumerate(task_list):
                from uuid import uuid4

                task_id = uuid4()
                title = str(task_def.get("title") or f"Task {idx + 1}")
                title_to_id[title] = task_id

                owner_role_key = self._normalize_role_key(
                    task_def.get("owner_role")
                    or task_def.get("role_key")
                    or task_def.get("role")
                    or ""
                )
                role_context = role_assignments.get(owner_role_key, {})

                assigned_agent_id: Optional[UUID] = None
                assigned_agent_raw = str(task_def.get("assigned_agent_id") or "").strip()
                if assigned_agent_raw and assigned_agent_raw in agent_id_map:
                    assigned_agent_id = agent_id_map[assigned_agent_raw].agent_id
                elif role_context.get("assigned_agent_id"):
                    role_agent_id = str(role_context.get("assigned_agent_id"))
                    if role_agent_id in agent_id_map:
                        assigned_agent_id = agent_id_map[role_agent_id].agent_id

                if assigned_agent_id:
                    used_agent_ids.add(assigned_agent_id)

                role_required_capabilities = self._coerce_string_list(
                    role_context.get("required_capabilities")
                )
                role_memory_scopes = self._coerce_string_list(role_context.get("memory_scopes"))
                role_knowledge_collections = self._coerce_string_list(
                    role_context.get("knowledge_collection_ids")
                )
                role_sop_hint = str(role_context.get("sop_hint") or "").strip()
                dependency_titles = self._coerce_string_list(task_def.get("dependencies"))

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
                        "dependencies": dependency_titles,
                        "owner_role": owner_role_key or None,
                        "owner_role_name": role_context.get("role_name"),
                        "role_required_capabilities": role_required_capabilities,
                        "role_memory_scopes": role_memory_scopes,
                        "role_knowledge_collections": role_knowledge_collections,
                        "role_sop_hint": role_sop_hint,
                        "assigned_agent_name": (
                            agent_id_map[str(assigned_agent_id)].name
                            if assigned_agent_id and str(assigned_agent_id) in agent_id_map
                            else None
                        ),
                    },
                )
                session.add(task)

            session.flush()

            # Resolve dependency title references to task_id arrays
            tasks_in_session = session.query(Task).filter(Task.mission_id == mission_id).all()
            for t in tasks_in_session:
                dep_titles = (t.task_metadata or {}).get("dependencies", [])
                dep_ids = [str(title_to_id[dt]) for dt in dep_titles if dt in title_to_id]
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
        for title, tid in title_to_id.items():
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_DECOMPOSED",
                task_id=tid,
                data={"title": title},
                message=f"Task created: {title}",
            )

        # Save plan to workspace
        self._workspace.write_file(
            mission_id, "shared/task_plan.json", json.dumps(task_list, indent=2)
        )
        if role_assignments:
            self._workspace.write_file(
                mission_id,
                "shared/team_blueprint.json",
                json.dumps(
                    {
                        "team_blueprint": list(role_assignments.values()),
                        "tasks": task_list,
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
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _execute_single(task_obj: Any) -> None:
            async with semaphore:
                # Wait for dependencies to complete
                dep_ids = task_obj.dependencies or []
                while dep_ids:
                    with get_db_session() as session:
                        dep_statuses = {
                            str(t.task_id): t.status
                            for t in session.query(Task).filter(Task.task_id.in_(dep_ids)).all()
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
                        self._emitter.emit(
                            mission_id=mission_id,
                            event_type="TASK_FAILED",
                            task_id=task_obj.task_id,
                            data={
                                "title": (task_obj.task_metadata or {}).get("title", "Untitled"),
                                "error": f"Missing dependencies: {', '.join(missing_deps)}",
                            },
                            message="Task failed due to missing dependencies",
                        )
                        return

                    failed_deps = [
                        dep_id for dep_id in dep_ids if dep_statuses.get(dep_id) == "failed"
                    ]
                    if failed_deps:
                        with get_db_session() as session:
                            t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                            if t:
                                t.status = "failed"
                                t.result = {
                                    "error": f"Blocked by failed dependencies: {', '.join(failed_deps)}"
                                }
                        self._emitter.emit(
                            mission_id=mission_id,
                            event_type="TASK_FAILED",
                            task_id=task_obj.task_id,
                            data={
                                "title": (task_obj.task_metadata or {}).get("title", "Untitled"),
                                "error": (
                                    "Blocked by failed dependencies: " f"{', '.join(failed_deps)}"
                                ),
                            },
                            message="Task failed due to failed dependencies",
                        )
                        return

                    all_done = all(dep_statuses.get(dep_id) == "completed" for dep_id in dep_ids)
                    if all_done:
                        break
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

        # Update mission counters based on actual DB task statuses
        update_mission_fields(
            mission_id,
            total_tasks=max(mission.total_tasks, total_count),
            completed_tasks=completed_count,
            failed_tasks=failed_count,
        )

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
        task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
        task_metadata = (
            task_obj.task_metadata if isinstance(task_obj.task_metadata, dict) else {}
        )
        review_feedback_raw = task_metadata.get("review_feedback")
        review_feedback = (
            review_feedback_raw.strip() if isinstance(review_feedback_raw, str) else ""
        )
        review_cycle = self._coerce_int(task_metadata.get("review_cycle_count", 0), 0)
        if len(review_feedback) > 4000:
            review_feedback = review_feedback[:4000] + "\n...[truncated]"
        resolved_agent_id: Optional[UUID] = getattr(task_obj, "assigned_agent_id", None)
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

        if resolved_agent_id is None and prefer_existing_agents:
            selected_platform = self._select_platform_agent_for_task(
                task_obj=task_obj,
                available_agents=available_platform_agents or [],
            )

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
                            t.task_metadata = meta

                    local_meta = dict(task_obj.task_metadata or {})
                    local_meta["assigned_agent_name"] = selected_platform["agent_name"]
                    local_meta["assigned_agent_temporary"] = False
                    local_meta["assignment_source"] = "platform_auto_match"
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
            self._emitter.emit(
                mission_id=mission_id,
                event_type="TASK_FAILED",
                task_id=task_obj.task_id,
                data={
                    "title": task_title,
                    "error": no_agent_error,
                    "prefer_existing_agents": prefer_existing_agents,
                    "allow_temporary_workers": allow_temporary_workers,
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
                role_context = (
                    str(task_metadata.get("owner_role_name") or task_metadata.get("owner_role") or "")
                    .strip()
                )
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
                    f"{review_feedback_section}"
                    "Produce the deliverable and confirm completion."
                )

                result = await self._execute_agent_task(agent, task_prompt)
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
                        t.completed_at = datetime.utcnow()

                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="TASK_COMPLETED",
                    task_id=task_obj.task_id,
                    data={"title": task_title},
                    message=f"Task completed: {task_title}",
                )
                update_mission_agent_status(
                    mission_id=mission_id,
                    agent_id=resolved_agent_id,
                    status="idle",
                )
                return True

            except Exception as exc:
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
                        "traceback": trace,
                    },
                    message=(f"Task attempt {attempt + 1}/{total_attempts} failed: {task_title}"),
                )

                if attempt < max_retries:
                    assert backoff is not None
                    await asyncio.sleep(backoff)
                else:
                    # Final failure
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
        for task_obj in task_data:
            task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
            if task_obj.status != "completed":
                failed_tasks.append(task_obj.task_id)
                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        t.status = "failed"
                        meta = dict(t.task_metadata or {})
                        review_cycle = self._coerce_int(meta.get("review_cycle_count", 0), 0) + 1
                        meta["review_cycle_count"] = review_cycle
                        meta["review_feedback"] = (
                            f"Task status is '{task_obj.status}', expected 'completed' before review."
                        )
                        t.task_metadata = meta
                        t.completed_at = None

                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="TASK_REVIEWED",
                    task_id=task_obj.task_id,
                    data={
                        "title": task_title,
                        "verdict": "FAIL",
                        "reason": "task_not_completed",
                    },
                    message=f"Task review: {task_title} -> FAIL (task not completed)",
                )
                continue

            task_output = (task_obj.result or {}).get("output", "No output")

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
                failed_tasks.append(task_obj.task_id)
                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        t.status = "failed"
                        meta = dict(t.task_metadata or {})
                        review_cycle = self._coerce_int(meta.get("review_cycle_count", 0), 0) + 1
                        meta["review_cycle_count"] = review_cycle
                        meta["review_feedback"] = review_output
                        t.task_metadata = meta
                        t.completed_at = None

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

        verdict = self._extract_binary_verdict(qa_output)

        self._emitter.emit(
            mission_id=mission_id,
            event_type="QA_VERDICT",
            data={"verdict": verdict},
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
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="QA_CYCLE_RETRY",
                    data={"cycle": qa_cycle, "max_qa_cycles": max_qa_cycles},
                    message="QA failed, routing back to review",
                )
                # Transition back to reviewing is handled in _phase_review.
                await self._phase_review(mission_id)
                await self._phase_qa(mission_id)
                return
            raise MissionError(
                mission_id,
                (
                    f"QA audit failed after {qa_cycle} cycle(s); configured max_qa_cycles="
                    f"{max_qa_cycles}"
                ),
            )

        # Save QA report to workspace
        self._workspace.write_file(mission_id, "shared/qa_report.md", qa_output)

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
    def _get_task_status_counts(mission_id: UUID) -> Dict[str, int]:
        """Get per-status task counts for a mission."""
        from database.connection import get_db_session
        from database.models import Task

        with get_db_session() as session:
            statuses = session.query(Task.status).filter(Task.mission_id == mission_id).all()
        counter = Counter(status for (status,) in statuses)
        return dict(counter)

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
