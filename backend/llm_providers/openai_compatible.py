"""Helpers for OpenAI-compatible provider integrations."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.parse import urlparse


def build_api_url(base_url: str, path: str) -> str:
    """Build an OpenAI-compatible API URL without duplicating `/v1`."""
    normalized_path = path if path.startswith("/") else f"/{path}"
    base = str(base_url or "").rstrip("/")
    if not base:
        return normalized_path
    if base.endswith(normalized_path):
        return base
    if base.endswith("/v1"):
        return f"{base}{normalized_path}"
    return f"{base}/v1{normalized_path}"


def build_api_url_candidates(base_url: str, path: str) -> List[str]:
    """Build a small deduplicated candidate list for non-standard gateways."""
    normalized_path = path if path.startswith("/") else f"/{path}"
    base = str(base_url or "").rstrip("/")
    candidates: List[str] = []

    def _add(value: str) -> None:
        candidate = str(value or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    primary = build_api_url(base, normalized_path)
    _add(primary)
    if not base:
        return candidates

    if base.endswith("/v1"):
        root = base[:-3].rstrip("/")
        if root:
            _add(f"{root}{normalized_path}")
        return candidates

    _add(f"{base}{normalized_path}")
    parsed = urlparse(base)
    base_path = (parsed.path or "").rstrip("/")
    has_api_segment = base_path == "/api" or "/api/" in f"{base_path}/"
    if not normalized_path.startswith("/api/") and not has_api_segment:
        _add(f"{base}/api{normalized_path}")

    return candidates


def merge_extra_body(payload: Dict[str, Any], extra_body: Any) -> Dict[str, Any]:
    """Merge OpenAI SDK-style `extra_body` into the actual request payload."""
    if not isinstance(extra_body, Mapping):
        return payload

    merged = dict(payload or {})
    for key, value in extra_body.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = {**dict(merged[key]), **dict(value)}
        else:
            merged[key] = value
    return merged


def normalize_message_content(content: Any) -> str:
    """Normalize OpenAI-compatible message content into plain text."""
    if isinstance(content, list):
        text_parts: List[str] = []
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                text_parts.append(part)
        return "".join(text_parts).strip()
    return (str(content) if content is not None else "").strip()


def extract_chat_completion_content(data: Mapping[str, Any]) -> str:
    """Extract final model text from an OpenAI-compatible chat response."""
    payload: Any = dict(data or {})
    if isinstance(payload.get("output"), str):
        wrapped_output = str(payload.get("output") or "").strip()
        if wrapped_output:
            try:
                parsed_output = json.loads(wrapped_output)
            except json.JSONDecodeError:
                return wrapped_output
            if isinstance(parsed_output, Mapping) and "choices" in parsed_output:
                payload = parsed_output
            else:
                return wrapped_output

    choice = {}
    if isinstance(payload, Mapping):
        choices = payload.get("choices")
        if isinstance(choices, Sequence) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, Mapping):
                choice = dict(first_choice)

    message = choice.get("message")
    if not isinstance(message, Mapping):
        message = {}

    for key in ("content", "reasoning_content", "reasoning", "thinking", "text"):
        normalized = normalize_message_content(message.get(key))
        if normalized:
            return normalized

    if isinstance(choice.get("text"), str):
        return str(choice.get("text")).strip()
    return ""


def normalize_model_name_for_match(model_name: str) -> str:
    """Normalize model identifiers for loose provider/model matching."""
    normalized = str(model_name or "").strip().lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def model_match_keys(model_name: str) -> set[str]:
    """Generate a few stable comparison keys for model identifiers."""
    normalized = normalize_model_name_for_match(model_name)
    if not normalized:
        return set()
    keys = {normalized}
    if "/" in normalized:
        keys.add(normalized.split("/")[-1])
    return {key for key in keys if key}


def model_names_match(left: str, right: str) -> bool:
    """Check whether two model identifiers refer to the same model."""
    left_keys = model_match_keys(left)
    right_keys = model_match_keys(right)
    return bool(left_keys and right_keys and left_keys.intersection(right_keys))


def normalize_rerank_scores(items: Iterable[Tuple[int, float]]) -> List[Tuple[int, float]]:
    """Normalize rerank scores into [0, 1] while preserving ordering."""
    parsed = [(int(index), float(score)) for index, score in items]
    if not parsed:
        return []

    scores = [score for _, score in parsed]
    if all(0.0 <= score <= 1.0 for score in scores):
        normalized = parsed
    else:
        min_score = min(scores)
        max_score = max(scores)
        if max_score - min_score <= 1e-9:
            normalized = [(index, 0.5) for index, _ in parsed]
        else:
            normalized = [
                (index, (score - min_score) / (max_score - min_score)) for index, score in parsed
            ]

    normalized.sort(key=lambda pair: pair[1], reverse=True)
    return normalized
