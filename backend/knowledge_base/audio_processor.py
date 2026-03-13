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
from typing import Any, Optional

import requests

from knowledge_base.config_utils import load_knowledge_base_config
from shared.config import get_config

logger = logging.getLogger(__name__)


def _resolve_transcription_settings() -> dict:
    """Resolve transcription runtime settings from knowledge_base.processing.transcription."""
    config = get_config()
    kb_config = load_knowledge_base_config(config)
    processing_cfg = kb_config.get("processing", {})
    transcription_cfg = processing_cfg.get("transcription", {})

    return {
        "engine": str(transcription_cfg.get("engine", "funasr")).strip().lower(),
        "model": str(transcription_cfg.get("model", "iic/SenseVoiceSmall")).strip(),
        "provider": str(transcription_cfg.get("provider", "")).strip(),
        "language": str(transcription_cfg.get("language", "auto")).strip().lower(),
        "temperature": transcription_cfg.get("temperature"),
        "funasr_service_url": str(transcription_cfg.get("funasr_service_url", "")).strip(),
        "funasr_service_timeout_seconds": transcription_cfg.get(
            "funasr_service_timeout_seconds", 300
        ),
        "funasr_service_api_key": str(transcription_cfg.get("funasr_service_api_key", "")).strip(),
    }


def _normalize_transcription_engine(value: Optional[str]) -> str:
    """Normalize supported transcription engine names."""
    raw = str(value or "funasr").strip().lower()
    alias_map = {
        "local": "funasr",
        "local_funasr": "funasr",
        "whisper": "funasr",
        "local_whisper": "funasr",
        "openai": "openai_compatible",
        "remote": "openai_compatible",
        "llm": "openai_compatible",
    }
    normalized = alias_map.get(raw, raw)
    if raw in {"whisper", "local_whisper"}:
        logger.warning(
            "Whisper transcription engine is deprecated; using FunASR instead",
            extra={"requested_engine": raw, "effective_engine": normalized},
        )
    return normalized


def _normalize_funasr_model_name(model_name: str) -> str:
    """Map legacy/remote model aliases to local FunASR defaults."""
    raw = (model_name or "").strip()
    if not raw:
        return "iic/SenseVoiceSmall"

    aliases = {
        "funaudiollm/sensevoicesmall": "iic/SenseVoiceSmall",
        "sensevoicesmall": "iic/SenseVoiceSmall",
    }
    return aliases.get(raw.lower(), raw)


def _extract_text_from_payload(payload: dict[str, Any]) -> str:
    """Extract transcription text from heterogeneous provider payloads."""
    candidate_keys = ("text", "transcript", "output_text", "result")
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        if isinstance(value, list):
            chunks: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        chunks.append(text)
                elif isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        chunks.append(text)
            if chunks:
                return " ".join(chunks)
        if isinstance(value, dict):
            text = str(value.get("text", "")).strip()
            if text:
                return text

    sentence_info = payload.get("sentence_info")
    if isinstance(sentence_info, list):
        segments = []
        for segment in sentence_info:
            if isinstance(segment, dict):
                text = str(segment.get("text", "")).strip()
                if text:
                    segments.append(text)
        if segments:
            return " ".join(segments)

    return ""


def _normalize_transcription_payload(payload: Any) -> dict[str, Any]:
    """Normalize transcription response payload into a dict with text."""
    if isinstance(payload, str):
        return {"text": payload}
    if not isinstance(payload, dict):
        raise ValueError("Invalid transcription response format")

    normalized = dict(payload)
    normalized["text"] = _extract_text_from_payload(normalized)
    return normalized


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""

    text: str
    language: str
    duration: float
    processing_time: float
    segments: list[dict]


