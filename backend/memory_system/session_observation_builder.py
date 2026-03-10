"""Session observation builder for extraction, normalization, and ledger projections."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agent_framework.agent_registry import get_agent_registry
from memory_system.session_ledger_repository import (
    MemoryMaterializationData,
    MemoryObservationData,
    MemorySessionEventData,
)
from shared.logging import get_logger

logger = get_logger(__name__)

_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH = 16
_SESSION_MEMORY_ITEM_MAX_CHARS = 320
_SESSION_MEMORY_MAX_PREFERENCE_FACTS = 12
_SESSION_MEMORY_MAX_AGENT_CANDIDATES = 4
_SESSION_MEMORY_LLM_MIN_PREFERENCE_CONFIDENCE = 0.62
_SESSION_MEMORY_LLM_MIN_AGENT_CONFIDENCE = 0.6
_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS = 14000
_SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS = 4.0
_SESSION_MEMORY_FAILURE_BACKOFF_SECONDS = 60.0
_SESSION_MEMORY_EXTRACTION_FAIL_UNTIL: Dict[str, float] = {}

_PERSISTENT_PREFERENCE_CUES = (
    "以后",
    "下次",
    "默认",
    "长期",
    "一直",
    "始终",
    "每次",
    "都按",
    "固定",
    "统一",
    "习惯",
    "from now on",
    "default",
    "always",
)
_AGENT_SOP_HINT_CUES = (
    "步骤",
    "流程",
    "sop",
    "step",
    "first",
    "then",
    "最后",
    "最后一步",
)
_BULLET_LINE_PATTERN = re.compile(
    r"^\s*(?:\d+[\.、\)]\s*|[-*•]\s*)(.+)$",
    flags=re.MULTILINE,
)
_FOOD_PREFERENCE_LIKE_PATTERNS = (
    re.compile(r"我(?:比较|更)?(?:偏)?喜欢(?:吃)?(?P<item>[^，。！？；,.!?]{1,24})"),
    re.compile(r"我爱吃(?P<item>[^，。！？；,.!?]{1,24})"),
    re.compile(r"我偏好(?P<item>[^，。！？；,.!?]{1,24})"),
)
_FOOD_PREFERENCE_AVOID_PATTERNS = (
    re.compile(r"我(?:不吃|不喜欢吃|忌口)(?P<item>[^，。！？；,.!?]{1,24})"),
    re.compile(r"我(?:对)?(?P<item>[^，。！？；,.!?]{1,24})过敏"),
)
_PREFERENCE_ITEM_TRAILING_CLEAN_PATTERN = re.compile(
    r"(?:怎么做|怎么弄|咋做|如何做|做法|怎么制作|如何制作).*$",
    flags=re.IGNORECASE,
)


def _to_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class SessionObservationBuilder:
    """Canonical session-memory extraction and projection builder."""

    @staticmethod
    def normalize_text(text: Any, max_chars: int = _SESSION_MEMORY_ITEM_MAX_CHARS) -> str:
        normalized = " ".join(str(text or "").split()).strip()
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3] + "..."

    @staticmethod
    def normalize_memory_key(value: Any, max_chars: int = 64) -> Optional[str]:
        key = str(value or "").strip().lower()
        if not key:
            return None
        key = re.sub(r"[^a-z0-9_]+", "_", key)
        key = re.sub(r"_+", "_", key).strip("_")
        if not key:
            return None
        if len(key) > max_chars:
            key = key[:max_chars].rstrip("_")
        return key or None

    @staticmethod
    def coerce_confidence(value: Any, default: float = 0.7) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def parse_iso_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value

        raw = str(value or "").strip()
        if not raw:
            return None

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    @classmethod
    def extract_json_object_from_text(cls, text: str) -> Optional[Dict[str, Any]]:
        parsed, _ = cls.extract_json_object_from_text_with_meta(text)
        return parsed

    @classmethod
    def extract_json_object_from_text_with_meta(
        cls,
        text: str,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        raw = str(text or "")
        stripped = raw.strip()
        metadata: Dict[str, Any] = {
            "parse_status": "empty_response",
            "parse_source": None,
            "json_root_type": None,
            "parse_error": None,
            "raw_content_chars": len(raw),
        }
        if not stripped:
            return None, metadata

        candidates: List[Tuple[str, str]] = []
        seen_candidates: set[str] = set()

        def _add_candidate(source: str, candidate: str) -> None:
            normalized_candidate = str(candidate or "").strip()
            if not normalized_candidate or normalized_candidate in seen_candidates:
                return
            seen_candidates.add(normalized_candidate)
            candidates.append((source, normalized_candidate))

        _add_candidate("raw", stripped)

        block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw, flags=re.IGNORECASE)
        if block_match:
            _add_candidate("code_fence", block_match.group(1))

        left = raw.find("{")
        right = raw.rfind("}")
        if left >= 0 and right > left:
            _add_candidate("brace_slice", raw[left : right + 1])

        first_non_object_root: Optional[str] = None
        parse_errors: List[str] = []
        for source, candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception as e:
                parse_errors.append(f"{source}:{cls.normalize_text(str(e), max_chars=96)}")
                continue

            if isinstance(parsed, dict):
                metadata.update(
                    {
                        "parse_status": "ok",
                        "parse_source": source,
                        "json_root_type": "object",
                    }
                )
                return parsed, metadata

            if not first_non_object_root:
                first_non_object_root = type(parsed).__name__

        if first_non_object_root:
            metadata.update(
                {
                    "parse_status": "json_not_object",
                    "json_root_type": first_non_object_root,
                }
            )
        else:
            metadata.update({"parse_status": "json_parse_failed"})

        if parse_errors:
            metadata["parse_error"] = cls.normalize_text("; ".join(parse_errors), max_chars=240)
        return None, metadata

    @staticmethod
    def contains_persistent_preference_cue(text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return False
        return any(cue in lowered for cue in _PERSISTENT_PREFERENCE_CUES)

    @staticmethod
    def detect_output_format_preference(text: str) -> Optional[str]:
        lowered = str(text or "").lower()
        if not lowered:
            return None
        if "markdown" in lowered or "md文档" in lowered or re.search(r"\bmd\b", lowered):
            return "markdown"
        if "pdf" in lowered:
            return "pdf"
        if "docx" in lowered or "word" in lowered or "word文档" in lowered:
            return "word"
        if "excel" in lowered or "xlsx" in lowered:
            return "excel"
        if "ppt" in lowered or "pptx" in lowered:
            return "ppt"
        if "json" in lowered:
            return "json"
        if "html" in lowered:
            return "html"
        if "表格" in lowered:
            return "table"
        return None

    @staticmethod
    def detect_language_preference(text: str) -> Optional[str]:
        lowered = str(text or "").lower()
        if not lowered:
            return None

        zh = ("中文" in lowered) or ("简体" in lowered) or ("zh-cn" in lowered)
        en = ("英文" in lowered) or ("english" in lowered) or ("en-us" in lowered)
        if zh and en:
            return "bilingual"
        if zh:
            return "zh-CN"
        if en:
            return "en-US"
        return None

    @staticmethod
    def detect_response_style_preference(text: str) -> Optional[str]:
        lowered = str(text or "").lower()
        if not lowered:
            return None
        if "简洁" in lowered or "简短" in lowered or "精简" in lowered:
            return "concise"
        if "详细" in lowered or "全面" in lowered:
            return "detailed"
        if "分步骤" in lowered or "step by step" in lowered:
            return "step_by_step"
        if "要点" in lowered:
            return "bullet_points"
        if "正式" in lowered:
            return "formal"
        return None

    @classmethod
    def _normalize_preference_item(cls, value: str, max_chars: int = 24) -> Optional[str]:
        item = str(value or "").strip()
        if not item:
            return None

        item = _PREFERENCE_ITEM_TRAILING_CLEAN_PATTERN.sub("", item).strip()
        item = re.sub(r"^[：:，,\s]+", "", item)
        item = re.sub(r"[，,。！？!?；;\s]+$", "", item)
        item = " ".join(item.split())
        if not item:
            return None
        if len(item) > max_chars:
            return None
        if item in {"什么", "啥", "一下", "一点"}:
            return None
        return item

    @classmethod
    def detect_food_preference_signal(cls, text: str) -> Optional[Tuple[str, str]]:
        message = str(text or "").strip()
        if not message:
            return None

        for pattern in _FOOD_PREFERENCE_AVOID_PATTERNS:
            match = pattern.search(message)
            if not match:
                continue
            item = cls._normalize_preference_item(match.group("item"))
            if item:
                return "food_preference_avoid", item

        for pattern in _FOOD_PREFERENCE_LIKE_PATTERNS:
            match = pattern.search(message)
            if not match:
                continue
            item = cls._normalize_preference_item(match.group("item"))
            if item:
                return "food_preference_like", item

        return None

    @staticmethod
    def _resolve_provider_default_chat_model_from_config(
        config: Any,
        provider_name: Optional[str],
    ) -> Optional[str]:
        if not config or not provider_name:
            return None

        raw_models = config.get(f"llm.providers.{provider_name}.models")
        if isinstance(raw_models, dict):
            for preferred_key in ("chat", "default", "completion", "instruct"):
                candidate = str(raw_models.get(preferred_key) or "").strip()
                if candidate:
                    return candidate
            for value in raw_models.values():
                candidate = str(value or "").strip()
                if candidate:
                    return candidate
            return None

        if isinstance(raw_models, list):
            for value in raw_models:
                candidate = str(value or "").strip()
                if candidate:
                    return candidate
            return None

        candidate = str(raw_models or "").strip()
        return candidate or None

    def build_llm_memory_extraction_prompt(
        self,
        turns: List[Dict[str, str]],
        agent_name: str,
    ) -> Tuple[str, Dict[int, Optional[str]]]:
        selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
        lines: List[str] = []
        turn_ts_map: Dict[int, Optional[str]] = {}

        for idx, turn in enumerate(selected_turns, start=1):
            user_text = self.normalize_text(turn.get("user_message", ""), max_chars=520)
            agent_text = self.normalize_text(turn.get("agent_response", ""), max_chars=760)
            timestamp = str(turn.get("timestamp") or "").strip() or None
            turn_ts_map[idx] = timestamp
            lines.append(
                "\n".join(
                    [
                        f"[TURN {idx}] timestamp={timestamp or '-'}",
                        f"USER: {user_text or '-'}",
                        f"ASSISTANT: {agent_text or '-'}",
                    ]
                )
            )

        transcript = "\n\n".join(lines)
        if len(transcript) > _SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:
            transcript = transcript[-_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:]

        prompt = f"""
