"""Builders for durable session-memory records and compatibility payloads."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_SESSION_MEMORY_ITEM_MAX_CHARS = 320


def _normalize_session_memory_text(
    text: Any,
    max_chars: int = _SESSION_MEMORY_ITEM_MAX_CHARS,
) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def _normalize_memory_key(value: Any, max_chars: int = 64) -> Optional[str]:
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


def _coerce_confidence(value: Any, default: float = 0.7) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(0.0, min(1.0, parsed))


def dedupe_user_preference_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the strongest user-preference signal per key."""

    deduped_signals_by_key: Dict[str, Dict[str, Any]] = {}
    for signal in signals:
        signal_key = str(signal.get("key") or "").strip()
        signal_value = str(signal.get("value") or "").strip()
        if not signal_key or not signal_value:
            continue
        existing_signal = deduped_signals_by_key.get(signal_key)
        if not existing_signal:
            deduped_signals_by_key[signal_key] = signal
            continue

        current_score = (
            int(bool(signal.get("persistent"))),
            int(signal.get("evidence_count") or 0),
            str(signal.get("latest_ts") or ""),
        )
        existing_score = (
            int(bool(existing_signal.get("persistent"))),
            int(existing_signal.get("evidence_count") or 0),
            str(existing_signal.get("latest_ts") or ""),
        )
        if current_score >= existing_score:
            deduped_signals_by_key[signal_key] = signal

    return list(deduped_signals_by_key.values())


def build_user_preference_memory_content(signal: Dict[str, Any]) -> str:
    return f"user.preference.{signal['key']}={signal['value']}"


def build_user_preference_seed_facts(signal: Dict[str, Any]) -> List[Dict[str, Any]]:
    preference_key = _normalize_memory_key(signal.get("key"), max_chars=80)
    preference_value = _normalize_session_memory_text(signal.get("value", ""), max_chars=120)
    if not preference_key or not preference_value:
        return []

    confidence = _coerce_confidence(signal.get("confidence"), default=0.78)
    importance = 0.9 if bool(signal.get("persistent")) else 0.74
    return [
        {
            "key": f"user.preference.{preference_key}",
            "value": preference_value,
            "category": "user_preference",
            "confidence": confidence,
            "importance": importance,
            "source": "session_llm",
        }
    ]


def split_user_preference_content(content: str) -> Tuple[Optional[str], Optional[str]]:
    normalized = str(content or "").strip()
    if not normalized.lower().startswith("user.preference.") or "=" not in normalized:
        return None, None

    left, right = normalized.split("=", 1)
    key = left.replace("user.preference.", "", 1).strip()
    value = right.strip()
    if not key or not value:
        return None, None
    return key, value


def build_agent_candidate_content(candidate: Dict[str, Any]) -> str:
    steps_raw = candidate.get("steps") or []
    normalized_steps: List[str] = []
    for step in steps_raw:
        normalized_step = _normalize_session_memory_text(step, max_chars=72)
        if normalized_step and normalized_step not in normalized_steps:
            normalized_steps.append(normalized_step)
    steps = normalized_steps[:4]
    step_text = " | ".join(steps)

    title = _normalize_session_memory_text(candidate.get("title", ""), max_chars=72)
    topic = _normalize_session_memory_text(candidate.get("topic", ""), max_chars=72)
    summary = _normalize_session_memory_text(candidate.get("summary", ""), max_chars=180)
    lines: List[str] = []
    if title:
        lines.append(f"interaction.sop.title={title}")
    if topic and topic != title:
        lines.append(f"interaction.sop.topic={topic}")
    lines.append(f"interaction.sop.steps={step_text}")
    if summary:
        lines.append(f"interaction.sop.summary={summary}")
    applicability = _normalize_session_memory_text(
        candidate.get("applicability", ""), max_chars=120
    )
    if applicability:
        lines.append(f"interaction.sop.applicability={applicability}")
    avoid = _normalize_session_memory_text(candidate.get("avoid", ""), max_chars=120)
    if avoid:
        lines.append(f"interaction.sop.avoid={avoid}")
    agent_name = str(candidate.get("agent_name") or "").strip()
    if agent_name:
        lines.append(f"agent.identity.name={agent_name}")
    return "\n".join(lines)


def build_agent_candidate_seed_facts(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    confidence = _coerce_confidence(candidate.get("confidence"), default=0.72)
    importance = 0.78
    topic = _normalize_session_memory_text(candidate.get("topic", ""), max_chars=72)
    title = _normalize_session_memory_text(candidate.get("title", ""), max_chars=72)

    def _append_fact(key: str, value: Any, *, category: str) -> None:
        normalized_value = _normalize_session_memory_text(value, max_chars=260)
        if not key or not normalized_value:
            return
        facts.append(
            {
                "key": key,
                "value": normalized_value,
                "category": category,
                "confidence": confidence,
                "importance": importance,
                "source": "session_llm",
            }
        )

    _append_fact("interaction.sop.title", title, category="interaction")
    if topic and topic != title:
        _append_fact("interaction.sop.topic", topic, category="interaction")
    steps = candidate.get("steps")
    if isinstance(steps, list):
        steps_value = " | ".join(
            _normalize_session_memory_text(step, max_chars=72) for step in steps if step
        )
        _append_fact("interaction.sop.steps", steps_value, category="interaction")
    _append_fact("interaction.sop.summary", candidate.get("summary"), category="interaction")
    _append_fact(
        "interaction.sop.applicability",
        candidate.get("applicability"),
        category="interaction",
    )
    _append_fact("interaction.sop.avoid", candidate.get("avoid"), category="interaction")
    _append_fact("agent.identity.name", candidate.get("agent_name"), category="agent")
    return facts
