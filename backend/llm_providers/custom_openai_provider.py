"""Custom OpenAI-compatible provider for non-standard APIs.

This module provides a custom LLM wrapper for APIs that claim to be OpenAI-compatible
but return non-standard response formats. Supports both streaming and non-streaming modes.
"""

from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field
import json
import httpx

from shared.logging import get_logger

logger = get_logger(__name__)


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
    max_retries: int = Field(default=2, description="Maximum retry attempts")
    streaming: bool = Field(default=False, description="Enable streaming mode")

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
                result.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
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
                return {}
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

        if "output" in chunk_data:
            content = chunk_data.get("output", "")
        elif "choices" in chunk_data and len(chunk_data["choices"]) > 0:
            choice = chunk_data["choices"][0]
            delta = choice.get("delta")

            # Streaming delta format.
            if isinstance(delta, dict):
                tool_call_chunks = self._extract_tool_call_chunks_from_delta(delta)
                thinking = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or delta.get("thinking")
                )
                regular_content = delta.get("content") or delta.get("output")
                if thinking:
                    content = thinking
                    content_type = "thinking"
                elif regular_content:
                    content = regular_content
            # Non-streaming completion payload accidentally returned on stream endpoint.
            else:
                message_data = choice.get("message", {})
                if isinstance(message_data, dict):
                    content = (
                        message_data.get("reasoning_content")
                        or message_data.get("reasoning")
                        or message_data.get("thinking")
                        or message_data.get("content")
                        or ""
                    )
                    tool_calls = self._extract_tool_calls_from_message(message_data)
                    tool_call_chunks = self._tool_calls_to_chunks(tool_calls)

        if content or tool_call_chunks or usage_data:
            additional_kwargs = {"content_type": content_type} if content else {}
            response_metadata = {"usage": usage_data} if usage_data else {}
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
        if isinstance(getattr(message, "response_metadata", None), dict):
            usage_data = message.response_metadata.get("usage") or {}
        if not usage_data and isinstance(chat_result.llm_output, dict):
            usage_data = chat_result.llm_output.get("token_usage") or {}

        additional_kwargs = {"content_type": "content"} if content else {}
        response_metadata = {"usage": usage_data} if usage_data else {}

        return ChatGenerationChunk(
            message=AIMessageChunk(
                content=content,
                additional_kwargs=additional_kwargs,
                response_metadata=response_metadata,
                tool_call_chunks=tool_call_chunks,
            )
        )

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream chat completion."""
        # Prepare request URL - intelligently handle /v1 suffix
        base = self.base_url.rstrip("/")
        # If base_url already ends with /v1, just append /chat/completions
        # Otherwise, append /v1/chat/completions
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"

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
            emitted_chunks = False
            with httpx.stream(
                "POST",
                url,
                json=data,
                headers=headers,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                raw_json_lines: List[str] = []

                # Process SSE stream
                for line in response.iter_lines():
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
                            chunk = self._build_stream_chunk_from_payload(chunk_data)
                            if chunk is not None:
                                emitted_chunks = True
                                yield chunk
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse non-SSE stream payload; falling back to non-streaming"
                            )

                if not emitted_chunks:
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

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during streaming: {e}")
            raise
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            raise

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate chat completion."""
        # Prepare request URL - intelligently handle /v1 suffix
        base = self.base_url.rstrip("/")
        # If base_url already ends with /v1, just append /chat/completions
        # Otherwise, append /v1/chat/completions
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"

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
            response = httpx.post(
                url,
                json=data,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()

            # Handle custom response format
            if "output" in result:
                # Custom format: {"output": "...", "request_tokens": ..., ...}
                content = result["output"]
                tool_calls = []
                token_usage = {
                    "prompt_tokens": result.get("request_tokens", 0),
                    "completion_tokens": result.get("response_tokens", 0),
                    "total_tokens": result.get("request_tokens", 0)
                    + result.get("response_tokens", 0),
                }
            elif "choices" in result and len(result["choices"]) > 0:
                # Standard OpenAI format
                choice = result["choices"][0]
                message_data = choice.get("message", {})

                # Check for reasoning/thinking content (for models like Qwen3-VL)
                # Priority: reasoning_content > reasoning > thinking > content
                content = (
                    message_data.get("reasoning_content") or
                    message_data.get("reasoning") or
                    message_data.get("thinking") or
                    message_data.get("content") or
                    ""
                )
                
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
            message = AIMessage(
                content=content,
                tool_calls=tool_calls,
                response_metadata={"usage": token_usage} if token_usage else {},
            )
            generation = ChatGeneration(message=message)

            return ChatResult(
                generations=[generation],
                llm_output={"token_usage": token_usage, "model_name": self.model},
            )

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
        # Prepare request URL - intelligently handle /v1 suffix
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"

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
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

            # Handle custom response format
            if "output" in result:
                content = result["output"]
                tool_calls = []
                token_usage = {
                    "prompt_tokens": result.get("request_tokens", 0),
                    "completion_tokens": result.get("response_tokens", 0),
                    "total_tokens": result.get("request_tokens", 0)
                    + result.get("response_tokens", 0),
                }
            elif "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                message_data = choice.get("message", {})
                content = (
                    message_data.get("reasoning_content")
                    or message_data.get("reasoning")
                    or message_data.get("thinking")
                    or message_data.get("content")
                    or ""
                )
                tool_calls = self._extract_tool_calls_from_message(message_data)
                token_usage = result.get("usage", {})
            else:
                raise ValueError(f"Unexpected response format: {result}")

            message = AIMessage(
                content=content,
                tool_calls=tool_calls,
                response_metadata={"usage": token_usage} if token_usage else {},
            )
            generation = ChatGeneration(message=message)

            return ChatResult(
                generations=[generation],
                llm_output={"token_usage": token_usage, "model_name": self.model},
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling LLM API: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            raise
