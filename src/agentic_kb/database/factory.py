"""Database Provider Factory and Extensible Registry."""

from typing import Any, Dict, List, Optional, Type, Union

from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.mock import MockDatabaseProvider
from agentic_kb.database.postgres import PostgreSQLProvider
from agentic_kb.database.sqlserver import SQLServerProvider
from agentic_kb.exceptions.errors import ConfigurationError
from agentic_kb.models.config import DatabaseConfig


class DatabaseProviderFactory:
    """
    Registry and factory for Database providers.

    Supports built-in providers (PostgreSQL, SQLite/Mock) and extensible user-registered providers.
    """

    _registry: Dict[str, Type[BaseDatabaseProvider]] = {
        "postgresql": PostgreSQLProvider,
        "postgres": PostgreSQLProvider,
        "sqlserver": SQLServerProvider,
        "mssql": SQLServerProvider,
        "sqlite": MockDatabaseProvider,
        "mock": MockDatabaseProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: Type[BaseDatabaseProvider]) -> None:
        """
        Register a custom database adapter with the factory.

        Example:
        ```python
        DatabaseProviderFactory.register("sqlserver", SQLServerProvider)
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
        return list(cls._registry.keys())

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
        # 1. Direct dependency injection
        if isinstance(config, BaseDatabaseProvider):
            return config

        # 2. Parse config
        if isinstance(config, dict):
            db_cfg = DatabaseConfig(**config)
        elif isinstance(config, DatabaseConfig):
            db_cfg = config
        else:
            raise ConfigurationError(
                f"Expected DatabaseConfig, dict, or BaseDatabaseProvider, got {type(config).__name__}"
            )

        db_type = db_cfg.type.lower()
        provider_cls = cls._registry.get(db_type)

        if not provider_cls:
            available = ", ".join(cls._registry.keys())
            raise ConfigurationError(
                f"Unsupported database type '{db_cfg.type}'. Supported types are: {available}. "
                f"You can register a custom database adapter via `DatabaseProviderFactory.register('{db_type}', YourProviderClass)`."
            )

        if provider_cls is PostgreSQLProvider:
            return PostgreSQLProvider(config=db_cfg, **kwargs)

        if provider_cls is SQLServerProvider:
            return SQLServerProvider(config=db_cfg, driver="pyodbc", **kwargs)

        if provider_cls is MockDatabaseProvider:
            return MockDatabaseProvider(database_name=db_cfg.database, **kwargs)

        return provider_cls(config=db_cfg, **kwargs)
