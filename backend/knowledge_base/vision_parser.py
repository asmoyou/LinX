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

# Prompt for structured document extraction
EXTRACTION_PROMPT = """Extract all text content from this document page.
Preserve the original structure including:
- Headings and subheadings
- Paragraphs
- Lists (bulleted and numbered)
- Tables (use markdown table format)
- Code blocks (use triple backticks)

Output the extracted text in clean markdown format.
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


def _resolve_vision_settings() -> tuple[str, str, float]:
    """Resolve current vision model/provider/timeout from runtime config."""
    config = get_config()
    kb_config = config.get_section("knowledge_base") if config else {}
    parsing_cfg = kb_config.get("parsing", {})
    vision_model = parsing_cfg.get("vision_model", "qwen3-vl:30b")
    vision_provider = parsing_cfg.get("vision_provider", "ollama")
    vision_timeout = float(parsing_cfg.get("vision_timeout_seconds", 120))
    vision_timeout = max(5.0, vision_timeout)
    return vision_model, vision_provider, vision_timeout


class VisionDocumentParser:
    """Parse documents using vision LLM for layout-aware extraction."""

    def __init__(
        self,
        vision_model: Optional[str] = None,
        vision_provider: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        """Initialize vision parser with config."""
        default_model, default_provider, default_timeout = _resolve_vision_settings()
        self.vision_model = vision_model or default_model
        self.vision_provider = vision_provider or default_provider
        self.timeout_seconds = float(timeout_seconds or default_timeout)

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
            },
        )

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

        doc = fitz.open(str(file_path))
        all_text = []
        sections = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Render page to image at 200 DPI
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            # Send to vision LLM
            page_text = await self._extract_with_vision(
                img_b64,
                f"This is page {page_num + 1} of a document. {EXTRACTION_PROMPT}",
            )

            if page_text:
                all_text.append(page_text)
                sections.append(
                    {
                        "page": page_num + 1,
                        "text_length": len(page_text),
                    }
                )

        doc.close()

        combined_text = "\n\n".join(all_text)

        logger.info(
            "PDF parsed with vision",
            extra={
                "file": str(file_path),
                "pages": len(doc),
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

        # Send to vision LLM
        text = await self._extract_with_vision(
            img_b64,
            prompt or EXTRACTION_PROMPT,
        )

        return ParseResult(
            text=text or "",
            pages=1,
            sections=[{"page": 1, "text_length": len(text or "")}],
            confidence=0.8,
            method="vision",
        )

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
        import aiohttp
        from langchain_core.messages import HumanMessage

        from llm_providers.custom_openai_provider import CustomOpenAIChat

        try:
            started = time.perf_counter()

            if self.api_format == "openai":
                human_message = HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ]
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
                        content = getattr(result, "content", "")
                        if isinstance(content, list):
                            # Normalize multimodal fragment list into plain text.
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text_parts.append(part.get("text", ""))
                            content = "".join(text_parts)
                        text = (content or "").strip()
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
                    "images": [image_b64],
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

                    text = (content or "").strip()
                    logger.info(
                        "Vision extraction completed",
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
    vision_model, vision_provider, timeout_seconds = _resolve_vision_settings()
    if (
        _vision_parser is None
        or _vision_parser.vision_model != vision_model
        or _vision_parser.vision_provider != vision_provider
        or _vision_parser.timeout_seconds != float(timeout_seconds)
    ):
        _vision_parser = VisionDocumentParser(
            vision_model=vision_model,
            vision_provider=vision_provider,
            timeout_seconds=timeout_seconds,
        )
    return _vision_parser


def reset_vision_parser() -> None:
    """Reset parser singleton so next access reloads latest config."""
    global _vision_parser
    _vision_parser = None
