"""Unit tests for audio transcription processor behavior."""

from pathlib import Path
from unittest.mock import Mock, patch

import knowledge_base.audio_processor as audio_module
from knowledge_base.audio_processor import AudioProcessor


def _reset_audio_singleton():
    audio_module._audio_processor = None
    audio_module._audio_processor_signature = None


def test_get_audio_processor_reuses_singleton_when_signature_unchanged():
    """Identical effective settings should keep singleton instance."""
    _reset_audio_singleton()
    settings = {
        "engine": "funasr",
        "model": "iic/SenseVoiceSmall",
        "provider": "",
        "language": "auto",
        "temperature": None,
    }
    instance = Mock()

    with patch.object(audio_module, "_resolve_transcription_settings", return_value=settings):
        with patch.object(audio_module, "AudioProcessor", return_value=instance) as processor_cls:
            p1 = audio_module.get_audio_processor()
            p2 = audio_module.get_audio_processor()

    assert p1 is instance
    assert p2 is instance
    assert processor_cls.call_count == 1


def test_get_audio_processor_reloads_singleton_when_signature_changes():
    """Changing engine/model/provider/language should rebuild singleton."""
    _reset_audio_singleton()
    settings_1 = {
        "engine": "funasr",
        "model": "iic/SenseVoiceSmall",
        "provider": "",
        "language": "auto",
        "temperature": None,
    }
    settings_2 = {
        "engine": "openai_compatible",
        "model": "Qwen2.5-Omni-7B",
        "provider": "llm-pool",
        "language": "zh",
        "temperature": None,
    }
    instance_1 = Mock()
    instance_2 = Mock()

    with patch.object(
        audio_module,
        "_resolve_transcription_settings",
        side_effect=[settings_1, settings_2],
    ):
        with patch.object(
            audio_module,
            "AudioProcessor",
            side_effect=[instance_1, instance_2],
        ) as processor_cls:
            p1 = audio_module.get_audio_processor()
            p2 = audio_module.get_audio_processor()

    assert p1 is instance_1
    assert p2 is instance_2
    assert processor_cls.call_count == 2


def test_whisper_alias_is_mapped_to_funasr():
    """Legacy whisper engine setting should map to funasr."""
    _reset_audio_singleton()
    settings = {
        "engine": "whisper",
        "model": "iic/SenseVoiceSmall",
        "provider": "",
        "language": "auto",
        "temperature": None,
    }
    instance = Mock()

    with patch.object(audio_module, "_resolve_transcription_settings", return_value=settings):
        with patch.object(audio_module, "AudioProcessor", return_value=instance) as processor_cls:
            audio_module.get_audio_processor()

    assert processor_cls.call_count == 1
    assert processor_cls.call_args.kwargs["engine"] == "funasr"


def test_openai_transcription_endpoint_avoids_double_v1(tmp_path: Path):
    """Provider base_url ending with /v1 should not produce /v1/v1 in endpoint."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"dummy-audio")

    class _FakeResponse:
        status_code = 200
        text = '{"text":"hello"}'

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"text": "hello"}

    processor = AudioProcessor(
        engine="openai_compatible",
        provider="llm-pool",
        model_name="gpt-4o-mini-transcribe",
        language="auto",
    )

    with patch("llm_providers.provider_resolver.resolve_provider") as resolve_provider:
        resolve_provider.return_value = {
            "base_url": "http://example.com/v1",
            "api_key": "test-key",
        }
        with patch("knowledge_base.audio_processor.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse()
            result = processor._transcribe_with_openai_compatible(audio_path)

    assert result["text"] == "hello"
    assert mock_post.call_count == 1
    assert mock_post.call_args[0][0] == "http://example.com/v1/audio/transcriptions"


def test_openai_transcription_maps_nonstandard_text_field(tmp_path: Path):
    """Non-standard provider payloads should still map transcript text."""
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"dummy-audio")

    class _FakeResponse:
        status_code = 200
        text = '{"transcript":"fallback text"}'

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"transcript": "fallback text"}

    processor = AudioProcessor(
        engine="openai_compatible",
        provider="llm-pool",
        model_name="Qwen2.5-Omni-7B",
        language="zh",
    )

    with patch("llm_providers.provider_resolver.resolve_provider") as resolve_provider:
        resolve_provider.return_value = {"base_url": "http://example.com", "api_key": None}
        with patch("knowledge_base.audio_processor.requests.post") as mock_post:
            mock_post.return_value = _FakeResponse()
            result = processor._transcribe_with_openai_compatible(audio_path)

    assert result["text"] == "fallback text"


def test_openai_transcription_fallbacks_to_non_v1_endpoint(tmp_path: Path):
    """When /v1/audio/transcriptions fails, fallback endpoint should be attempted."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"dummy-audio")

    class _ErrorResponse:
        status_code = 500
        text = "internal error"

        @staticmethod
        def json():
            return {"error": "internal error"}

    class _SuccessResponse:
        status_code = 200
        text = '{"text":"ok"}'

        @staticmethod
        def json():
            return {"text": "ok"}

    processor = AudioProcessor(
        engine="openai_compatible",
        provider="llm-pool",
        model_name="FunAudioLLM/SenseVoiceSmall",
        language="auto",
    )

    with patch("llm_providers.provider_resolver.resolve_provider") as resolve_provider:
        resolve_provider.return_value = {"base_url": "http://example.com", "api_key": None}
        with patch("knowledge_base.audio_processor.requests.post") as mock_post:
            mock_post.side_effect = [_ErrorResponse(), _SuccessResponse()]
            result = processor._transcribe_with_openai_compatible(audio_path)

    assert result["text"] == "ok"
    assert result["_endpoint"] == "http://example.com/audio/transcriptions"
    assert mock_post.call_count == 2


def test_funasr_model_alias_normalizes_to_local_default():
    """Legacy remote model alias should normalize to local FunASR model."""
    processor = AudioProcessor(engine="funasr", model_name="FunAudioLLM/SenseVoiceSmall")
    assert processor.model_name == "iic/SenseVoiceSmall"


def test_funasr_service_transcription_success(tmp_path: Path):
    """FunASR service endpoint should return normalized payload."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"dummy-audio")

    class _FakeResponse:
        status_code = 200
        text = '{"text":"hello world"}'

        @staticmethod
        def json():
            return {"text": "hello world", "language": "zh"}

    processor = AudioProcessor(
        engine="funasr",
        model_name="iic/SenseVoiceSmall",
        language="auto",
        funasr_service_url="http://asr.local:10095",
    )

    with patch("knowledge_base.audio_processor.requests.post") as mock_post:
        mock_post.return_value = _FakeResponse()
        result = processor._transcribe_with_funasr_service(audio_path)

    assert result["text"] == "hello world"
    assert result["_endpoint"] == "http://asr.local:10095/transcribe"
    assert mock_post.call_args.kwargs["data"]["model"] == "iic/SenseVoiceSmall"


def test_transcribe_prefers_funasr_service_when_url_configured(tmp_path: Path):
    """FunASR engine should use service path when service URL is configured."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"dummy-audio")
    processor = AudioProcessor(
        engine="funasr",
        model_name="iic/SenseVoiceSmall",
        funasr_service_url="http://asr.local:10095",
    )

    with patch.object(processor, "_transcribe_with_funasr_service") as service_method:
        service_method.return_value = {"text": "svc", "language": "unknown", "segments": []}
        with patch.object(processor, "_transcribe_with_local_funasr") as local_method:
            result = processor.transcribe(audio_path)

    assert result.text == "svc"
    service_method.assert_called_once()
    local_method.assert_not_called()
