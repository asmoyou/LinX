"""Unit tests for vision parser provider integration."""

import asyncio

from knowledge_base.vision_parser import VisionDocumentParser


def _build_parser(api_format: str = "openai") -> VisionDocumentParser:
    parser = VisionDocumentParser.__new__(VisionDocumentParser)
    parser.vision_model = "Qwen/Qwen3-VL-32B-Instruct"
    parser.vision_provider = "llm-pool"
    parser.timeout_seconds = 30
    parser.base_url = "https://example.test/v1"
    parser.api_key = "test-key"
    parser.api_format = api_format
    return parser


def test_openai_vision_uses_custom_provider(monkeypatch):
    """OpenAI-compatible vision parsing should route through CustomOpenAIChat."""
    parser = _build_parser(api_format="openai")
    captured: dict = {}

    class DummyResult:
        content = "extracted text"

    class DummyLLM:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def invoke(self, messages):
            captured["messages"] = messages
            return DummyResult()

    monkeypatch.setattr(
        "llm_providers.custom_openai_provider.CustomOpenAIChat",
        DummyLLM,
    )

    text = asyncio.run(parser._extract_with_vision("ZmFrZQ==", "extract please"))

    assert text == "extracted text"
    assert captured["init"]["model"] == "Qwen/Qwen3-VL-32B-Instruct"
    assert captured["init"]["base_url"] == "https://example.test/v1"
    assert captured["init"]["api_key"] == "test-key"
    assert captured["messages"], "vision parser should send at least one user message"


def test_openai_vision_normalizes_list_content(monkeypatch):
    """List-based content responses should be normalized to plain text."""
    parser = _build_parser(api_format="openai")

    class DummyResult:
        content = [{"type": "text", "text": "line-1 "}, {"type": "text", "text": "line-2"}]

    class DummyLLM:
        def __init__(self, **kwargs):
            _ = kwargs

        def invoke(self, messages):
            _ = messages
            return DummyResult()

    monkeypatch.setattr(
        "llm_providers.custom_openai_provider.CustomOpenAIChat",
        DummyLLM,
    )

    text = asyncio.run(parser._extract_with_vision("ZmFrZQ==", "extract please"))

    assert text == "line-1 line-2"
