"""Thread-safe In-Memory Cache Provider with TTL support."""

import time
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from agentic_kb.cache.base import BaseCacheProvider


class InMemoryCacheProvider(BaseCacheProvider):
    """Thread-safe in-memory cache provider."""

    def __init__(self, default_ttl_seconds: int = 300):
        self._default_ttl = default_ttl_seconds
        # key -> (value, expires_at_timestamp)
        self._store: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                return None

            value, expires_at = self._store[key]
            if expires_at is not None and time.time() > expires_at:
                del self._store[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl if ttl and ttl > 0 else None

        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def health_check(self) -> bool:
        return True
