"""Normalization helpers for knowledge-base indexing and retrieval text."""

from __future__ import annotations

import re
from typing import Any, Iterable, List

_CONTROL_TOKEN_RE = re.compile(r"<\|[^>]+\|>")
_MARKDOWN_HEADING_RE = re.compile(r"(?m)^\s*#{1,6}\s*")
_MARKDOWN_LIST_RE = re.compile(r"(?m)^\s*(?:[-*]|\d+[.)])\s+")
_BOLD_MARK_RE = re.compile(r"\*\*(.*?)\*\*|__(.*?)__")
_INLINE_CODE_RE = re.compile(r"`{1,3}")
_SEGMENT_HEADER_RE = re.compile(r"(?im)^\s*segment\s+\d{4}s-\d{4}s:\s*")
_EXTRA_SPACES_RE = re.compile(r"[ \t]+")
_EXTRA_BLANK_LINES_RE = re.compile(r"\n{3,}")

_AUDIO_LABEL = "Audio Transcript:"
_VISUAL_LABEL = "Visual Analysis:"
_SUMMARY_LABEL = "Video Summary:"
_DETAIL_LABEL = "Segment Details:"
_KNOWN_SECTION_LABELS = {
    _AUDIO_LABEL.lower(),
    _VISUAL_LABEL.lower(),
    _SUMMARY_LABEL.lower(),
    _DETAIL_LABEL.lower(),
    "summary:",
    "transcript:",
    "scene details:",
}


def _strip_markdown(text: str) -> str:
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _CONTROL_TOKEN_RE.sub(" ", cleaned)
    cleaned = _MARKDOWN_HEADING_RE.sub("", cleaned)
    cleaned = _MARKDOWN_LIST_RE.sub("", cleaned)
    cleaned = _SEGMENT_HEADER_RE.sub("", cleaned)
    cleaned = _INLINE_CODE_RE.sub("", cleaned)
    cleaned = _BOLD_MARK_RE.sub(lambda match: match.group(1) or match.group(2) or "", cleaned)
    return cleaned


def _normalize_text_block(text: str) -> str:
    cleaned = _strip_markdown(text)
    normalized_lines: List[str] = []
    for raw_line in cleaned.splitlines():
        line = _EXTRA_SPACES_RE.sub(" ", raw_line).strip()
        if not line:
            if normalized_lines and normalized_lines[-1]:
                normalized_lines.append("")
            continue
        if line.lower() in _KNOWN_SECTION_LABELS:
            continue
        normalized_lines.append(line)

    normalized = "\n".join(normalized_lines).strip()
    normalized = _EXTRA_BLANK_LINES_RE.sub("\n\n", normalized)
    return normalized.strip()


def _extract_section(text: str, label: str, end_labels: Iterable[str]) -> str:
    source = str(text or "")
    start = source.find(label)
    if start < 0:
        return ""
    body = source[start + len(label) :]
    end_positions = [body.find(candidate) for candidate in end_labels]
    end_positions = [position for position in end_positions if position >= 0]
    if end_positions:
        body = body[: min(end_positions)]
    return body.strip()


def _normalize_multimodal_text(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    audio_text = _extract_section(source, _AUDIO_LABEL, (_VISUAL_LABEL,))
    visual_text = _extract_section(source, _VISUAL_LABEL, ())
    summary_source = visual_text or source
    summary_text = _extract_section(summary_source, _SUMMARY_LABEL, (_DETAIL_LABEL,))
    detail_text = _extract_section(summary_source, _DETAIL_LABEL, ())

    parts: List[str] = []
    for candidate in (
        summary_text,
        audio_text,
        detail_text,
        visual_text if not summary_text and not detail_text else "",
    ):
        normalized = _normalize_text_block(candidate)
        if not normalized:
            continue
        if normalized not in parts:
            parts.append(normalized)

    return "\n\n".join(parts).strip()


def normalize_knowledge_text(text: Any) -> str:
    """Normalize extracted/indexed knowledge text for retrieval use."""
    raw = str(text or "").strip()
    if not raw:
        return ""

    if any(label in raw for label in (_AUDIO_LABEL, _VISUAL_LABEL, _SUMMARY_LABEL, _DETAIL_LABEL)):
        normalized = _normalize_multimodal_text(raw)
        if normalized:
            return normalized

    return _normalize_text_block(raw)


__all__ = ["normalize_knowledge_text"]
