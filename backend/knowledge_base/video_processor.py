"""Video processing with audio extraction and transcription.

References:
- Requirements 16: Document Processing
- Design Section 14.2: Supported File Types
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import tempfile

from moviepy.editor import VideoFileClip
from knowledge_base.audio_processor import AudioProcessor, TranscriptionResult

logger = logging.getLogger(__name__)


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
        self.audio_processor = audio_processor or AudioProcessor()
        logger.info("VideoProcessor initialized")
    
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
            video = VideoFileClip(str(video_path))
            
            # Extract metadata
            video_duration = video.duration
            video_size = video.size
            fps = video.fps
            
            # Extract audio to temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                temp_audio_path = Path(temp_audio.name)
                video.audio.write_audiofile(str(temp_audio_path), logger=None)
            
            # Transcribe audio
            transcription = self.audio_processor.transcribe(temp_audio_path)
            
            # Clean up
            temp_audio_path.unlink()
            video.close()
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                "Video processing completed",
                extra={
                    "file": str(video_path),
                    "duration": video_duration,
                    "text_length": len(transcription.text),
                    "time": processing_time,
                }
            )
            
            return VideoProcessingResult(
                transcription=transcription,
                video_duration=video_duration,
                video_size=video_size,
                fps=fps,
                processing_time=processing_time,
            )
            
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
