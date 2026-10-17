"""Configuration models and loader for agentic-kb."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from agentic_kb.exceptions.errors import ConfigurationError

ENV_VAR_PATTERN = re.compile(r"\$\{([^}^{]+)\}")


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand environment variables in the format ${VAR_NAME} or ${VAR_NAME:-default}."""
    if isinstance(value, str):
        def _replace_match(match: re.Match) -> str:
            expr = match.group(1)
            if ":-" in expr:
                var_name, default_val = expr.split(":-", 1)
                return os.environ.get(var_name, default_val)
            val = os.environ.get(expr)
            if val is None:
                # Return original expression if not set, or empty
                return ""
            return val

        return ENV_VAR_PATTERN.sub(_replace_match, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


class AgentMetadataConfig(BaseModel):
    """General agent metadata."""
    name: str = "database-assistant"
    description: str = "Agentic AI Database Assistant"
    version: str = "0.1.0"


# Alias for convenience
AgentConfig = AgentMetadataConfig


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = Field(default="openai", description="LLM provider: openai, azure, gemini, etc.")
    model: str = Field(default="gpt-4o", description="Model name to use")
    api_key_env: Optional[str] = Field(default="OPENAI_API_KEY", description="Environment variable holding the API key")
    api_key: Optional[str] = Field(default=None, description="Explicit API key (discouraged in config files)")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=2000, gt=0)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    azure_endpoint: Optional[str] = None
    azure_deployment: Optional[str] = None
    api_version: Optional[str] = None

    def get_api_key(self) -> Optional[str]:
        """Resolve API key from direct field or environment variable."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None


class DatabaseConfig(BaseModel):
    """Database connectivity and credentials configuration."""
    type: str = Field(default="postgresql", description="Database dialect: postgresql or sqlserver")
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Database username")
    password_env: Optional[str] = Field(default="DB_PASSWORD", description="Environment variable holding DB password")
    password: Optional[str] = Field(default=None, description="Direct DB password")
    ssl_mode: Optional[str] = Field(default="prefer")
    connection_timeout_seconds: float = Field(default=10.0, gt=0)
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v

    def get_password(self) -> Optional[str]:
        """Resolve password from direct field or environment variable."""
        if self.password:
            return self.password
        if self.password_env:
            return os.getenv(self.password_env)
        return None

    def get_connection_url(self, async_driver: bool = False) -> str:
        """Build SQLAlchemy connection string."""
        pwd = self.get_password() or ""
        pwd_part = f":{pwd}" if pwd else ""
        user_pwd = f"{self.username}{pwd_part}"
        if self.type == "postgresql":
            driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
            return f"{driver}://{user_pwd}@{self.host}:{self.port}/{self.database}"
        elif self.type == "sqlserver":
            driver = "mssql+pymssql"
            return f"{driver}://{user_pwd}@{self.host}:{self.port}/{self.database}"
        raise ConfigurationError(f"Unsupported database type: {self.type}")


class KnowledgeBaseConfig(BaseModel):
    """Knowledgebase and schema allowlist configuration."""
    allowed_schemas: List[str] = Field(default_factory=list, description="List of allowed schema names")
    allowed_tables: List[str] = Field(default_factory=list, description="List of allowed table names in schema.table format")
    allowed_columns: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Optional column allowlist per table: {'sales.orders': ['id', 'total']}"
    )
    vector_store_type: str = Field(default="pgvector", description="Vector store provider: pgvector, inmemory")
    table_descriptions: Dict[str, str] = Field(default_factory=dict)
    column_descriptions: Dict[str, str] = Field(default_factory=dict)
    business_rules: List[str] = Field(default_factory=list)

    @field_validator("allowed_tables")
    @classmethod
    def validate_table_format(cls, tables: List[str]) -> List[str]:
        cleaned = []
        for t in tables:
            t = t.strip()
            if t:
                cleaned.append(t)
        return cleaned


class SecurityConfig(BaseModel):
    """Security, execution safety, and query boundaries."""
    read_only: bool = Field(default=True, description="Strictly forbid data-modifying queries")
    max_rows: int = Field(default=1000, gt=0, le=50000, description="Max rows returned by any query")
    query_timeout_seconds: float = Field(default=30.0, gt=0, description="Max database query execution time")
    allow_dml: bool = Field(default=False, description="Whether INSERT/UPDATE/DELETE are allowed (must be False in production)")
    block_ddl: bool = Field(default=True, description="Block CREATE, ALTER, DROP, TRUNCATE")
    enforce_limit: bool = Field(default=True, description="Automatically append or enforce LIMIT clause")
    mask_pii: bool = Field(default=True, description="Mask common sensitive fields in results and responses")


class ResponseConfig(BaseModel):
    """Response formatting and visibility options."""
    show_sql: bool = Field(default=False, description="Whether to include generated SQL in user response")
    include_sources: bool = Field(default=True, description="Include source tables or evidence in metadata")
    system_instructions: Optional[str] = Field(
        default=None,
        description="Optional custom system prompt guidelines for tone or domain behavior"
    )


class ConversationConfig(BaseModel):
    """Conversation memory and state management."""
    enabled: bool = Field(default=True)
    max_history_turns: int = Field(default=10, ge=1)
    storage_type: str = Field(default="memory", description="State storage: memory, redis")


class CacheConfig(BaseModel):
    """Caching settings for metadata and query results."""
    enabled: bool = Field(default=True, description="Enable metadata and query caching")
    type: str = Field(default="memory", description="Cache provider: memory, redis")
    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    ttl_seconds: int = Field(default=300, ge=0, description="Cache time-to-live in seconds")


class AgenticKBConfig(BaseModel):
    """Root configuration object for AgenticKnowledgeBase."""
    agent: AgentMetadataConfig = Field(default_factory=AgentMetadataConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig
    knowledgebase: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    response: ResponseConfig = Field(default_factory=ResponseConfig)
    conversation: ConversationConfig = Field(default_factory=ConversationConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgenticKBConfig":
        """Instantiate configuration from a dictionary with env variable expansion."""
        expanded = _expand_env_vars(data)
        try:
            return cls(**expanded)
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {str(e)}") from e

    @classmethod
    def from_yaml(cls, file_path: Union[str, Path]) -> "AgenticKBConfig":
        """Load and validate configuration from a YAML file."""
        path = Path(file_path)
        if not path.is_file():
            raise ConfigurationError(f"Configuration file not found: {path.resolve()}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
            if not isinstance(content, dict):
                raise ConfigurationError(f"YAML configuration root must be a mapping, got {type(content).__name__}")
            return cls.from_dict(content)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Error parsing YAML configuration: {str(e)}") from e
