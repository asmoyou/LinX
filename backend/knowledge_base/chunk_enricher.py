"""LLM-driven chunk enrichment for improved retrieval.

Extracts keywords, generates questions, and produces summaries for each
document chunk. Enriched text is combined with original for better embeddings.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from shared.config import get_config

logger = logging.getLogger(__name__)

# Prompt templates inspired by RAGFlow
KEYWORD_PROMPT = """Extract the top {topn} keywords from the following text.
The keywords should be in the same language as the text.
Output ONLY the keywords, comma-separated, one line, no numbering.
Do NOT output thinking, analysis, or reasoning process.

Text:
{text}

Keywords:"""

QUESTION_PROMPT = """Based on the following text, propose {topn} questions that can be answered by this text.
Questions should be in the same language as the text.
Output one question per line, no numbering.
Do NOT output thinking, analysis, or reasoning process.

Text:
{text}

Questions:"""

SUMMARY_PROMPT = """Write a concise summary (2-3 sentences) of the following text.
The summary should be in the same language as the text.
Do NOT output thinking, analysis, or reasoning process.

Text:
{text}

Summary:"""


@dataclass
class EnrichmentResult:
    """Result of chunk enrichment."""

    keywords: List[str]
    questions: List[str]
    summary: str
    enriched_text: str


class ChunkEnricher:
    """Enrich document chunks with LLM-generated metadata."""

    DEFAULT_MAX_TOKENS = 1024
    MIN_MAX_TOKENS = 64
    MAX_MAX_TOKENS = 8192

    def __init__(self):
        """Initialize chunk enricher with config."""
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}
        enrichment_cfg = kb_config.get("enrichment", {})

        self.keywords_topn = enrichment_cfg.get("keywords_topn", 5)
        self.questions_topn = enrichment_cfg.get("questions_topn", 3)
        self.generate_summary = enrichment_cfg.get("generate_summary", True)
        self.temperature = enrichment_cfg.get("temperature", 0.2)
        self.batch_size = enrichment_cfg.get("batch_size", 5)

        # Read enrichment-specific model/provider from KB config
        self.provider_name = str(enrichment_cfg.get("provider", "ollama")).strip() or "ollama"
        self.model_name = str(enrichment_cfg.get("model", "qwen3-vl:30b")).strip() or "qwen3-vl:30b"

        # Resolve base_url from DB (primary) or config.yaml (fallback)
        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self.provider_name)
        self.base_url = provider_cfg.get("base_url", "http://localhost:11434")
        self.api_key = provider_cfg.get("api_key")
        self.max_tokens = self._resolve_max_tokens(enrichment_cfg, provider_cfg)

        # Determine API format from protocol
        protocol = provider_cfg.get(
            "protocol", "ollama" if self.provider_name == "ollama" else "openai_compatible"
        )
        self.api_format = "ollama" if protocol == "ollama" else "openai"

        logger.info(
            "ChunkEnricher initialized",
            extra={
                "keywords_topn": self.keywords_topn,
                "questions_topn": self.questions_topn,
                "provider": self.provider_name,
                "model": self.model_name,
                "base_url": self.base_url,
                "api_format": self.api_format,
                "max_tokens": self.max_tokens,
            },
        )

    @classmethod
    def _normalize_max_tokens(cls, value: Any, default: int) -> int:
        """Normalize max tokens value with bounded safe fallback."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(cls.MIN_MAX_TOKENS, min(parsed, cls.MAX_MAX_TOKENS))

    def _resolve_model_max_output_tokens(self, provider_cfg: dict) -> Optional[int]:
        """Try to read max output tokens from provider model metadata."""
        model_metadata = provider_cfg.get("model_metadata")
        if not isinstance(model_metadata, dict):
            return None

        model_meta = model_metadata.get(self.model_name)
        if not isinstance(model_meta, dict):
            # Fallback: case-insensitive model key match.
            lowered = self.model_name.casefold()
            for key, value in model_metadata.items():
                if isinstance(key, str) and key.casefold() == lowered and isinstance(value, dict):
                    model_meta = value
                    break

        if not isinstance(model_meta, dict):
            return None

        candidate = model_meta.get("max_output_tokens")
        if candidate is None:
            return None
        return self._normalize_max_tokens(candidate, self.DEFAULT_MAX_TOKENS)

    def _resolve_max_tokens(self, enrichment_cfg: dict, provider_cfg: dict) -> int:
        """Resolve runtime max tokens for enrichment generation."""
        explicit = enrichment_cfg.get("max_tokens")
        if explicit is not None:
            try:
                explicit_int = int(explicit)
            except (TypeError, ValueError):
                explicit_int = self.DEFAULT_MAX_TOKENS
            if explicit_int > 0:
                return self._normalize_max_tokens(explicit_int, self.DEFAULT_MAX_TOKENS)

        metadata_value = self._resolve_model_max_output_tokens(provider_cfg)
        if metadata_value is not None:
            return metadata_value

        return self.DEFAULT_MAX_TOKENS

    async def enrich(self, chunk_text: str) -> EnrichmentResult:
        """Enrich a single chunk with keywords, questions, and summary.

        Args:
            chunk_text: Original chunk text

        Returns:
            EnrichmentResult with extracted metadata
        """
        # Extract keywords
        keywords = await self._extract_keywords(chunk_text)

        # Generate questions
        questions = await self._generate_questions(chunk_text)

        # Generate summary
        summary = ""
        if self.generate_summary:
            summary = await self._generate_summary(chunk_text)

        # Build enriched text for embedding
        enriched_parts = [chunk_text]
        if keywords:
            enriched_parts.append("Keywords: " + ", ".join(keywords))
        if questions:
            enriched_parts.append("Questions: " + " ".join(questions))

        enriched_text = "\n".join(enriched_parts)

        return EnrichmentResult(
            keywords=keywords,
            questions=questions,
            summary=summary,
            enriched_text=enriched_text,
        )

    async def enrich_batch(
        self,
        chunks: List[str],
        chunk_metadata: List[dict],
    ) -> Tuple[List[str], List[dict]]:
        """Enrich a batch of chunks, returning enriched text and updated metadata.

        Args:
            chunks: Original chunk texts
            chunk_metadata: Original chunk metadata

        Returns:
            Tuple of (enriched_chunks, updated_metadata)
        """
        enriched_chunks = []
        updated_metadata = []

        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_meta = chunk_metadata[i : i + self.batch_size]

            # Process batch concurrently
            results = await asyncio.gather(
                *[self.enrich(chunk) for chunk in batch],
                return_exceptions=True,
            )

            for j, (result, meta) in enumerate(zip(results, batch_meta)):
                if isinstance(result, Exception):
                    logger.warning(f"Enrichment failed for chunk {i + j}: {result}")
                    enriched_chunks.append(batch[j])
                    updated_metadata.append(meta)
                else:
                    enriched_chunks.append(result.enriched_text)
                    updated_meta = dict(meta)
                    updated_meta["keywords"] = result.keywords
                    updated_meta["questions"] = result.questions
                    updated_meta["summary"] = result.summary
                    updated_metadata.append(updated_meta)

        return enriched_chunks, updated_metadata

    def enrich_batch_sync(
        self,
        chunks: List[str],
        chunk_metadata: List[dict],
    ) -> Tuple[List[str], List[dict]]:
        """Synchronous wrapper for enrich_batch, for use in threaded worker.

        Args:
            chunks: Original chunk texts
            chunk_metadata: Original chunk metadata

        Returns:
            Tuple of (enriched_chunks, updated_metadata)
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.enrich_batch(chunks, chunk_metadata))
        finally:
            loop.close()

    async def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text using LLM.

        Args:
            text: Input text

        Returns:
            List of keyword strings
        """
        prompt = KEYWORD_PROMPT.format(topn=self.keywords_topn, text=text[:2000])
        response = await self._llm_generate(prompt)
        if not response:
            return []

        cleaned = self._extract_labeled_payload(response, labels=["keywords", "关键词"])
        # Support both comma and line-based outputs.
        raw_items = re.split(r"[,\n，、;；]+", cleaned)
        keywords: List[str] = []
        seen: set[str] = set()

        for item in raw_items:
            keyword = self._normalize_list_item(item)
            if not keyword:
                continue
            if self._looks_like_reasoning(keyword):
                continue

            # Guardrail: keywords should stay concise.
            if len(keyword) > 40:
                continue

            canonical = keyword.casefold()
            if canonical in seen:
                continue
            seen.add(canonical)
            keywords.append(keyword)

            if len(keywords) >= self.keywords_topn:
                break

        return keywords

    async def _generate_questions(self, text: str) -> List[str]:
        """Generate questions answerable by the text.

        Args:
            text: Input text

        Returns:
            List of question strings
        """
        prompt = QUESTION_PROMPT.format(topn=self.questions_topn, text=text[:2000])
        response = await self._llm_generate(prompt)
        if not response:
            return []

        cleaned = self._extract_labeled_payload(response, labels=["questions", "问题"])

        # Prefer one-question-per-line, then fallback to sentence splitting.
        raw_items = [line for line in cleaned.splitlines() if line.strip()]
        if len(raw_items) <= 1:
            raw_items = re.split(r"(?<=[？?])\s+", cleaned)

        questions: List[str] = []
        seen: set[str] = set()

        for item in raw_items:
            question = self._normalize_list_item(item)
            if not question:
                continue
            if self._looks_like_reasoning(question):
                continue

            canonical = question.casefold()
            if canonical in seen:
                continue
            seen.add(canonical)
            questions.append(question)

            if len(questions) >= self.questions_topn:
                break

        return questions

    async def _generate_summary(self, text: str) -> str:
        """Generate a concise summary of the text.

        Args:
            text: Input text

        Returns:
            Summary string
        """
        prompt = SUMMARY_PROMPT.format(text=text[:2000])
        response = await self._llm_generate(prompt)
        if not response:
            return ""

        cleaned = self._extract_labeled_payload(response, labels=["summary", "摘要", "总结"])
        return cleaned[:800]

    @staticmethod
    def _normalize_list_item(value: str) -> str:
        """Normalize one list-like item returned by the model."""
        item = (value or "").strip()
        if not item:
            return ""

        item = re.sub(r"^\s*[-*•]+\s*", "", item)
        item = re.sub(r"^\s*\d+[\.\):：]\s*", "", item)
        item = re.sub(
            r"^\s*(?:keywords?|questions?|summary|关键词|问题|摘要|总结)\s*[:：]\s*",
            "",
            item,
            flags=re.IGNORECASE,
        )
        item = item.strip().strip("\"'`")
        return item

    @staticmethod
    def _looks_like_reasoning(text: str) -> bool:
        """Heuristic check to filter reasoning/process lines."""
        if not text:
            return False
        return bool(
            re.match(
                r"^\s*(?:思考|分析|推理|reasoning|thinking|analysis|let'?s think)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    def _extract_labeled_payload(self, raw: str, labels: List[str]) -> str:
        """Strip reasoning noise and prefer the final labeled answer payload."""
        cleaned = self._strip_reasoning_noise(raw)
        if not cleaned:
            return ""

        # If the model still echoes label sections, keep text after the last matching label marker.
        last_marker_end = -1
        for label in labels:
            marker = re.compile(rf"(?i)\b{re.escape(label)}\s*[:：]")
            for match in marker.finditer(cleaned):
                last_marker_end = max(last_marker_end, match.end())

        if last_marker_end > -1:
            return cleaned[last_marker_end:].strip()

        return cleaned.strip()

    def _strip_reasoning_noise(self, raw: str) -> str:
        """Remove common reasoning blocks/tags from model output."""
        text = (raw or "").strip()
        if not text:
            return ""

        # Remove explicit reasoning tags/blocks often emitted by thinking models.
        text = re.sub(r"(?is)<think>.*?</think>", " ", text)
        text = re.sub(r"(?is)<analysis>.*?</analysis>", " ", text)
        text = re.sub(r"(?is)```(?:thinking|analysis)[\s\S]*?```", " ", text)

        lines: List[str] = []
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if self._looks_like_reasoning(candidate):
                continue
            lines.append(candidate)

        return "\n".join(lines).strip()

    async def _llm_generate(self, prompt: str) -> str:
        """Call LLM for text generation. Supports Ollama and OpenAI-compatible APIs.

        Args:
            prompt: Input prompt

        Returns:
            Generated text
        """
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if self.api_format == "openai":
                    # vLLM / OpenAI-compatible API
                    payload = {
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                    }
                    headers = {"Content-Type": "application/json"}
                    if self.api_key:
                        headers["Authorization"] = f"Bearer {self.api_key}"
                    async with session.post(
                        f"{self.base_url}/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                        choices = data.get("choices", [])
                        if choices:
                            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                            content = message.get("content", "")
                            reasoning = (
                                message.get("reasoning_content")
                                or message.get("reasoning")
                                or message.get("thinking")
                                or ""
                            )

                            # Knowledge enrichment must consume final content only.
                            # Reasoning/thinking is intentionally excluded to avoid data pollution.
                            if isinstance(content, list):
                                text_parts = []
                                for part in content:
                                    if isinstance(part, dict) and part.get("type") == "text":
                                        text_parts.append(str(part.get("text", "")))
                                content = "".join(text_parts)

                            content = str(content or "").strip()
                            if not content and reasoning:
                                logger.warning(
                                    "Enrichment response contained reasoning but empty content; reasoning discarded",
                                    extra={
                                        "provider": self.provider_name,
                                        "model": self.model_name,
                                    },
                                )
                            return content
                        return ""
                else:
                    # Ollama API
                    payload = {
                        "model": self.model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": self.max_tokens,
                        },
                    }
                    headers = {"Content-Type": "application/json"}
                    if self.api_key:
                        headers["Authorization"] = f"Bearer {self.api_key}"
                    async with session.post(
                        f"{self.base_url}/api/generate",
                        json=payload,
                        headers=headers,
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                        content = data.get("response", "")
                        thinking = data.get("thinking", "")
                        content = str(content or "").strip()

                        if not content and thinking:
                            logger.warning(
                                "Enrichment response contained thinking but empty response; thinking discarded",
                                extra={
                                    "provider": self.provider_name,
                                    "model": self.model_name,
                                },
                            )
                        return content

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return ""


# Singleton instance
_chunk_enricher: Optional[ChunkEnricher] = None
_chunk_enricher_signature: Optional[str] = None


def _build_chunk_enricher_signature() -> str:
    """Build a config signature so singleton refreshes after runtime config updates."""
    try:
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}
        enrichment_cfg = kb_config.get("enrichment", {})
        provider_name = str(enrichment_cfg.get("provider", "ollama")).strip().lower() or "ollama"

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(provider_name)
        protocol = provider_cfg.get(
            "protocol",
            "ollama" if provider_name == "ollama" else "openai_compatible",
        )
        model_name = enrichment_cfg.get("model", "qwen3-vl:30b")
        model_max_output_tokens = None
        model_metadata = provider_cfg.get("model_metadata")
        if isinstance(model_metadata, dict):
            model_meta = model_metadata.get(model_name)
            if isinstance(model_meta, dict):
                model_max_output_tokens = model_meta.get("max_output_tokens")

        payload = {
            "provider": provider_name,
            "model": model_name,
            "keywords_topn": enrichment_cfg.get("keywords_topn", 5),
            "questions_topn": enrichment_cfg.get("questions_topn", 3),
            "generate_summary": bool(enrichment_cfg.get("generate_summary", True)),
            "temperature": enrichment_cfg.get("temperature", 0.2),
            "batch_size": enrichment_cfg.get("batch_size", 5),
            "max_tokens": enrichment_cfg.get("max_tokens", 0),
            "model_max_output_tokens": model_max_output_tokens,
            "base_url": provider_cfg.get("base_url"),
            "protocol": protocol,
            "timeout": provider_cfg.get("timeout"),
            "has_api_key": bool(provider_cfg.get("api_key")),
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return ""


def get_chunk_enricher() -> ChunkEnricher:
    """Get or create the chunk enricher singleton.

    Returns:
        ChunkEnricher instance
    """
    global _chunk_enricher, _chunk_enricher_signature
    signature = _build_chunk_enricher_signature()
    if _chunk_enricher is None or signature != _chunk_enricher_signature:
        _chunk_enricher = ChunkEnricher()
        _chunk_enricher_signature = signature
    return _chunk_enricher


def reset_chunk_enricher() -> None:
    """Reset enricher singleton for tests or explicit runtime refresh."""
    global _chunk_enricher, _chunk_enricher_signature
    _chunk_enricher = None
    _chunk_enricher_signature = None
