"""Session observation builder for extraction, normalization, and ledger projections."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent_framework.agent_registry import get_agent_registry
from shared.logging import get_logger
from user_memory.fact_identity import (
    build_user_fact_identity,
    build_user_fact_semantic_key,
    build_user_memory_view_key,
    normalize_fact_kind as normalize_user_fact_kind,
)
from user_memory.session_ledger_repository import (
    MemoryProjectionData,
    MemoryObservationData,
    MemorySessionEventData,
)

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
_RELATIVE_DAY_OFFSETS = {
    "前天": -2,
    "昨天": -1,
    "今日": 0,
    "今天": 0,
    "今晚": 0,
    "今早": 0,
    "明早": 1,
    "明晚": 1,
    "明天": 1,
    "后天": 2,
}
_RELATIVE_TEMPORAL_CUES = (
    "今天",
    "今日",
    "今晚",
    "今早",
    "明天",
    "明早",
    "明晚",
    "后天",
    "昨天",
    "前天",
    "下周",
    "下个月",
    "近期",
    "最近",
)
_GENERIC_RELATIONSHIP_PREDICATES = {
    "associate",
    "acquaintance",
    "companion",
    "contact",
    "friend",
    "teammate",
    "coworker",
    "colleague",
}
_GENERIC_RELATIONSHIP_EXPLICIT_CUES = (
    "我的朋友",
    "我朋友",
    "是我朋友",
    "我的同事",
    "我同事",
    "是我同事",
    "我的同学",
    "我同学",
    "是我同学",
    "我的搭档",
    "我搭档",
    "是我搭档",
)
_EVENT_SCOPED_RELATIONSHIP_PLAN_CUES = (
    "计划",
    "打算",
    "安排",
    "准备",
    "约",
    "约好",
    "约了",
    "将",
    "会",
    "明天",
    "后天",
    "今天",
    "今晚",
    "下周",
    "下个月",
)
_EVENT_SCOPED_RELATIONSHIP_ACTIVITY_CUES = (
    "一起",
    "去",
    "吃",
    "喝",
    "聊",
    "见面",
    "碰面",
    "外出",
    "出门",
    "出行",
    "旅行",
    "行程",
    "搬家",
    "赴约",
    "聚餐",
    "约会",
)

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
_QUESTION_SUFFIX_PATTERN = re.compile(r"(?:[?？!！。]+|(?:好?吗|呢|呀|啊|吧|嘛|不))+$")
_INTERROGATIVE_FRAGMENT_PATTERN = re.compile(
    r"(什么|啥|哪些|哪种|哪类|哪儿|哪里|哪个|谁|为何|为什么|怎么|如何|怎样|"
    r"多少|几个|几月|几号|几点|什么时候|何时)"
)
_CONVERSATIONAL_QUERY_PREFIXES = (
    "你知道",
    "你记得",
    "你还记得",
    "你清楚",
    "你能告诉我",
    "能告诉我",
    "告诉我",
    "请问",
    "麻烦你",
    "帮我回忆",
    "回忆一下",
    "我想知道",
    "我想问",
    "想问问",
)
_EXPERIENCE_PATTERNS = (
    re.compile(r"我(?:之前|以前|曾经)?(?:做过|干过|从事过)(?P<item>[^，。！？；,.!?]{1,40})"),
    re.compile(r"我(?:在|曾在)(?P<item>[^，。！？；,.!?]{1,40})(?:工作|上班|任职)"),
)
_SKILL_PATTERNS = (
    re.compile(r"(?:^|[，,；;、\s])(?:我(?:比较)?|也)?擅长(?P<item>[^，。！？；,.!?]{1,32})"),
    re.compile(r"(?:^|[，,；;、\s])(?:我(?:比较)?|也)?熟悉(?P<item>[^，。！？；,.!?]{1,32})"),
)
_LONG_TERM_GOAL_PATTERNS = (
    re.compile(r"我(?:长期)?(?:目标是|想要|希望)(?P<item>[^，。！？；,.!?]{2,40})"),
    re.compile(r"以后(?:想|希望)(?P<item>[^，。！？；,.!?]{2,40})"),
)
_BUDGET_PATTERNS = (
    re.compile(r"(?:预算|价位)(?:在|大概|约|控制在)?(?P<item>[^，。！？；,.!?]{1,24})"),
)
_RELATIONSHIP_PATTERNS = (
    re.compile(
        r"我(?P<relation>老婆|老公|妻子|丈夫|女朋友|男朋友|妈妈|母亲|爸爸|父亲|儿子|女儿|孩子)(?:叫|是)(?P<name>[^，。！？；,.!?]{1,24})"
    ),
    re.compile(
        r"(?P<name>[^，。！？；,.!?]{1,24})是我(?P<relation>老婆|老公|妻子|丈夫|女朋友|男朋友|妈妈|母亲|爸爸|父亲|儿子|女儿|孩子)"
    ),
)
_EVENT_TIME_FRAGMENT = (
    r"(?:20\d{2}年(?:\d{1,2}月(?:\d{1,2}日)?)?|去年(?:底|初|春天|夏天|秋天|冬天)?|前年|今年|"
    r"上个月|上月|上周|最近)"
)
_EVENT_PATTERNS = (
    re.compile(
        rf"(?P<time>{_EVENT_TIME_FRAGMENT})(?:的时候)?(?:，|,)?(?:我)?"
        r"(?P<item>(?:搬到(?:了)?|搬去(?:了)?|去了|去过|结婚(?:了)?|毕业(?:了)?|"
        r"入职(?:了)?|离职(?:了)?|开始(?:做|学|创业)|换到(?:了)?|创业(?:了)?|"
        r"生了孩子|生娃)[^，。！？；,.!?]{0,28})"
    ),
    re.compile(
        rf"(?:我)?(?P<item>(?:搬到(?:了)?|搬去(?:了)?|去了|去过|结婚(?:了)?|毕业(?:了)?|"
        r"入职(?:了)?|离职(?:了)?|开始(?:做|学|创业)|换到(?:了)?|创业(?:了)?|"
        r"生了孩子|生娃)[^，。！？；,.!?]{0,28})(?:是在|在)?(?P<time>"
        rf"{_EVENT_TIME_FRAGMENT})"
    ),
)
_RELATIONSHIP_LABELS = {
    "老婆": "spouse",
    "老公": "spouse",
    "妻子": "spouse",
    "丈夫": "spouse",
    "女朋友": "partner",
    "男朋友": "partner",
    "妈妈": "mother",
    "母亲": "mother",
    "爸爸": "father",
    "父亲": "father",
    "儿子": "son",
    "女儿": "daughter",
    "孩子": "child",
}
_RELATIONSHIP_CANONICAL_LABELS = {
    "spouse": "配偶",
    "partner": "伴侣",
    "mother": "母亲",
    "father": "父亲",
    "son": "儿子",
    "daughter": "女儿",
    "child": "孩子",
}
_USER_FACT_KIND_TITLE = {
    "preference": "User preference",
    "identity": "User identity",
    "relationship": "User relationship",
    "experience": "User experience",
    "expertise": "User expertise",
    "goal": "User goal",
    "constraint": "User constraint",
    "habit": "User habit",
    "event": "User event",
}


def _to_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class SessionObservationBuilder:
    """Canonical session-memory extraction and projection builder."""

    @staticmethod
    def _iter_json_object_candidates(text: str) -> List[str]:
        raw = str(text or "")
        if not raw:
            return []
        decoder = json.JSONDecoder()
        candidates: List[str] = []
        seen: set[str] = set()
        for index, char in enumerate(raw):
            if char != "{":
                continue
            try:
                parsed, end_index = decoder.raw_decode(raw[index:])
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            candidate = raw[index : index + end_index].strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
        return candidates

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

    @staticmethod
    def _normalize_reference_datetime(value: Any) -> Optional[datetime]:
        parsed = SessionObservationBuilder.parse_iso_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _contains_relative_temporal_cue(*values: Any) -> bool:
        text = " ".join(str(value or "") for value in values)
        if not text:
            return False
        return any(cue in text for cue in _RELATIVE_TEMPORAL_CUES)

    @classmethod
    def _normalize_relative_event_time(
        cls,
        event_time: Optional[str],
        reference_ts: Optional[str],
    ) -> Optional[str]:
        normalized = cls.normalize_text(event_time or "", max_chars=64) or None
        if not normalized:
            return None
        if normalized not in _RELATIVE_DAY_OFFSETS:
            return normalized

        reference_dt = cls._normalize_reference_datetime(reference_ts)
        if reference_dt is None:
            return normalized

        absolute_day = reference_dt.date() + timedelta(days=_RELATIVE_DAY_OFFSETS[normalized])
        return absolute_day.isoformat()

    @classmethod
    def _looks_like_ephemeral_relationship_signal(
        cls,
        *,
        semantic_key: str,
        predicate: Optional[str],
        value: str,
        canonical_statement: str,
        event_time: Optional[str],
    ) -> bool:
        relation_key = cls.normalize_text(
            predicate or semantic_key.replace("relationship_", ""),
            max_chars=64,
        )
        if relation_key not in _RELATIONSHIP_CANONICAL_LABELS and "_" in relation_key:
            relation_prefix = relation_key.split("_", 1)[0].strip()
            if relation_prefix:
                relation_key = relation_prefix
        if relation_key in _RELATIONSHIP_CANONICAL_LABELS:
            return False

        combined_text = " ".join(
            part for part in (value, canonical_statement) if isinstance(part, str) and part.strip()
        )
        has_activity_cue = any(cue in combined_text for cue in _EVENT_SCOPED_RELATIONSHIP_ACTIVITY_CUES)
        has_plan_cue = any(cue in combined_text for cue in _EVENT_SCOPED_RELATIONSHIP_PLAN_CUES)

        # Event-scoped companionship like "计划和小陈一起去吃汉堡" should stay as an
        # event memory instead of hardening into a durable relationship fact.
        if has_activity_cue:
            if event_time or has_plan_cue or cls._contains_relative_temporal_cue(combined_text):
                return True

        if relation_key not in _GENERIC_RELATIONSHIP_PREDICATES:
            return False

        if any(cue in combined_text for cue in _GENERIC_RELATIONSHIP_EXPLICIT_CUES):
            return False

        # Generic relationships inferred from a single interaction are too noisy to persist.
        if "用户与" in combined_text and "关系" in combined_text:
            return True

        return cls._contains_relative_temporal_cue(combined_text) and any(
            cue in combined_text for cue in ("一起", "外出", "去", "赴约")
        )

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

        for candidate in cls._iter_json_object_candidates(raw):
            _add_candidate("json_object_scan", candidate)

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
        item = _QUESTION_SUFFIX_PATTERN.sub("", item).strip()
        item = re.sub(r"^[：:，,\s]+", "", item)
        item = re.sub(r"[，,。！？!?；;\s]+$", "", item)
        item = " ".join(item.split())
        if not item:
            return None
        if len(item) > max_chars:
            return None
        if item in {"什么", "啥", "一下", "一点"}:
            return None
        if cls._looks_like_interrogative_fragment(item):
            return None
        return item

    @classmethod
    def _looks_like_interrogative_fragment(cls, value: str) -> bool:
        normalized = cls.normalize_text(value or "", max_chars=120)
        if not normalized:
            return False
        if "?" in normalized or "？" in normalized:
            return True
        if any(normalized.startswith(prefix) for prefix in _CONVERSATIONAL_QUERY_PREFIXES):
            return True
        return bool(_INTERROGATIVE_FRAGMENT_PATTERN.search(normalized))

    @classmethod
    def _looks_like_question_artifact(
        cls,
        *,
        value: str,
        canonical_statement: str,
    ) -> bool:
        candidates = [str(value or "").strip(), str(canonical_statement or "").strip()]
        return any(cls._looks_like_interrogative_fragment(candidate) for candidate in candidates)

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
    def _normalize_string_list(
        values: Any,
        *,
        max_items: int = 8,
        max_chars: int = 48,
    ) -> List[str]:
        if not isinstance(values, list):
            return []
        normalized: List[str] = []
        for item in values:
            text = " ".join(str(item or "").split()).strip()
            if not text:
                continue
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
            if text not in normalized:
                normalized.append(text)
            if len(normalized) >= max(int(max_items), 1):
                break
        return normalized

    @classmethod
    def _extract_event_location(cls, value: str) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        match = re.search(
            r"(?:搬到(?:了)?|搬去(?:了)?|去了|去过|换到(?:了)?)(?P<location>[^，。！？；,.!?]{1,24})",
            text,
        )
        if not match:
            return None
        return cls._normalize_preference_item(match.group("location"), max_chars=24)

    @staticmethod
    def _infer_event_topic(value: str) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        if any(keyword in text for keyword in ("搬到", "搬去", "换到")):
            return "迁居"
        if any(keyword in text for keyword in ("去了", "去过")):
            return "出行"
        if "结婚" in text:
            return "婚姻"
        if any(keyword in text for keyword in ("入职", "离职", "创业")):
            return "职业"
        if any(keyword in text for keyword in ("毕业", "开始学")):
            return "学习"
        if any(keyword in text for keyword in ("生了孩子", "生娃")):
            return "家庭"
        return "重要事件"

    def _normalize_user_fact_kind(self, value: Any) -> str:
        return normalize_user_fact_kind(value)

    def _stabilize_user_fact_key(
        self,
        *,
        key: str,
        value: str,
        fact_kind: str,
    ) -> str:
        return build_user_fact_identity(
            fact_kind=fact_kind,
            raw_key=key,
            value=value,
        ).fact_key

    def _build_user_fact_canonical_statement(
        self,
        *,
        fact_kind: str,
        semantic_key: str,
        value: str,
        canonical_statement: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        event_time: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> str:
        statement = self.normalize_text(canonical_statement or "", max_chars=220)
        if statement:
            return statement

        if fact_kind == "relationship":
            relation_key = self.normalize_text(
                predicate or semantic_key.replace("relationship_", ""),
                max_chars=48,
            )
            relation = _RELATIONSHIP_CANONICAL_LABELS.get(relation_key, relation_key or "关系对象")
            target = self.normalize_text(obj or value, max_chars=96)
            return f"用户的{relation}是{target}"
        if fact_kind == "experience":
            return f"用户做过{value}"
        if fact_kind == "expertise":
            return f"用户擅长{value}"
        if fact_kind == "goal":
            return f"用户的长期目标是{value}"
        if fact_kind == "constraint":
            return f"用户的稳定约束是{value}"
        if fact_kind == "identity":
            return f"用户的身份信息是{value}"
        if fact_kind == "habit":
            return f"用户的习惯是{value}"
        if fact_kind == "event":
            if event_time:
                return f"在{event_time}，{value}"
            event_topic = self.normalize_text(topic or "", max_chars=48)
            if event_topic:
                return f"{event_topic}：{value}"
            return f"用户经历过{value}"
        return f"用户偏好{semantic_key}是{value}"

    def _build_user_fact_title(
        self,
        *,
        fact_kind: str,
        semantic_key: str,
        value: str,
        canonical_statement: str,
    ) -> str:
        title_prefix = _USER_FACT_KIND_TITLE.get(fact_kind, "User fact")
        key_label = semantic_key.replace("_", " ").strip()
        title = canonical_statement if len(canonical_statement) <= 72 else ""
        if title:
            return title
        if key_label:
            return f"{title_prefix}: {key_label}"
        return f"{title_prefix}: {self.normalize_text(value, max_chars=64)}"

    @staticmethod
    def _build_user_episode_view_key(
        *,
        stable_key: str,
        canonical_statement: str,
        event_time: Optional[str],
        value: str,
    ) -> str:
        return build_user_memory_view_key(
            view_type="episode",
            stable_key=stable_key,
            canonical_statement=canonical_statement,
            event_time=event_time,
            value=value,
        )

    def _build_user_episode_title(
        self,
        *,
        canonical_statement: str,
        event_time: Optional[str],
        topic: Optional[str],
        value: str,
    ) -> str:
        statement = self.normalize_text(canonical_statement or "", max_chars=96)
        if statement and len(statement) <= 72:
            return statement
        time_label = self.normalize_text(event_time or "", max_chars=32)
        topic_label = self.normalize_text(topic or "", max_chars=32)
        value_label = self.normalize_text(value or "", max_chars=72)
        if time_label and topic_label:
            return f"{time_label} · {topic_label}"
        if time_label and value_label:
            return f"{time_label} · {value_label}"
        if topic_label:
            return topic_label
        return statement or value_label or "User episode"

    @staticmethod
    def _should_materialize_user_fact(fact_kind: str, persistent: bool) -> bool:
        if fact_kind == "event":
            return False
        return True if persistent else fact_kind in {"relationship", "experience", "expertise", "goal"}

    @classmethod
    def _build_user_fact_signal(
        cls,
        *,
        fact_kind: str,
        semantic_key: str,
        value: str,
        confidence: float,
        persistent: bool,
        latest_ts: Optional[datetime],
        reason: Optional[str] = None,
        explicit_source: bool = True,
        strong_signal: Optional[bool] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        persons: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
        event_time: Optional[str] = None,
        location: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        builder = cls()
        identity = build_user_fact_identity(
            fact_kind=fact_kind,
            raw_key=semantic_key,
            value=value,
            predicate=predicate,
            obj=obj,
            persons=persons,
            entities=entities,
            event_time=event_time,
            location=location,
            topic=topic,
        )
        canonical_statement = builder._build_user_fact_canonical_statement(
            fact_kind=fact_kind,
            semantic_key=identity.semantic_key,
            value=value,
            predicate=predicate,
            obj=obj,
            event_time=event_time,
            topic=topic,
        )
        return {
            "key": identity.fact_key,
            "semantic_key": identity.semantic_key,
            "identity_signature": identity.identity_signature,
            "value": value,
            "fact_kind": fact_kind,
            "canonical_statement": canonical_statement,
            "predicate": predicate,
            "object": obj,
            "persons": persons or [],
            "entities": entities or [],
            "event_time": event_time,
            "location": location,
            "topic": topic,
            "evidence_count": 1,
            "persistent": persistent,
            "strong_signal": bool(explicit_source if strong_signal is None else strong_signal),
            "confidence": confidence,
            "latest_ts": latest_ts.isoformat() if isinstance(latest_ts, datetime) else None,
            "reason": reason,
            "explicit_source": explicit_source,
            "materialize_profile": builder._should_materialize_user_fact(fact_kind, persistent),
        }

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
            origin = str(turn.get("turn_origin") or "new").strip().lower() or "new"
            origin_label = "OVERLAP" if origin == "overlap" else "NEW"
            turn_ts_map[idx] = timestamp
            lines.append(
                "\n".join(
                    [
                        f"[TURN {idx}][{origin_label}] timestamp={timestamp or '-'}",
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
1. user_facts: 提取“用户事实原子”，不仅限于喜欢/不喜欢，也包括关系、经历、能力、目标、约束、重要事件。
2. skill_candidates: 提取“做事成功路径经验 / 可沉淀为 skill 的方法模板”（后续人工审批）。

user_facts 覆盖范围:
- preference: 偏好/禁忌/语言/输出风格/习惯
- relationship: 谁与谁是什么关系
- experience: 做过什么、从事过什么、在哪里工作过
- expertise: 擅长什么、熟悉什么
- goal: 长期目标、长期计划
- constraint: 预算、过敏、稳定限制
- event: 对后续任务仍可能有帮助的重要经历、明确里程碑、带明确时间的个人事实
- identity: 用户身份、角色、背景信息

强约束:
- 只提取用户明确说过的信息，禁止猜测、禁止扩写。
- 带有 `OVERLAP` 标记的 turn 只用于理解上下文、补全指代、补时间和关系消歧。
- 任何 user_facts / skill_candidates 都必须至少有一个 evidence_turn 命中 `NEW` turn；如果证据只来自 `OVERLAP`，不要提取。
- 同一次会话里如果存在多条有效事实，必须全部提取，不要只保留 1 条。
- `canonical_statement` 必须是脱离上下文也能读懂的完整陈述；不要用“他/她/这个/那个/昨天/上周”。
- 如果用户说了明确时间，优先转为绝对时间或绝对日期。
- 不要生成 durable key，系统会根据结构化槽位生成稳定 identity。
- 如无有效项，返回空数组。

高优先级规则:
- 对用户直接陈述优先提取，例如：
  - 我喜欢X / 我不吃X
  - 我做过X / 我以前在X工作
  - 我擅长X / 我熟悉X
  - 我老婆叫X / X是我妈妈
  - 我在2024年做过X / 我去年搬到X
- 这类直接陈述建议 explicit_source=true，confidence >= 0.82。

skill_candidates 规则:
- 重点提取“最终成功的做事路径”，尤其是经历过多次尝试后，最后真正走通的那条路径。
- 目标是让 agent 下次遇到相似任务时，少走弯路，优先复用成功方法。
- 必须可迁移、可复用：避免绑定具体人名/地名/商品名/单次任务细节。
- summary 说明“为什么这条路径有效”；steps 只保留成功路径上的关键动作，2-5 步即可。
- avoid 用来总结应避免的弯路/失败尝试/不适用条件。
- 如果本次对话没有形成可复用的成功方法，不要提取。

输出 JSON Schema:
{{
  "user_facts": [
    {{
      "fact_kind": "preference|relationship|experience|expertise|goal|constraint|event|identity|habit",
      "value": "简短明确",
      "canonical_statement": "完整、自包含的事实陈述",
      "predicate": "可选，关系或动作谓词",
      "object": "可选，关系对象或事实对象",
      "event_time": "可选，ISO 8601 或绝对日期",
      "persons": ["涉及的人"],
      "entities": ["涉及的实体"],
      "location": "可选，地点",
      "topic": "可选，主题",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.0,
      "reason": "为什么值得记忆",
      "evidence_turns": [1, 2]
    }}
  ],
  "skill_candidates": [
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
USER: 我老婆叫王敏。我做过电商运营，也擅长写SQL。2024年8月我搬到了杭州。
ASSISTANT: 收到

输出:
{{
  "user_facts": [
    {{
      "fact_kind": "relationship",
      "value": "王敏",
      "canonical_statement": "用户的配偶是王敏",
      "predicate": "spouse",
      "object": "王敏",
      "persons": ["王敏"],
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.93,
      "reason": "用户明确陈述家庭关系",
      "evidence_turns": [1]
    }},
    {{
      "fact_kind": "experience",
      "value": "做过电商运营",
      "canonical_statement": "用户做过电商运营",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.88,
      "reason": "用户明确陈述过往经历",
      "evidence_turns": [1]
    }},
    {{
      "fact_kind": "expertise",
      "value": "SQL",
      "canonical_statement": "用户擅长SQL",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.9,
      "reason": "用户明确陈述技能",
      "evidence_turns": [1]
    }},
    {{
      "fact_kind": "event",
      "value": "用户搬到了杭州",
      "canonical_statement": "2024年8月用户搬到了杭州",
      "event_time": "2024-08",
      "location": "杭州",
      "persistent": false,
      "explicit_source": true,
      "confidence": 0.82,
      "reason": "带明确时间的用户重要经历",
      "evidence_turns": [1]
    }}
  ],
  "skill_candidates": []
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
            origin = str(turn.get("turn_origin") or "new").strip().lower() or "new"
            origin_label = "OVERLAP" if origin == "overlap" else "NEW"
            turn_ts_map[idx] = timestamp
            lines.append(
                "\n".join(
                    [
                        f"[TURN {idx}][{origin_label}] timestamp={timestamp or '-'}",
                        f"USER: {user_text or '-'}",
                        f"ASSISTANT: {agent_text or '-'}",
                    ]
                )
            )

        transcript = "\n\n".join(lines)
        if len(transcript) > _SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:
            transcript = transcript[-_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:]

        prompt = f"""
