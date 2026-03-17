"""Unit tests for protocol clients without binding local sockets."""

import pytest

from llm_providers.models import ProviderProtocol
from llm_providers.protocol_clients import (
    OllamaClient,
    OpenAICompatibleClient,
    get_protocol_client,
)


class _FakeResponse:
    def __init__(self, status: int, json_payload=None, text_payload: str = ""):
        self.status = status
        self._json_payload = json_payload or {}
        self._text_payload = text_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json_payload

    async def text(self):
        return self._text_payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_ollama_client_fetch_models_success(monkeypatch):
    client = OllamaClient()
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                json_payload={
                    "models": [
                        {"name": "llama2"},
                        {"name": "mistral"},
                        {"name": "codellama"},
                    ]
                },
            )
        ]
    )
    monkeypatch.setattr("llm_providers.protocol_clients.aiohttp.ClientSession", lambda: session)

    models = await client.fetch_models("http://ollama.local")

    assert models == ["llama2", "mistral", "codellama"]
    assert session.calls[0][0] == "http://ollama.local/api/tags"


@pytest.mark.asyncio
async def test_ollama_client_fetch_models_timeout(monkeypatch):
    client = OllamaClient()
    session = _FakeSession([Exception("timeout")])
    monkeypatch.setattr("llm_providers.protocol_clients.aiohttp.ClientSession", lambda: session)

    with pytest.raises(Exception, match="timeout"):
        await client.fetch_models("http://ollama.local", timeout=1)


@pytest.mark.asyncio
async def test_openai_compatible_client_fetch_models_success(monkeypatch):
    client = OpenAICompatibleClient()
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                json_payload={
                    "data": [
                        {"id": "gpt-4"},
                        {"id": "gpt-3.5-turbo"},
                        {"id": "text-davinci-003"},
                    ]
                },
                text_payload="ok",
            )
        ]
    )
    monkeypatch.setattr("llm_providers.protocol_clients.aiohttp.ClientSession", lambda: session)

    models = await client.fetch_models("http://openai.local", api_key="test-key")

    assert models == ["gpt-4", "gpt-3.5-turbo", "text-davinci-003"]
    url, kwargs = session.calls[0]
    assert url == "http://openai.local/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_openai_compatible_client_fetch_models_no_api_key(monkeypatch):
    client = OpenAICompatibleClient()
    session = _FakeSession(
        [
            _FakeResponse(401, json_payload={"error": "Unauthorized"}, text_payload="Unauthorized"),
            _FakeResponse(401, json_payload={"error": "Unauthorized"}, text_payload="Unauthorized"),
        ]
    )
    monkeypatch.setattr("llm_providers.protocol_clients.aiohttp.ClientSession", lambda: session)

    with pytest.raises(Exception, match="Unauthorized"):
        await client.fetch_models("http://openai.local")


@pytest.mark.asyncio
async def test_openai_compatible_client_fetch_model_metadata_preserves_audio_fields(monkeypatch):
    client = OpenAICompatibleClient()
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                json_payload={
                    "id": "sensevoicesmall",
                    "model_type": "audio",
                    "description": "ASR model",
                    "model_ability": ["audio"],
                    "context_length": 16384,
                },
            )
        ]
    )
    monkeypatch.setattr("llm_providers.protocol_clients.aiohttp.ClientSession", lambda: session)

    metadata = await client.fetch_model_metadata("http://openai.local", "sensevoicesmall")

    assert metadata == {
        "model_id": "sensevoicesmall",
        "object": None,
        "created": None,
        "owned_by": None,
        "context_window": 16384,
        "model_type": "audio",
        "description": "ASR model",
        "model_ability": ["audio"],
    }


def test_get_protocol_client_ollama():
    client = get_protocol_client(ProviderProtocol.OLLAMA)
    assert isinstance(client, OllamaClient)


def test_get_protocol_client_openai():
    client = get_protocol_client(ProviderProtocol.OPENAI_COMPATIBLE)
    assert isinstance(client, OpenAICompatibleClient)


def test_get_protocol_client_invalid():
    with pytest.raises(ValueError, match="Unsupported protocol"):
        get_protocol_client("invalid_protocol")
