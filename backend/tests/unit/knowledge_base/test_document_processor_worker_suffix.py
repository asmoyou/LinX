"""Tests for MIME-to-suffix mapping in document processor worker."""

from knowledge_base.document_processor_worker import DocumentProcessorWorker


def test_get_suffix_supports_m4a_mime_variants() -> None:
    """M4A uploads should keep a usable suffix for ASR/transcription engines."""
    assert DocumentProcessorWorker._get_suffix("audio/mp4") == ".m4a"
    assert DocumentProcessorWorker._get_suffix("audio/x-m4a") == ".m4a"
    assert DocumentProcessorWorker._get_suffix("audio/m4a; codecs=mp4a.40.2") == ".m4a"


def test_get_suffix_supports_flac_and_common_video_variants() -> None:
    """Less common MIME labels should map to stable file extensions."""
    assert DocumentProcessorWorker._get_suffix("audio/flac") == ".flac"
    assert DocumentProcessorWorker._get_suffix("video/quicktime") == ".mov"
    assert DocumentProcessorWorker._get_suffix("video/x-matroska") == ".mkv"
