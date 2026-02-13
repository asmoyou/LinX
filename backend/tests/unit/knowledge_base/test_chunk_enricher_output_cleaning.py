"""Tests for enrichment output cleanup against thinking/reasoning pollution."""

import pytest

from knowledge_base.chunk_enricher import ChunkEnricher


def _build_enricher() -> ChunkEnricher:
    """Create a minimal enricher instance without running full config init."""
    enricher = ChunkEnricher.__new__(ChunkEnricher)
    enricher.keywords_topn = 5
    enricher.questions_topn = 3
    return enricher


@pytest.mark.asyncio
async def test_extract_keywords_strips_thinking_blocks() -> None:
    enricher = _build_enricher()

    async def fake_generate(_prompt: str) -> str:
        return (
            "<think>先分析文本重点，再组织关键词。</think>\n"
            "Keywords: 冠脉检测，冠状动脉钙化评分, 风险评估, CTA筛查"
        )

    enricher._llm_generate = fake_generate  # type: ignore[attr-defined]

    keywords = await enricher._extract_keywords("test text")
    assert keywords == ["冠脉检测", "冠状动脉钙化评分", "风险评估", "CTA筛查"]


@pytest.mark.asyncio
async def test_generate_questions_ignores_reasoning_lines() -> None:
    enricher = _build_enricher()

    async def fake_generate(_prompt: str) -> str:
        return (
            "思考：需要先提炼主题再构造问题。\n"
            "Questions:\n"
            "1. 冠脉CTA适用于哪些高危人群？\n"
            "2) 钙化评分与事件风险有何关系？\n"
            "- 如何结合血脂指标评估风险？"
        )

    enricher._llm_generate = fake_generate  # type: ignore[attr-defined]

    questions = await enricher._generate_questions("test text")
    assert questions == [
        "冠脉CTA适用于哪些高危人群？",
        "钙化评分与事件风险有何关系？",
        "如何结合血脂指标评估风险？",
    ]


@pytest.mark.asyncio
async def test_generate_summary_drops_think_and_keeps_summary() -> None:
    enricher = _build_enricher()

    async def fake_generate(_prompt: str) -> str:
        return (
            "<think>先给出推理过程，再给总结。</think>\n"
            "Summary: 该表用于冠脉风险分层，关键指标包括钙化评分、"
            "血脂异常与既往病史。"
        )

    enricher._llm_generate = fake_generate  # type: ignore[attr-defined]

    summary = await enricher._generate_summary("test text")
    assert "think" not in summary.lower()
    assert summary.startswith("该表用于冠脉风险分层")
