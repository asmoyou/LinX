"""Document chunking for efficient embedding generation.

Supports fixed-size, paragraph, and semantic chunking strategies.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import tiktoken

from shared.config import get_config

logger = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    """Chunking strategy for documents."""

    FIXED_SIZE = "fixed_size"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SEMANTIC = "semantic"
    HIERARCHICAL = "hierarchical"


@dataclass
class ChunkResult:
    """Result of document chunking."""

    chunks: List[str]
    chunk_metadata: List[dict]
    total_tokens: int
    chunk_count: int


class DocumentChunker:
    """Chunk documents for efficient embedding generation."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        encoding_name: str = "cl100k_base",
    ):
        """Initialize document chunker.

        Args:
            chunk_size: Target size of each chunk in tokens
            chunk_overlap: Number of overlapping tokens between chunks
            encoding_name: Tiktoken encoding name
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding(encoding_name)

        # Load semantic chunking config
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}
        chunking_cfg = kb_config.get("chunking", {})
        self.delimiters = chunking_cfg.get("delimiters", "\n。；！？.!?")
        self.overlap_percent = chunking_cfg.get("overlap_percent", 10)

        logger.info(
            "DocumentChunker initialized",
            extra={
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "encoding": encoding_name,
            },
        )

    def chunk(
        self,
        text: str,
        document_id: str,
        strategy: ChunkingStrategy = ChunkingStrategy.FIXED_SIZE,
        metadata: Optional[dict] = None,
    ) -> ChunkResult:
        """Chunk document text.

        Args:
            text: Document text to chunk
            document_id: Unique document identifier
            strategy: Chunking strategy to use
            metadata: Additional metadata to include with chunks

        Returns:
            ChunkResult with chunks and metadata
        """
        if strategy == ChunkingStrategy.FIXED_SIZE:
            return self._chunk_fixed_size(text, document_id, metadata)
        elif strategy == ChunkingStrategy.PARAGRAPH:
            return self._chunk_by_paragraph(text, document_id, metadata)
        elif strategy == ChunkingStrategy.SEMANTIC:
            return self._chunk_semantic(text, document_id, metadata)
        else:
            # Default to fixed size
            return self._chunk_fixed_size(text, document_id, metadata)

    def _chunk_fixed_size(
        self,
        text: str,
        document_id: str,
        metadata: Optional[dict] = None,
    ) -> ChunkResult:
        """Chunk text into fixed-size chunks with overlap.

        Args:
            text: Text to chunk
            document_id: Document identifier
            metadata: Additional metadata

        Returns:
            ChunkResult with fixed-size chunks
        """
        # Encode text to tokens
        tokens = self.encoding.encode(text)
        total_tokens = len(tokens)

        chunks = []
        chunk_metadata = []
        chunk_index = 0

        # Create overlapping chunks
        start = 0
        while start < total_tokens:
            end = min(start + self.chunk_size, total_tokens)
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)

            chunks.append(chunk_text)
            chunk_metadata.append(
                {
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "start_token": start,
                    "end_token": end,
                    "token_count": len(chunk_tokens),
                    **(metadata or {}),
                }
            )

            chunk_index += 1
            start += self.chunk_size - self.chunk_overlap

        logger.info(
            "Document chunked",
            extra={
                "document_id": document_id,
                "total_tokens": total_tokens,
                "chunk_count": len(chunks),
            },
        )

        return ChunkResult(
            chunks=chunks,
            chunk_metadata=chunk_metadata,
            total_tokens=total_tokens,
            chunk_count=len(chunks),
        )

    def _chunk_by_paragraph(
        self,
        text: str,
        document_id: str,
        metadata: Optional[dict] = None,
    ) -> ChunkResult:
        """Chunk text by paragraphs, combining small ones.

        Args:
            text: Text to chunk
            document_id: Document identifier
            metadata: Additional metadata

        Returns:
            ChunkResult with paragraph-based chunks
        """
        paragraphs = text.split("\n\n")
        chunks = []
        chunk_metadata = []
        chunk_index = 0
        current_chunk = []
        current_tokens = 0
        total_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = self.encoding.encode(para)
            para_token_count = len(para_tokens)
            total_tokens += para_token_count

            if current_tokens + para_token_count > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(chunk_text)
                chunk_metadata.append(
                    {
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "token_count": current_tokens,
                        **(metadata or {}),
                    }
                )
                chunk_index += 1
                current_chunk = [para]
                current_tokens = para_token_count
            else:
                current_chunk.append(para)
                current_tokens += para_token_count

        # Add remaining chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(chunk_text)
            chunk_metadata.append(
                {
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "token_count": current_tokens,
                    **(metadata or {}),
                }
            )

        return ChunkResult(
            chunks=chunks,
            chunk_metadata=chunk_metadata,
            total_tokens=total_tokens,
            chunk_count=len(chunks),
        )

    def _chunk_semantic(
        self,
        text: str,
        document_id: str,
        metadata: Optional[dict] = None,
    ) -> ChunkResult:
        """Semantic-aware chunking that respects delimiters, tables, and code blocks.

        Splits by configurable delimiters, accumulates until chunk_token_num,
        carries overlap from previous chunk, and keeps tables/code blocks intact.

        Inspired by RAGFlow's naive_merge() approach.

        Args:
            text: Text to chunk
            document_id: Document identifier
            metadata: Additional metadata

        Returns:
            ChunkResult with semantically-aware chunks
        """
        # Split text into segments respecting special blocks
        segments = self._split_into_segments(text)

        chunks = []
        chunk_metadata = []
        chunk_index = 0
        total_tokens = 0

        current_segments = []
        current_tokens = 0
        overlap_text = ""

        for segment in segments:
            seg_tokens = self.encoding.encode(segment)
            seg_token_count = len(seg_tokens)
            total_tokens += seg_token_count

            # If a single segment exceeds chunk size, emit it as its own chunk
            if seg_token_count > self.chunk_size:
                # First, emit accumulated segments
                if current_segments:
                    chunk_text = "".join(current_segments)
                    if overlap_text:
                        chunk_text = overlap_text + chunk_text
                    chunks.append(chunk_text.strip())
                    chunk_metadata.append(
                        {
                            "document_id": document_id,
                            "chunk_index": chunk_index,
                            "token_count": current_tokens,
                            **(metadata or {}),
                        }
                    )
                    chunk_index += 1
                    overlap_text = self._compute_overlap("".join(current_segments))
                    current_segments = []
                    current_tokens = 0

                # Emit the large segment
                large_text = segment
                if overlap_text:
                    large_text = overlap_text + large_text
                chunks.append(large_text.strip())
                chunk_metadata.append(
                    {
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "token_count": seg_token_count,
                        **(metadata or {}),
                    }
                )
                chunk_index += 1
                overlap_text = self._compute_overlap(segment)
                continue

            # Check if adding this segment would exceed chunk size
            if current_tokens + seg_token_count > self.chunk_size and current_segments:
                # Emit current chunk
                chunk_text = "".join(current_segments)
                if overlap_text:
                    chunk_text = overlap_text + chunk_text
                chunks.append(chunk_text.strip())
                chunk_metadata.append(
                    {
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "token_count": current_tokens,
                        **(metadata or {}),
                    }
                )
                chunk_index += 1

                # Compute overlap from previous chunk
                overlap_text = self._compute_overlap("".join(current_segments))
                current_segments = [segment]
                current_tokens = seg_token_count
            else:
                current_segments.append(segment)
                current_tokens += seg_token_count

        # Emit remaining segments
        if current_segments:
            chunk_text = "".join(current_segments)
            if overlap_text:
                chunk_text = overlap_text + chunk_text
            chunks.append(chunk_text.strip())
            chunk_metadata.append(
                {
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "token_count": current_tokens,
                    **(metadata or {}),
                }
            )

        logger.info(
            "Document chunked (semantic)",
            extra={
                "document_id": document_id,
                "total_tokens": total_tokens,
                "chunk_count": len(chunks),
            },
        )

        return ChunkResult(
            chunks=chunks,
            chunk_metadata=chunk_metadata,
            total_tokens=total_tokens,
            chunk_count=len(chunks),
        )

    def _split_into_segments(self, text: str) -> List[str]:
        """Split text into segments respecting tables, code blocks, and delimiters.

        Tables (lines with | markers) and code blocks (triple backticks) are
        kept as single segments. Other text is split by delimiters.

        Args:
            text: Input text

        Returns:
            List of text segments
        """
        segments = []
        lines = text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Detect code blocks (triple backticks)
            if line.strip().startswith("```"):
                block_lines = [line]
                i += 1
                while i < len(lines):
                    block_lines.append(lines[i])
                    if lines[i].strip().startswith("```") and len(block_lines) > 1:
                        i += 1
                        break
                    i += 1
                segments.append("\n".join(block_lines) + "\n")
                continue

            # Detect table rows (lines with | markers)
            if "|" in line and line.strip().startswith("|"):
                table_lines = [line]
                i += 1
                while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                segments.append("\n".join(table_lines) + "\n")
                continue

            # Regular text: split by delimiters
            text_line = line + "\n"
            if self.delimiters:
                # Build regex pattern from delimiters
                parts = self._split_by_delimiters(text_line)
                segments.extend(parts)
            else:
                segments.append(text_line)

            i += 1

        # Filter empty segments
        return [s for s in segments if s.strip()]

    def _split_by_delimiters(self, text: str) -> List[str]:
        """Split text by configured delimiters, keeping delimiters attached.

        Args:
            text: Text to split

        Returns:
            List of text segments with delimiters attached to preceding segment
        """
        if not self.delimiters:
            return [text] if text.strip() else []

        # Escape special regex chars and build pattern
        escaped = [re.escape(d) for d in self.delimiters if d != "\n"]
        if not escaped:
            return [text] if text.strip() else []

        pattern = "(" + "|".join(escaped) + ")"
        parts = re.split(pattern, text)

        # Rejoin: attach delimiter to preceding text
        segments = []
        current = ""
        for part in parts:
            current += part
            # If part is a delimiter, the segment ends here
            if len(part) == 1 and part in self.delimiters:
                if current.strip():
                    segments.append(current)
                current = ""

        if current.strip():
            segments.append(current)

        return segments

    def _compute_overlap(self, text: str) -> str:
        """Compute overlap text from end of previous chunk.

        Takes overlap_percent of the text from the end.

        Args:
            text: Previous chunk text

        Returns:
            Overlap text to prepend to next chunk
        """
        if self.overlap_percent <= 0:
            return ""

        tokens = self.encoding.encode(text)
        overlap_tokens = max(1, int(len(tokens) * self.overlap_percent / 100))
        overlap_tokens = min(overlap_tokens, len(tokens))

        overlap = self.encoding.decode(tokens[-overlap_tokens:])
        return overlap


# Singleton instance
_document_chunker: Optional[DocumentChunker] = None


def get_document_chunker(
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> DocumentChunker:
    """Get or create the document chunker singleton.

    Args:
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks in tokens

    Returns:
        DocumentChunker instance
    """
    global _document_chunker
    if _document_chunker is None:
        _document_chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    return _document_chunker
