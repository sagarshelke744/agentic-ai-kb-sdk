"""Abstract base class for metadata and query cache providers."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseCacheProvider(ABC):
    """Abstract interface for caching database metadata and repeated queries."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached value by key. Returns None if absent or expired."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store a value with an optional time-to-live in seconds."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete an entry by key. Returns True if key existed."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all keys in this cache namespace."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check cache provider availability."""
        pass
