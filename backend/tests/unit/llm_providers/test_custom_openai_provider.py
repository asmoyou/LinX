"""Unit tests for CustomOpenAIChat tool-calling behavior."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from llm_providers.custom_openai_provider import CustomOpenAIChat, StreamCancelledError


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    return expression


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self._payload


def test_bind_tools_sends_openai_tool_payload(monkeypatch):
    captured_payload: Dict[str, Any] = {}

    def _fake_post(
        _url: str,
        *,
        json: Dict[str, Any],
        headers: Dict[str, Any],
        timeout: int,
    ) -> _FakeResponse:
        del headers, timeout
        captured_payload.update(json)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": '{"expression":"23223 * 23 / 32"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            }
        )

    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.post", _fake_post)

    llm = CustomOpenAIChat(base_url="https://example.com/v1", model="qwen3.5-flash")
    bound = llm.bind_tools([calculator], tool_choice="calculator")
    message = bound.invoke([HumanMessage(content="23223*23/32=?")])

    assert "tools" in captured_payload
    assert isinstance(captured_payload["tools"], list)
    assert captured_payload["tools"][0]["function"]["name"] == "calculator"
    assert captured_payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "calculator"},
    }
    assert message.tool_calls
    assert message.tool_calls[0]["name"] == "calculator"
    assert message.tool_calls[0]["args"]["expression"] == "23223 * 23 / 32"


def test_stream_restores_tool_calls_from_chunks(monkeypatch):
    lines: List[str] = [
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"calculator","arguments":"{\\"expression\\":\\""}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"23223 * 23 / 32\\"}"}}]}}]}',
        "data: [DONE]",
    ]

    class _FakeStreamResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            for line in lines:
                yield line

    class _FakeStreamContext:
        def __enter__(self) -> _FakeStreamResponse:
            return _FakeStreamResponse()

        def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
            del exc_type, exc_val, exc_tb
            return False

    def _fake_stream(
        _method: str,
        _url: str,
        *,
        json: Dict[str, Any],
        headers: Dict[str, Any],
        timeout: int,
    ) -> _FakeStreamContext:
        del json, headers, timeout
        return _FakeStreamContext()

    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.stream", _fake_stream)

    llm = CustomOpenAIChat(base_url="https://example.com/v1", model="qwen3.5-flash")
    chunks = list(llm.stream([HumanMessage(content="23223*23/32=?")]))
    assert chunks

    merged = None
    for chunk in chunks:
        merged = chunk if merged is None else merged + chunk

    assert merged is not None
    assert merged.tool_calls
    assert merged.tool_calls[0]["name"] == "calculator"
    assert merged.tool_calls[0]["args"]["expression"] == "23223 * 23 / 32"


def test_stream_handles_non_sse_json_body(monkeypatch):
    lines: List[str] = [
        (
            '{"choices":[{"message":{"content":"plain json response"}}],'
            '"usage":{"prompt_tokens":3,"completion_tokens":2}}'
        ),
    ]

    class _FakeStreamResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            for line in lines:
                yield line

    class _FakeStreamContext:
        def __enter__(self) -> _FakeStreamResponse:
            return _FakeStreamResponse()

        def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
            del exc_type, exc_val, exc_tb
            return False

    def _fake_stream(
        _method: str,
        _url: str,
        *,
        json: Dict[str, Any],
        headers: Dict[str, Any],
        timeout: int,
    ) -> _FakeStreamContext:
        del json, headers, timeout
        return _FakeStreamContext()

    def _unexpected_post(*_args, **_kwargs):
        raise AssertionError("non-SSE stream should be parsed directly without post fallback")

    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.stream", _fake_stream)
    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.post", _unexpected_post)

    llm = CustomOpenAIChat(base_url="https://example.com/v1", model="qwen3.5-flash")
    chunks = list(llm.stream([HumanMessage(content="hello")]))
    assert chunks
    assert any(chunk.content == "plain json response" for chunk in chunks)


def test_stream_timeout_uses_longer_read_deadline():
    llm = CustomOpenAIChat(
        base_url="https://example.com/v1",
        model="qwen3.5-flash",
        timeout=30,
    )

    timeout = llm._build_stream_timeout()

    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 30
    assert timeout.read == 120


def test_stream_cancellation_closes_active_response(monkeypatch):
    lines: List[str] = [
        'data: {"choices":[{"delta":{"content":"first"}}]}',
        'data: {"choices":[{"delta":{"content":"second"}}]}',
        "data: [DONE]",
    ]
    active_response: Dict[str, Any] = {}

    class _FakeStreamResponse:
        def __init__(self):
            self.closed = False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            for line in lines:
                if self.closed:
                    return
                yield line

        def close(self) -> None:
            self.closed = True

    class _FakeStreamContext:
        def __enter__(self) -> _FakeStreamResponse:
            response = _FakeStreamResponse()
            active_response["response"] = response
            return response

        def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
            del exc_type, exc_val, exc_tb
            return False

    def _fake_stream(
        _method: str,
        _url: str,
        *,
        json: Dict[str, Any],
        headers: Dict[str, Any],
        timeout: httpx.Timeout,
    ) -> _FakeStreamContext:
        del json, headers, timeout
        return _FakeStreamContext()

    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.stream", _fake_stream)

    llm = CustomOpenAIChat(base_url="https://example.com/v1", model="qwen3.5-flash")
    stream_iter = llm.stream([HumanMessage(content="hello")])
    first_chunk = next(stream_iter)
    assert first_chunk.content == "first"

    llm.request_cancellation("client disconnected")

    final_chunk = next(stream_iter)
    assert final_chunk.content == ""

    with pytest.raises(StopIteration):
        next(stream_iter)

    assert active_response["response"].closed is True


def test_generate_raises_without_dispatch_when_cancelled(monkeypatch):
    def _unexpected_post(*_args, **_kwargs):
        raise AssertionError("request should not be dispatched after cancellation")

    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.post", _unexpected_post)

    llm = CustomOpenAIChat(base_url="https://example.com/v1", model="qwen3.5-flash")
    llm.request_cancellation("cancelled before invoke")

    with pytest.raises(StreamCancelledError):
        llm.invoke([HumanMessage(content="hello")])


def test_request_cancellation_calls_protocol_abort_for_response_id(monkeypatch):
    lines: List[str] = [
        'data: {"id":"resp_test_123","object":"response.chunk","output":"hello"}',
        "data: [DONE]",
    ]
    cancel_urls: List[str] = []

    class _FakeStreamResponse:
        def __init__(self):
            self.closed = False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            for line in lines:
                if self.closed:
                    return
                yield line

        def close(self) -> None:
            self.closed = True

    class _FakeStreamContext:
        def __enter__(self) -> _FakeStreamResponse:
            return _FakeStreamResponse()

        def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
            del exc_type, exc_val, exc_tb
            return False

    class _FakeCancelResponse:
        status_code = 200

    def _fake_stream(
        _method: str,
        _url: str,
        *,
        json: Dict[str, Any],
        headers: Dict[str, Any],
        timeout: httpx.Timeout,
    ) -> _FakeStreamContext:
        del json, headers, timeout
        return _FakeStreamContext()

    def _fake_post(_url: str, *args: Any, **kwargs: Any) -> _FakeCancelResponse:
        del args, kwargs
        cancel_urls.append(_url)
        return _FakeCancelResponse()

    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.stream", _fake_stream)
    monkeypatch.setattr("llm_providers.custom_openai_provider.httpx.post", _fake_post)

    llm = CustomOpenAIChat(base_url="https://example.com/v1", model="qwen3.5-flash")
    stream_iter = llm.stream([HumanMessage(content="hello")])
    first_chunk = next(stream_iter)
    assert first_chunk.content == "hello"

    llm.request_cancellation("client disconnected")

    assert cancel_urls == ["https://example.com/v1/responses/resp_test_123/cancel"]
