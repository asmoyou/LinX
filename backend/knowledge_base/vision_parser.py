"""Vision-LLM document parsing using Qwen3-VL or similar models.

Converts document pages to images and uses a vision LLM for layout-aware
text extraction, OCR, and structural understanding.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import base64
import logging
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


class VisionDocumentParser:
    """Parse documents using vision LLM for layout-aware extraction."""

    def __init__(self):
        """Initialize vision parser with config."""
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}
        parsing_cfg = kb_config.get("parsing", {})

        self.vision_model = parsing_cfg.get("vision_model", "qwen3-vl:30b")
        self.vision_provider = parsing_cfg.get("vision_provider", "ollama")

        # Resolve base_url from DB (primary) or config.yaml (fallback)
        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self.vision_provider)
        self.base_url = provider_cfg.get("base_url", "http://localhost:11434")

        logger.info(
            "VisionDocumentParser initialized",
            extra={
                "model": self.vision_model,
                "provider": self.vision_provider,
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

    async def parse_image(self, file_path: Path) -> ParseResult:
        """Parse an image using vision LLM for OCR and understanding.

        Args:
            file_path: Path to image file

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
            EXTRACTION_PROMPT,
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

        Uses the Ollama /api/generate endpoint with images parameter.

        Args:
            image_b64: Base64-encoded image
            prompt: Extraction prompt

        Returns:
            Extracted text from vision LLM
        """
        import aiohttp

        payload = {
            "model": self.vision_model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            },
        }

        try:
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Handle qwen3-vl response format
                    content = data.get("response", "")
                    thinking = data.get("thinking", "")
                    if not content and thinking:
                        content = thinking

                    return content

        except Exception as e:
            logger.error(f"Vision extraction failed: {e}", exc_info=True)
            return ""


# Singleton instance
_vision_parser: Optional[VisionDocumentParser] = None


def get_vision_parser() -> VisionDocumentParser:
    """Get or create the vision parser singleton.

    Returns:
        VisionDocumentParser instance
    """
    global _vision_parser
    if _vision_parser is None:
        _vision_parser = VisionDocumentParser()
    return _vision_parser