你是“会话记忆抽取器”。你要从会话中提取高价值、可长期复用的记忆。输出必须是 JSON 对象，不要输出解释文字。

Agent 名称: {agent_name or "-"}

抽取目标:
1. user_preferences: 提取“用户画像事实”，不仅限于喜欢/不喜欢。
2. agent_memory_candidates: 提取“做事成功路径经验 / 可沉淀为 skill 的方法模板”（后续人工审批）。

user_preferences 可包含的画像要素（示例）:
- 偏好/禁忌: food_preference_like, food_preference_avoid, communication_style_preference
- 经历/背景: experience_*
- 能力/擅长: skill_*, capability_*
- 长期目标: goal_*
- 稳定约束: allergy_*, constraint_*, budget_preference_*
- 习惯/决策方式: habit_*, decision_style_*

强约束:
- 只保留“未来任务仍有帮助”的稳定事实；一次性临时诉求不提取。
- 禁止猜测和延伸推断，只能提取用户明确说过的信息。
- 若单次会话出现多条有效画像事实，必须全部提取，不要只保留 1 条。
- key 使用英文 snake_case；value 简短明确。
- 如无有效项，返回空数组。

高优先级规则:
- 对用户直接陈述（如“我喜欢X/我做过X/我擅长X/我不吃X/我过敏X/我通常预算X”）优先提取。
- 这类直接陈述建议 explicit_source=true，confidence >= 0.82。

agent_memory_candidates 规则:
- 重点提取“最终成功的做事路径”，尤其是经历过多次尝试后，最后真正走通的那条路径。
- 目标是让 agent 下次遇到相似任务时，少走弯路，优先复用成功方法。
- 必须可迁移、可复用：避免绑定具体人名/地名/商品名/单次任务细节。
- summary 说明“为什么这条路径有效”；steps 只保留成功路径上的关键动作，2-5 步即可。
- avoid 用来总结应避免的弯路/失败尝试/不适用条件。
- 如果本次对话没有形成可复用的成功方法，不要提取。

输出 JSON Schema:
{{
  "user_preferences": [
    {{
      "key": "snake_case",
      "value": "简短明确",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.0,
      "reason": "为什么值得记忆",
      "evidence_turns": [1, 2]
    }}
  ],
  "agent_memory_candidates": [
    {{
      "candidate_type": "successful_path",
      "title": "成功路径标题",
      "summary": "这条路径为什么有效",
      "steps": ["步骤1", "步骤2", "步骤3"],
      "applicability": "适用场景",
      "avoid": "应避免的弯路/失败尝试/注意事项",
      "confidence": 0.0,
      "evidence_turns": [2]
    }}
  ]
}}

示例:
输入:
USER: 我喜欢骑车，做过电商运营，也擅长写SQL
ASSISTANT: 收到

输出:
{{
  "user_preferences": [
    {{
      "key": "activity_preference_like",
      "value": "骑车",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.9,
      "reason": "用户明确陈述喜欢的活动",
      "evidence_turns": [1]
    }},
    {{
      "key": "experience_background",
      "value": "做过电商运营",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.86,
      "reason": "用户明确陈述过往经历",
      "evidence_turns": [1]
    }},
    {{
      "key": "skill_strength",
      "value": "SQL",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.88,
      "reason": "用户明确陈述擅长技能",
      "evidence_turns": [1]
    }}
  ],
  "agent_memory_candidates": []
}}

