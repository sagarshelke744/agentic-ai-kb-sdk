"""Unit tests for Cache subsystem (InMemoryCacheProvider, Redis fallback, and factory)."""

import time
from agentic_kb.cache.factory import CacheProviderFactory
from agentic_kb.cache.memory import InMemoryCacheProvider
from agentic_kb.cache.redis import RedisCacheProvider
from agentic_kb.models.config import CacheConfig


def test_in_memory_cache_crud():
    cache = InMemoryCacheProvider(default_ttl_seconds=60)
    assert cache.get("missing_key") is None

    cache.set("foo", {"data": 123})
    assert cache.get("foo") == {"data": 123}

    deleted = cache.delete("foo")
    assert deleted is True
    assert cache.get("foo") is None

    # Test clear
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_in_memory_cache_ttl_expiration():
    # Cache with 0.05 second TTL
    cache = InMemoryCacheProvider(default_ttl_seconds=1)
    cache.set("short_lived", "value", ttl_seconds=0.05)

    assert cache.get("short_lived") == "value"
    time.sleep(0.08)
    assert cache.get("short_lived") is None


def test_redis_cache_fallback_resilience():
    # Attempt connection to non-existent redis port -> falls back to in-memory gracefully
    redis_cache = RedisCacheProvider(redis_url="redis://127.0.0.1:59999/0", default_ttl_seconds=60)
    assert redis_cache.health_check() is True  # In-memory fallback is healthy

    redis_cache.set("key_via_fallback", "hello_world")
    assert redis_cache.get("key_via_fallback") == "hello_world"

    redis_cache.delete("key_via_fallback")
    assert redis_cache.get("key_via_fallback") is None


def test_cache_factory():
    mem_config = CacheConfig(type="memory", ttl_seconds=120)
    provider = CacheProviderFactory.create(mem_config)
    assert isinstance(provider, InMemoryCacheProvider)

    redis_config = CacheConfig(type="redis", host="localhost", port=6379, ttl_seconds=300)
    redis_provider = CacheProviderFactory.create(redis_config)
    assert isinstance(redis_provider, RedisCacheProvider)
