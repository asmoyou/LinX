"""Text extraction from various document formats.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import markdown
import pdfplumber
import PyPDF2
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of text extraction from a document."""

    text: str
    metadata: Dict[str, Any]
    page_count: Optional[int] = None
    word_count: int = 0
    extraction_time: float = 0.0
    confidence: float = 1.0  # 1.0 for direct extraction, lower for OCR


class TextExtractor(ABC):
    """Abstract base class for text extractors."""

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from a document.

        Args:
            file_path: Path to the document

        Returns:
            ExtractionResult with extracted text and metadata
        """
        pass

    def _count_words(self, text: str) -> int:
        """Count words in text.

        Args:
            text: Text to count words in

        Returns:
            Number of words
        """
        return len(text.split())


class PDFExtractor(TextExtractor):
    """Extract text from PDF files."""

    def __init__(self, use_pdfplumber: bool = True):
        """Initialize PDF extractor.

        Args:
            use_pdfplumber: Whether to use pdfplumber (better for tables) or PyPDF2
        """
        self.use_pdfplumber = use_pdfplumber

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            ExtractionResult with extracted text
        """
        start_time = datetime.now()

        try:
            if self.use_pdfplumber:
                text, metadata, page_count = self._extract_with_pdfplumber(file_path)
            else:
                text, metadata, page_count = self._extract_with_pypdf2(file_path)

            extraction_time = (datetime.now() - start_time).total_seconds()
            word_count = self._count_words(text)

            logger.info(
                "PDF extraction completed",
                extra={
                    "file": str(file_path),
                    "pages": page_count,
                    "words": word_count,
                    "time": extraction_time,
                },
            )

            return ExtractionResult(
                text=text,
                metadata=metadata,
                page_count=page_count,
                word_count=word_count,
                extraction_time=extraction_time,
            )

        except Exception as e:
            logger.error(f"PDF extraction failed: {e}", exc_info=True)
            raise

    def _extract_with_pdfplumber(self, file_path: Path) -> tuple[str, Dict, int]:
        """Extract text using pdfplumber."""
        text_parts = []
        metadata = {}

        with pdfplumber.open(file_path) as pdf:
            metadata = pdf.metadata or {}
            page_count = len(pdf.pages)

            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        return "\n\n".join(text_parts), metadata, page_count

    def _extract_with_pypdf2(self, file_path: Path) -> tuple[str, Dict, int]:
        """Extract text using PyPDF2."""
        text_parts = []
        metadata = {}

        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            metadata = pdf_reader.metadata or {}
            page_count = len(pdf_reader.pages)

            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        return "\n\n".join(text_parts), dict(metadata), page_count


class DOCXExtractor(TextExtractor):
    """Extract text from DOCX files."""

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from DOCX file.

        Args:
            file_path: Path to DOCX file

        Returns:
            ExtractionResult with extracted text
        """
        start_time = datetime.now()

        try:
            doc = DocxDocument(file_path)

            # Extract text from paragraphs
            text_parts = [para.text for para in doc.paragraphs if para.text.strip()]

            # Extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text for cell in row.cells)
                    if row_text.strip():
                        text_parts.append(row_text)

            text = "\n\n".join(text_parts)

            # Extract metadata
            metadata = {
                "author": doc.core_properties.author,
                "title": doc.core_properties.title,
                "subject": doc.core_properties.subject,
                "created": (
                    str(doc.core_properties.created) if doc.core_properties.created else None
                ),
                "modified": (
                    str(doc.core_properties.modified) if doc.core_properties.modified else None
                ),
            }

            extraction_time = (datetime.now() - start_time).total_seconds()
            word_count = self._count_words(text)

            logger.info(
                "DOCX extraction completed",
                extra={
                    "file": str(file_path),
                    "words": word_count,
                    "time": extraction_time,
                },
            )

            return ExtractionResult(
                text=text,
                metadata=metadata,
                word_count=word_count,
                extraction_time=extraction_time,
            )

        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}", exc_info=True)
            raise


class TextFileExtractor(TextExtractor):
    """Extract text from plain text files."""

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from text file.

        Args:
            file_path: Path to text file

        Returns:
            ExtractionResult with extracted text
        """
        start_time = datetime.now()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            metadata = {
                "filename": file_path.name,
                "size": file_path.stat().st_size,
            }

            extraction_time = (datetime.now() - start_time).total_seconds()
            word_count = self._count_words(text)

            return ExtractionResult(
                text=text,
                metadata=metadata,
                word_count=word_count,
                extraction_time=extraction_time,
            )

        except Exception as e:
            logger.error(f"Text file extraction failed: {e}", exc_info=True)
            raise


class MarkdownExtractor(TextExtractor):
    """Extract text from Markdown files."""

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from Markdown file.

        Args:
            file_path: Path to Markdown file

        Returns:
            ExtractionResult with extracted text (preserves formatting)
        """
        start_time = datetime.now()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                md_text = f.read()

            # Convert to HTML then extract text (preserves structure)
            html = markdown.markdown(md_text)

            # Keep both markdown and plain text
            metadata = {
                "filename": file_path.name,
                "size": file_path.stat().st_size,
                "format": "markdown",
                "html": html,
            }

            extraction_time = (datetime.now() - start_time).total_seconds()
            word_count = self._count_words(md_text)

            return ExtractionResult(
                text=md_text,  # Keep original markdown
                metadata=metadata,
                word_count=word_count,
                extraction_time=extraction_time,
            )

        except Exception as e:
            logger.error(f"Markdown extraction failed: {e}", exc_info=True)
            raise


def get_extractor(file_type: str) -> TextExtractor:
    """Get appropriate text extractor for file type.

    Args:
        file_type: MIME type or file extension

    Returns:
        TextExtractor instance

    Raises:
        ValueError: If file type is not supported
    """
    if "pdf" in file_type.lower():
        return PDFExtractor()
    elif "word" in file_type.lower() or "docx" in file_type.lower():
        return DOCXExtractor()
    elif "markdown" in file_type.lower() or file_type.endswith(".md"):
        return MarkdownExtractor()
    elif "text" in file_type.lower() or file_type.endswith(".txt"):
        return TextFileExtractor()
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
