"""Video processing with audio extraction and transcription.

References:
- Requirements 16: Document Processing
- Design Section 14.2: Supported File Types
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from knowledge_base.audio_processor import AudioProcessor, TranscriptionResult

logger = logging.getLogger(__name__)


def _load_video_file_clip():
    """Load VideoFileClip with compatibility for moviepy v1 and v2."""
    try:
        from moviepy.editor import VideoFileClip

        return VideoFileClip
    except ModuleNotFoundError:
        try:
            from moviepy import VideoFileClip

            return VideoFileClip
        except ModuleNotFoundError as err:
            raise RuntimeError(
                "moviepy is required for video processing. Install with: pip install moviepy"
            ) from err


@dataclass
class VideoProcessingResult:
    """Result of video processing."""

    transcription: TranscriptionResult
    video_duration: float
    video_size: tuple[int, int]
    fps: float
    processing_time: float


class VideoProcessor:
    """Process video files by extracting audio and transcribing."""

    def __init__(self, audio_processor: Optional[AudioProcessor] = None):
        """Initialize video processor.

        Args:
            audio_processor: AudioProcessor instance for transcription
        """
        self.audio_processor = audio_processor
        logger.info("VideoProcessor initialized")

    def _get_audio_processor(self) -> AudioProcessor:
        """Lazily load AudioProcessor so missing whisper does not break module import."""
        if self.audio_processor is None:
            from knowledge_base.audio_processor import get_audio_processor

            self.audio_processor = get_audio_processor()
        return self.audio_processor

    def process(self, video_path: Path) -> VideoProcessingResult:
        """Process video file by extracting and transcribing audio.

        Args:
            video_path: Path to video file

        Returns:
            VideoProcessingResult with transcription and metadata
        """
        start_time = datetime.now()

        try:
            # Load video
            VideoFileClip = _load_video_file_clip()
            video = VideoFileClip(str(video_path))

            try:
                # Extract metadata
                video_duration = video.duration
                video_size = video.size
                fps = video.fps

                if video.audio is None:
                    raise ValueError("Video file has no audio track")

                # Extract audio to temporary file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                    temp_audio_path = Path(temp_audio.name)
                try:
                    video.audio.write_audiofile(str(temp_audio_path), logger=None)
                    # Transcribe audio
                    transcription = self._get_audio_processor().transcribe(temp_audio_path)
                finally:
                    temp_audio_path.unlink(missing_ok=True)
            finally:
                video.close()

            processing_time = (datetime.now() - start_time).total_seconds()

            logger.info(
                "Video processing completed",
                extra={
                    "file": str(video_path),
                    "duration": video_duration,
                    "text_length": len(transcription.text),
                    "time": processing_time,
                },
            )

            return VideoProcessingResult(
                transcription=transcription,
                video_duration=video_duration,
                video_size=video_size,
                fps=fps,
                processing_time=processing_time,
            )

        except ModuleNotFoundError as e:
            logger.warning(f"Video processing dependency missing: {e}")
            raise
        except Exception as e:
            logger.error(f"Video processing failed: {e}", exc_info=True)
            raise


# Singleton instance
_video_processor: Optional[VideoProcessor] = None


def get_video_processor() -> VideoProcessor:
    """Get or create the video processor singleton.

    Returns:
        VideoProcessor instance
    """
    global _video_processor
    if _video_processor is None:
        _video_processor = VideoProcessor()
    return _video_processor
