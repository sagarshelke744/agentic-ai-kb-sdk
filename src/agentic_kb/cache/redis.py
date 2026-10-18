"""Redis cache provider with automatic in-memory fallback for high availability."""

import json
from typing import Any, Optional

from agentic_kb.cache.base import BaseCacheProvider
from agentic_kb.cache.memory import InMemoryCacheProvider
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.cache.redis")


class RedisCacheProvider(BaseCacheProvider):
    """
    Redis cache adapter.
    If Redis is unreachable or the redis library is not installed,
    it falls back gracefully to an in-memory cache to guarantee zero downtime.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", default_ttl_seconds: int = 300):
        self.redis_url = redis_url
        self.default_ttl = default_ttl_seconds
        self._fallback = InMemoryCacheProvider(default_ttl_seconds=default_ttl_seconds)
        self._client = None
        self._is_connected = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0
            )
            self._client.ping()
            self._is_connected = True
            logger.info(f"Connected to Redis cache at {self.redis_url}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis ({e}). Using in-memory fallback cache.")
            self._is_connected = False
            self._client = None

    def get(self, key: str) -> Optional[Any]:
        if self._is_connected and self._client:
            try:
                raw = self._client.get(key)
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception as e:
                logger.warning(f"Redis get error for key '{key}': {e}. Using fallback.")
                return self._fallback.get(key)
        return self._fallback.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        try:
            if hasattr(value, "model_dump"):
                serialized = json.dumps(value.model_dump(), default=str)
            elif hasattr(value, "dict"):
                serialized = json.dumps(value.dict(), default=str)
            else:
                serialized = json.dumps(value, default=str)
        except Exception:
            serialized = json.dumps(str(value))

        if self._is_connected and self._client:
            try:
                if ttl and ttl > 0:
                    self._client.setex(key, ttl, serialized)
                else:
                    self._client.set(key, serialized)
                return
            except Exception as e:
                logger.warning(f"Redis set error for key '{key}': {e}. Using fallback.")
                self._fallback.set(key, value, ttl_seconds)
                return

        self._fallback.set(key, value, ttl_seconds)

    def delete(self, key: str) -> bool:
        deleted = False
        if self._is_connected and self._client:
            try:
                deleted = bool(self._client.delete(key))
            except Exception as e:
                logger.warning(f"Redis delete error for key '{key}': {e}.")
        return deleted or self._fallback.delete(key)

    def clear(self) -> None:
        if self._is_connected and self._client:
            try:
                self._client.flushdb()
            except Exception as e:
                logger.warning(f"Redis clear error: {e}.")
        self._fallback.clear()

    def health_check(self) -> bool:
        if self._is_connected and self._client:
            try:
                return bool(self._client.ping())
            except Exception:
                return False
        return self._fallback.health_check()
