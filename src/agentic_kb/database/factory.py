"""Database Provider Factory and Extensible Registry."""

import importlib
from typing import Any, Dict, List, Type, Union

from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.mock import MockDatabaseProvider
from agentic_kb.exceptions.errors import ConfigurationError
from agentic_kb.models.config import DatabaseConfig

# Built-in providers are imported lazily so only the driver you actually use needs to be installed.
# name -> ("module path", "class name", "pip extra that provides the driver")
_BUILTIN: Dict[str, tuple] = {
    "postgresql": ("agentic_kb.database.postgres", "PostgreSQLProvider", "postgres"),
    "postgres": ("agentic_kb.database.postgres", "PostgreSQLProvider", "postgres"),
    "mysql": ("agentic_kb.database.mysql", "MySQLProvider", "mysql"),
    "sqlserver": ("agentic_kb.database.sqlserver", "SQLServerProvider", "sqlserver"),
    "mongodb": ("agentic_kb.database.mongodb", "MongoDBProvider", "mongodb"),
}


class DatabaseProviderFactory:
    """
    Registry and factory for Database providers.

    Built in: PostgreSQL, MySQL/MariaDB, SQL Server, MongoDB, plus SQLite/Mock for tests.
    Custom adapters can be registered with `DatabaseProviderFactory.register`.
    """

    _registry: Dict[str, Type[BaseDatabaseProvider]] = {
        "sqlite": MockDatabaseProvider,
        "mock": MockDatabaseProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: Type[BaseDatabaseProvider]) -> None:
        """
        Register a custom database adapter with the factory.

        Example:
        ```python
        DatabaseProviderFactory.register("snowflake", SnowflakeProvider)
        ```
        """
        if not issubclass(provider_cls, BaseDatabaseProvider):
            raise ConfigurationError(
                f"Provider class {provider_cls.__name__} must inherit from BaseDatabaseProvider"
            )
        cls._registry[name.lower()] = provider_cls

    @classmethod
    def get_registered_providers(cls) -> List[str]:
        """Return list of currently registered database providers."""
        return list(dict.fromkeys([*_BUILTIN, *cls._registry]))

    @classmethod
    def _resolve(cls, db_type: str) -> Type[BaseDatabaseProvider]:
        if db_type in cls._registry:  # user registrations (and mock) win
            return cls._registry[db_type]
        if db_type in _BUILTIN:
            module, class_name, extra = _BUILTIN[db_type]
            try:
                return getattr(importlib.import_module(module), class_name)
            except ImportError as e:
                raise ConfigurationError(
                    f"The '{db_type}' driver is not installed ({e.name or e}). "
                    f"Install it with `pip install agentic-kb[{extra}]`."
                ) from e
        available = ", ".join(cls.get_registered_providers())
        raise ConfigurationError(
            f"Unsupported database type '{db_type}'. Supported types are: {available}. "
            f"You can register a custom database adapter via `DatabaseProviderFactory.register('{db_type}', YourProviderClass)`."
        )

    @classmethod
    def create(
        cls,
        config: Union[DatabaseConfig, BaseDatabaseProvider, Dict[str, Any]],
        **kwargs: Any,
    ) -> BaseDatabaseProvider:
        """
        Create or return a DatabaseProvider instance.

        Accepts:
        - An existing BaseDatabaseProvider instance (dependency injection)
        - A DatabaseConfig model instance
        - A dictionary matching DatabaseConfig fields
        """
        if isinstance(config, BaseDatabaseProvider):
            return config

        if isinstance(config, dict):
            db_cfg = DatabaseConfig(**config)
        elif isinstance(config, DatabaseConfig):
            db_cfg = config
        else:
            raise ConfigurationError(
                f"Expected DatabaseConfig, dict, or BaseDatabaseProvider, got {type(config).__name__}"
            )

        provider_cls = cls._resolve(db_cfg.type.lower())

        if provider_cls is MockDatabaseProvider:
            return MockDatabaseProvider(database_name=db_cfg.database, **kwargs)

        return provider_cls(config=db_cfg, **kwargs)
