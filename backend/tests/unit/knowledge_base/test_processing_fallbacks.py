"""Regression tests for image/video fallback processing."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from knowledge_base.document_processor_worker import DocumentProcessorWorker
from knowledge_base.knowledge_indexer import KnowledgeIndexer
from knowledge_base.vision_parser import ParseResult


def test_load_video_file_clip_compatibility():
    """moviepy v2 has no moviepy.editor; loader should still resolve VideoFileClip."""
    from knowledge_base.video_processor import _load_video_file_clip

    video_clip_cls = _load_video_file_clip()
    assert video_clip_cls is not None


def test_image_fallback_to_ocr_when_vision_returns_empty():
    """If vision parser returns empty text, image OCR should be used."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)
    worker.parsing_method = "auto"

    mock_parser = Mock()
    mock_parser.parse_image = AsyncMock(
        return_value=ParseResult(text="", pages=1, sections=[], confidence=0.0, method="vision")
    )

    mock_ocr_processor = Mock()
    mock_ocr_processor.process.return_value = Mock(text="OCR fallback text")

    with patch("knowledge_base.vision_parser.get_vision_parser", return_value=mock_parser):
        with patch(
            "knowledge_base.ocr_processor.get_ocr_processor",
            return_value=mock_ocr_processor,
        ):
            result = worker._extract_text(Path("/tmp/test.png"), "image/png")

    assert result == "OCR fallback text"


def test_video_fallback_to_vision_when_audio_transcription_fails():
    """Video parsing should fallback to vision-frame extraction when audio path fails."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)
    worker.parsing_method = "standard"
    worker._extract_video_with_vision = Mock(return_value="Frame 1: test scene")

    mock_video_processor = Mock()
    mock_video_processor.process.side_effect = RuntimeError("audio stack unavailable")

    with patch(
        "knowledge_base.video_processor.get_video_processor", return_value=mock_video_processor
    ):
        result = worker._extract_text(Path("/tmp/test.mp4"), "video/mp4")

    assert result == "Frame 1: test scene"


def test_video_combines_audio_and_vision_when_both_available():
    """Video parsing should include both audio transcript and visual analysis."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)
    worker.parsing_method = "standard"
    worker._extract_video_with_vision = Mock(return_value="Frame summary text")

    mock_video_processor = Mock()
    mock_video_processor.process.return_value = Mock(
        transcription=Mock(text="Audio transcript text")
    )

    with patch(
        "knowledge_base.video_processor.get_video_processor", return_value=mock_video_processor
    ):
        result = worker._extract_text(Path("/tmp/test.mp4"), "video/mp4")

    assert "Audio Transcript:\nAudio transcript text" in result
    assert "Visual Analysis:\nFrame summary text" in result
    worker._extract_video_with_vision.assert_called_once_with(Path("/tmp/test.mp4"))


def test_image_vision_mode_raises_instead_of_fallback_when_vision_fails():
    """When parsing method is vision, extraction failure should not silently fallback to OCR."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)
    worker.parsing_method = "vision"

    mock_parser = Mock()
    mock_parser.parse_image = AsyncMock(side_effect=TimeoutError("vision timeout"))

    mock_ocr_processor = Mock()
    mock_ocr_processor.process.return_value = Mock(text="OCR fallback text")

    with patch("knowledge_base.vision_parser.get_vision_parser", return_value=mock_parser):
        with patch(
            "knowledge_base.ocr_processor.get_ocr_processor",
            return_value=mock_ocr_processor,
        ):
            with pytest.raises(ValueError, match="Vision parsing failed in vision mode"):
                worker._extract_text(Path("/tmp/test.png"), "image/png")

    mock_ocr_processor.process.assert_not_called()


def test_video_fallback_to_metadata_when_audio_and_vision_are_unavailable():
    """When both audio and vision extraction fail, worker should still return fallback text."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)
    worker.parsing_method = "standard"
    worker._extract_video_with_vision = Mock(return_value="")

    mock_video_processor = Mock()
    mock_video_processor.process.side_effect = RuntimeError("audio stack unavailable")

    with patch(
        "knowledge_base.video_processor.get_video_processor", return_value=mock_video_processor
    ):
        result = worker._extract_text(Path("/tmp/test.mp4"), "video/mp4")

    assert "Video file 'test.mp4' was processed" in result
    assert "audio transcription failed" in result


def test_extract_text_infers_docx_type_when_mime_is_octet_stream(tmp_path):
    """Generic binary MIME should fallback to extension-based extractor routing."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)
    worker.parsing_method = "standard"

    docx_file = tmp_path / "sample.docx"
    docx_file.write_bytes(b"fake-docx")

    mock_extractor = Mock()
    mock_extractor.extract.return_value = Mock(text="extracted docx text")

    with patch(
        "knowledge_base.document_processor_worker.get_extractor", return_value=mock_extractor
    ) as mocked_get:
        result = worker._extract_text(docx_file, "application/octet-stream")

    assert result == "extracted docx text"
    mocked_get.assert_called_once_with(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_extract_video_with_vision_uses_15s_batches_and_summary():
    """Video vision fallback should batch 15 frames per request and summarize batches."""
    worker = DocumentProcessorWorker.__new__(DocumentProcessorWorker)

    mock_parser = Mock()
    mock_parser.parse_images = AsyncMock(
        side_effect=[
            ParseResult(text="batch-1 text"),
            ParseResult(text="batch-2 text"),
            ParseResult(text="batch-3 text"),
        ]
    )
    mock_parser.summarize_video_batches = AsyncMock(return_value="final summary")

    def _fake_ffmpeg_run(command, check):  # noqa: ANN001
        assert check is True
        assert "fps=1,scale=720:480" in command
        frame_pattern = command[-1]
        frame_dir = Path(frame_pattern).parent
        for i in range(1, 32):
            (frame_dir / f"frame_{i:03d}.jpg").write_bytes(b"x")

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("subprocess.run", side_effect=_fake_ffmpeg_run):
            with patch("knowledge_base.vision_parser.get_vision_parser", return_value=mock_parser):
                result = worker._extract_video_with_vision(Path("/tmp/test.mp4"))

    assert "Video Summary:\nfinal summary" in result
    assert "Segment 0000s-0014s:\nbatch-1 text" in result
    assert "Segment 0015s-0029s:\nbatch-2 text" in result
    assert "Segment 0030s-0030s:\nbatch-3 text" in result

    batch_sizes = [len(call.args[0]) for call in mock_parser.parse_images.await_args_list]
    assert batch_sizes == [15, 15, 1]
    mock_parser.summarize_video_batches.assert_awaited_once()


def test_indexer_skips_empty_chunks():
    """Empty chunk list should not call Milvus and should return a zero result."""
    indexer = KnowledgeIndexer.__new__(KnowledgeIndexer)
    result = KnowledgeIndexer.index_chunks(
        indexer,
        document_id="doc-empty",
        chunks=[],
        chunk_metadata=[],
        user_id="user-1",
    )

    assert result.document_id == "doc-empty"
    assert result.chunks_indexed == 0
    assert result.embeddings_generated == 0
