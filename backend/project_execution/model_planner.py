from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from database.connection import get_db_session
from llm_providers.db_manager import ProviderDBManager
from llm_providers.router import get_llm_provider
from project_execution.planning import build_step_definitions, normalize_execution_mode
from shared.config import get_config
from shared.logging import get_logger
from shared.platform_settings import get_project_execution_settings

logger = get_logger(__name__)

_GENERATION_MODEL_TYPES = {"", "chat", "vision", "reasoning", "code"}
_DEFAULT_PLANNER_TEMPERATURE = 0.2
_DEFAULT_PLANNER_MAX_TOKENS = 4000


class PlannerClarificationQuestion(BaseModel):
    question: str = Field(..., min_length=1)
    importance: str = Field(default="important", min_length=1)


class PlannerStep(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    step_kind: str = Field(..., min_length=1)
    executor_kind: str = Field(..., min_length=1)
    execution_mode: str = Field(..., min_length=1)
    required_capabilities: list[str] = Field(default_factory=list)
    suggested_agent_ids: list[str] = Field(default_factory=list)
    acceptance: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: Optional[str] = None


class PlannerResult(BaseModel):
    summary: str = Field(..., min_length=1)
    needs_clarification: bool = False
    clarification_questions: list[PlannerClarificationQuestion] = Field(default_factory=list)
    steps: list[PlannerStep] = Field(default_factory=list)
    planner_source: str = Field(default="model", min_length=1)
    planner_provider: Optional[str] = None
    planner_model: Optional[str] = None


class ProjectExecutionPlanner:
    def __init__(self, *, allow_model_calls_in_tests: bool = False):
        self.allow_model_calls_in_tests = allow_model_calls_in_tests

    async def plan(
        self,
        *,
        title: str,
        description: Optional[str],
        execution_mode: str,
        project_context: Optional[dict[str, Any]] = None,
        available_agents: Optional[list[dict[str, Any]]] = None,
    ) -> PlannerResult:
        normalized_execution_mode = normalize_execution_mode(execution_mode)
        provider_name, model_name, temperature, max_tokens = self._resolve_planner_target()

        if os.environ.get("PYTEST_CURRENT_TEST") and not self.allow_model_calls_in_tests:
            return self._build_fallback_result(
                title=title,
                description=description,
                execution_mode=normalized_execution_mode,
                planner_provider=provider_name,
                planner_model=model_name,
            )

        if not provider_name or not model_name:
            return self._build_fallback_result(
                title=title,
                description=description,
                execution_mode=normalized_execution_mode,
                planner_provider=provider_name,
                planner_model=model_name,
            )

        prompt = self._build_planner_prompt(
            title=title,
            description=description,
            execution_mode=normalized_execution_mode,
            project_context=project_context or {},
            available_agents=available_agents or [],
        )

        try:
            llm_router = get_llm_provider()
            response = await llm_router.generate(
                prompt=prompt,
                provider=provider_name,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            parsed = self._parse_model_response(
                content=str(response.content or ""),
                execution_mode=normalized_execution_mode,
                available_agents=available_agents or [],
                planner_provider=provider_name,
                planner_model=model_name,
            )
            return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Project execution planner model call failed; falling back to heuristic planner",
                extra={
                    "error": str(exc),
                    "planner_provider": provider_name,
                    "planner_model": model_name,
                },
            )
            return self._build_fallback_result(
                title=title,
                description=description,
                execution_mode=normalized_execution_mode,
                planner_provider=provider_name,
                planner_model=model_name,
            )

    def _resolve_planner_target(self) -> tuple[Optional[str], Optional[str], float, int]:
        with get_db_session() as session:
            settings = get_project_execution_settings(session)

        planner_provider = str(settings.get("planner_provider") or "").strip()
        planner_model = str(settings.get("planner_model") or "").strip()
        planner_temperature = float(
            settings.get("planner_temperature", _DEFAULT_PLANNER_TEMPERATURE)
        )
        planner_max_tokens = int(settings.get("planner_max_tokens", _DEFAULT_PLANNER_MAX_TOKENS))

        if planner_provider and planner_model:
            return planner_provider, planner_model, planner_temperature, planner_max_tokens

        config = get_config()
        fallback_provider = planner_provider or str(config.get("llm.default_provider") or "").strip()
        if not fallback_provider:
            return None, None, planner_temperature, planner_max_tokens

        fallback_model = planner_model or self._resolve_default_generation_model(fallback_provider)
        if not fallback_model:
            return fallback_provider, None, planner_temperature, planner_max_tokens

        return fallback_provider, fallback_model, planner_temperature, planner_max_tokens

    def _resolve_default_generation_model(self, provider_name: str) -> Optional[str]:
        with get_db_session() as session:
            db_manager = ProviderDBManager(session)
            provider = db_manager.get_provider(provider_name)
            if provider and provider.enabled:
                metadata_map = provider.model_metadata or {}
                for model_name in provider.models or []:
                    raw_metadata = metadata_map.get(model_name) if isinstance(metadata_map, dict) else None
                    model_type = str((raw_metadata or {}).get("model_type") or "").strip().lower()
                    if model_type in _GENERATION_MODEL_TYPES:
                        return model_name
                if provider.models:
                    return str(provider.models[0]).strip() or None

        llm_config = get_config().get_section("llm") or {}
        provider_cfg = ((llm_config.get("providers") or {}).get(provider_name) or {})
        models_cfg = provider_cfg.get("models") or {}
        if isinstance(models_cfg, dict):
            for key in ("chat", "code", "summarization", "translation"):
                candidate = str(models_cfg.get(key) or "").strip()
                if candidate:
                    return candidate
            for candidate in models_cfg.values():
                normalized = str(candidate or "").strip()
                if normalized:
                    return normalized
        elif isinstance(models_cfg, list):
            for candidate in models_cfg:
                normalized = str(candidate or "").strip()
                if normalized:
                    return normalized
        elif isinstance(models_cfg, str):
            return models_cfg.strip() or None

        return None

    def _build_planner_prompt(
        self,
        *,
        title: str,
        description: Optional[str],
        execution_mode: str,
        project_context: dict[str, Any],
        available_agents: list[dict[str, Any]],
    ) -> str:
        return f"""
You are the Project Execution planner for LinX.

Generate a strict JSON plan for the task below.

Rules:
- If execution_mode is "project_sandbox", every step must use execution_mode "project_sandbox" and executor_kind "agent". Do not emit host_action or external_runtime steps.
- If execution_mode is "external_runtime", you may emit host_action or external_runtime steps.
- If execution_mode is "auto", choose the best mode per step.
- Use suggested_agent_ids only from the provided available_agents list.
- For complex tasks, decompose into multiple steps with explicit dependencies and parallel groups when appropriate.
- If the task is too ambiguous to execute safely, set needs_clarification=true and return clarification_questions instead of executable steps.
- Return JSON only. No markdown, no prose outside JSON.

Output schema:
{{
  "summary": "string",
  "needs_clarification": false,
  "clarification_questions": [{{"question": "string", "importance": "critical|important|optional"}}],
  "steps": [
    {{
      "id": "step_id",
      "name": "string",
      "step_kind": "research|writing|implementation|review|qa|ops|host_action",
      "executor_kind": "agent|execution_node",
      "execution_mode": "project_sandbox|external_runtime",
      "required_capabilities": ["string"],
      "suggested_agent_ids": ["uuid"],
      "acceptance": "string",
      "depends_on": ["step_id"],
      "parallel_group": "string|null"
    }}
  ]
}}

Task title:
{title}

Task description:
{description or ""}

Execution mode:
{execution_mode}

Project context:
{json.dumps(project_context, ensure_ascii=False)}

Available agents:
{json.dumps(available_agents, ensure_ascii=False)}
""".strip()

    def _parse_model_response(
        self,
        *,
        content: str,
        execution_mode: str,
        available_agents: list[dict[str, Any]],
        planner_provider: str,
        planner_model: str,
    ) -> PlannerResult:
        payload = self._extract_json_payload(content)
        try:
            result = PlannerResult.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"planner_response_validation_failed: {exc}") from exc

        normalized = self._normalize_result(
            result,
            execution_mode=execution_mode,
            allowed_agent_ids={str(agent.get("id")) for agent in available_agents},
            planner_provider=planner_provider,
            planner_model=planner_model,
        )
        if not normalized.needs_clarification and not normalized.steps:
            raise ValueError("planner_response_missing_steps")
        return normalized

    @staticmethod
    def _extract_json_payload(content: str) -> dict[str, Any]:
        raw = str(content or "").strip()
        if not raw:
            raise ValueError("empty_planner_response")

        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if fence_match:
            raw = fence_match.group(1).strip()
        else:
            object_match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if object_match:
                raw = object_match.group(1).strip()

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("planner_response_not_object")
        return parsed

    def _normalize_result(
        self,
        result: PlannerResult,
        *,
        execution_mode: str,
        allowed_agent_ids: set[str],
        planner_provider: str,
        planner_model: str,
    ) -> PlannerResult:
        seen_step_ids: set[str] = set()
        normalized_steps: list[PlannerStep] = []
        fallback_group_counter: defaultdict[str, int] = defaultdict(int)

        for index, step in enumerate(result.steps, start=1):
            step_id = str(step.id or f"step_{index}").strip()
            if not step_id or step_id in seen_step_ids:
                step_id = f"step_{index}"
            seen_step_ids.add(step_id)

            step_execution_mode = normalize_execution_mode(step.execution_mode)
            if execution_mode == "project_sandbox":
                step_execution_mode = "project_sandbox"

            step_kind = str(step.step_kind or "implementation").strip().lower()
            executor_kind = str(step.executor_kind or "agent").strip().lower()
            if step_execution_mode == "project_sandbox":
                if step_kind == "host_action":
                    step_kind = "implementation"
                executor_kind = "agent"
            elif step_kind == "host_action":
                executor_kind = "execution_node"

            suggested_agent_ids = [
                agent_id
                for agent_id in [str(agent_id).strip() for agent_id in step.suggested_agent_ids]
                if agent_id and agent_id in allowed_agent_ids
            ]
            depends_on = [
                dependency
                for dependency in [str(dependency).strip() for dependency in step.depends_on]
                if dependency and dependency != step_id
            ]
            parallel_group = str(step.parallel_group or "").strip() or None
            if parallel_group:
                fallback_group_counter[parallel_group] += 1

            normalized_steps.append(
                PlannerStep(
                    id=step_id,
                    name=str(step.name or step_id).strip() or step_id,
                    step_kind=step_kind,
                    executor_kind=executor_kind,
                    execution_mode=step_execution_mode,
                    required_capabilities=[
                        str(capability).strip()
                        for capability in step.required_capabilities
                        if str(capability).strip()
                    ],
                    suggested_agent_ids=suggested_agent_ids,
                    acceptance=str(step.acceptance or "").strip() or None,
                    depends_on=depends_on,
                    parallel_group=parallel_group,
                )
            )

        valid_step_ids = {step.id for step in normalized_steps}
        normalized_steps = [
            step.model_copy(update={"depends_on": [dep for dep in step.depends_on if dep in valid_step_ids]})
            for step in normalized_steps
        ]

        clarification_questions = result.clarification_questions
        if result.needs_clarification and not clarification_questions:
            clarification_questions = [
                PlannerClarificationQuestion(
                    question="Please provide more detail so the planner can safely decompose this task.",
                    importance="critical",
                )
            ]

        return PlannerResult(
            summary=str(result.summary or "").strip() or "Project execution plan",
            needs_clarification=result.needs_clarification,
            clarification_questions=clarification_questions,
            steps=normalized_steps,
            planner_source="model",
            planner_provider=planner_provider,
            planner_model=planner_model,
        )

    def _build_fallback_result(
        self,
        *,
        title: str,
        description: Optional[str],
        execution_mode: str,
        planner_provider: Optional[str],
        planner_model: Optional[str],
    ) -> PlannerResult:
        heuristic_steps = build_step_definitions(
            title,
            description,
            execution_mode=execution_mode,
        )
        steps = [
            PlannerStep(
                id=f"step_{index}",
                name=str(step.get("name") or title),
                step_kind=str(step.get("step_kind") or "implementation"),
                executor_kind=str(step.get("executor_kind") or "agent"),
                execution_mode=normalize_execution_mode(str(step.get("execution_mode") or execution_mode)),
                required_capabilities=[],
                suggested_agent_ids=[],
                acceptance=None,
                depends_on=[f"step_{index - 1}"] if index > 1 else [],
                parallel_group=None,
            )
            for index, step in enumerate(heuristic_steps, start=1)
        ]
        return PlannerResult(
            summary=description or title,
            needs_clarification=False,
            clarification_questions=[],
            steps=steps,
            planner_source="fallback_heuristic",
            planner_provider=planner_provider,
            planner_model=planner_model,
        )


def build_plan_definition(result: PlannerResult) -> dict[str, Any]:
    parallel_groups: dict[str, list[str]] = defaultdict(list)
    for step in result.steps:
        if step.parallel_group:
            parallel_groups[step.parallel_group].append(step.id)

    return {
        "summary": result.summary,
        "needs_clarification": result.needs_clarification,
        "clarification_questions": [
            question.model_dump() for question in result.clarification_questions
        ],
        "steps": [step.model_dump() for step in result.steps],
        "dependencies": {step.id: step.depends_on for step in result.steps if step.depends_on},
        "parallel_groups": dict(parallel_groups),
        "planner_source": result.planner_source,
        "planner_provider": result.planner_provider,
        "planner_model": result.planner_model,
    }
