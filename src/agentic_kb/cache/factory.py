"""Cache factory and registry."""

from typing import Dict, Type
from agentic_kb.cache.base import BaseCacheProvider
from agentic_kb.cache.memory import InMemoryCacheProvider
from agentic_kb.cache.redis import RedisCacheProvider
from agentic_kb.models.config import CacheConfig


class CacheProviderFactory:
    """Factory for instantiating cache providers."""

    _registry: Dict[str, Type[BaseCacheProvider]] = {
        "memory": InMemoryCacheProvider,
        "redis": RedisCacheProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class: Type[BaseCacheProvider]) -> None:
        cls._registry[name.lower()] = provider_class

    @classmethod
    def create(cls, config: CacheConfig) -> BaseCacheProvider:
        provider_type = (config.type or "memory").lower()
        if provider_type == "redis":
            redis_url = f"redis://{config.host}:{config.port}/0"
            return RedisCacheProvider(redis_url=redis_url, default_ttl_seconds=config.ttl_seconds)
        return InMemoryCacheProvider(default_ttl_seconds=config.ttl_seconds)
