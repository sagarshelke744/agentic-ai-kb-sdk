"""Embeddings provider abstraction and implementations."""

import abc
import asyncio
import hashlib
import math
from typing import Any, Dict, List, Optional, Type
from agentic_kb.exceptions.errors import ConfigurationError
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.knowledgebase.embeddings")


class BaseEmbeddingProvider(abc.ABC):
    """Abstract interface for text embedding models."""

    def __init__(self, model: str, dimension: int, **kwargs: Any):
        self.model = model
        self.dimension = dimension
        self.extra_kwargs = kwargs

    @abc.abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string into a vector."""
        pass

    @abc.abstractmethod
    async def aembed_text(self, text: str) -> List[float]:
        """Asynchronously embed a single text string."""
        pass

    @abc.abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of text strings into vectors."""
        pass

    @abc.abstractmethod
    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        """Asynchronously embed a batch of text strings."""
        pass


import re


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic pseudo-embedding provider for testing and offline development.
    Uses consistent word-token hashing to generate semantically relevant normalized vectors.
    """

    def __init__(self, dimension: int = 64, **kwargs: Any):
        super().__init__(model="mock-embeddings", dimension=dimension, **kwargs)

    def embed_text(self, text: str) -> List[float]:
        # Extract word tokens
        words = re.findall(r"\w+", text.lower().strip())
        if not words:
            words = ["empty"]

        accum = [0.0] * self.dimension
        for word in words:
            for i in range(self.dimension):
                h = hashlib.sha256(f"{word}_{i}".encode("utf-8")).hexdigest()
                val = (int(h[:8], 16) / 0xFFFFFFFF) * 2.0 - 1.0
                accum[i] += val

        # Normalize to unit length
        norm = math.sqrt(sum(v * v for v in accum)) or 1.0
        return [v / norm for v in accum]

    async def aembed_text(self, text: str) -> List[float]:
        return self.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        return self.embed_batch(texts)


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI Embedding model provider (e.g. text-embedding-3-small)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        **kwargs: Any,
    ):
        super().__init__(model=model, dimension=dimension, **kwargs)
        self.api_key = api_key
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ConfigurationError(
                    "The 'openai' package is required for OpenAIEmbeddingProvider. "
                    "Install it via `pip install openai` or `pip install agentic-kb[llm]`."
                )
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ConfigurationError("The 'openai' package is required for OpenAIEmbeddingProvider.")
            self._async_client = AsyncOpenAI(api_key=self.api_key)
        return self._async_client

    def embed_text(self, text: str) -> List[float]:
        client = self._get_client()
        resp = client.embeddings.create(input=[text], model=self.model)
        return resp.data[0].embedding

    async def aembed_text(self, text: str) -> List[float]:
        client = self._get_async_client()
        resp = await client.embeddings.create(input=[text], model=self.model)
        return resp.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        client = self._get_client()
        resp = client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in resp.data]

    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        client = self._get_async_client()
        resp = await client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in resp.data]


class EmbeddingProviderFactory:
    """Registry and factory for embedding models."""

    _registry: Dict[str, Type[BaseEmbeddingProvider]] = {
        "openai": OpenAIEmbeddingProvider,
        "mock": MockEmbeddingProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: Type[BaseEmbeddingProvider]) -> None:
        cls._registry[name.lower()] = provider_cls

    @classmethod
    def create(cls, provider: str = "mock", **kwargs: Any) -> BaseEmbeddingProvider:
        prov_key = provider.lower()
        provider_cls = cls._registry.get(prov_key)
        if not provider_cls:
            available = ", ".join(cls._registry.keys())
            raise ConfigurationError(
                f"Unknown embedding provider '{provider}'. Available providers: {available}"
            )
        return provider_cls(**kwargs)