class AudioProcessor:
    """Process audio files with local FunASR or OpenAI-compatible transcription."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        engine: Optional[str] = None,
        provider: Optional[str] = None,
        language: Optional[str] = None,
        temperature: Optional[float] = None,
        funasr_service_url: Optional[str] = None,
        funasr_service_timeout_seconds: Optional[int] = None,
        funasr_service_api_key: Optional[str] = None,
    ):
        """Initialize audio processor.

        Args:
            model_name: Transcription model name
            engine: Transcription engine, e.g. funasr/openai_compatible
            provider: Provider name for OpenAI-compatible transcription
            language: Language code or "auto"
            temperature: Optional transcription temperature
            funasr_service_url: Optional FunASR HTTP service endpoint
            funasr_service_timeout_seconds: FunASR service request timeout in seconds
            funasr_service_api_key: Optional auth key for FunASR service
        """
        transcription_cfg = _resolve_transcription_settings()

        self.engine = _normalize_transcription_engine(
            str(engine if engine is not None else transcription_cfg.get("engine", "funasr"))
        )
        self.model_name = str(
            model_name
            if model_name is not None
            else transcription_cfg.get("model", "iic/SenseVoiceSmall")
        ).strip()
        if self.engine == "funasr":
            self.model_name = _normalize_funasr_model_name(self.model_name)
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
        self.funasr_service_url = str(
            funasr_service_url
            if funasr_service_url is not None
            else transcription_cfg.get("funasr_service_url", "")
        ).strip()
        self.funasr_service_timeout_seconds = int(
            funasr_service_timeout_seconds
            if funasr_service_timeout_seconds is not None
            else transcription_cfg.get("funasr_service_timeout_seconds", 300)
        )
        self.funasr_service_api_key = str(
            funasr_service_api_key
            if funasr_service_api_key is not None
            else transcription_cfg.get("funasr_service_api_key", "")
        ).strip()
        self._model = None

        logger.info(
            "AudioProcessor initialized",
            extra={
                "engine": self.engine,
                "model": self.model_name,
                "provider": self.provider,
                "language": self.language,
                "funasr_service_url": self.funasr_service_url,
            },
        )

    def _transcribe_with_funasr_service(self, audio_path: Path) -> dict:
        """Transcribe with external FunASR service via HTTP."""
        if not self.funasr_service_url:
            raise ValueError("funasr_service_url is empty")

        endpoint = f"{self.funasr_service_url.rstrip('/')}/transcribe"
        headers = {}
        if self.funasr_service_api_key:
            headers["Authorization"] = f"Bearer {self.funasr_service_api_key}"

        data = {"model": self.model_name}
        if self.language and self.language != "auto":
            data["language"] = self.language

        content_type = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"
        with open(audio_path, "rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, content_type)}
            response = requests.post(
                endpoint,
                headers=headers,
                data=data,
                files=files,
                timeout=max(30, self.funasr_service_timeout_seconds),
            )

        if response.status_code >= 400:
            details = response.text.replace("\n", " ").strip()[:400]
            raise RuntimeError(
                f"FunASR service failed ({response.status_code}) at {endpoint}: "
                f"{details or '<empty body>'}"
            )

        payload = _normalize_transcription_payload(response.json())
        payload["_endpoint"] = endpoint
        if not payload.get("language"):
            payload["language"] = self.language if self.language != "auto" else "unknown"
        if not payload.get("segments"):
            payload["segments"] = []
        return payload

    def _get_local_funasr_model(self):
        """Lazily load local FunASR model only when needed."""
        if self._model is None:
            try:
                from funasr import AutoModel
            except ModuleNotFoundError as err:
                raise RuntimeError(
                    "Local FunASR is unavailable (missing package or dependency). "
                    "Install/repair funasr dependencies in backend/.venv, or switch "
                    "transcription engine to openai_compatible. "
                    f"Original error: {err}"
                ) from err
            try:
                self._model = AutoModel(model=self.model_name)
            except Exception as err:
                raise RuntimeError(
                    "Local FunASR model initialization failed. "
                    "Please verify FunASR runtime dependencies and model files. "
                    f"Original error: {err}"
                ) from err
        return self._model

    def _transcribe_with_local_funasr(self, audio_path: Path) -> dict:
        """Transcribe with local FunASR model."""
        model = self._get_local_funasr_model()
        options: dict[str, Any] = {"input": str(audio_path)}
        if self.language and self.language != "auto":
            options["language"] = self.language

        try:
            result = model.generate(**options)
        except TypeError:
            # Some FunASR builds do not accept language kwarg.
            options.pop("language", None)
            result = model.generate(**options)

        payload: Any = result[0] if isinstance(result, list) and result else result
        normalized = _normalize_transcription_payload(payload)
        if not normalized.get("segments"):
            sentence_info = payload.get("sentence_info") if isinstance(payload, dict) else None
            normalized["segments"] = sentence_info if isinstance(sentence_info, list) else []
        if not normalized.get("language"):
            normalized["language"] = self.language if self.language != "auto" else "unknown"
        return normalized

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

        base_without_v1 = base_url[:-3] if base_url.endswith("/v1") else base_url
        if base_url.endswith("/v1"):
            endpoints = [f"{base_url}/audio/transcriptions"]
        else:
            endpoints = [f"{base_url}/v1/audio/transcriptions"]
        endpoints.append(f"{base_without_v1}/audio/transcriptions")
        endpoints = list(dict.fromkeys(endpoints))

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        data = {"model": self.model_name}
        if self.language and self.language != "auto":
            data["language"] = self.language
        if self.temperature is not None:
            data["temperature"] = self.temperature

        content_type = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"

        errors: list[str] = []
        for endpoint in endpoints:
            try:
                with open(audio_path, "rb") as audio_file:
                    files = {"file": (audio_path.name, audio_file, content_type)}
                    response = requests.post(
                        endpoint,
                        headers=headers,
                        data=data,
                        files=files,
                        timeout=180,
                    )
            except requests.RequestException as exc:
                errors.append(f"{endpoint} -> request_error: {exc}")
                continue

            if response.status_code >= 400:
                details = response.text.replace("\n", " ").strip()[:240]
                errors.append(
                    f"{endpoint} -> HTTP {response.status_code}: {details or '<empty body>'}"
                )
                continue

            try:
                payload = _normalize_transcription_payload(response.json())
            except ValueError as exc:
                errors.append(f"{endpoint} -> invalid_response: {exc}")
                continue
            payload["_endpoint"] = endpoint
            return payload

        raise RuntimeError(
            "All OpenAI-compatible transcription endpoints failed. " + " | ".join(errors)
        )

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file

        Returns:
            TranscriptionResult with transcribed text
        """
        start_time = datetime.now()

        try:
            if self.engine == "funasr":
                if self.funasr_service_url:
                    result = self._transcribe_with_funasr_service(audio_path)
                else:
                    result = self._transcribe_with_local_funasr(audio_path)
            elif self.engine == "openai_compatible":
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
                    "endpoint": result.get("_endpoint"),
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
_audio_processor_signature: Optional[
    tuple[str, str, str, str, Optional[float], str, int, str]
] = None


