"""LLM-driven chunk enrichment for improved retrieval.

Extracts keywords, generates questions, and produces summaries for each
document chunk. Enriched text is combined with original for better embeddings.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from shared.config import get_config

logger = logging.getLogger(__name__)

# Prompt templates inspired by RAGFlow
KEYWORD_PROMPT = """Extract the top {topn} keywords from the following text.
The keywords should be in the same language as the text.
Output ONLY the keywords, comma-separated, one line, no numbering.

Text:
{text}

Keywords:"""

QUESTION_PROMPT = """Based on the following text, propose {topn} questions that can be answered by this text.
Questions should be in the same language as the text.
Output one question per line, no numbering.

Text:
{text}

Questions:"""

SUMMARY_PROMPT = """Write a concise summary (2-3 sentences) of the following text.
The summary should be in the same language as the text.

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
        self.provider_name = enrichment_cfg.get("provider", "ollama")
        self.model_name = enrichment_cfg.get("model", "qwen3-vl:30b")

        # Resolve base_url from DB (primary) or config.yaml (fallback)
        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self.provider_name)
        self.base_url = provider_cfg.get("base_url", "http://localhost:11434")
        self.api_key = provider_cfg.get("api_key")

        # Determine API format from protocol
        protocol = provider_cfg.get("protocol", "ollama" if self.provider_name == "ollama" else "openai_compatible")
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
            },
        )

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

        # Parse comma-separated keywords
        keywords = [k.strip() for k in response.split(",") if k.strip()]
        return keywords[: self.keywords_topn]

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

        # Parse line-separated questions
        questions = [q.strip() for q in response.strip().split("\n") if q.strip()]
        # Remove numbering if present
        cleaned = []
        for q in questions:
            # Strip leading numbers like "1." or "1)"
            stripped = q.lstrip("0123456789.-) ")
            if stripped:
                cleaned.append(stripped)
        return cleaned[: self.questions_topn]

    async def _generate_summary(self, text: str) -> str:
        """Generate a concise summary of the text.

        Args:
            text: Input text

        Returns:
            Summary string
        """
        prompt = SUMMARY_PROMPT.format(text=text[:2000])
        response = await self._llm_generate(prompt)
        return response.strip() if response else ""

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
                        "max_tokens": 512,
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
                            return choices[0].get("message", {}).get("content", "")
                        return ""
                else:
                    # Ollama API
                    payload = {
                        "model": self.model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": 512,
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
                        if not content and thinking:
                            content = thinking
                        return content

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return ""


# Singleton instance
_chunk_enricher: Optional[ChunkEnricher] = None


def get_chunk_enricher() -> ChunkEnricher:
    """Get or create the chunk enricher singleton.

    Returns:
        ChunkEnricher instance
    """
    global _chunk_enricher
    if _chunk_enricher is None:
        _chunk_enricher = ChunkEnricher()
    return _chunk_enricher
