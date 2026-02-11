"""Audio transcription for audio/video content.

References:
- Requirements 16: Document Processing
- Design Section 14.2: Supported File Types
"""

import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from shared.config import get_config

logger = logging.getLogger(__name__)


def _resolve_transcription_settings() -> dict:
    """Resolve transcription runtime settings from knowledge_base.processing.transcription."""
    config = get_config()
    kb_config = config.get_section("knowledge_base") if config else {}
    processing_cfg = kb_config.get("processing", {})
    transcription_cfg = processing_cfg.get("transcription", {})

    return {
        "engine": str(transcription_cfg.get("engine", "whisper")).strip().lower(),
        "model": str(transcription_cfg.get("model", "base")).strip(),
        "provider": str(transcription_cfg.get("provider", "")).strip(),
        "language": str(transcription_cfg.get("language", "auto")).strip().lower(),
        "temperature": transcription_cfg.get("temperature"),
    }


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""

    text: str
    language: str
    duration: float
    processing_time: float
    segments: list[dict]


class AudioProcessor:
    """Process audio files with local or OpenAI-compatible transcription."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        engine: Optional[str] = None,
        provider: Optional[str] = None,
        language: Optional[str] = None,
        temperature: Optional[float] = None,
    ):
        """Initialize audio processor.

        Args:
            model_name: Transcription model name
            engine: Transcription engine, e.g. whisper/openai_compatible
            provider: Provider name for OpenAI-compatible transcription
            language: Language code or "auto"
            temperature: Optional transcription temperature
        """
        transcription_cfg = _resolve_transcription_settings()

        self.engine = (
            str(engine if engine is not None else transcription_cfg.get("engine", "whisper"))
            .strip()
            .lower()
        )
        self.model_name = str(
            model_name if model_name is not None else transcription_cfg.get("model", "base")
        ).strip()
        self.provider = str(
            provider if provider is not None else transcription_cfg.get("provider", "")
        ).strip()
        self.language = (
            str(language if language is not None else transcription_cfg.get("language", "auto"))
            .strip()
            .lower()
        )
        self.temperature = (
            temperature if temperature is not None else transcription_cfg.get("temperature")
        )
        self._model = None

        logger.info(
            "AudioProcessor initialized",
            extra={
                "engine": self.engine,
                "model": self.model_name,
                "provider": self.provider,
                "language": self.language,
            },
        )

    def _get_local_whisper_model(self):
        """Lazily load local whisper model only when needed."""
        if self._model is None:
            try:
                import whisper
            except ModuleNotFoundError as err:
                raise RuntimeError(
                    "Local whisper is not installed. "
                    "Install openai-whisper or switch transcription engine to openai_compatible."
                ) from err
            self._model = whisper.load_model(self.model_name)
        return self._model

    def _transcribe_with_local_whisper(self, audio_path: Path) -> dict:
        """Transcribe with local whisper model."""
        model = self._get_local_whisper_model()
        options = {}
        if self.language and self.language != "auto":
            options["language"] = self.language
        result = model.transcribe(str(audio_path), **options)
        return result

    def _transcribe_with_openai_compatible(self, audio_path: Path) -> dict:
        """Transcribe via OpenAI-compatible audio transcription endpoint."""
        from llm_providers.provider_resolver import resolve_provider

        if not self.provider:
            raise ValueError("transcription.provider is required when engine is openai_compatible")

        provider_cfg = resolve_provider(self.provider)
        if not provider_cfg:
            raise ValueError(f"Provider '{self.provider}' not found")

        base_url = (provider_cfg.get("base_url") or "").rstrip("/")
        api_key = provider_cfg.get("api_key")
        if not base_url:
            raise ValueError(f"Provider '{self.provider}' has no base_url configured")

        if base_url.endswith("/v1"):
            endpoint = f"{base_url}/audio/transcriptions"
        else:
            endpoint = f"{base_url}/v1/audio/transcriptions"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        data = {"model": self.model_name}
        if self.language and self.language != "auto":
            data["language"] = self.language
        if self.temperature is not None:
            data["temperature"] = self.temperature

        content_type = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"

        with open(audio_path, "rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, content_type)}
            response = requests.post(
                endpoint,
                headers=headers,
                data=data,
                files=files,
                timeout=180,
            )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, str):
            return {"text": payload}
        if not isinstance(payload, dict):
            raise ValueError("Invalid transcription response format")
        if "text" not in payload:
            payload["text"] = str(
                payload.get("transcript")
                or payload.get("output_text")
                or payload.get("result")
                or ""
            )
        return payload

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file

        Returns:
            TranscriptionResult with transcribed text
        """
        start_time = datetime.now()

        try:
            if self.engine in {"whisper", "local", "local_whisper"}:
                result = self._transcribe_with_local_whisper(audio_path)
            elif self.engine in {"openai", "openai_compatible", "remote", "llm"}:
                result = self._transcribe_with_openai_compatible(audio_path)
            else:
                raise ValueError(f"Unsupported transcription engine: {self.engine}")

            processing_time = (datetime.now() - start_time).total_seconds()

            logger.info(
                "Audio transcription completed",
                extra={
                    "file": str(audio_path),
                    "engine": self.engine,
                    "provider": self.provider,
                    "model": self.model_name,
                    "language": result.get("language", "unknown"),
                    "text_length": len(result.get("text", "")),
                    "time": processing_time,
                },
            )

            return TranscriptionResult(
                text=result.get("text", ""),
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
_audio_processor_signature: Optional[tuple[str, str, str, str, Optional[float]]] = None


def _normalize_temperature(value) -> Optional[float]:
    """Normalize temperature for signature comparison."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_audio_processor(
    model_name: Optional[str] = None,
    engine: Optional[str] = None,
    provider: Optional[str] = None,
    language: Optional[str] = None,
    temperature: Optional[float] = None,
) -> AudioProcessor:
    """Get or create the audio processor singleton.

    Args:
        model_name: Transcription model name override
        engine: Transcription engine override
        provider: Provider override for OpenAI-compatible transcription
        language: Language override
        temperature: Temperature override

    Returns:
        AudioProcessor instance
    """
    global _audio_processor, _audio_processor_signature

    resolved = _resolve_transcription_settings()
    effective_engine = str(
        engine if engine is not None else resolved.get("engine", "whisper")
    ).strip()
    effective_engine = (effective_engine or "whisper").lower()
    effective_model = str(
        model_name if model_name is not None else resolved.get("model", "base")
    ).strip()
    effective_provider = str(
        provider if provider is not None else resolved.get("provider", "")
    ).strip()
    effective_language = str(language if language is not None else resolved.get("language", "auto"))
    effective_language = effective_language.strip().lower() or "auto"
    effective_temperature = temperature if temperature is not None else resolved.get("temperature")
    effective_temperature = _normalize_temperature(effective_temperature)

    signature = (
        effective_engine,
        effective_model,
        effective_provider,
        effective_language,
        effective_temperature,
    )

    if _audio_processor is None or _audio_processor_signature != signature:
        _audio_processor = AudioProcessor(
            model_name=effective_model,
            engine=effective_engine,
            provider=effective_provider,
            language=effective_language,
            temperature=effective_temperature,
        )
        _audio_processor_signature = signature
    return _audio_processor
