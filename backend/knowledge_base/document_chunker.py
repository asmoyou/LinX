"""Document chunking for efficient embedding generation.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import tiktoken

logger = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    """Chunking strategy for documents."""
    
    FIXED_SIZE = "fixed_size"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
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
        
        logger.info(
            "DocumentChunker initialized",
            extra={
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "encoding": encoding_name,
            }
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
            chunk_metadata.append({
                "document_id": document_id,
                "chunk_index": chunk_index,
                "start_token": start,
                "end_token": end,
                "token_count": len(chunk_tokens),
                **(metadata or {}),
            })
            
            chunk_index += 1
            start += self.chunk_size - self.chunk_overlap
        
        logger.info(
            "Document chunked",
            extra={
                "document_id": document_id,
                "total_tokens": total_tokens,
                "chunk_count": len(chunks),
            }
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
        paragraphs = text.split('\n\n')
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
                chunk_text = '\n\n'.join(current_chunk)
                chunks.append(chunk_text)
                chunk_metadata.append({
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "token_count": current_tokens,
                    **(metadata or {}),
                })
                chunk_index += 1
                current_chunk = [para]
                current_tokens = para_token_count
            else:
                current_chunk.append(para)
                current_tokens += para_token_count
        
        # Add remaining chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(chunk_text)
            chunk_metadata.append({
                "document_id": document_id,
                "chunk_index": chunk_index,
                "token_count": current_tokens,
                **(metadata or {}),
            })
        
        return ChunkResult(
            chunks=chunks,
            chunk_metadata=chunk_metadata,
            total_tokens=total_tokens,
            chunk_count=len(chunks),
        )


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
