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
            logger.exception("Mission %s failed: %s", mission_id, exc)
            self._snapshot_deliverables(mission_id)
            update_mission_status(mission_id, "failed", error_message=str(exc))
            self._emitter.emit(
                mission_id=mission_id,
                event_type="MISSION_FAILED",
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
        cfg = mission.mission_config or {}
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
        cfg = mission.mission_config or {}
        exec_cfg = cfg.get("execution_config", {})
        if not isinstance(exec_cfg, dict):
            exec_cfg = {}

        merged = dict(exec_cfg)
        for key in ("max_retries", "task_timeout_s", "max_rework_cycles", "max_concurrent_tasks"):
            if key in cfg:
                merged[key] = cfg[key]
        if "network_access" in cfg:
            merged["network_access"] = cfg["network_access"]
        elif "network_access" not in merged and "network_enabled" in cfg:
            merged["network_access"] = bool(cfg["network_enabled"])
        return merged

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
        registry = AgentRegistry()
        temp_agent = registry.register_agent(
            name=self._build_temporary_agent_name(task_title, task_obj.task_id),
            agent_type="mission_temp_worker",
            owner_user_id=mission.created_by_user_id,
            capabilities=["mission_execution", "task_specialist"],
            llm_provider=llm_cfg.get("llm_provider"),
            llm_model=llm_cfg.get("llm_model"),
            temperature=float(llm_cfg.get("temperature", 0.7)),
            max_tokens=int(llm_cfg.get("max_tokens", 4096)),
            access_level="private",
            system_prompt=(
                "You are a temporary specialist worker spawned for a mission task. "
                "Focus on completing the assigned task and producing concrete artifacts."
            ),
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
                task.task_metadata = metadata

        task_obj.assigned_agent_id = temp_agent.agent_id
        task_metadata = dict(task_obj.task_metadata or {})
        task_metadata["assigned_agent_name"] = temp_agent.name
        task_metadata["assigned_agent_temporary"] = True
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
            },
            message=f"Temporary worker assigned: {temp_agent.name}",
        )
        return temp_agent.agent_id

    @staticmethod
    async def _execute_agent_task(agent: Any, prompt: str) -> Dict[str, Any]:
        """Run blocking agent calls in a worker thread so the event loop stays responsive."""
        return await asyncio.to_thread(agent.execute_task, prompt)

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

        result = await self._execute_agent_task(leader, task_prompt)
        output = result.get("output", "")

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
            result = await self._execute_agent_task(leader, followup_prompt)
            output = result.get("output", "")

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
        assignment_instruction = (
            "For each task, include `assigned_agent_id` using one of the provided agent IDs. "
            "If no good match exists, set it to an empty string so the runtime can spawn a "
            "temporary specialist worker."
            if available_agents
            else "Set `assigned_agent_id` to an empty string for each task."
        )
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

        result = await self._execute_agent_task(leader, task_prompt)
        output = result.get("output", "")

        # Parse JSON task list from agent output
        task_list = self._extract_json_array(output)
        if not task_list:
            raise MissionError(
                mission_id,
                "Leader failed to produce a valid task plan",
            )

        # Store tasks in DB
        from database.connection import get_db_session
        from database.models import Task

        title_to_id: Dict[str, UUID] = {}
        used_agent_ids: set[UUID] = set()
        with get_db_session() as session:
            for idx, task_def in enumerate(task_list):
                from uuid import uuid4

                task_id = uuid4()
                title = task_def.get("title", f"Task {idx + 1}")
                title_to_id[title] = task_id

                assigned_agent_id: Optional[UUID] = None
                assigned_agent_raw = str(task_def.get("assigned_agent_id") or "").strip()
                if assigned_agent_raw and assigned_agent_raw in agent_id_map:
                    assigned_agent_id = agent_id_map[assigned_agent_raw].agent_id

                if assigned_agent_id:
                    used_agent_ids.add(assigned_agent_id)

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
                        "dependencies": task_def.get("dependencies", []),
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

        self._emitter.emit(
            mission_id=mission_id,
            event_type="PHASE_COMPLETED",
            data={"phase": "planning", "task_count": len(task_list)},
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

        # Fetch pending/failed tasks for this mission
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
        max_concurrent = int(exec_cfg.get("max_concurrent_tasks", 3))
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
                                    "Blocked by failed dependencies: "
                                    f"{', '.join(failed_deps)}"
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
                    max_retries=int(exec_cfg.get("max_retries", 2)),
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
    ) -> bool:
        """Execute a single task with exponential backoff retry.

        Returns True on success, False on failure.
        """
        llm_cfg = self._get_llm_config(mission, "temporary_worker")
        task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
        resolved_agent_id: Optional[UUID] = getattr(task_obj, "assigned_agent_id", None)
        agent = None

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

        if resolved_agent_id is None:
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

                task_prompt = (
                    f"Execute the following task:\n\n"
                    f"## Task: {task_title}\n"
                    f"## Instructions\n{task_obj.goal_text}\n\n"
                    f"## Acceptance Criteria\n{task_obj.acceptance_criteria or 'None specified'}\n\n"
                    "Produce the deliverable and confirm completion."
                )

                result = await self._execute_agent_task(agent, task_prompt)
                output = result.get("output", "")

                # Mark task completed
                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        t.status = "completed"
                        t.result = {"output": output}
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
                logger.warning(
                    "Task %s attempt %d failed: %s",
                    task_obj.task_id,
                    attempt + 1,
                    exc,
                )
                if attempt < max_retries:
                    backoff = 2**attempt
                    await asyncio.sleep(backoff)
                else:
                    # Final failure
                    with get_db_session() as session:
                        t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                        if t:
                            t.status = "failed"
                            t.result = {"error": str(exc)}

                    self._emitter.emit(
                        mission_id=mission_id,
                        event_type="TASK_FAILED",
                        task_id=task_obj.task_id,
                        data={"title": task_title, "error": str(exc)},
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

        failed_tasks: List[UUID] = []
        for task_obj in task_data:
            task_title = (task_obj.task_metadata or {}).get("title", "Untitled")
            if task_obj.status != "completed":
                failed_tasks.append(task_obj.task_id)
                with get_db_session() as session:
                    t = session.query(Task).filter(Task.task_id == task_obj.task_id).first()
                    if t:
                        t.status = "failed"
                        meta = t.task_metadata or {}
                        review_cycle = int(meta.get("review_cycle_count", 0)) + 1
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

            result = await self._execute_agent_task(supervisor, review_prompt)
            review_output = result.get("output", "")

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
                        meta = t.task_metadata or {}
                        review_cycle = meta.get("review_cycle_count", 0) + 1
                        meta["review_cycle_count"] = review_cycle
                        meta["review_feedback"] = review_output
                        t.task_metadata = meta
                        t.completed_at = None

        exec_cfg = self._get_execution_config(mission)
        configured_max_rework_cycles = int(
            exec_cfg.get("max_rework_cycles", MAX_REVIEW_CYCLES)
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
                        cycle = (t.task_metadata or {}).get("review_cycle_count", 0)
                        max_cycle = max(max_cycle, cycle)

            if max_cycle <= max_rework_cycles:
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="REVIEW_CYCLE_RETRY",
                    data={"failed_count": len(failed_tasks), "cycle": max_cycle},
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

        result = await self._execute_agent_task(qa_agent, audit_prompt)
        qa_output = result.get("output", "")

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
            qa_cycle = int(cfg.get("qa_cycle_count", 0)) + 1

            # Persist cycle count for observability and retry tracking
            update_mission_fields(
                mission_id,
                mission_config={**(mission.mission_config or {}), "qa_cycle_count": qa_cycle},
            )
            if qa_cycle <= MAX_QA_CYCLES:
                self._emitter.emit(
                    mission_id=mission_id,
                    event_type="QA_CYCLE_RETRY",
                    data={"cycle": qa_cycle},
                    message="QA failed, routing back to review",
                )
                # Transition back to reviewing is handled in _phase_review.
                await self._phase_review(mission_id)
                await self._phase_qa(mission_id)
                return
            raise MissionError(
                mission_id,
                f"QA audit failed after {qa_cycle} cycle(s)",
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
        try:
            self._workspace.cleanup_workspace(mission_id)
        except Exception:
            logger.exception("Workspace cleanup failed for mission %s", mission_id)


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
