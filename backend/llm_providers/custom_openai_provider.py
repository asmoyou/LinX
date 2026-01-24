"""Custom OpenAI-compatible provider for non-standard APIs.

This module provides a custom LLM wrapper for APIs that claim to be OpenAI-compatible
but return non-standard response formats. Supports both streaming and non-streaming modes.
"""

import logging
from typing import Any, Dict, Iterator, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
import httpx
import json

logger = logging.getLogger(__name__)


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
            "stream": True,  # Enable streaming
        }
        
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
                for line in response.iter_lines():
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            chunk_data = json.loads(data_str)
                            
                            # Handle custom format
                            if "output" in chunk_data:
                                content = chunk_data.get("output", "")
                            elif "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                delta = chunk_data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                            else:
                                continue
                            
                            if content:
                                chunk = ChatGenerationChunk(
                                    message=AIMessageChunk(content=content)
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
                content = result["choices"][0]["message"]["content"]
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
