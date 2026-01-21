"""Embedding generation service using local LLM providers.

This module provides embedding generation using local LLM providers (Ollama/vLLM)
for semantic similarity search in the memory system.

References:
- Requirements 3.2, 5: Vector Database and LLM Integration
- Design Section 6.3: Embedding Strategy
- Design Section 9: LLM Integration Design
"""

import json
import logging
from typing import List, Optional

import requests

from memory_system.memory_interface import EmbeddingServiceInterface
from shared.config import get_config

logger = logging.getLogger(__name__)


class OllamaEmbeddingService(EmbeddingServiceInterface):
    """
    Embedding service using Ollama local LLM provider.

    This service generates embeddings using Ollama's embedding models
    (e.g., nomic-embed-text, mxbai-embed-large).

    Example:
        >>> service = OllamaEmbeddingService()
        >>> embedding = service.generate_embedding("Hello world")
        >>> len(embedding)
        768
    """

    def __init__(
        self, base_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 30
    ):
        """
        Initialize the Ollama embedding service.

        Args:
            base_url: Ollama API base URL (default from config)
            model: Embedding model name (default from config)
            timeout: Request timeout in seconds
        """
        self._config = get_config()

        # Load configuration
        llm_config = self._config.get_section("llm")
        ollama_config = llm_config.get("ollama", {})

        self._base_url = base_url or ollama_config.get("base_url", "http://localhost:11434")
        self._model = model or ollama_config.get("embedding_model", "nomic-embed-text")
        self._timeout = timeout
        self._embedding_dim = ollama_config.get("embedding_dimension", 768)

        logger.info(
            f"Initialized Ollama embedding service: "
            f"url={self._base_url}, model={self._model}, dim={self._embedding_dim}"
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using Ollama.

        Args:
            text: Input text

        Returns:
            List[float]: Embedding vector

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            # Call Ollama embeddings API
            url = f"{self._base_url}/api/embeddings"
            payload = {"model": self._model, "prompt": text}

            response = requests.post(url, json=payload, timeout=self._timeout)

            response.raise_for_status()

            # Extract embedding from response
            result = response.json()
            embedding = result.get("embedding")

            if not embedding:
                raise RuntimeError("No embedding returned from Ollama")

            logger.debug(f"Generated embedding for text (length={len(text)})")
            return embedding

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding via Ollama: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Note: Ollama doesn't have a native batch API, so this calls
        the single embedding endpoint multiple times. For better performance,
        consider using vLLM for batch operations.

        Args:
            texts: List of input texts

        Returns:
            List[List[float]]: List of embedding vectors

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not texts:
            return []

        embeddings = []
        for i, text in enumerate(texts):
            try:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to generate embedding for text {i}: {e}")
                # Continue with other texts, append None for failed ones
                embeddings.append(None)

        # Check if any embeddings failed
        failed_count = sum(1 for e in embeddings if e is None)
        if failed_count > 0:
            logger.warning(f"Failed to generate {failed_count}/{len(texts)} embeddings")

        return embeddings

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service.

        Returns:
            int: Embedding dimension
        """
        return self._embedding_dim


class VLLMEmbeddingService(EmbeddingServiceInterface):
    """
    Embedding service using vLLM local LLM provider.

    This service generates embeddings using vLLM's high-performance
    embedding models for production-scale deployments.

    Example:
        >>> service = VLLMEmbeddingService()
        >>> embeddings = service.generate_embeddings_batch(["text1", "text2"])
        >>> len(embeddings)
        2
    """

    def __init__(
        self, base_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 30
    ):
        """
        Initialize the vLLM embedding service.

        Args:
            base_url: vLLM API base URL (default from config)
            model: Embedding model name (default from config)
            timeout: Request timeout in seconds
        """
        self._config = get_config()

        # Load configuration
        llm_config = self._config.get_section("llm")
        vllm_config = llm_config.get("vllm", {})

        self._base_url = base_url or vllm_config.get("base_url", "http://localhost:8000")
        self._model = model or vllm_config.get("embedding_model", "BAAI/bge-large-en-v1.5")
        self._timeout = timeout
        self._embedding_dim = vllm_config.get("embedding_dimension", 1024)

        logger.info(
            f"Initialized vLLM embedding service: "
            f"url={self._base_url}, model={self._model}, dim={self._embedding_dim}"
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using vLLM.

        Args:
            text: Input text

        Returns:
            List[float]: Embedding vector

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            # Call vLLM embeddings API (OpenAI-compatible)
            url = f"{self._base_url}/v1/embeddings"
            payload = {"model": self._model, "input": text}

            response = requests.post(url, json=payload, timeout=self._timeout)

            response.raise_for_status()

            # Extract embedding from response
            result = response.json()
            embedding = result["data"][0]["embedding"]

            logger.debug(f"Generated embedding for text (length={len(text)})")
            return embedding

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding via vLLM: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch using vLLM.

        vLLM supports batch embedding generation for better performance.

        Args:
            texts: List of input texts

        Returns:
            List[List[float]]: List of embedding vectors

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not texts:
            return []

        try:
            # Call vLLM embeddings API with batch input
            url = f"{self._base_url}/v1/embeddings"
            payload = {"model": self._model, "input": texts}

            response = requests.post(
                url, json=payload, timeout=self._timeout * 2  # Longer timeout for batch
            )

            response.raise_for_status()

            # Extract embeddings from response
            result = response.json()
            embeddings = [item["embedding"] for item in result["data"]]

            logger.debug(f"Generated {len(embeddings)} embeddings in batch")
            return embeddings

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate batch embeddings via vLLM: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating batch embeddings: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service.

        Returns:
            int: Embedding dimension
        """
        return self._embedding_dim


# Global embedding service instance
_embedding_service: Optional[EmbeddingServiceInterface] = None


def get_embedding_service() -> EmbeddingServiceInterface:
    """
    Get the global embedding service instance.

    This function returns the singleton embedding service instance.
    The service type (Ollama/vLLM) is determined by configuration.

    Returns:
        EmbeddingServiceInterface: Global embedding service instance
    """
    global _embedding_service

    if _embedding_service is None:
        config = get_config()
        llm_config = config.get_section("llm")

        # Determine which provider to use
        provider = llm_config.get("embedding_provider", "ollama").lower()

        if provider == "vllm":
            _embedding_service = VLLMEmbeddingService()
        else:
            # Default to Ollama
            _embedding_service = OllamaEmbeddingService()

        logger.info(f"Initialized embedding service: {provider}")

    return _embedding_service


def set_embedding_service(service: EmbeddingServiceInterface) -> None:
    """
    Set a custom embedding service instance.

    This is useful for testing or using custom embedding providers.

    Args:
        service: Embedding service instance
    """
    global _embedding_service
    _embedding_service = service
    logger.info(f"Set custom embedding service: {type(service).__name__}")