会话文本:
{transcript}
""".strip()

        return prompt, turn_ts_map

    def build_llm_explicit_preference_recall_prompt(
        self,
        turns: List[Dict[str, str]],
    ) -> Tuple[str, Dict[int, Optional[str]]]:
        selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
        lines: List[str] = []
        turn_ts_map: Dict[int, Optional[str]] = {}

        for idx, turn in enumerate(selected_turns, start=1):
            user_text = self.normalize_text(turn.get("user_message", ""), max_chars=520)
            agent_text = self.normalize_text(turn.get("agent_response", ""), max_chars=420)
            timestamp = str(turn.get("timestamp") or "").strip() or None
            turn_ts_map[idx] = timestamp
            lines.append(
                "\n".join(
                    [
                        f"[TURN {idx}] timestamp={timestamp or '-'}",
                        f"USER: {user_text or '-'}",
                        f"ASSISTANT: {agent_text or '-'}",
                    ]
                )
            )

        transcript = "\n\n".join(lines)
        if len(transcript) > _SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:
            transcript = transcript[-_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:]

        prompt = f"""
你是“用户偏好补充抽取器”。你的目标是补充抽取用户明确陈述的稳定画像事实。
输出必须是 JSON 对象，不要输出解释文字。

补充抽取规则:
- 不仅抽取偏好，也可抽取经历/能力/长期目标/稳定约束/习惯（都要求用户明确陈述）。
- 可以是单轮，但必须是“用户直接表达”；禁止猜测、禁止偏好延伸。
- 一次性临时要求（如“这次导出 PDF”）不抽取。
- 同一会话若有多条有效画像事实，应全部提取。
- key 必须是英文 snake_case；value 必须简短。
- 如无有效项，返回空数组。
- 若出现明确陈述（如“我喜欢吃黄焖鸡/我擅长SQL/我做过运营”），不得漏提。

输出 JSON Schema:
{{
  "user_preferences": [
    {{
      "key": "snake_case",
      "value": "简短明确",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.0,
      "reason": "为什么值得记忆",
      "evidence_turns": [1]
    }}
  ]
}}

示例:
输入:
USER: 我喜欢吃黄焖鸡，也做过前端开发，擅长 SQL
ASSISTANT: 收到

输出:
{{
  "user_preferences": [
    {{
      "key": "food_preference_like",
      "value": "黄焖鸡",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.9,
      "reason": "用户明确陈述喜欢的食物",
      "evidence_turns": [1]
    }},
    {{
      "key": "experience_background",
      "value": "做过前端开发",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.86,
      "reason": "用户明确陈述过往经历",
      "evidence_turns": [1]
    }},
    {{
      "key": "skill_strength",
      "value": "SQL",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.88,
      "reason": "用户明确陈述擅长技能",
      "evidence_turns": [1]
    }}
  ]
}}