你是“用户事实补充抽取器”。你的目标是补充抽取用户明确陈述的稳定画像事实和重要个人事实。
输出必须是 JSON 对象，不要输出解释文字。

补充抽取规则:
- 不仅抽取偏好，也可抽取关系/经历/能力/长期目标/稳定约束/习惯/重要个人事件（都要求用户明确陈述）。
- 可以是单轮，但必须是“用户直接表达”；禁止猜测、禁止偏好延伸。
- `OVERLAP` turn 只能作为上下文，最终提取结果必须至少有一个 evidence_turn 命中 `NEW` turn。
- 一次性临时要求（如“这次导出 PDF”）不抽取。
- 同一会话若有多条有效画像事实，应全部提取。
- `canonical_statement` 必须是完整、自包含的陈述；若存在明确时间，转成绝对时间/日期。
- 不要生成 durable key，系统会根据结构化槽位生成稳定 identity；value 必须简短。
- 如无有效项，返回空数组。
- 若出现明确陈述（如“我喜欢吃黄焖鸡/我擅长SQL/我做过运营/我老婆叫王敏”），不得漏提。

输出 JSON Schema:
{{
  "user_facts": [
    {{
      "fact_kind": "preference|relationship|experience|expertise|goal|constraint|event|identity|habit",
      "value": "简短明确",
      "canonical_statement": "完整事实陈述",
      "predicate": "可选",
      "object": "可选",
      "event_time": "可选",
      "persons": ["可选"],
      "entities": ["可选"],
      "location": "可选",
      "topic": "可选",
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
  "user_facts": [
    {{
      "fact_kind": "preference",
      "value": "黄焖鸡",
      "canonical_statement": "用户喜欢吃黄焖鸡",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.9,
      "reason": "用户明确陈述喜欢的食物",
      "evidence_turns": [1]
    }},
    {{
      "fact_kind": "experience",
      "value": "做过前端开发",
      "canonical_statement": "用户做过前端开发",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.86,
      "reason": "用户明确陈述过往经历",
      "evidence_turns": [1]
    }},
    {{
      "fact_kind": "expertise",
      "value": "SQL",
      "canonical_statement": "用户擅长SQL",
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
    def _is_thinking_control_not_supported_error(error: Exception) -> bool:
        message = str(error or "").lower()
        if not message:
            return False
        field_cues = ("chat_template_kwargs", "enable_thinking")
        unsupported_cues = (
            "unsupported",
            "unexpected keyword argument",
            "extra fields not permitted",
            "unknown field",
            "not allowed",
        )
        return any(field in message for field in field_cues) and any(
            cue in message for cue in unsupported_cues
        )

    @staticmethod
    def _should_disable_thinking(
        *,
        provider: Optional[str],
        model: Optional[str],
    ) -> bool:
        provider_name = str(provider or "").strip().lower()
        model_name = str(model or "").strip().lower()
        if provider_name == "vllm":
            return True
        return "qwen" in model_name

    @classmethod
    def _build_reasoning_control_kwargs(
        cls,
        *,
        provider: Optional[str],
        model: Optional[str],
    ) -> Dict[str, Any]:
        if not cls._should_disable_thinking(provider=provider, model=model):
            return {}
        return {
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False},
            }
        }

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
            timeout_limit = max(float(timeout_seconds), 0.5)
            base_request_kwargs = dict(base_kwargs)
            if with_response_format:
                base_request_kwargs["response_format"] = {"type": "json_object"}

            reasoning_control_kwargs = self._build_reasoning_control_kwargs(
                provider=provider,
                model=model,
            )
            request_variants = []
            if reasoning_control_kwargs:
                request_variants.append((True, reasoning_control_kwargs))
            request_variants.append((False, {}))

            last_error: Optional[Exception] = None
            response: Any = None
            thinking_control_applied = False
            for use_reasoning_control, extra_kwargs in request_variants:
                kwargs = dict(base_request_kwargs)
                kwargs.update(extra_kwargs)
                try:
                    response = await asyncio.wait_for(
                        llm_router.generate(**kwargs),
                        timeout=timeout_limit,
                    )
                    thinking_control_applied = use_reasoning_control
                    break
                except asyncio.TimeoutError as timeout_error:
                    await self._invalidate_timed_out_llm_provider(
                        llm_router=llm_router,
                        provider_name=provider,
                    )
                    raise TimeoutError(
                        f"session_memory_extraction_timeout_{timeout_limit:.1f}s"
                    ) from timeout_error
                except Exception as generate_error:
                    last_error = generate_error
                    if use_reasoning_control and self._is_thinking_control_not_supported_error(
                        generate_error
                    ):
                        continue
                    raise

            if response is None:
                if last_error is not None:
                    raise last_error
                raise ValueError("session_memory_extraction_no_response")
            raw_content = str(getattr(response, "content", "") or "")
            parsed_payload, parse_meta = self.extract_json_object_from_text_with_meta(raw_content)
            parse_meta.update(
                {
                    "response_mode": response_mode,
                    "fallback_triggered": fallback_triggered,
                    "thinking_control_applied": thinking_control_applied,
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
            fact_kind = self._normalize_user_fact_kind(raw.get("fact_kind"))
            # Compatibility-only semantic hint. Durable identity still comes from
            # server-side slot normalization, not the model-provided key.
            semantic_hint = self.normalize_memory_key(raw.get("key"), max_chars=80)
            value = self.normalize_text(raw.get("value", ""), max_chars=120)
            if not value:
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
            allow_single_turn = (
                explicit_source
                or confidence >= 0.82
                or fact_kind
                in {
                    "relationship",
                    "experience",
                    "expertise",
                    "goal",
                    "constraint",
                    "identity",
                    "event",
                }
            )
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
            predicate = self.normalize_text(raw.get("predicate", ""), max_chars=48) or None
            obj = self.normalize_text(raw.get("object", ""), max_chars=120) or None
            event_time = self._normalize_relative_event_time(
                self.normalize_text(raw.get("event_time", ""), max_chars=64) or None,
                latest_turn_ts,
            )
            location = self.normalize_text(raw.get("location", ""), max_chars=96) or None
            topic = self.normalize_text(raw.get("topic", ""), max_chars=72) or None
            persons = self._normalize_string_list(raw.get("persons"), max_items=8, max_chars=48)
            entities = self._normalize_string_list(raw.get("entities"), max_items=8, max_chars=48)
            semantic_key = build_user_fact_semantic_key(
                fact_kind=fact_kind,
                raw_key=semantic_hint,
                predicate=predicate,
                obj=obj,
                topic=topic,
                value=value,
            )
            canonical_statement = self._build_user_fact_canonical_statement(
                fact_kind=fact_kind,
                semantic_key=semantic_key,
                value=value,
                canonical_statement=raw.get("canonical_statement"),
                predicate=predicate,
                obj=obj,
                event_time=event_time,
                topic=topic,
            )
            if self._looks_like_question_artifact(
                value=value,
                canonical_statement=canonical_statement,
            ):
                continue
            if fact_kind == "relationship" and self._looks_like_ephemeral_relationship_signal(
                semantic_key=semantic_key,
                predicate=predicate,
                value=value,
                canonical_statement=canonical_statement,
                event_time=event_time,
            ):
                continue
            identity = build_user_fact_identity(
                fact_kind=fact_kind,
                raw_key=semantic_hint,
                value=value,
                canonical_statement=canonical_statement,
                predicate=predicate,
                obj=obj,
                persons=persons,
                entities=entities,
                event_time=event_time,
                location=location,
                topic=topic,
            )
            extracted.append(
                {
                    "key": identity.fact_key,
                    "semantic_key": identity.semantic_key,
                    "identity_signature": identity.identity_signature,
                    "value": value,
                    "fact_kind": fact_kind,
                    "canonical_statement": canonical_statement,
                    "predicate": predicate,
                    "object": obj,
                    "event_time": event_time,
                    "persons": persons,
                    "entities": entities,
                    "location": location,
                    "topic": topic,
                    "evidence_count": evidence_count,
                    "persistent": is_persistent,
                    "strong_signal": is_persistent or explicit_source,
                    "confidence": confidence,
                    "latest_ts": latest_turn_ts,
                    "reason": reason or None,
                    "explicit_source": explicit_source,
                    "materialize_profile": self._should_materialize_user_fact(
                        fact_kind,
                        is_persistent,
                    ),
                    "evidence_turns": evidence_turns,
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
                    "evidence_turns": evidence_turns,
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
        secondary_recall_enabled = True
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
            configured_provider = cfg.get("user_memory.extraction.provider") or cfg.get(
                "skill_candidates.extraction.provider"
            )
            configured_model = cfg.get("user_memory.extraction.model") or cfg.get(
                "skill_candidates.extraction.model"
            )
            configured_chat = cfg.get("llm.model_mapping.chat")
            configured_timeout = cfg.get("user_memory.extraction.timeout_seconds") or cfg.get(
                "skill_candidates.extraction.timeout_seconds"
            )
            configured_failure_backoff = cfg.get(
                "user_memory.extraction.failure_backoff_seconds"
            ) or cfg.get("skill_candidates.extraction.failure_backoff_seconds")
            configured_max_facts = cfg.get("user_memory.extraction.max_facts")
            configured_max_preferences = cfg.get("user_memory.extraction.max_preference_facts")
            configured_max_candidates = cfg.get("skill_candidates.extraction.max_candidates")
            configured_secondary_recall = cfg.get("user_memory.extraction.secondary_recall_enabled")
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
            secondary_recall_enabled = bool(
                True if configured_secondary_recall is None else configured_secondary_recall
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
            secondary_recall_enabled = True

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

        user_items = parsed.get("user_facts")
        if not isinstance(user_items, list):
            user_items = parsed.get("user_preferences")
        candidate_items = parsed.get("skill_candidates")
        if not isinstance(candidate_items, list):
            candidate_items = []
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
        if secondary_recall_enabled and not user_signals:
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
                recall_user_items = recall_parsed.get("user_facts")
                if not isinstance(recall_user_items, list):
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
            detections: List[Dict[str, Any]] = []

            output_format = self.detect_output_format_preference(user_message)
            if output_format:
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="preference",
                        semantic_key="output_format",
                        value=output_format,
                        confidence=0.88,
                        persistent=False,
                        latest_ts=latest_ts,
                        reason="用户明确表达输出格式偏好",
                        strong_signal=False,
                    )
                )

            language = self.detect_language_preference(user_message)
            if language:
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="preference",
                        semantic_key="language",
                        value=language,
                        confidence=0.88,
                        persistent=False,
                        latest_ts=latest_ts,
                        reason="用户明确表达语言偏好",
                        strong_signal=False,
                    )
                )

            style = self.detect_response_style_preference(user_message)
            if style:
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="preference",
                        semantic_key="response_style",
                        value=style,
                        confidence=0.9,
                        persistent=False,
                        latest_ts=latest_ts,
                        reason="用户明确表达回答风格偏好",
                        strong_signal=False,
                    )
                )

            food_preference = self.detect_food_preference_signal(user_message)
            if food_preference:
                food_key, food_value = food_preference
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="preference",
                        semantic_key=food_key,
                        value=food_value,
                        confidence=0.92,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确表达饮食偏好或禁忌",
                    )
                )

            for pattern in _EXPERIENCE_PATTERNS:
                match = pattern.search(user_message)
                if not match:
                    continue
                experience_value = self._normalize_preference_item(
                    match.group("item"), max_chars=40
                )
                if not experience_value:
                    continue
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="experience",
                        semantic_key="experience_background",
                        value=experience_value,
                        confidence=0.9,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确陈述过往经历或工作背景",
                    )
                )

            for pattern in _SKILL_PATTERNS:
                match = pattern.search(user_message)
                if not match:
                    continue
                skill_value = self._normalize_preference_item(match.group("item"), max_chars=32)
                if not skill_value:
                    continue
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="expertise",
                        semantic_key="expertise_strength",
                        value=skill_value,
                        confidence=0.9,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确陈述擅长或熟悉的能力",
                    )
                )

            for pattern in _LONG_TERM_GOAL_PATTERNS:
                match = pattern.search(user_message)
                if not match:
                    continue
                goal_value = self._normalize_preference_item(match.group("item"), max_chars=40)
                if not goal_value:
                    continue
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="goal",
                        semantic_key="long_term_goal",
                        value=goal_value,
                        confidence=0.86,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确陈述长期目标或计划",
                    )
                )

            for pattern in _BUDGET_PATTERNS:
                match = pattern.search(user_message)
                if not match:
                    continue
                budget_value = self._normalize_preference_item(match.group("item"), max_chars=24)
                if not budget_value:
                    continue
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="constraint",
                        semantic_key="budget_preference",
                        value=budget_value,
                        confidence=0.84,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确陈述预算或价位约束",
                    )
                )

            for pattern in _RELATIONSHIP_PATTERNS:
                match = pattern.search(user_message)
                if not match:
                    continue
                relation_label = _RELATIONSHIP_LABELS.get(
                    str(match.group("relation") or "").strip()
                )
                relation_name = self._normalize_preference_item(match.group("name"), max_chars=24)
                if not relation_label or not relation_name:
                    continue
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="relationship",
                        semantic_key=f"relationship_{relation_label}",
                        value=relation_name,
                        confidence=0.93,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确陈述人物关系",
                        predicate=relation_label,
                        obj=relation_name,
                        persons=[relation_name],
                    )
                )

            for pattern in _EVENT_PATTERNS:
                match = pattern.search(user_message)
                if not match:
                    continue
                event_time = self.normalize_text(match.group("time"), max_chars=64)
                event_value = self._normalize_preference_item(match.group("item"), max_chars=40)
                if not event_time or not event_value:
                    continue
                event_location = self._extract_event_location(event_value)
                event_topic = self._infer_event_topic(event_value)
                detections.append(
                    self._build_user_fact_signal(
                        fact_kind="event",
                        semantic_key="important_event",
                        value=event_value,
                        confidence=0.84,
                        persistent=True,
                        latest_ts=latest_ts,
                        reason="用户明确陈述带时间锚点的重要经历",
                        event_time=event_time,
                        location=event_location,
                        topic=event_topic,
                    )
                )

            for signal in detections:
                preference_key = str(signal.get("key") or "").strip()
                preference_value = str(signal.get("value") or "").strip()
                strong_signal = bool(signal.get("strong_signal"))
                if not preference_key or not preference_value:
                    continue
                if self._looks_like_question_artifact(
                    value=preference_value,
                    canonical_statement=str(signal.get("canonical_statement") or ""),
                ):
                    continue
                bucket = grouped.setdefault(
                    (preference_key, preference_value),
                    {
                        "count": 0,
                        "persistent": False,
                        "strong_signal": False,
                        "latest_ts": None,
                        "signal": signal,
                    },
                )
                bucket["count"] += 1
                bucket["persistent"] = bool(bucket["persistent"] or persistent)
                bucket["strong_signal"] = bool(bucket["strong_signal"] or strong_signal)
                if latest_ts and (bucket["latest_ts"] is None or latest_ts > bucket["latest_ts"]):
                    bucket["latest_ts"] = latest_ts
                bucket["signal"] = signal

        extracted: List[Dict[str, Any]] = []
        for (_preference_key, _preference_value), bucket in grouped.items():
            evidence_count = int(bucket["count"])
            is_persistent = bool(bucket["persistent"])
            strong_signal = bool(bucket.get("strong_signal"))
            if not is_persistent and not strong_signal and evidence_count < 2:
                continue

            latest_ts = bucket.get("latest_ts")
            signal = dict(bucket.get("signal") or {})
            signal["evidence_count"] = evidence_count
            signal["persistent"] = bool(signal.get("persistent") or is_persistent)
            signal["strong_signal"] = bool(signal.get("strong_signal") or strong_signal)
            signal["confidence"] = max(
                float(signal.get("confidence") or 0.0),
                (0.92 if strong_signal else 0.88 if is_persistent else 0.68),
            )
            signal["latest_ts"] = latest_ts.isoformat() if isinstance(latest_ts, datetime) else None
            signal["materialize_profile"] = self._should_materialize_user_fact(
                str(signal.get("fact_kind") or "preference"),
                bool(signal.get("persistent")),
            )
            extracted.append(signal)

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

    def extract_skill_candidates(
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
    ) -> tuple[List[MemoryObservationData], List[MemoryProjectionData]]:
        observations: List[MemoryObservationData] = []
        projections: List[MemoryProjectionData] = []
        if not user_id:
            return observations, projections

        source_event_indexes = list(range(max(len(turns) * 2, 0)))
        for signal in extracted_signals:
            key = str(signal.get("key") or "").strip()
            semantic_key = str(signal.get("semantic_key") or key).strip()
            value = str(signal.get("value") or "").strip()
            if not key or not value:
                continue
            fact_kind = self._normalize_user_fact_kind(signal.get("fact_kind"))
            canonical_statement = self._build_user_fact_canonical_statement(
                fact_kind=fact_kind,
                semantic_key=semantic_key,
                value=value,
                canonical_statement=signal.get("canonical_statement"),
                predicate=signal.get("predicate"),
                obj=signal.get("object"),
                event_time=signal.get("event_time"),
                topic=signal.get("topic"),
            )
            observation_key = self._stable_key(
                "user_fact",
                fact_kind,
                key,
                value,
                signal.get("event_time"),
                canonical_statement,
            )
            confidence = float(signal.get("confidence") or 0.78)
            importance = 0.9 if bool(signal.get("persistent")) else 0.72
            title = self._build_user_fact_title(
                fact_kind=fact_kind,
                semantic_key=semantic_key,
                value=value,
                canonical_statement=canonical_statement,
            )
            summary = canonical_statement
            details = str(signal.get("reason") or "").strip() or None
            observations.append(
                MemoryObservationData(
                    observation_key=observation_key,
                    observation_type="user_fact_signal",
                    title=title,
                    summary=summary,
                    details=details,
                    source_event_indexes=source_event_indexes,
                    confidence=confidence,
                    importance=importance,
                    metadata={
                        "fact_key": key,
                        "semantic_key": semantic_key,
                        "fact_value": value,
                        "fact_kind": fact_kind,
                        "identity_signature": signal.get("identity_signature"),
                        "canonical_statement": canonical_statement,
                        "predicate": signal.get("predicate"),
                        "object": signal.get("object"),
                        "event_time": signal.get("event_time"),
                        "persons": list(signal.get("persons") or []),
                        "entities": list(signal.get("entities") or []),
                        "location": signal.get("location"),
                        "topic": signal.get("topic"),
                        "persistent": bool(signal.get("persistent")),
                        "explicit_source": bool(signal.get("explicit_source")),
                        "evidence_count": int(signal.get("evidence_count") or 0),
                        "evidence_turns": list(signal.get("evidence_turns") or []),
                        "latest_turn_ts": signal.get("latest_ts"),
                        "reason": signal.get("reason"),
                    },
                )
            )
            should_project_profile = bool(
                signal.get(
                    "materialize_profile",
                    self._should_materialize_user_fact(
                        fact_kind,
                        bool(signal.get("persistent")),
                    ),
                )
            )
            if should_project_profile:
                projections.append(
                    MemoryProjectionData(
                        owner_type="user",
                        owner_id=user_id,
                        projection_type="user_profile",
                        projection_key=key,
                        title=title,
                        summary=summary,
                        details=details,
                        payload={
                            "key": key,
                            "semantic_key": semantic_key,
                            "value": value,
                            "fact_kind": fact_kind,
                            "identity_signature": signal.get("identity_signature"),
                            "canonical_statement": canonical_statement,
                            "predicate": signal.get("predicate"),
                            "object": signal.get("object"),
                            "event_time": signal.get("event_time"),
                            "persons": list(signal.get("persons") or []),
                            "entities": list(signal.get("entities") or []),
                            "location": signal.get("location"),
                            "topic": signal.get("topic"),
                            "confidence": confidence,
                            "importance": importance,
                            "persistent": bool(signal.get("persistent")),
                            "explicit_source": bool(signal.get("explicit_source")),
                            "evidence_count": int(signal.get("evidence_count") or 0),
                            "evidence_turns": list(signal.get("evidence_turns") or []),
                        },
                        source_observation_key=observation_key,
                    )
                )
            if fact_kind == "event":
                episode_key = self._build_user_episode_view_key(
                    stable_key=key,
                    canonical_statement=canonical_statement,
                    event_time=signal.get("event_time"),
                    value=value,
                )
                projections.append(
                    MemoryProjectionData(
                        owner_type="user",
                        owner_id=user_id,
                        projection_type="episode",
                        projection_key=episode_key,
                        title=self._build_user_episode_title(
                            canonical_statement=canonical_statement,
                            event_time=signal.get("event_time"),
                            topic=signal.get("topic"),
                            value=value,
                        ),
                        summary=canonical_statement,
                        details=details,
                        payload={
                            "key": key,
                            "semantic_key": semantic_key,
                            "value": value,
                            "fact_kind": fact_kind,
                            "identity_signature": signal.get("identity_signature"),
                            "canonical_statement": canonical_statement,
                            "predicate": signal.get("predicate"),
                            "object": signal.get("object"),
                            "event_time": signal.get("event_time"),
                            "persons": list(signal.get("persons") or []),
                            "entities": list(signal.get("entities") or []),
                            "location": signal.get("location"),
                            "topic": signal.get("topic"),
                            "confidence": confidence,
                            "importance": importance,
                            "persistent": bool(signal.get("persistent")),
                            "explicit_source": bool(signal.get("explicit_source")),
                            "source_entry_key": key,
                            "is_active": True,
                            "evidence_count": int(signal.get("evidence_count") or 0),
                            "evidence_turns": list(signal.get("evidence_turns") or []),
                        },
                        source_observation_key=observation_key,
                    )
                )
        return observations, projections

    def build_skill_candidate_observations(
        self,
        *,
        agent_id: str,
        agent_name: str,
        turns: List[Dict[str, Any]],
        extracted_agent_candidates: List[Dict[str, Any]],
    ) -> tuple[List[MemoryObservationData], List[MemoryProjectionData]]:
        observations: List[MemoryObservationData] = []
        projections: List[MemoryProjectionData] = []
        if not agent_id:
            return observations, projections

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
            observation_key = self._stable_key("skill_candidate", fingerprint, title)
            observations.append(
                MemoryObservationData(
                    observation_key=observation_key,
                    observation_type="skill_candidate",
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
                        "evidence_turns": list(candidate.get("evidence_turns") or []),
                        "latest_turn_ts": candidate.get("latest_ts"),
                    },
                )
            )
            projections.append(
                MemoryProjectionData(
                    owner_type="agent",
                    owner_id=agent_id,
                    projection_type="skill_candidate",
                    projection_key=fingerprint,
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
                        "evidence_turns": list(candidate.get("evidence_turns") or []),
                        "latest_turn_ts": candidate.get("latest_ts"),
                    },
                    source_observation_key=observation_key,
                )
            )
        return observations, projections


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


def extract_skill_candidates(
    turns: List[Dict[str, str]],
    agent_name: str,
) -> List[Dict[str, Any]]:
    return get_session_observation_builder().extract_skill_candidates(turns, agent_name)


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
