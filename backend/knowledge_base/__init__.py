"""Knowledge Base and Document Processing module.

This module provides document processing pipeline including:
- Document upload and validation
- Text extraction from various formats (PDF, DOCX, TXT, MD)
- OCR for images and vision-LLM parsing
- Audio/video transcription
- Semantic-aware document chunking
- LLM-driven chunk enrichment (keywords, questions, summaries)
- Dual indexing (Milvus vector + PostgreSQL BM25)
- Hybrid search with Reciprocal Rank Fusion

All submodules are imported directly where needed (e.g.,
``from knowledge_base.document_chunker import get_document_chunker``).
This avoids top-level import failures when optional dependencies
(FunASR, libmagic, etc.) are not installed.

References:
- Requirements 4, 16: Knowledge Base and Document Processing
- Design Section 14: Document Processing Pipeline
"""