会话文本:
{transcript}
""".strip()

        return prompt, turn_ts_map

    @staticmethod
    def _is_response_format_not_supported_error(error: Exception) -> bool:
        message = str(error or "").lower()
        if not message:
            return False
        unsupported_cues = (
            "response_format",
            "json_object",
            "json schema",
            "unsupported",
            "unexpected keyword argument",
            "extra fields not permitted",
            "unknown field",
        )
        return any(cue in message for cue in unsupported_cues)

    @staticmethod
    def _coerce_positive_timeout_seconds(value: Any, *, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if parsed <= 0:
            return default
        return min(max(parsed, 0.5), 120.0)

    @staticmethod
    async def _invalidate_timed_out_llm_provider(
        *,
        llm_router: Any,
        provider_name: Optional[str],
    ) -> None:
        if not provider_name:
            return
        invalidate_fn = getattr(llm_router, "invalidate_provider", None)
        if not callable(invalidate_fn):
            return
        try:
            invalidated = await invalidate_fn(provider_name)
            if invalidated:
                logger.info(
                    "Session memory extraction invalidated timed-out provider cache",
                    extra={"provider": provider_name},
                )
        except Exception as e:
            logger.warning(
                "Session memory extraction failed to invalidate timed-out provider cache",
                extra={"provider": provider_name, "error": str(e)},
            )

    async def call_llm_for_memory_json(
        self,
        *,
        llm_router: Any,
        prompt: str,
        provider: Optional[str],
        model: Optional[str],
        timeout_seconds: float = _SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        base_kwargs = {
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "temperature": 0.1,
            "max_tokens": 1800,
        }

        async def _generate_and_parse(
            *,
            with_response_format: bool,
            response_mode: str,
            fallback_triggered: bool,
        ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            kwargs = dict(base_kwargs)
            if with_response_format:
                kwargs["response_format"] = {"type": "json_object"}
            try:
                response = await asyncio.wait_for(
                    llm_router.generate(**kwargs),
                    timeout=max(float(timeout_seconds), 0.5),
                )
            except asyncio.TimeoutError as timeout_error:
                await self._invalidate_timed_out_llm_provider(
                    llm_router=llm_router,
                    provider_name=provider,
                )
                raise TimeoutError(
                    f"session_memory_extraction_timeout_{max(float(timeout_seconds), 0.5):.1f}s"
                ) from timeout_error
            raw_content = str(getattr(response, "content", "") or "")
            parsed_payload, parse_meta = self.extract_json_object_from_text_with_meta(raw_content)
            parse_meta.update(
                {
                    "response_mode": response_mode,
                    "fallback_triggered": fallback_triggered,
                }
            )
            return parsed_payload or {}, parse_meta

        try:
            parsed_payload, parse_meta = await _generate_and_parse(
                with_response_format=True,
                response_mode="json_object",
                fallback_triggered=False,
            )
            if str(parse_meta.get("parse_status")) == "ok":
                return parsed_payload, parse_meta
            logger.info(
                "Session memory extraction fallback to plain response mode after non-json response",
                extra={
                    "provider": provider or "auto",
                    "model": model or "auto",
                    "parse_status": parse_meta.get("parse_status"),
                    "raw_content_chars": parse_meta.get("raw_content_chars"),
                },
            )
        except Exception as first_error:
            if not self._is_response_format_not_supported_error(first_error):
                raise
            logger.info(
                "Session memory extraction fallback to plain response mode",
                extra={
                    "provider": provider or "auto",
                    "model": model or "auto",
                    "error": str(first_error),
                },
            )

        return await _generate_and_parse(
            with_response_format=False,
            response_mode="plain_fallback",
            fallback_triggered=True,
        )

    def normalize_llm_user_preference_signals(
        self,
        raw_items: Any,
        turn_ts_map: Dict[int, Optional[str]],
        max_items: int = _SESSION_MEMORY_MAX_PREFERENCE_FACTS,
    ) -> List[Dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []

        safe_max_items = max(int(max_items or 0), 1)
        extracted: List[Dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            key = self.normalize_memory_key(raw.get("key"))
            value = self.normalize_text(raw.get("value", ""), max_chars=120)
            if not key or not value:
                continue

            confidence = self.coerce_confidence(raw.get("confidence"), default=0.72)
            if confidence < _SESSION_MEMORY_LLM_MIN_PREFERENCE_CONFIDENCE:
                continue

            evidence_turns_raw = raw.get("evidence_turns")
            evidence_turns: List[int] = []
            if isinstance(evidence_turns_raw, list):
                for item in evidence_turns_raw:
                    parsed = _to_positive_int(item)
                    if parsed and parsed not in evidence_turns:
                        evidence_turns.append(parsed)

            evidence_count = (
                len(evidence_turns)
                if evidence_turns
                else (_to_positive_int(raw.get("evidence_count")) or 1)
            )
            is_persistent = bool(raw.get("persistent"))
            explicit_source = bool(raw.get("explicit_source"))
            allow_single_turn = explicit_source or confidence >= 0.82
            if not is_persistent and evidence_count < 2 and not allow_single_turn:
                continue

            latest_turn_ts: Optional[str] = None
            for turn_idx in evidence_turns:
                candidate_ts = turn_ts_map.get(turn_idx)
                if not candidate_ts:
                    continue
                if (latest_turn_ts is None) or str(candidate_ts) > str(latest_turn_ts):
                    latest_turn_ts = str(candidate_ts)

            reason = self.normalize_text(raw.get("reason", ""), max_chars=200)
            extracted.append(
                {
                    "key": key,
                    "value": value,
                    "evidence_count": evidence_count,
                    "persistent": is_persistent,
                    "strong_signal": is_persistent,
                    "confidence": confidence,
                    "latest_ts": latest_turn_ts,
                    "reason": reason or None,
                    "explicit_source": explicit_source,
                }
            )

        extracted.sort(
            key=lambda item: (
                int(bool(item.get("persistent"))),
                float(item.get("confidence") or 0.0),
                int(item.get("evidence_count") or 0),
                str(item.get("latest_ts") or ""),
            ),
            reverse=True,
        )
        return extracted[:safe_max_items]

    @staticmethod
    def build_agent_candidate_fingerprint(topic: str, steps: List[str]) -> str:
        payload = f"{topic.strip().lower()}||{'|'.join(steps).strip().lower()}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]

    def normalize_llm_agent_candidates(
        self,
        raw_items: Any,
        *,
        agent_name: str,
        turn_ts_map: Dict[int, Optional[str]],
        max_items: int = _SESSION_MEMORY_MAX_AGENT_CANDIDATES,
    ) -> List[Dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []

        safe_max_items = max(int(max_items or 0), 1)
        candidates: List[Dict[str, Any]] = []
        seen_fingerprints: set[str] = set()

        for raw in raw_items:
            if not isinstance(raw, dict):
                continue

            title = self.normalize_text(raw.get("title", ""), max_chars=72)
            topic = self.normalize_text(raw.get("topic", ""), max_chars=72)
            summary = self.normalize_text(raw.get("summary", ""), max_chars=180)
            steps_raw = raw.get("steps")
            steps: List[str] = []
            if isinstance(steps_raw, list):
                for step in steps_raw:
                    normalized_step = self.normalize_text(step, max_chars=72)
                    if normalized_step and normalized_step not in steps:
                        steps.append(normalized_step)
            elif isinstance(steps_raw, str):
                for chunk in re.split(r"[|\n]", steps_raw):
                    normalized_step = self.normalize_text(chunk, max_chars=72)
                    if normalized_step and normalized_step not in steps:
                        steps.append(normalized_step)

            if len(steps) > 4:
                steps = steps[:4]

            if len(steps) < 2 and len(summary) < 30:
                continue

            confidence = self.coerce_confidence(raw.get("confidence"), default=0.7)
            if confidence < _SESSION_MEMORY_LLM_MIN_AGENT_CONFIDENCE:
                continue

            candidate_type = self.normalize_memory_key(raw.get("candidate_type"), max_chars=32)
            candidate_type = candidate_type or "sop"
            applicability = self.normalize_text(raw.get("applicability", ""), max_chars=140)
            avoid = self.normalize_text(raw.get("avoid", ""), max_chars=140)

            topic_for_fingerprint = topic or title or summary or "generic_sop"
            fingerprint = self.build_agent_candidate_fingerprint(topic_for_fingerprint, steps)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)

            evidence_turns_raw = raw.get("evidence_turns")
            evidence_turns: List[int] = []
            if isinstance(evidence_turns_raw, list):
                for item in evidence_turns_raw:
                    parsed = _to_positive_int(item)
                    if parsed and parsed not in evidence_turns:
                        evidence_turns.append(parsed)
            latest_turn_ts: Optional[str] = None
            for turn_idx in evidence_turns:
                candidate_ts = turn_ts_map.get(turn_idx)
                if not candidate_ts:
                    continue
                if (latest_turn_ts is None) or str(candidate_ts) > str(latest_turn_ts):
                    latest_turn_ts = str(candidate_ts)

            candidates.append(
                {
                    "candidate_type": candidate_type,
                    "topic": topic or None,
                    "title": title or None,
                    "summary": summary,
                    "steps": steps,
                    "applicability": applicability or None,
                    "avoid": avoid or None,
                    "confidence": confidence,
                    "fingerprint": fingerprint,
                    "agent_name": agent_name,
                    "latest_ts": latest_turn_ts,
                }
            )
            if len(candidates) >= safe_max_items:
                break

        return candidates

    async def extract_session_memory_signals_with_llm(
        self,
        *,
        turns: List[Dict[str, str]],
        agent_id: Any,
        agent_name: str,
        session_id: Optional[str] = None,
        agent_registry_getter=None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not turns:
            return [], []

        prompt, turn_ts_map = self.build_llm_memory_extraction_prompt(turns, agent_name)

        agent_provider_name: Optional[str] = None
        agent_model_name: Optional[str] = None
        configured_provider_name: Optional[str] = None
        configured_model_name: Optional[str] = None
        global_chat_model: Optional[str] = None
        extraction_timeout_seconds = _SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS
        failure_backoff_seconds = _SESSION_MEMORY_FAILURE_BACKOFF_SECONDS
        max_preference_facts = _SESSION_MEMORY_MAX_PREFERENCE_FACTS
        max_agent_candidates = _SESSION_MEMORY_MAX_AGENT_CANDIDATES
        cfg: Any = None
        try:
            registry = (agent_registry_getter or get_agent_registry)()
            agent_info = registry.get_agent(agent_id)
            if agent_info:
                agent_provider_name = str(agent_info.llm_provider or "").strip() or None
                agent_model_name = str(agent_info.llm_model or "").strip() or None
        except Exception:
            agent_provider_name = None
            agent_model_name = None

        try:
            from shared.config import get_config

            cfg = get_config()
            configured_provider = cfg.get("memory.enhanced_memory.fact_extraction.provider")
            configured_model = cfg.get("memory.enhanced_memory.fact_extraction.model")
            configured_chat = cfg.get("llm.model_mapping.chat")
            configured_timeout = cfg.get("memory.enhanced_memory.fact_extraction.timeout_seconds")
            configured_failure_backoff = cfg.get(
                "memory.enhanced_memory.fact_extraction.failure_backoff_seconds"
            )
            configured_max_facts = cfg.get("memory.enhanced_memory.fact_extraction.max_facts")
            configured_max_preferences = cfg.get(
                "memory.enhanced_memory.fact_extraction.max_preference_facts"
            )
            configured_max_candidates = cfg.get(
                "memory.enhanced_memory.fact_extraction.max_agent_candidates"
            )
            configured_provider_name = str(configured_provider or "").strip() or None
            configured_model_name = str(configured_model or "").strip() or None
            global_chat_model = str(configured_chat).strip() if configured_chat else None
            extraction_timeout_seconds = self._coerce_positive_timeout_seconds(
                configured_timeout,
                default=_SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS,
            )
            failure_backoff_seconds = self._coerce_positive_timeout_seconds(
                configured_failure_backoff,
                default=_SESSION_MEMORY_FAILURE_BACKOFF_SECONDS,
            )
            configured_max_facts_value = _to_positive_int(configured_max_facts)
            max_preference_facts = (
                _to_positive_int(configured_max_preferences)
                or configured_max_facts_value
                or _SESSION_MEMORY_MAX_PREFERENCE_FACTS
            )
            max_agent_candidates = (
                _to_positive_int(configured_max_candidates) or _SESSION_MEMORY_MAX_AGENT_CANDIDATES
            )
        except Exception:
            cfg = None
            configured_provider_name = None
            configured_model_name = None
            global_chat_model = None
            extraction_timeout_seconds = _SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS
            failure_backoff_seconds = _SESSION_MEMORY_FAILURE_BACKOFF_SECONDS
            max_preference_facts = _SESSION_MEMORY_MAX_PREFERENCE_FACTS
            max_agent_candidates = _SESSION_MEMORY_MAX_AGENT_CANDIDATES

        backoff_key = f"{str(agent_id)}::{str(session_id or '')}"
        current_monotonic = time.monotonic()
        backoff_until = _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL.get(backoff_key, 0.0)
        if current_monotonic < backoff_until:
            logger.info(
                "Session memory extraction skipped due to active failure backoff",
                extra={
                    "agent_id": str(agent_id),
                    "session_id": session_id,
                    "remaining_backoff_seconds": round(backoff_until - current_monotonic, 3),
                    "failure_backoff_seconds": failure_backoff_seconds,
                },
            )
            return [], []

        def _activate_failure_backoff(reason: str) -> None:
            if failure_backoff_seconds <= 0:
                return
            fail_until = time.monotonic() + max(float(failure_backoff_seconds), 0.5)
            _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL[backoff_key] = fail_until
            logger.info(
                "Session memory extraction failure backoff activated",
                extra={
                    "agent_id": str(agent_id),
                    "session_id": session_id,
                    "reason": reason,
                    "failure_backoff_seconds": failure_backoff_seconds,
                    "fail_until_monotonic": round(fail_until, 3),
                },
            )

        primary_provider = configured_provider_name or agent_provider_name
        primary_model = configured_model_name
        if not primary_model and primary_provider:
            primary_model = self._resolve_provider_default_chat_model_from_config(
                cfg, primary_provider
            )
        if not primary_model and primary_provider == agent_provider_name:
            primary_model = agent_model_name
        if not primary_model:
            primary_model = global_chat_model

        attempt_plan: List[Tuple[Optional[str], Optional[str]]] = []
        if primary_provider or primary_model:
            attempt_plan.append((primary_provider, primary_model))
        if agent_provider_name or agent_model_name:
            attempt_plan.append((agent_provider_name, agent_model_name))
        if primary_model:
            attempt_plan.append((None, primary_model))
        attempt_plan.append((None, None))

        attempts: List[Tuple[Optional[str], Optional[str]]] = []
        for candidate in attempt_plan:
            if candidate not in attempts:
                attempts.append(candidate)
        extraction_log_base = {
            "agent_id": str(agent_id),
            "session_id": session_id,
        }
        logger.info(
            "Session memory extraction attempt plan",
            extra={
                **extraction_log_base,
                "attempt_plan": [
                    {"provider": provider_name or "auto", "model": model_name or "auto"}
                    for provider_name, model_name in attempts
                ],
                "attempt_timeout_seconds": extraction_timeout_seconds,
                "failure_backoff_seconds": failure_backoff_seconds,
                "max_preference_facts": max_preference_facts,
                "max_agent_candidates": max_agent_candidates,
            },
        )

        try:
            from llm_providers.router import get_llm_provider

            llm_router = get_llm_provider()
        except Exception as e:
            logger.warning(
                "LLM-based session memory extraction failed",
                extra={**extraction_log_base, "error": str(e)},
            )
            _activate_failure_backoff("llm_router_unavailable")
            return [], []

        async def _run_extraction_with_attempts(
            extraction_prompt: str,
            phase: str,
        ) -> Tuple[
            Dict[str, Any], Optional[str], Optional[str], Optional[Exception], Dict[str, Any]
        ]:
            parsed_payload: Dict[str, Any] = {}
            used_provider: Optional[str] = None
            used_model: Optional[str] = None
            last_error: Optional[Exception] = None
            extraction_meta: Dict[str, Any] = {
                "phase": phase,
                "parse_status": "not_attempted",
                "response_mode": None,
                "fallback_triggered": False,
                "raw_content_chars": 0,
            }

            for attempt_index, (attempt_provider, attempt_model) in enumerate(attempts, start=1):
                try:
                    parsed_payload, extraction_meta = await self.call_llm_for_memory_json(
                        llm_router=llm_router,
                        prompt=extraction_prompt,
                        provider=attempt_provider,
                        model=attempt_model,
                        timeout_seconds=extraction_timeout_seconds,
                    )
                    extraction_meta = {
                        **extraction_meta,
                        "phase": phase,
                        "attempt": attempt_index,
                        "provider": attempt_provider or "auto",
                        "model": attempt_model or "auto",
                    }
                    parse_status = str(extraction_meta.get("parse_status") or "")
                    if parse_status != "ok":
                        last_error = ValueError(f"memory_json_{parse_status or 'unknown'}")
                        logger.warning(
                            "Session memory extraction response parse failed",
                            extra={
                                **extraction_log_base,
                                "phase": phase,
                                "attempt": attempt_index,
                                "provider": attempt_provider or "auto",
                                "model": attempt_model or "auto",
                                "parse_status": parse_status or "unknown",
                                "parse_source": extraction_meta.get("parse_source"),
                                "json_root_type": extraction_meta.get("json_root_type"),
                                "response_mode": extraction_meta.get("response_mode"),
                                "raw_content_chars": extraction_meta.get("raw_content_chars"),
                                "fallback_triggered": bool(
                                    extraction_meta.get("fallback_triggered")
                                ),
                                "parse_error": extraction_meta.get("parse_error"),
                            },
                        )
                        continue
                    used_provider = attempt_provider
                    used_model = attempt_model
                    if primary_provider and attempt_provider != primary_provider:
                        logger.info(
                            "Session memory extraction fallback provider succeeded",
                            extra={
                                **extraction_log_base,
                                "phase": phase,
                                "original_provider": primary_provider,
                                "attempt": attempt_index,
                                "fallback_provider": attempt_provider or "auto",
                            },
                        )
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Session memory extraction attempt failed",
                        extra={
                            **extraction_log_base,
                            "phase": phase,
                            "attempt": attempt_index,
                            "provider": attempt_provider or "auto",
                            "model": attempt_model or "auto",
                            "error": str(e),
                        },
                    )

            return parsed_payload, used_provider, used_model, last_error, extraction_meta

        parsed, used_provider, used_model, last_error, primary_extraction_meta = (
            await _run_extraction_with_attempts(prompt, "primary")
        )
        if last_error and not parsed:
            logger.warning(
                "LLM-based session memory extraction failed",
                extra={
                    **extraction_log_base,
                    "error": str(last_error),
                    "phase": primary_extraction_meta.get("phase"),
                    "parse_status": primary_extraction_meta.get("parse_status"),
                    "response_mode": primary_extraction_meta.get("response_mode"),
                    "raw_content_chars": primary_extraction_meta.get("raw_content_chars"),
                    "attempt": primary_extraction_meta.get("attempt"),
                    "provider": primary_extraction_meta.get("provider"),
                    "model": primary_extraction_meta.get("model"),
                    "parse_error": primary_extraction_meta.get("parse_error"),
                },
            )
            _activate_failure_backoff("all_attempts_failed")
            return [], []

        user_items = parsed.get("user_preferences")
        candidate_items = parsed.get("agent_memory_candidates")
        user_signals = self.normalize_llm_user_preference_signals(
            user_items,
            turn_ts_map,
            max_items=max_preference_facts,
        )
        agent_candidates = self.normalize_llm_agent_candidates(
            candidate_items,
            agent_name=agent_name,
            turn_ts_map=turn_ts_map,
            max_items=max_agent_candidates,
        )

        secondary_raw_user_preferences = 0
        secondary_normalized_user_preferences = 0
        secondary_preference_pass_used = False
        secondary_extraction_meta: Dict[str, Any] = {
            "phase": "explicit_preference_recall",
            "parse_status": "not_run",
            "response_mode": None,
            "fallback_triggered": False,
            "raw_content_chars": 0,
        }
        if not user_signals:
            secondary_preference_pass_used = True
            recall_prompt, recall_turn_ts_map = self.build_llm_explicit_preference_recall_prompt(
                turns
            )
            (
                recall_parsed,
                recall_provider,
                recall_model,
                recall_error,
                secondary_extraction_meta,
            ) = await _run_extraction_with_attempts(recall_prompt, "explicit_preference_recall")
            if recall_error and not recall_parsed:
                logger.warning(
                    "LLM explicit-preference recall extraction failed",
                    extra={
                        **extraction_log_base,
                        "error": str(recall_error),
                        "phase": secondary_extraction_meta.get("phase"),
                        "parse_status": secondary_extraction_meta.get("parse_status"),
                        "response_mode": secondary_extraction_meta.get("response_mode"),
                        "raw_content_chars": secondary_extraction_meta.get("raw_content_chars"),
                        "attempt": secondary_extraction_meta.get("attempt"),
                        "provider": secondary_extraction_meta.get("provider"),
                        "model": secondary_extraction_meta.get("model"),
                        "parse_error": secondary_extraction_meta.get("parse_error"),
                    },
                )
            else:
                recall_user_items = recall_parsed.get("user_preferences")
                secondary_raw_user_preferences = (
                    len(recall_user_items) if isinstance(recall_user_items, list) else 0
                )
                recall_signals = self.normalize_llm_user_preference_signals(
                    recall_user_items,
                    recall_turn_ts_map,
                    max_items=max_preference_facts,
                )
                secondary_normalized_user_preferences = len(recall_signals)
                if recall_signals:
                    merged_by_key: Dict[str, Dict[str, Any]] = {
                        str(item.get("key")): item for item in user_signals if item.get("key")
                    }
                    for signal in recall_signals:
                        key = str(signal.get("key") or "").strip()
                        if not key:
                            continue
                        existing = merged_by_key.get(key)
                        if not existing:
                            merged_by_key[key] = signal
                            continue
                        current_score = (
                            int(bool(signal.get("persistent"))),
                            int(bool(signal.get("explicit_source"))),
                            float(signal.get("confidence") or 0.0),
                            int(signal.get("evidence_count") or 0),
                            str(signal.get("latest_ts") or ""),
                        )
                        existing_score = (
                            int(bool(existing.get("persistent"))),
                            int(bool(existing.get("explicit_source"))),
                            float(existing.get("confidence") or 0.0),
                            int(existing.get("evidence_count") or 0),
                            str(existing.get("latest_ts") or ""),
                        )
                        if current_score >= existing_score:
                            merged_by_key[key] = signal
                    user_signals = sorted(
                        merged_by_key.values(),
                        key=lambda item: (
                            int(bool(item.get("persistent"))),
                            int(bool(item.get("explicit_source"))),
                            float(item.get("confidence") or 0.0),
                            int(item.get("evidence_count") or 0),
                            str(item.get("latest_ts") or ""),
                        ),
                        reverse=True,
                    )[:max_preference_facts]
                if not used_provider and recall_provider:
                    used_provider = recall_provider
                if not used_model and recall_model:
                    used_model = recall_model

        primary_raw_user_preferences = len(user_items) if isinstance(user_items, list) else 0
        primary_raw_agent_candidates = (
            len(candidate_items) if isinstance(candidate_items, list) else 0
        )
        if (
            str(primary_extraction_meta.get("parse_status")) == "ok"
            and primary_raw_user_preferences == 0
            and primary_raw_agent_candidates == 0
        ):
            logger.info(
                "Session memory extraction primary response contained no extractable candidates",
                extra={
                    **extraction_log_base,
                    "response_mode": primary_extraction_meta.get("response_mode"),
                    "parse_source": primary_extraction_meta.get("parse_source"),
                    "raw_content_chars": primary_extraction_meta.get("raw_content_chars"),
                    "parsed_top_level_keys": sorted(list(parsed.keys()))[:10],
                },
            )

        logger.info(
            "Session memory extraction completed",
            extra={
                **extraction_log_base,
                "provider": used_provider or "auto",
                "model": used_model or "auto",
                "turn_count": len(turns),
                "raw_user_preferences": primary_raw_user_preferences,
                "raw_agent_candidates": primary_raw_agent_candidates,
                "normalized_user_preferences": len(user_signals),
                "normalized_agent_candidates": len(agent_candidates),
                "secondary_preference_pass_used": secondary_preference_pass_used,
                "secondary_raw_user_preferences": secondary_raw_user_preferences,
                "secondary_normalized_user_preferences": secondary_normalized_user_preferences,
                "primary_phase": primary_extraction_meta.get("phase"),
                "primary_attempt": primary_extraction_meta.get("attempt"),
                "primary_parse_status": primary_extraction_meta.get("parse_status"),
                "primary_parse_source": primary_extraction_meta.get("parse_source"),
                "primary_response_mode": primary_extraction_meta.get("response_mode"),
                "primary_fallback_triggered": bool(
                    primary_extraction_meta.get("fallback_triggered")
                ),
                "primary_raw_content_chars": primary_extraction_meta.get("raw_content_chars"),
                "secondary_phase": secondary_extraction_meta.get("phase"),
                "secondary_attempt": secondary_extraction_meta.get("attempt"),
                "secondary_parse_status": secondary_extraction_meta.get("parse_status"),
                "secondary_parse_source": secondary_extraction_meta.get("parse_source"),
                "secondary_response_mode": secondary_extraction_meta.get("response_mode"),
                "secondary_fallback_triggered": bool(
                    secondary_extraction_meta.get("fallback_triggered")
                ),
                "secondary_raw_content_chars": secondary_extraction_meta.get("raw_content_chars"),
            },
        )
        _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL.pop(backoff_key, None)
        return user_signals, agent_candidates

    def extract_user_preference_signals(self, turns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
        grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for turn in selected_turns:
            user_message = self.normalize_text(turn.get("user_message", ""))
            if not user_message:
                continue

            persistent = self.contains_persistent_preference_cue(user_message)
            latest_ts = self.parse_iso_datetime(turn.get("timestamp"))
            detections: List[Tuple[str, str, bool]] = []

            output_format = self.detect_output_format_preference(user_message)
            if output_format:
                detections.append(("output_format", output_format, False))

            language = self.detect_language_preference(user_message)
            if language:
                detections.append(("language", language, False))

            style = self.detect_response_style_preference(user_message)
            if style:
                detections.append(("response_style", style, False))

            food_preference = self.detect_food_preference_signal(user_message)
            if food_preference:
                detections.append((food_preference[0], food_preference[1], True))

            for preference_key, preference_value, strong_signal in detections:
                bucket = grouped.setdefault(
                    (preference_key, preference_value),
                    {
                        "count": 0,
                        "persistent": False,
                        "strong_signal": False,
                        "latest_ts": None,
                    },
                )
                bucket["count"] += 1
                bucket["persistent"] = bool(bucket["persistent"] or persistent)
                bucket["strong_signal"] = bool(bucket["strong_signal"] or strong_signal)
                if latest_ts and (bucket["latest_ts"] is None or latest_ts > bucket["latest_ts"]):
                    bucket["latest_ts"] = latest_ts

        extracted: List[Dict[str, Any]] = []
        for (preference_key, preference_value), bucket in grouped.items():
            evidence_count = int(bucket["count"])
            is_persistent = bool(bucket["persistent"])
            strong_signal = bool(bucket.get("strong_signal"))
            if not is_persistent and not strong_signal and evidence_count < 2:
                continue

            latest_ts = bucket.get("latest_ts")
            extracted.append(
                {
                    "key": preference_key,
                    "value": preference_value,
                    "evidence_count": evidence_count,
                    "persistent": is_persistent,
                    "strong_signal": strong_signal,
                    "confidence": (0.92 if strong_signal else 0.88 if is_persistent else 0.68),
                    "latest_ts": latest_ts.isoformat() if isinstance(latest_ts, datetime) else None,
                }
            )

        extracted.sort(
            key=lambda item: (
                int(bool(item.get("persistent")) or bool(item.get("strong_signal"))),
                int(bool(item.get("strong_signal"))),
                int(item.get("evidence_count") or 0),
                str(item.get("latest_ts") or ""),
            ),
            reverse=True,
        )
        return extracted[:_SESSION_MEMORY_MAX_PREFERENCE_FACTS]

    def _extract_step_lines(self, response: str) -> List[str]:
        matches = _BULLET_LINE_PATTERN.findall(str(response or ""))
        cleaned: List[str] = []
        for line in matches:
            value = self.normalize_text(line, max_chars=96)
            if value:
                cleaned.append(value)
        return cleaned

    def extract_agent_memory_candidates(
        self,
        turns: List[Dict[str, str]],
        agent_name: str,
    ) -> List[Dict[str, Any]]:
        selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
        candidates: List[Dict[str, Any]] = []
        seen_fingerprints = set()

        for turn in reversed(selected_turns):
            raw_response_text = str(turn.get("agent_response") or "")
            response_text = self.normalize_text(raw_response_text, max_chars=2400)
            if len(response_text) < 40:
                continue

            step_lines = self._extract_step_lines(raw_response_text)
            if len(step_lines) < 3:
                continue

            topic = self.normalize_text(turn.get("user_message", ""), max_chars=96)
            if not topic:
                continue

            step_lines = step_lines[:5]
            fingerprint = self.build_agent_candidate_fingerprint(topic, step_lines)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)

            lowered_response = raw_response_text.lower()
            has_sop_hint = any(cue in lowered_response for cue in _AGENT_SOP_HINT_CUES)
            confidence = 0.76 if has_sop_hint else 0.64
            turn_ts = self.parse_iso_datetime(turn.get("timestamp"))

            candidates.append(
                {
                    "candidate_type": "sop",
                    "topic": topic,
                    "steps": step_lines,
                    "confidence": confidence,
                    "fingerprint": fingerprint,
                    "agent_name": agent_name,
                    "latest_ts": turn_ts.isoformat() if isinstance(turn_ts, datetime) else None,
                }
            )

            if len(candidates) >= _SESSION_MEMORY_MAX_AGENT_CANDIDATES:
                break

        return candidates

    @staticmethod
    def _stable_key(prefix: str, *parts: Any) -> str:
        payload = "||".join(str(part or "").strip() for part in parts)
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}_{digest}"

    def build_session_events(self, turns: List[Dict[str, Any]]) -> List[MemorySessionEventData]:
        events: List[MemorySessionEventData] = []
        for idx, turn in enumerate(turns):
            event_ts = self.parse_iso_datetime(turn.get("timestamp"))
            user_message = str(turn.get("user_message") or "").strip()
            agent_response = str(turn.get("agent_response") or "").strip()
            agent_name = str(turn.get("agent_name") or "").strip()
            if user_message:
                events.append(
                    MemorySessionEventData(
                        event_index=len(events),
                        event_kind="message",
                        role="user",
                        content=user_message,
                        event_timestamp=event_ts,
                        payload={
                            "turn_index": idx,
                            "speaker": "user",
                            "agent_name": agent_name or None,
                        },
                    )
                )
            if agent_response:
                events.append(
                    MemorySessionEventData(
                        event_index=len(events),
                        event_kind="message",
                        role="assistant",
                        content=agent_response,
                        event_timestamp=event_ts,
                        payload={
                            "turn_index": idx,
                            "speaker": "assistant",
                            "agent_name": agent_name or None,
                        },
                    )
                )
        return events

    def build_user_preference_observations(
        self,
        *,
        user_id: str,
        turns: List[Dict[str, Any]],
        extracted_signals: List[Dict[str, Any]],
    ) -> tuple[List[MemoryObservationData], List[MemoryMaterializationData]]:
        observations: List[MemoryObservationData] = []
        materializations: List[MemoryMaterializationData] = []
        if not user_id:
            return observations, materializations

        source_event_indexes = list(range(max(len(turns) * 2, 0)))
        for signal in extracted_signals:
            key = str(signal.get("key") or "").strip()
            value = str(signal.get("value") or "").strip()
            if not key or not value:
                continue
            observation_key = self._stable_key("pref", key, value)
            confidence = float(signal.get("confidence") or 0.78)
            importance = 0.9 if bool(signal.get("persistent")) else 0.72
            title = f"User preference: {key}"
            summary = value
            details = str(signal.get("reason") or "").strip() or None
            observations.append(
                MemoryObservationData(
                    observation_key=observation_key,
                    observation_type="user_preference_signal",
                    title=title,
                    summary=summary,
                    details=details,
                    source_event_indexes=source_event_indexes,
                    confidence=confidence,
                    importance=importance,
                    metadata={
                        "preference_key": key,
                        "preference_value": value,
                        "persistent": bool(signal.get("persistent")),
                        "explicit_source": bool(signal.get("explicit_source")),
                        "latest_turn_ts": signal.get("latest_ts"),
                        "reason": signal.get("reason"),
                    },
                )
            )
            materializations.append(
                MemoryMaterializationData(
                    owner_type="user",
                    owner_id=user_id,
                    materialization_type="user_profile",
                    materialization_key=key,
                    title=title,
                    summary=summary,
                    details=details,
                    payload={
                        "key": key,
                        "value": value,
                        "confidence": confidence,
                        "importance": importance,
                        "persistent": bool(signal.get("persistent")),
                        "explicit_source": bool(signal.get("explicit_source")),
                    },
                    source_observation_key=observation_key,
                )
            )
        return observations, materializations

    def build_agent_experience_observations(
        self,
        *,
        agent_id: str,
        agent_name: str,
        turns: List[Dict[str, Any]],
        extracted_agent_candidates: List[Dict[str, Any]],
    ) -> tuple[List[MemoryObservationData], List[MemoryMaterializationData]]:
        observations: List[MemoryObservationData] = []
        materializations: List[MemoryMaterializationData] = []
        if not agent_id:
            return observations, materializations

        source_event_indexes = list(range(max(len(turns) * 2, 0)))
        for candidate in extracted_agent_candidates:
            fingerprint = str(candidate.get("fingerprint") or "").strip()
            title = str(candidate.get("title") or candidate.get("topic") or "").strip()
            summary = str(candidate.get("summary") or "").strip() or None
            steps = [
                str(step).strip() for step in candidate.get("steps") or [] if str(step).strip()
            ]
            if not fingerprint or not title or not steps:
                continue
            details = " -> ".join(steps)
            avoid = str(candidate.get("avoid") or "").strip() or None
            applicability = str(candidate.get("applicability") or "").strip() or None
            observation_key = self._stable_key("agent_path", fingerprint, title)
            observations.append(
                MemoryObservationData(
                    observation_key=observation_key,
                    observation_type="agent_success_path",
                    title=title,
                    summary=summary,
                    details=details,
                    source_event_indexes=source_event_indexes,
                    confidence=float(candidate.get("confidence") or 0.72),
                    importance=0.82,
                    metadata={
                        "agent_name": agent_name or None,
                        "candidate_type": str(candidate.get("candidate_type") or "successful_path"),
                        "fingerprint": fingerprint,
                        "topic": candidate.get("topic"),
                        "steps": steps,
                        "avoid": avoid,
                        "applicability": applicability,
                        "skill_candidate": True,
                    },
                )
            )
            materializations.append(
                MemoryMaterializationData(
                    owner_type="agent",
                    owner_id=agent_id,
                    materialization_type="agent_experience",
                    materialization_key=fingerprint,
                    title=title,
                    summary=summary,
                    details=details,
                    status="pending_review",
                    payload={
                        "goal": title,
                        "successful_path": steps,
                        "why_it_worked": summary,
                        "applicability": applicability,
                        "avoid": avoid,
                        "agent_name": agent_name or None,
                        "skill_candidate": True,
                        "review_status": "pending",
                        "review_required": True,
                        "inject_policy": "only_published",
                        "confidence": float(candidate.get("confidence") or 0.72),
                        "latest_turn_ts": candidate.get("latest_ts"),
                    },
                    source_observation_key=observation_key,
                )
            )
        return observations, materializations


_session_observation_builder: Optional[SessionObservationBuilder] = None


def get_session_observation_builder() -> SessionObservationBuilder:
    global _session_observation_builder
    if _session_observation_builder is None:
        _session_observation_builder = SessionObservationBuilder()
    return _session_observation_builder


async def extract_session_memory_signals_with_llm(**kwargs):
    return await get_session_observation_builder().extract_session_memory_signals_with_llm(**kwargs)


def extract_user_preference_signals(turns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    return get_session_observation_builder().extract_user_preference_signals(turns)


def extract_agent_memory_candidates(
    turns: List[Dict[str, str]],
    agent_name: str,
) -> List[Dict[str, Any]]:
    return get_session_observation_builder().extract_agent_memory_candidates(turns, agent_name)


def call_llm_for_memory_json(**kwargs):
    return get_session_observation_builder().call_llm_for_memory_json(**kwargs)


def normalize_llm_user_preference_signals(
    raw_items: Any,
    turn_ts_map: Dict[int, Optional[str]],
    max_items: int = _SESSION_MEMORY_MAX_PREFERENCE_FACTS,
) -> List[Dict[str, Any]]:
    return get_session_observation_builder().normalize_llm_user_preference_signals(
        raw_items,
        turn_ts_map,
        max_items=max_items,
    )


def normalize_llm_agent_candidates(
    raw_items: Any,
    *,
    agent_name: str,
    turn_ts_map: Dict[int, Optional[str]],
    max_items: int = _SESSION_MEMORY_MAX_AGENT_CANDIDATES,
) -> List[Dict[str, Any]]:
    return get_session_observation_builder().normalize_llm_agent_candidates(
        raw_items,
        agent_name=agent_name,
        turn_ts_map=turn_ts_map,
        max_items=max_items,
    )