def _normalize_temperature(value) -> Optional[float]:
    """Normalize temperature for signature comparison."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_timeout_seconds(value, default: int = 300) -> int:
    """Normalize timeout value for signature comparison."""
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return default
    return max(5, timeout)


def get_audio_processor(
    model_name: Optional[str] = None,
    engine: Optional[str] = None,
    provider: Optional[str] = None,
    language: Optional[str] = None,
    temperature: Optional[float] = None,
    funasr_service_url: Optional[str] = None,
    funasr_service_timeout_seconds: Optional[int] = None,
    funasr_service_api_key: Optional[str] = None,
) -> AudioProcessor:
    """Get or create the audio processor singleton.

    Args:
        model_name: Transcription model name override
        engine: Transcription engine override
        provider: Provider override for OpenAI-compatible transcription
        language: Language override
        temperature: Temperature override
        funasr_service_url: FunASR service endpoint override
        funasr_service_timeout_seconds: FunASR service timeout override
        funasr_service_api_key: FunASR service API key override

    Returns:
        AudioProcessor instance
    """
    global _audio_processor, _audio_processor_signature

    resolved = _resolve_transcription_settings()
    effective_engine = _normalize_transcription_engine(
        str(engine if engine is not None else resolved.get("engine", "funasr")).strip()
    )
    effective_model = str(
        model_name if model_name is not None else resolved.get("model", "iic/SenseVoiceSmall")
    ).strip()
    effective_provider = str(
        provider if provider is not None else resolved.get("provider", "")
    ).strip()
    effective_language = str(language if language is not None else resolved.get("language", "auto"))
    effective_language = effective_language.strip().lower() or "auto"
    effective_temperature = temperature if temperature is not None else resolved.get("temperature")
    effective_temperature = _normalize_temperature(effective_temperature)
    effective_funasr_service_url = str(
        funasr_service_url
        if funasr_service_url is not None
        else resolved.get("funasr_service_url", "")
    ).strip()
    effective_funasr_service_timeout_seconds = _normalize_timeout_seconds(
        funasr_service_timeout_seconds
        if funasr_service_timeout_seconds is not None
        else resolved.get("funasr_service_timeout_seconds", 300)
    )
    effective_funasr_service_api_key = str(
        funasr_service_api_key
        if funasr_service_api_key is not None
        else resolved.get("funasr_service_api_key", "")
    ).strip()

    signature = (
        effective_engine,
        effective_model,
        effective_provider,
        effective_language,
        effective_temperature,
        effective_funasr_service_url,
        effective_funasr_service_timeout_seconds,
        effective_funasr_service_api_key,
    )

    if _audio_processor is None or _audio_processor_signature != signature:
        _audio_processor = AudioProcessor(
            model_name=effective_model,
            engine=effective_engine,
            provider=effective_provider,
            language=effective_language,
            temperature=effective_temperature,
            funasr_service_url=effective_funasr_service_url,
            funasr_service_timeout_seconds=effective_funasr_service_timeout_seconds,
            funasr_service_api_key=effective_funasr_service_api_key,
        )
        _audio_processor_signature = signature
    return _audio_processor
