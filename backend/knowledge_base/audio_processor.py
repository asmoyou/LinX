"""Audio transcription using Whisper.

References:
- Requirements 16: Document Processing
- Design Section 14.2: Supported File Types
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import whisper

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""

    text: str
    language: str
    duration: float
    processing_time: float
    segments: list[dict]


class AudioProcessor:
    """Process audio files with Whisper transcription."""

    def __init__(self, model_name: str = "base"):
        """Initialize audio processor.

        Args:
            model_name: Whisper model name (tiny, base, small, medium, large)
        """
        self.model_name = model_name
        self.model = whisper.load_model(model_name)
        logger.info(f"AudioProcessor initialized with model: {model_name}")

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file

        Returns:
            TranscriptionResult with transcribed text
        """
        start_time = datetime.now()

        try:
            # Transcribe audio
            result = self.model.transcribe(str(audio_path))

            processing_time = (datetime.now() - start_time).total_seconds()

            logger.info(
                "Audio transcription completed",
                extra={
                    "file": str(audio_path),
                    "language": result.get("language", "unknown"),
                    "text_length": len(result["text"]),
                    "time": processing_time,
                },
            )

            return TranscriptionResult(
                text=result["text"],
                language=result.get("language", "unknown"),
                duration=result.get("duration", 0.0),
                processing_time=processing_time,
                segments=result.get("segments", []),
            )

        except Exception as e:
            logger.error(f"Audio transcription failed: {e}", exc_info=True)
            raise


# Singleton instance
_audio_processor: Optional[AudioProcessor] = None


def get_audio_processor(model_name: str = "base") -> AudioProcessor:
    """Get or create the audio processor singleton.

    Args:
        model_name: Whisper model name

    Returns:
        AudioProcessor instance
    """
    global _audio_processor
    if _audio_processor is None:
        _audio_processor = AudioProcessor(model_name=model_name)
    return _audio_processor
