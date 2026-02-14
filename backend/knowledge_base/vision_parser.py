"""Vision-LLM document parsing using Qwen3-VL or similar models.

Converts document pages to images and uses a vision LLM for layout-aware
text extraction, OCR, and structural understanding.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from shared.config import get_config

logger = logging.getLogger(__name__)

def _build_extraction_prompt(output_language: str) -> str:
    """Build extraction prompt with configurable output language."""
    return f"""Extract all text content from this document page.
Preserve the original structure including:
- Headings and subheadings
- Paragraphs
- Lists (bulleted and numbered)
- Tables (use markdown table format)
- Code blocks (use triple backticks)

Output requirements:
- Primary output language must be {output_language}
- Keep key source-language terms (names, product labels, UI text) in parentheses
- Preserve critical source text snippets verbatim when possible
- Output in clean markdown

If the image contains handwritten text, extract it as best as possible.
If the image is a diagram or chart, describe its content textually."""


@dataclass
class ParseResult:
    """Result of document parsing."""

    text: str
    pages: int = 1
    sections: List[dict] = field(default_factory=list)
    confidence: float = 0.0
    method: str = "vision"


def _resolve_vision_settings() -> tuple[str, str, float, str]:
    """Resolve current vision model/provider/timeout/output language from config."""
    config = get_config()
    kb_config = config.get_section("knowledge_base") if config else {}
    parsing_cfg = kb_config.get("parsing", {})
    vision_model = parsing_cfg.get("vision_model", "qwen3-vl:30b")
    vision_provider = parsing_cfg.get("vision_provider", "ollama")
    vision_timeout = float(parsing_cfg.get("vision_timeout_seconds", 120))
    vision_timeout = max(5.0, vision_timeout)
    output_language = str(parsing_cfg.get("output_language", "zh-CN")).strip() or "zh-CN"
    return vision_model, vision_provider, vision_timeout, output_language


class VisionDocumentParser:
    """Parse documents using vision LLM for layout-aware extraction."""

    def __init__(
        self,
        vision_model: Optional[str] = None,
        vision_provider: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        output_language: Optional[str] = None,
    ):
        """Initialize vision parser with config."""
        default_model, default_provider, default_timeout, default_output_language = (
            _resolve_vision_settings()
        )
        self.vision_model = vision_model or default_model
        self.vision_provider = vision_provider or default_provider
        self.timeout_seconds = float(timeout_seconds or default_timeout)
        self.output_language = str(output_language or default_output_language).strip() or "zh-CN"

        # Resolve base_url from DB (primary) or config.yaml (fallback)
        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self.vision_provider)
        self.base_url = provider_cfg.get("base_url", "http://localhost:11434")
        self.api_key = provider_cfg.get("api_key")
        protocol = provider_cfg.get(
            "protocol",
            "ollama" if self.vision_provider == "ollama" else "openai_compatible",
        )
        self.api_format = "ollama" if protocol == "ollama" else "openai"

        logger.info(
            "VisionDocumentParser initialized",
            extra={
                "model": self.vision_model,
                "provider": self.vision_provider,
                "api_format": self.api_format,
                "timeout_seconds": self.timeout_seconds,
                "output_language": self.output_language,
            },
        )

    def _get_output_language(self) -> str:
        """Return configured output language with safe default."""
        language = str(getattr(self, "output_language", "zh-CN") or "").strip()
        return language or "zh-CN"

    async def parse_pdf(self, file_path: Path) -> ParseResult:
        """Parse a PDF document by converting pages to images and using vision LLM.

        Args:
            file_path: Path to PDF file

        Returns:
            ParseResult with extracted text
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF (fitz) not installed. Install with: pip install PyMuPDF")
            raise ImportError("PyMuPDF required for vision PDF parsing")

        all_text = []
        sections = []
        page_count = 0

        with fitz.open(str(file_path)) as doc:
            page_count = len(doc)
            for page_num in range(page_count):
                page = doc.load_page(page_num)
                # Render page to image at 200 DPI
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")

                # Send to vision LLM
                page_prompt = (
                    f"This is page {page_num + 1} of a document. "
                    f"{_build_extraction_prompt(self._get_output_language())}"
                )
                page_text = await self._extract_with_vision(
                    img_b64,
                    page_prompt,
                )

                if page_text:
                    all_text.append(page_text)
                    sections.append(
                        {
                            "page": page_num + 1,
                            "text_length": len(page_text),
                        }
                    )

        combined_text = "\n\n".join(all_text)

        logger.info(
            "PDF parsed with vision",
            extra={
                "file": str(file_path),
                "pages": page_count,
                "text_length": len(combined_text),
            },
        )

        return ParseResult(
            text=combined_text,
            pages=len(sections),
            sections=sections,
            confidence=0.85,
            method="vision",
        )

    async def parse_image(self, file_path: Path, prompt: Optional[str] = None) -> ParseResult:
        """Parse an image using vision LLM for OCR and understanding.

        Args:
            file_path: Path to image file
            prompt: Optional custom prompt for extraction

        Returns:
            ParseResult with extracted text
        """
        # Read and encode image
        with open(file_path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        mime_type = self._guess_image_mime_type(file_path)

        # Send to vision LLM
        text = await self._extract_with_vision_batch(
            [(mime_type, img_b64)],
            prompt or _build_extraction_prompt(self._get_output_language()),
        )

        return ParseResult(
            text=text or "",
            pages=1,
            sections=[{"page": 1, "text_length": len(text or "")}],
            confidence=0.8,
            method="vision",
        )

    async def parse_images(
        self, file_paths: List[Path], prompt: Optional[str] = None
    ) -> ParseResult:
        """Parse multiple images in one model request."""
        if not file_paths:
            return ParseResult(text="", pages=0, sections=[], confidence=0.0, method="vision")

        image_payloads: List[tuple[str, str]] = []
        for file_path in file_paths:
            with open(file_path, "rb") as f:
                img_bytes = f.read()
            image_payloads.append(
                (
                    self._guess_image_mime_type(file_path),
                    base64.b64encode(img_bytes).decode("utf-8"),
                )
            )

        text = await self._extract_with_vision_batch(
            image_payloads,
            prompt or _build_extraction_prompt(self._get_output_language()),
        )
        return ParseResult(
            text=text or "",
            pages=len(file_paths),
            sections=[{"page": i + 1, "text_length": 0} for i in range(len(file_paths))],
            confidence=0.8,
            method="vision",
        )

    async def summarize_video_batches(self, batch_texts: List[str]) -> str:
        """Summarize extracted per-batch video text into a final overview."""
        if not batch_texts:
            return ""

        timeline = "\n\n".join(
            f"Segment {i + 1}:\n{text}" for i, text in enumerate(batch_texts)
        )
        output_language = self._get_output_language()
        prompt = (
            "You are summarizing OCR and scene descriptions extracted from video frames.\n"
            f"Primary output language must be {output_language}.\n"
            "Keep key source-language labels or names in parentheses.\n"
            "Produce a concise but complete summary with:\n"
            "1) overall storyline,\n"
            "2) key entities/objects,\n"
            "3) important on-screen text,\n"
            "4) notable timeline changes.\n\n"
            f"Segments:\n{timeline}"
        )
        return await self._generate_text(prompt)

    @staticmethod
    def _normalize_response_content(content: object) -> str:
        """Normalize model response payload to plain text."""
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            return "".join(text_parts).strip()
        return (str(content) if content is not None else "").strip()

    @staticmethod
    def _guess_image_mime_type(file_path: Path) -> str:
        """Infer image mime type from file extension."""
        suffix = file_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".webp":
            return "image/webp"
        return "image/png"

    async def _generate_text(self, prompt: str) -> str:
        """Generate text-only completion with the configured provider/model."""
        import aiohttp
        from langchain_core.messages import HumanMessage

        from llm_providers.custom_openai_provider import CustomOpenAIChat

        try:
            started = time.perf_counter()

            if self.api_format == "openai":
                last_error: Optional[Exception] = None
                attempt_timeout = max(5, min(int(self.timeout_seconds), 45))
                for max_tokens in (1024, 768):
                    try:
                        llm = CustomOpenAIChat(
                            base_url=self.base_url,
                            model=self.vision_model,
                            api_key=self.api_key,
                            temperature=0.1,
                            max_tokens=max_tokens,
                            timeout=attempt_timeout,
                            streaming=False,
                        )
                        result = await asyncio.to_thread(
                            llm.invoke, [HumanMessage(content=prompt)]
                        )
                        text = self._normalize_response_content(
                            getattr(result, "content", "")
                        )
                        if text:
                            logger.info(
                                "Vision text generation completed",
                                extra={
                                    "provider": self.vision_provider,
                                    "model": self.vision_model,
                                    "api_format": self.api_format,
                                    "elapsed_ms": round(
                                        (time.perf_counter() - started) * 1000.0, 2
                                    ),
                                    "text_length": len(text),
                                    "max_tokens": max_tokens,
                                    "timeout_seconds": attempt_timeout,
                                },
                            )
                            return text
                    except Exception as openai_err:
                        last_error = openai_err
                        logger.warning(
                            "OpenAI text generation attempt failed",
                            extra={
                                "provider": self.vision_provider,
                                "model": self.vision_model,
                                "max_tokens": max_tokens,
                                "timeout_seconds": attempt_timeout,
                                "error": str(openai_err),
                            },
                        )
                if last_error:
                    raise last_error
                return ""

            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {
                    "model": self.vision_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1536,
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
                    if not content and data.get("thinking"):
                        content = data.get("thinking", "")
                    text = self._normalize_response_content(content)
                    logger.info(
                        "Vision text generation completed",
                        extra={
                            "provider": self.vision_provider,
                            "model": self.vision_model,
                            "api_format": self.api_format,
                            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                            "text_length": len(text),
                        },
                    )
                    return text
        except Exception as e:
            logger.error(f"Vision text generation failed: {type(e).__name__}: {e}", exc_info=True)
            return ""

    async def _extract_with_vision(self, image_b64: str, prompt: str) -> str:
        """Send image to vision LLM and extract text.

        Uses:
        - OpenAI-compatible providers via the same CustomOpenAIChat stack as agents
        - Ollama providers via /api/generate with images parameter

        Args:
            image_b64: Base64-encoded image
            prompt: Extraction prompt

        Returns:
            Extracted text from vision LLM
        """
        return await self._extract_with_vision_batch([("image/png", image_b64)], prompt)

    async def _extract_with_vision_batch(
        self, image_payloads: List[tuple[str, str]], prompt: str
    ) -> str:
        """Send one or more images to vision LLM and extract text."""
        import aiohttp
        from langchain_core.messages import HumanMessage

        from llm_providers.custom_openai_provider import CustomOpenAIChat

        try:
            started = time.perf_counter()

            if self.api_format == "openai":
                content_parts = [{"type": "text", "text": prompt}]
                for mime_type, image_b64 in image_payloads:
                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                        }
                    )
                human_message = HumanMessage(
                    content=content_parts
                )
                last_error: Optional[Exception] = None
                # Keep each request bounded; avoids long hangs before OCR fallback.
                attempt_timeout = max(5, min(int(self.timeout_seconds), 45))
                for max_tokens in (768, 384):
                    try:
                        llm = CustomOpenAIChat(
                            base_url=self.base_url,
                            model=self.vision_model,
                            api_key=self.api_key,
                            temperature=0.1,
                            # Keep output bounded; oversized generations can trigger avoidable timeouts.
                            max_tokens=max_tokens,
                            timeout=attempt_timeout,
                            streaming=False,
                        )
                        result = await asyncio.to_thread(llm.invoke, [human_message])
                        text = self._normalize_response_content(
                            getattr(result, "content", "")
                        )
                        if text:
                            logger.info(
                                "Vision extraction completed",
                                extra={
                                    "provider": self.vision_provider,
                                    "model": self.vision_model,
                                    "api_format": self.api_format,
                                    "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                                    "text_length": len(text),
                                    "max_tokens": max_tokens,
                                    "timeout_seconds": attempt_timeout,
                                    "image_count": len(image_payloads),
                                },
                            )
                            return text
                    except Exception as openai_err:
                        last_error = openai_err
                        logger.warning(
                            "OpenAI vision attempt failed",
                            extra={
                                "provider": self.vision_provider,
                                "model": self.vision_model,
                                "max_tokens": max_tokens,
                                "timeout_seconds": attempt_timeout,
                                "error": str(openai_err),
                            },
                        )
                if last_error:
                    raise last_error
                return ""

            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {
                    "model": self.vision_model,
                    "prompt": prompt,
                    "images": [image_b64 for _mime_type, image_b64 in image_payloads],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1536,
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

                    # Handle qwen3-vl response format
                    content = data.get("response", "")
                    thinking = data.get("thinking", "")
                    if not content and thinking:
                        content = thinking

                    text = self._normalize_response_content(content)
                    logger.info(
                        "Vision extraction completed",
                        extra={
                            "provider": self.vision_provider,
                            "model": self.vision_model,
                            "api_format": self.api_format,
                            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                            "text_length": len(text),
                            "image_count": len(image_payloads),
                        },
                    )
                    return text

        except Exception as e:
            logger.error(f"Vision extraction failed: {type(e).__name__}: {e}", exc_info=True)
            return ""


# Singleton instance
_vision_parser: Optional[VisionDocumentParser] = None


def get_vision_parser() -> VisionDocumentParser:
    """Get or create the vision parser singleton.

    Returns:
        VisionDocumentParser instance
    """
    global _vision_parser
    vision_model, vision_provider, timeout_seconds, output_language = _resolve_vision_settings()
    if (
        _vision_parser is None
        or _vision_parser.vision_model != vision_model
        or _vision_parser.vision_provider != vision_provider
        or _vision_parser.timeout_seconds != float(timeout_seconds)
        or _vision_parser.output_language != output_language
    ):
        _vision_parser = VisionDocumentParser(
            vision_model=vision_model,
            vision_provider=vision_provider,
            timeout_seconds=timeout_seconds,
            output_language=output_language,
        )
    return _vision_parser


def reset_vision_parser() -> None:
    """Reset parser singleton so next access reloads latest config."""
    global _vision_parser
    _vision_parser = None
