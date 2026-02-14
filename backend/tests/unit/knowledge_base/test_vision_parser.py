"""Unit tests for vision parser provider integration."""

import asyncio
import sys
from unittest.mock import AsyncMock

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


def test_openai_parse_images_sends_all_images_in_single_request(monkeypatch, tmp_path):
    """parse_images should package multiple frames into one vision request."""
    parser = _build_parser(api_format="openai")
    captured: dict = {}

    class DummyResult:
        content = "batch extracted text"

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

    frame_1 = tmp_path / "frame_001.jpg"
    frame_2 = tmp_path / "frame_002.jpg"
    frame_1.write_bytes(b"frame-1")
    frame_2.write_bytes(b"frame-2")

    result = asyncio.run(
        parser.parse_images([frame_1, frame_2], prompt="video segment extraction")
    )

    assert result.text == "batch extracted text"
    assert result.pages == 2
    message = captured["messages"][0]
    content = message.content
    image_parts = [
        part
        for part in content
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]
    assert len(image_parts) == 2
    assert content[0]["type"] == "text"


def test_openai_summarize_video_batches_uses_text_only_prompt(monkeypatch):
    """Batch summary should use a text-only request with the same model."""
    parser = _build_parser(api_format="openai")
    captured: dict = {}

    class DummyResult:
        content = "summarized video"

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

    summary = asyncio.run(
        parser.summarize_video_batches(["Segment 1: intro", "Segment 2: action"])
    )

    assert summary == "summarized video"
    message = captured["messages"][0]
    assert isinstance(message.content, str)
    assert "Segment 1" in message.content


def test_parse_pdf_avoids_len_on_closed_document(monkeypatch, tmp_path):
    """parse_pdf should not touch document length after document context exits."""
    parser = _build_parser(api_format="openai")
    parser._extract_with_vision = AsyncMock(return_value="page text")

    class FakePixmap:
        def tobytes(self, fmt):
            assert fmt == "png"
            return b"fake-png"

    class FakePage:
        def get_pixmap(self, dpi=200):
            assert dpi == 200
            return FakePixmap()

    class FakeDoc:
        def __init__(self, page_count: int):
            self._page_count = page_count
            self.closed = False

        def __len__(self):
            if self.closed:
                raise ValueError("document closed")
            return self._page_count

        def load_page(self, page_num: int):
            if self.closed:
                raise ValueError("document closed")
            assert 0 <= page_num < self._page_count
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.closed = True
            return False

    fake_doc = FakeDoc(page_count=2)

    class FakeFitz:
        @staticmethod
        def open(path):
            assert path.endswith(".pdf")
            return fake_doc

    monkeypatch.setitem(sys.modules, "fitz", FakeFitz)

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    result = asyncio.run(parser.parse_pdf(pdf_path))

    assert result.text == "page text\n\npage text"
    assert result.pages == 2
    assert fake_doc.closed is True
    assert parser._extract_with_vision.await_count == 2
