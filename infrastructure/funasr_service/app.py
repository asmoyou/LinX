"""Standalone FunASR transcription microservice.

This service isolates FunASR runtime dependencies from the main backend.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

logger = logging.getLogger("funasr-service")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DEFAULT_MODEL = os.getenv("FUNASR_MODEL", "iic/SenseVoiceSmall").strip() or "iic/SenseVoiceSmall"
OPTIONAL_AUTH_TOKEN = os.getenv("FUNASR_AUTH_TOKEN", "").strip()
SERVICE_PORT = int(os.getenv("PORT", "10095"))

app = FastAPI(title="FunASR Service", version="1.0.0")

_models: dict[str, Any] = {}
_model_lock = Lock()


def _extract_text_from_payload(payload: dict[str, Any]) -> str:
    """Extract text from heterogeneous FunASR payload variants."""
    for key in ("text", "transcript", "result", "output_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            chunks: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    chunks.append(item.strip())
                elif isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        chunks.append(text)
            if chunks:
                return " ".join(chunks)

    sentence_info = payload.get("sentence_info")
    if isinstance(sentence_info, list):
        chunks = []
        for seg in sentence_info:
            if isinstance(seg, dict):
                text = str(seg.get("text", "")).strip()
                if text:
                    chunks.append(text)
        if chunks:
            return " ".join(chunks)

    return ""


def _normalize_response_payload(raw_payload: Any, language: str) -> dict[str, Any]:
    """Normalize FunASR result into stable response shape."""
    payload = raw_payload[0] if isinstance(raw_payload, list) and raw_payload else raw_payload
    if isinstance(payload, str):
        return {
            "text": payload.strip(),
            "language": language if language != "auto" else "unknown",
            "segments": [],
        }
    if not isinstance(payload, dict):
        raise RuntimeError("Unsupported FunASR response payload")

    text = _extract_text_from_payload(payload)
    segments = payload.get("sentence_info") if isinstance(payload.get("sentence_info"), list) else []
    result = dict(payload)
    result["text"] = text
    result["segments"] = segments
    if not result.get("language"):
        result["language"] = language if language != "auto" else "unknown"
    return result


def _get_model(model_name: str):
    """Get cached model instance for the target model name."""
    normalized = model_name.strip() or DEFAULT_MODEL

    with _model_lock:
        if normalized in _models:
            return _models[normalized]

        try:
            from funasr import AutoModel
        except Exception as err:  # pragma: no cover - startup/runtime environment issue
            raise RuntimeError(f"Failed to import FunASR AutoModel: {err}") from err

        logger.info("Loading FunASR model: %s", normalized)
        try:
            model = AutoModel(model=normalized)
        except Exception as err:
            raise RuntimeError(f"Failed to initialize model '{normalized}': {err}") from err

        _models[normalized] = model
        return model


def _verify_auth_header(authorization: str | None) -> None:
    """Validate optional bearer token auth."""
    if not OPTIONAL_AUTH_TOKEN:
        return
    expected = f"Bearer {OPTIONAL_AUTH_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict[str, Any]:
    """Service health endpoint."""
    return {"status": "ok", "default_model": DEFAULT_MODEL, "loaded_models": list(_models.keys())}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
    language: str = Form("auto"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Transcribe uploaded audio using FunASR."""
    _verify_auth_header(authorization)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing audio filename")

    suffix = Path(file.filename).suffix or ".wav"
    started = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
        temp_path = Path(temp_audio.name)
        temp_audio.write(await file.read())

    try:
        model_instance = _get_model(model)
        options: dict[str, Any] = {"input": str(temp_path)}
        normalized_language = (language or "auto").strip().lower()
        if normalized_language and normalized_language != "auto":
            options["language"] = normalized_language

        try:
            payload = model_instance.generate(**options)
        except TypeError:
            options.pop("language", None)
            payload = model_instance.generate(**options)

        normalized = _normalize_response_payload(payload, normalized_language)
        normalized["model"] = model
        normalized["processing_time"] = round(time.perf_counter() - started, 4)
        return normalized
    except HTTPException:
        raise
    except Exception as err:
        logger.error("FunASR transcription failed: %s", err, exc_info=True)
        raise HTTPException(status_code=500, detail=f"FunASR transcription failed: {err}") from err
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
