"""Custom OpenAI-compatible provider for non-standard APIs.

This module provides a custom LLM wrapper for APIs that claim to be OpenAI-compatible
but return non-standard response formats. Supports both streaming and non-streaming modes.
"""

import json
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, PrivateAttr

from shared.logging import get_logger

logger = get_logger(__name__)


class StreamCancelledError(RuntimeError):
    """Raised when an active streaming call is cancelled by caller."""


class CustomOpenAIChat(BaseChatModel):
    """Custom chat model for non-standard OpenAI-compatible APIs.

    This handles APIs that return responses in format:
    {"output": "...", "request_tokens": ..., "response_tokens": ..., "cost": ...}

    Instead of standard OpenAI format:
    {"choices": [{"message": {"content": "..."}}]}

    Supports both streaming and non-streaming modes.
    """

    base_url: str = Field(..., description="Base URL for the API")
    model: str = Field(..., description="Model name")
    api_key: Optional[str] = Field(default=None, description="API key")
    temperature: float = Field(default=0.7, description="Temperature")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens to generate")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    stream_read_timeout: Optional[int] = Field(
        default=None,
        description=(
            "Optional read-timeout override for streaming responses. "
            "When unset, uses max(timeout, 120s)."
        ),
    )
    max_retries: int = Field(default=2, description="Maximum retry attempts")
    streaming: bool = Field(default=False, description="Enable streaming mode")
    protocol_abort_enabled: bool = Field(
        default=True,
        description="Try protocol-level cancel endpoints when request IDs are available.",
    )
    protocol_abort_timeout: float = Field(
        default=5.0,
        description="Timeout in seconds for protocol-level cancel requests.",
    )
    _cancel_requested: threading.Event = PrivateAttr(default_factory=threading.Event)
    _active_stream_response: Optional[httpx.Response] = PrivateAttr(default=None)
    _active_request_id: Optional[str] = PrivateAttr(default=None)
    _active_request_kind: Optional[str] = PrivateAttr(default=None)
    _active_stream_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def reset_cancellation(self) -> None:
        """Clear cancellation marker for a fresh run."""
        with self._active_stream_lock:
            self._cancel_requested.clear()
            self._active_request_id = None
            self._active_request_kind = None

    def request_cancellation(self, reason: Optional[str] = None) -> None:
        """Request cooperative cancellation for active or upcoming requests."""
        self._cancel_requested.set()
        self.cancel_active_requests(reason=reason)

    def cancel_active_requests(self, reason: Optional[str] = None) -> None:
        """Abort active streaming response immediately if one exists."""
        response: Optional[httpx.Response]
        request_id: Optional[str]
        request_kind: Optional[str]
        with self._active_stream_lock:
            response = self._active_stream_response
            request_id = self._active_request_id
            request_kind = self._active_request_kind
            self._active_stream_response = None
            self._active_request_id = None
            self._active_request_kind = None

        if response is None:
            self._abort_upstream_by_protocol(request_id, request_kind, reason=reason)
            return

        try:
            response.close()
            logger.warning(
                "Cancelled active LLM streaming response",
                extra={"reason": reason or "unspecified"},
            )
        except Exception as close_error:
            logger.warning(
                "Failed to close active LLM stream during cancellation: %s",
                close_error,
            )
        finally:
            self._abort_upstream_by_protocol(request_id, request_kind, reason=reason)

    def _build_api_url(self, path: str) -> str:
        """Build OpenAI-compatible URL with `/v1` fallback."""
        normalized = path if path.startswith("/") else f"/{path}"
        base = self.base_url.rstrip("/")
        if base.endswith(normalized):
            return base
        if base.endswith("/v1"):
            return f"{base}{normalized}"
        return f"{base}/v1{normalized}"

    @staticmethod
    def _infer_request_kind(
        payload: Dict[str, Any], request_id: str, fallback_kind: Optional[str] = None
    ) -> Optional[str]:
        """Infer whether request belongs to responses API or chat completions API."""
        object_type = str(payload.get("object") or "").strip().lower()
        if object_type.startswith("response"):
            return "responses"
        if object_type.startswith("chat.completion"):
            return "chat.completions"
        if request_id.startswith("resp_"):
            return "responses"
        if request_id.startswith("chatcmpl-"):
            return "chat.completions"
        return fallback_kind

    def _track_active_request(self, payload: Dict[str, Any]) -> None:
        """Track active upstream request ID for protocol-level cancellation."""
        raw_request_id = payload.get("id")
        if not isinstance(raw_request_id, str):
            return
        request_id = raw_request_id.strip()
        if not request_id:
            return

        with self._active_stream_lock:
            request_kind = self._infer_request_kind(
                payload,
                request_id,
                fallback_kind=self._active_request_kind,
            )
            self._active_request_id = request_id
            if request_kind:
                self._active_request_kind = request_kind

    def _build_protocol_abort_candidates(
        self, request_id: str, request_kind: Optional[str]
    ) -> List[str]:
        """Build candidate cancel endpoints for OpenAI-compatible APIs."""
        candidates: List[str] = []
        normalized_kind = (request_kind or "").strip().lower()

        if normalized_kind == "responses" or request_id.startswith("resp_"):
            candidates.append(self._build_api_url(f"/responses/{request_id}/cancel"))

        if normalized_kind == "chat.completions" and request_id.startswith("chatcmpl-"):
            # Non-standard but supported by some OpenAI-compatible gateways.
            candidates.append(self._build_api_url(f"/chat/completions/{request_id}/cancel"))

        return candidates

    def _abort_upstream_by_protocol(
        self, request_id: Optional[str], request_kind: Optional[str], reason: Optional[str] = None
    ) -> bool:
        """Best-effort protocol-level cancellation using provider cancel endpoints."""
        if not self.protocol_abort_enabled:
            return False

        normalized_request_id = str(request_id or "").strip()
        if not normalized_request_id:
            return False

        candidates = self._build_protocol_abort_candidates(normalized_request_id, request_kind)
        if not candidates:
            return False

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        timeout_value = max(0.1, float(self.protocol_abort_timeout or 5.0))

        for url in candidates:
            try:
                response = httpx.post(url, headers=headers, timeout=timeout_value)
            except Exception as abort_error:
                logger.debug("Protocol abort request failed: %s", abort_error)
                continue

            if 200 <= response.status_code < 300:
                logger.warning(
                    "Cancelled upstream request via protocol endpoint",
                    extra={
                        "request_id": normalized_request_id,
                        "request_kind": request_kind or "unknown",
                        "url": url,
                        "reason": reason or "unspecified",
                    },
                )
                return True

            if response.status_code in (404, 405, 501):
                logger.debug(
                    "Protocol abort endpoint unsupported by upstream",
                    extra={
                        "request_id": normalized_request_id,
                        "request_kind": request_kind or "unknown",
                        "status_code": response.status_code,
                    },
                )
                continue

            logger.warning(
                "Protocol abort endpoint returned unexpected status",
                extra={
                    "request_id": normalized_request_id,
                    "request_kind": request_kind or "unknown",
                    "status_code": response.status_code,
                },
            )

        return False

    @property
    def _llm_type(self) -> str:
        """Return type of LLM."""
        return "custom-openai-chat"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        """Bind tools to this model using OpenAI-compatible schema."""
        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]
        tool_names: List[str] = []
        for tool in formatted_tools:
            fn = tool.get("function") if isinstance(tool, dict) else None
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                tool_names.append(fn["name"])

        if tool_choice:
            if isinstance(tool_choice, str):
                if tool_choice in tool_names:
                    tool_choice = {"type": "function", "function": {"name": tool_choice}}
                elif tool_choice == "any":
                    tool_choice = "required"
            elif isinstance(tool_choice, bool):
                tool_choice = "required"
            kwargs["tool_choice"] = tool_choice

        return super().bind(tools=formatted_tools, **kwargs)

    def _convert_messages_to_dicts(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """Convert LangChain messages to API format.

        Handles both plain text content (str) and multimodal content (list of dicts)
        for vision models.
        """
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                tool_calls = getattr(msg, "tool_calls", None) or []
                content_value = msg.content
                if tool_calls and (content_value == "" or content_value is None):
                    content_value = None
                payload: Dict[str, Any] = {"role": "assistant", "content": content_value}
                if tool_calls:
                    normalized_tool_calls: List[Dict[str, Any]] = []
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        tool_name = str(
                            tool_call.get("name")
                            or ((tool_call.get("function") or {}).get("name"))
                            or ""
                        ).strip()
                        raw_args = (
                            tool_call.get("args")
                            or tool_call.get("arguments")
                            or ((tool_call.get("function") or {}).get("arguments"))
                            or {}
                        )
                        if isinstance(raw_args, str):
                            arguments = raw_args
                        else:
                            arguments = json.dumps(raw_args, ensure_ascii=False)
                        normalized_tool_calls.append(
                            {
                                "id": str(tool_call.get("id") or ""),
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": arguments,
                                },
                            }
                        )
                    payload["tool_calls"] = normalized_tool_calls
                result.append(payload)
            elif isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                result.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": getattr(msg, "tool_call_id", None),
                    }
                )
            else:
                result.append({"role": "user", "content": str(msg.content)})
        return result

    @staticmethod
    def _apply_openai_compatible_token_limits(
        payload: Dict[str, Any], max_tokens: Optional[int]
    ) -> None:
        """Apply token limit fields for OpenAI-compatible gateways.

        Keep `max_tokens` for broad compatibility and add
        `max_completion_tokens` for reasoning-style models behind
        OpenAI-compatible proxies (e.g. One API).
        """
        if not max_tokens:
            return
        payload["max_tokens"] = max_tokens
        payload["max_completion_tokens"] = max_tokens

    @staticmethod
    def _parse_tool_arguments(arguments: Any) -> Dict[str, Any]:
        """Parse tool arguments into a dictionary."""
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                stripped = arguments.strip()
                if stripped:
                    return {"__raw_arguments__": stripped}
                return {}
            if arguments.strip():
                return {"__raw_arguments__": arguments.strip()}
        return {}

    @classmethod
    def _extract_tool_calls_from_message(cls, message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract normalized tool calls from a non-streaming assistant message."""
        normalized: List[Dict[str, Any]] = []
        raw_tool_calls = message_data.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            for idx, raw_call in enumerate(raw_tool_calls):
                if not isinstance(raw_call, dict):
                    continue
                fn = raw_call.get("function")
                fn_data = fn if isinstance(fn, dict) else {}
                name = raw_call.get("name") or fn_data.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                raw_args = (
                    fn_data.get("arguments")
                    if "arguments" in fn_data
                    else raw_call.get("arguments", raw_call.get("args"))
                )
                args = cls._parse_tool_arguments(raw_args)
                normalized.append(
                    {
                        "name": name.strip(),
                        "args": args,
                        "id": str(raw_call.get("id") or f"call_{idx}"),
                        "type": "tool_call",
                    }
                )

        # Backward compatibility: legacy function_call field.
        if not normalized and isinstance(message_data.get("function_call"), dict):
            function_call = message_data["function_call"]
            name = function_call.get("name")
            if isinstance(name, str) and name.strip():
                args = cls._parse_tool_arguments(function_call.get("arguments"))
                normalized.append(
                    {
                        "name": name.strip(),
                        "args": args,
                        "id": "call_0",
                        "type": "tool_call",
                    }
                )

        return normalized

    @staticmethod
    def _extract_tool_call_chunks_from_delta(delta: Dict[str, Any]) -> List[ToolCallChunk]:
        """Extract tool call chunks from streaming deltas."""
        chunks: List[ToolCallChunk] = []
        raw_tool_calls = delta.get("tool_calls")
        if not isinstance(raw_tool_calls, list):
            return chunks

        for idx, raw_call in enumerate(raw_tool_calls):
            if not isinstance(raw_call, dict):
                continue

            fn = raw_call.get("function")
            fn_data = fn if isinstance(fn, dict) else {}
            name = raw_call.get("name") or fn_data.get("name")
            raw_args = (
                fn_data.get("arguments")
                if "arguments" in fn_data
                else raw_call.get("arguments", raw_call.get("args"))
            )
            if raw_args is not None and not isinstance(raw_args, str):
                try:
                    raw_args = json.dumps(raw_args, ensure_ascii=False)
                except Exception:
                    raw_args = str(raw_args)

            raw_index = raw_call.get("index", idx)
            try:
                tool_index = int(raw_index)
            except (TypeError, ValueError):
                tool_index = idx

            chunks.append(
                ToolCallChunk(
                    name=name.strip() if isinstance(name, str) and name.strip() else None,
                    args=raw_args if isinstance(raw_args, str) else None,
                    id=str(raw_call["id"]) if raw_call.get("id") else None,
                    index=tool_index,
                )
            )

        return chunks

    @staticmethod
    def _tool_calls_to_chunks(tool_calls: List[Dict[str, Any]]) -> List[ToolCallChunk]:
        """Convert normalized tool calls to stream-compatible tool call chunks."""
        chunks: List[ToolCallChunk] = []
        for idx, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            args = tool_call.get("args")
            if isinstance(args, dict):
                args = json.dumps(args, ensure_ascii=False)
            elif args is None:
                args = "{}"
            elif not isinstance(args, str):
                args = str(args)

            chunks.append(
                ToolCallChunk(
                    name=name.strip(),
                    args=args,
                    id=str(tool_call["id"]) if tool_call.get("id") else None,
                    index=idx,
                )
            )

        return chunks

    def _build_stream_chunk_from_payload(
        self, chunk_data: Dict[str, Any]
    ) -> Optional[ChatGenerationChunk]:
        """Build a stream chunk from either SSE delta payload or full JSON payload."""
        content = ""
        content_type = "content"
        usage_data = chunk_data.get("usage")
        tool_call_chunks: List[ToolCallChunk] = []
        finish_reason = str(chunk_data.get("finish_reason") or "").strip()

        reasoning_content = ""

        if "output" in chunk_data:
            content = chunk_data.get("output", "")
        elif "choices" in chunk_data and len(chunk_data["choices"]) > 0:
            choice = chunk_data["choices"][0]
            finish_reason = str(choice.get("finish_reason") or finish_reason).strip()
            delta = choice.get("delta")

            # Streaming delta format.
            if isinstance(delta, dict):
                tool_call_chunks = self._extract_tool_call_chunks_from_delta(delta)
                reasoning_content = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or delta.get("thinking")
                )
                regular_content = delta.get("content") or delta.get("output")
                if regular_content:
                    content = regular_content
                elif reasoning_content:
                    content = reasoning_content
                    content_type = "thinking"
            # Non-streaming completion payload accidentally returned on stream endpoint.
            else:
                message_data = choice.get("message", {})
                if isinstance(message_data, dict):
                    reasoning_content = (
                        message_data.get("reasoning_content")
                        or message_data.get("reasoning")
                        or message_data.get("thinking")
                        or ""
                    )
                    content = message_data.get("content") or reasoning_content or ""
                    if not message_data.get("content") and reasoning_content:
                        content_type = "thinking"
                    tool_calls = self._extract_tool_calls_from_message(message_data)
                    tool_call_chunks = self._tool_calls_to_chunks(tool_calls)

        if content or tool_call_chunks or usage_data or finish_reason:
            additional_kwargs = {"content_type": content_type} if content else {}
            if content and reasoning_content and content_type != "thinking":
                additional_kwargs["reasoning_content"] = reasoning_content
            response_metadata: Dict[str, Any] = {"usage": usage_data} if usage_data else {}
            if finish_reason:
                response_metadata["finish_reason"] = finish_reason
            return ChatGenerationChunk(
                message=AIMessageChunk(
                    content=content,
                    additional_kwargs=additional_kwargs,
                    response_metadata=response_metadata,
                    tool_call_chunks=tool_call_chunks,
                )
            )

        if "usage" in chunk_data:
            logger.debug("[STREAM-USAGE] Found non-dict usage payload in chunk")
            return ChatGenerationChunk(message=AIMessageChunk(content="", additional_kwargs={}))

        return None

    def _build_stream_chunk_from_chat_result(
        self, chat_result: ChatResult
    ) -> Optional[ChatGenerationChunk]:
        """Convert non-streaming chat result into a single stream chunk."""
        if not chat_result.generations:
            return None

        generation = chat_result.generations[0]
        message = generation.message
        content = (
            message.content
            if isinstance(message.content, str)
            else (str(message.content) if message.content is not None else "")
        )
        tool_calls = getattr(message, "tool_calls", None) or []
        tool_call_chunks = self._tool_calls_to_chunks(tool_calls)

        usage_data: Dict[str, Any] = {}
        finish_reason = ""
        if isinstance(getattr(message, "response_metadata", None), dict):
            usage_data = message.response_metadata.get("usage") or {}
            finish_reason = str(message.response_metadata.get("finish_reason") or "").strip()
        if not usage_data and isinstance(chat_result.llm_output, dict):
            usage_data = chat_result.llm_output.get("token_usage") or {}
        if not finish_reason and isinstance(chat_result.llm_output, dict):
            finish_reason = str(chat_result.llm_output.get("finish_reason") or "").strip()

        additional_kwargs = {"content_type": "content"} if content else {}
        response_metadata: Dict[str, Any] = {"usage": usage_data} if usage_data else {}
        if finish_reason:
            response_metadata["finish_reason"] = finish_reason

        return ChatGenerationChunk(
            message=AIMessageChunk(
                content=content,
                additional_kwargs=additional_kwargs,
                response_metadata=response_metadata,
                tool_call_chunks=tool_call_chunks,
            )
        )

    def _build_stream_timeout(self) -> httpx.Timeout:
        """Build timeout config for streaming calls.

        For reasoning-heavy models, the first token may take longer than the
        generic request timeout. Keep connect/write/pool strict while relaxing
        stream read timeout.
        """
        base_timeout = float(self.timeout or 30)
        read_timeout = float(self.stream_read_timeout or max(base_timeout, 120.0))
        return httpx.Timeout(timeout=base_timeout, read=read_timeout)

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream chat completion."""
        url = self._build_api_url("/chat/completions")

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "model": self.model,
            "messages": self._convert_messages_to_dicts(messages),
            "temperature": self.temperature,
            "stream": True,  # Enable streaming
            "stream_options": {"include_usage": True},  # Request usage statistics in stream
        }
        self._apply_openai_compatible_token_limits(data, self.max_tokens)

        if stop:
            data["stop"] = stop

        data.update(kwargs)

        # Make streaming request
        try:
            if self._cancel_requested.is_set():
                raise StreamCancelledError("LLM stream cancelled before request dispatch")
            emitted_chunks = False
            with httpx.stream(
                "POST",
                url,
                json=data,
                headers=headers,
                timeout=self._build_stream_timeout(),
            ) as response:
                with self._active_stream_lock:
                    self._active_stream_response = response
                response.raise_for_status()
                raw_json_lines: List[str] = []

                # Process SSE stream
                for line in response.iter_lines():
                    if self._cancel_requested.is_set():
                        raise StreamCancelledError("LLM stream cancelled by caller")
                    if not line or line.startswith(":"):
                        continue

                    data_str = line.strip()
                    if data_str.startswith("data:"):
                        data_str = data_str[5:].strip()

                        if data_str == "[DONE]":
                            break
                    else:
                        # Some providers ignore stream=true and return one-shot JSON body.
                        raw_json_lines.append(data_str)
                        continue

                    try:
                        chunk_data = json.loads(data_str)
                        self._track_active_request(chunk_data)
                        chunk = self._build_stream_chunk_from_payload(chunk_data)
                        if chunk is not None:
                            emitted_chunks = True
                            yield chunk
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse streaming chunk: {data_str}")
                        continue

                # Handle providers that return plain JSON without SSE framing.
                if not emitted_chunks and raw_json_lines:
                    merged_payload = "".join(raw_json_lines).strip()
                    if merged_payload:
                        try:
                            chunk_data = json.loads(merged_payload)
                            self._track_active_request(chunk_data)
                            chunk = self._build_stream_chunk_from_payload(chunk_data)
                            if chunk is not None:
                                emitted_chunks = True
                                yield chunk
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse non-SSE stream payload; falling back to non-streaming"
                            )

                if not emitted_chunks:
                    if self._cancel_requested.is_set():
                        raise StreamCancelledError("LLM stream cancelled by caller")
                    logger.warning(
                        "Streaming produced no parseable chunks, falling back to non-streaming invoke"
                    )
                    fallback_kwargs = dict(kwargs)
                    fallback_kwargs.pop("stream", None)
                    fallback_kwargs.pop("stream_options", None)
                    fallback_result = self._generate(
                        messages,
                        stop=stop,
                        run_manager=run_manager,
                        **fallback_kwargs,
                    )
                    fallback_chunk = self._build_stream_chunk_from_chat_result(fallback_result)
                    if fallback_chunk is not None:
                        yield fallback_chunk
        except StreamCancelledError:
            logger.info("Stopped LLM streaming due to cancellation request")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during streaming: {e}")
            raise
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            raise
        finally:
            with self._active_stream_lock:
                self._active_stream_response = None
                self._active_request_id = None
                self._active_request_kind = None

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate chat completion."""
        url = self._build_api_url("/chat/completions")

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "model": self.model,
            "messages": self._convert_messages_to_dicts(messages),
            "temperature": self.temperature,
        }
        self._apply_openai_compatible_token_limits(data, self.max_tokens)

        if stop:
            data["stop"] = stop

        # Add any additional kwargs
        data.update(kwargs)

        # Make request
        try:
            if self._cancel_requested.is_set():
                raise StreamCancelledError("LLM request cancelled before dispatch")
            response = httpx.post(
                url,
                json=data,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            self._track_active_request(result)

            # Handle custom response format
            finish_reason = str(result.get("finish_reason") or "").strip()
            if "output" in result:
                # Custom format: {"output": "...", "request_tokens": ..., ...}
                content = result["output"]
                tool_calls = []
                additional_kwargs = {"final_content": content} if content else {}
                token_usage = {
                    "prompt_tokens": result.get("request_tokens", 0),
                    "completion_tokens": result.get("response_tokens", 0),
                    "total_tokens": result.get("request_tokens", 0)
                    + result.get("response_tokens", 0),
                }
            elif "choices" in result and len(result["choices"]) > 0:
                # Standard OpenAI format
                choice = result["choices"][0]
                finish_reason = str(choice.get("finish_reason") or finish_reason).strip()
                message_data = choice.get("message", {})
                final_content = message_data.get("content") or ""
                reasoning_content = (
                    message_data.get("reasoning_content")
                    or message_data.get("reasoning")
                    or message_data.get("thinking")
                    or ""
                )

                # Preserve reasoning separately, but keep visible message content as
                # the actual final answer whenever the provider returns one.
                content = final_content or reasoning_content or ""
                additional_kwargs = {}
                if final_content:
                    additional_kwargs["final_content"] = final_content
                if reasoning_content:
                    additional_kwargs["reasoning_content"] = reasoning_content

                # If content is still empty but we have completion_tokens, log warning
                token_usage = result.get("usage", {})
                if not content and token_usage.get("completion_tokens", 0) > 0:
                    logger.warning(
                        f"LLM generated {token_usage.get('completion_tokens')} tokens but content is empty. "
                        f"Response may have been truncated. Full message: {message_data}"
                    )
                    # Try to extract any text from the message
                    content = str(message_data)

                tool_calls = self._extract_tool_calls_from_message(message_data)
                token_usage = result.get("usage", {})
            else:
                raise ValueError(f"Unexpected response format: {result}")

            # Create generation
            response_metadata: Dict[str, Any] = {"usage": token_usage} if token_usage else {}
            if finish_reason:
                response_metadata["finish_reason"] = finish_reason
            message = AIMessage(
                content=content,
                tool_calls=tool_calls,
                additional_kwargs=additional_kwargs,
                response_metadata=response_metadata,
            )
            generation = ChatGeneration(message=message)

            llm_output: Dict[str, Any] = {"token_usage": token_usage, "model_name": self.model}
            if finish_reason:
                llm_output["finish_reason"] = finish_reason
            return ChatResult(generations=[generation], llm_output=llm_output)
        except StreamCancelledError:
            logger.info("Stopped non-streaming LLM request due to cancellation request")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling LLM API: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            raise

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate chat completion."""
        url = self._build_api_url("/chat/completions")

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "model": self.model,
            "messages": self._convert_messages_to_dicts(messages),
            "temperature": self.temperature,
        }
        self._apply_openai_compatible_token_limits(data, self.max_tokens)

        if stop:
            data["stop"] = stop

        data.update(kwargs)

        # Make async request
        try:
            if self._cancel_requested.is_set():
                raise StreamCancelledError("Async LLM request cancelled before dispatch")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()
            self._track_active_request(result)

            # Handle custom response format
            finish_reason = str(result.get("finish_reason") or "").strip()
            if "output" in result:
                content = result["output"]
                tool_calls = []
                additional_kwargs = {"final_content": content} if content else {}
                token_usage = {
                    "prompt_tokens": result.get("request_tokens", 0),
                    "completion_tokens": result.get("response_tokens", 0),
                    "total_tokens": result.get("request_tokens", 0)
                    + result.get("response_tokens", 0),
                }
            elif "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                finish_reason = str(choice.get("finish_reason") or finish_reason).strip()
                message_data = choice.get("message", {})
                final_content = message_data.get("content") or ""
                reasoning_content = (
                    message_data.get("reasoning_content")
                    or message_data.get("reasoning")
                    or message_data.get("thinking")
                    or ""
                )
                content = final_content or reasoning_content or ""
                additional_kwargs = {}
                if final_content:
                    additional_kwargs["final_content"] = final_content
                if reasoning_content:
                    additional_kwargs["reasoning_content"] = reasoning_content
                tool_calls = self._extract_tool_calls_from_message(message_data)
                token_usage = result.get("usage", {})
            else:
                raise ValueError(f"Unexpected response format: {result}")

            response_metadata: Dict[str, Any] = {"usage": token_usage} if token_usage else {}
            if finish_reason:
                response_metadata["finish_reason"] = finish_reason
            message = AIMessage(
                content=content,
                tool_calls=tool_calls,
                additional_kwargs=additional_kwargs,
                response_metadata=response_metadata,
            )
            generation = ChatGeneration(message=message)

            llm_output: Dict[str, Any] = {"token_usage": token_usage, "model_name": self.model}
            if finish_reason:
                llm_output["finish_reason"] = finish_reason
            return ChatResult(generations=[generation], llm_output=llm_output)
        except StreamCancelledError:
            logger.info("Stopped async LLM request due to cancellation request")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling LLM API: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            raise
