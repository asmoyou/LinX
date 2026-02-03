"""Custom OpenAI-compatible provider for non-standard APIs.

This module provides a custom LLM wrapper for APIs that claim to be OpenAI-compatible
but return non-standard response formats. Supports both streaming and non-streaming modes.
"""

from typing import Any, Dict, Iterator, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
import httpx
import json

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
    
    def _convert_messages_to_dicts(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """Convert LangChain messages to API format."""
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
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream chat completion."""
        # Prepare request URL - intelligently handle /v1 suffix
        base = self.base_url.rstrip('/')
        # If base_url already ends with /v1, just append /chat/completions
        # Otherwise, append /v1/chat/completions
        if base.endswith('/v1'):
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
        
        if self.max_tokens:
            data["max_tokens"] = self.max_tokens
        
        if stop:
            data["stop"] = stop
        
        data.update(kwargs)
        
        # Make streaming request
        try:
            with httpx.stream(
                "POST",
                url,
                json=data,
                headers=headers,
                timeout=self.timeout
            ) as response:
                response.raise_for_status()
                
                # Process SSE stream
                line_count = 0
                for line in response.iter_lines():
                    line_count += 1
                    # Debug: Log every line to see what we're receiving
                    if line_count <= 10:  # Only log first 10 lines to avoid spam
                        print(f"[SSE-LINE-{line_count}] Raw line: {repr(line)}")
                        logger.info(f"[SSE-LINE-{line_count}] Raw line: {repr(line)}")
                    
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            chunk_data = json.loads(data_str)
                            
                            # Debug: Log the raw chunk structure
                            if line_count <= 10:
                                logger.info(f"[STREAM-DEBUG] Raw chunk keys: {list(chunk_data.keys())}")
                                logger.info(f"[STREAM-DEBUG] Raw chunk data: {json.dumps(chunk_data, ensure_ascii=False)[:500]}")
                            
                            # Handle custom format
                            content = ""
                            content_type = "content"  # 'thinking' or 'content'
                            
                            if "output" in chunk_data:
                                content = chunk_data.get("output", "")
                                logger.info(f"[STREAM-DEBUG] Found 'output' field: {len(content)} chars")
                            elif "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                delta = chunk_data["choices"][0].get("delta", {})
                                
                                # Debug: Print to stdout AND log (to ensure we see it)
                                if line_count <= 10:
                                    print(f"[STREAM-RAW] Delta keys: {list(delta.keys())}, Delta: {json.dumps(delta, ensure_ascii=False)[:200]}")
                                    logger.info(f"[STREAM-RAW] Full delta: {json.dumps(delta, ensure_ascii=False)}")
                                
                                # Check for thinking/reasoning content FIRST
                                # Different providers use different field names:
                                # - llm-pool: "reasoning_content" (for Qwen3-VL-32B-Thinking)
                                # - Ollama: "reasoning"
                                # - Some models: "thinking"
                                thinking = (
                                    delta.get("reasoning_content") or  # llm-pool format
                                    delta.get("reasoning") or          # Ollama format
                                    delta.get("thinking")              # Generic format
                                )
                                
                                # Check regular content fields
                                # Note: For llm-pool's Qwen3-VL-32B-Thinking, content is always null/empty
                                # All actual content is in reasoning_content
                                regular_content = delta.get("content") or delta.get("output")
                                
                                # Priority: thinking content > regular content
                                # This ensures reasoning_content is captured even if content field exists
                                if thinking:
                                    content = thinking
                                    content_type = "thinking"
                                    print(f"[STREAM-{line_count}] Detected THINKING: len={len(thinking)}, text={thinking[:50]}")
                                    logger.info(f"[STREAM-{line_count}] Detected thinking content: {len(thinking)} chars")
                                elif regular_content:
                                    content = regular_content
                                    content_type = "content"
                                    print(f"[STREAM-{line_count}] Detected CONTENT: len={len(regular_content)}")
                                    logger.info(f"[STREAM-{line_count}] Detected regular content: {len(regular_content)} chars")
                                
                                # Debug: Check content variable state
                                print(f"[STREAM-{line_count}] After detection: content={repr(content)}, type={content_type}")
                            
                            # First, yield content chunk if we have content
                            if content:
                                # Create chunk with content_type in additional_kwargs
                                # This ensures the metadata flows through to the agent
                                print(f"[CHUNK-CREATE-{line_count}] Creating chunk: content_len={len(content)}, type={content_type}, text={content[:50]}")
                                logger.info(f"[CHUNK-CREATE-{line_count}] Creating chunk: content_len={len(content)}, type={content_type}")
                                chunk = ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content=content,
                                        additional_kwargs={"content_type": content_type}
                                    )
                                )
                                print(f"[CHUNK-YIELD-{line_count}] About to yield chunk")
                                logger.info(f"[CHUNK-YIELD-{line_count}] Yielding chunk with content_len={len(chunk.message.content)}")
                                yield chunk
                            
                            # Then, check for usage data (llm-pool sends this in EVERY chunk, vLLM only in final chunk)
                            # Only yield usage chunk if there's no content (to avoid duplicate chunks)
                            if "usage" in chunk_data and not content:
                                usage = chunk_data["usage"]
                                logger.info(f"[STREAM-USAGE] Found usage in chunk (no content): {usage}")
                                # Create a chunk with usage metadata but no content
                                # This will be captured by the agent execution loop
                                chunk = ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content="",
                                        additional_kwargs={}
                                    ),
                                    generation_info={"usage": usage}
                                )
                                yield chunk
                                
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse streaming chunk: {data_str}")
                            continue
                            
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
        base = self.base_url.rstrip('/')
        # If base_url already ends with /v1, just append /chat/completions
        # Otherwise, append /v1/chat/completions
        if base.endswith('/v1'):
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
        
        if self.max_tokens:
            data["max_tokens"] = self.max_tokens
        
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
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            
            # Handle custom response format
            if "output" in result:
                # Custom format: {"output": "...", "request_tokens": ..., ...}
                content = result["output"]
                token_usage = {
                    "prompt_tokens": result.get("request_tokens", 0),
                    "completion_tokens": result.get("response_tokens", 0),
                    "total_tokens": result.get("request_tokens", 0) + result.get("response_tokens", 0),
                }
            elif "choices" in result and len(result["choices"]) > 0:
                # Standard OpenAI format
                choice = result["choices"][0]
                message_data = choice["message"]
                
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
                
                token_usage = result.get("usage", {})
            else:
                raise ValueError(f"Unexpected response format: {result}")
            
            # Create generation
            message = AIMessage(content=content)
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
        # Prepare request URL - append /v1/chat/completions to base_url
        base = self.base_url.rstrip('/')
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
        
        if self.max_tokens:
            data["max_tokens"] = self.max_tokens
        
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
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
            
            # Handle custom response format
            if "output" in result:
                content = result["output"]
                token_usage = {
                    "prompt_tokens": result.get("request_tokens", 0),
                    "completion_tokens": result.get("response_tokens", 0),
                    "total_tokens": result.get("request_tokens", 0) + result.get("response_tokens", 0),
                }
            elif "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                token_usage = result.get("usage", {})
            else:
                raise ValueError(f"Unexpected response format: {result}")
            
            message = AIMessage(content=content)
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
