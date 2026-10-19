"""Main AgenticKnowledgeBase entrypoint."""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from agentic_kb.agent.planner import SQLAgentPlanner
from agentic_kb.cache.factory import CacheProviderFactory
from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.factory import DatabaseProviderFactory
from agentic_kb.database.models import DatabaseSchemaMetadata
from agentic_kb.exceptions.errors import (
    AgenticKBError,
    ConfigurationError,
    error_payload,
)
from agentic_kb.knowledgebase.catalog import apply_catalog, load_catalog
from agentic_kb.knowledgebase.embeddings import MockEmbeddingProvider
from agentic_kb.knowledgebase.kb import KnowledgeBase
from agentic_kb.knowledgebase.metadata import BusinessTerm
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage
from agentic_kb.llm.factory import LLMProviderFactory
from agentic_kb.models.config import AgenticKBConfig, DatabaseConfig, LLMConfig
from agentic_kb.models.request import ChatRequest
from agentic_kb.models.response import AgentMetadata, ChatResponse, StreamChunk
from agentic_kb.observability.events import reset_event_sink, set_event_sink
from agentic_kb.observability.logging import get_logger
from agentic_kb.security.mongo_validator import MongoPermissionEngine, MongoQueryValidator
from agentic_kb.security.permissions import PermissionEngine
from agentic_kb.security.sql_validator import SQLValidator

logger = get_logger("agentic_kb.agent")


class AgenticKnowledgeBase:
    """Production-ready Agentic AI Database Knowledgebase platform."""

    def __init__(
        self,
        config: Optional[Union[AgenticKBConfig, Dict[str, Any]]] = None,
        llm: Optional[Union[BaseLLMProvider, LLMConfig, Dict[str, Any]]] = None,
        db: Optional[Union[BaseDatabaseProvider, DatabaseConfig, Dict[str, Any]]] = None,
        kb: Optional[KnowledgeBase] = None,
        **kwargs: Any,
    ):
        """
        Initialize AgenticKnowledgeBase.

        Accepts:
        - config: AgenticKBConfig instance or configuration dictionary.
        - llm: Optional custom LLM provider instance (BaseLLMProvider) for dependency injection,
               or an LLMConfig / dict.
        - db: Optional custom Database provider instance (BaseDatabaseProvider) for dependency injection,
              or a DatabaseConfig / dict.
        - kb: Optional custom KnowledgeBase instance for dependency injection.
        - kwargs: Database, knowledgebase, security, etc. configuration parameters.
        """
        self._injected_llm = llm
        self._injected_db = db
        self._injected_kb = kb

        if config is None and kwargs:
            raw_config: Dict[str, Any] = kwargs
        elif isinstance(config, dict):
            raw_config = {**config, **kwargs}
        elif isinstance(config, AgenticKBConfig):
            self.config = config
            self._initialize_components()
            return
        else:
            raise ConfigurationError(
                "Must provide configuration either via 'config' parameter or keyword arguments."
            )

        # Handle dependency injections passed via kwargs
        if "llm" in raw_config and isinstance(raw_config["llm"], BaseLLMProvider):
            self._injected_llm = raw_config.pop("llm")
        if "db" in raw_config and isinstance(raw_config["db"], BaseDatabaseProvider):
            self._injected_db = raw_config.pop("db")
        if "kb" in raw_config and isinstance(raw_config["kb"], KnowledgeBase):
            self._injected_kb = raw_config.pop("kb")

        self.config = AgenticKBConfig.from_dict(raw_config)
        self._initialize_components()

    @classmethod
    def from_yaml(
        cls,
        file_path: Union[str, Path],
        llm: Optional[BaseLLMProvider] = None,
        db: Optional[BaseDatabaseProvider] = None,
        kb: Optional[KnowledgeBase] = None,
    ) -> "AgenticKnowledgeBase":
        """Instantiate AgenticKnowledgeBase from a YAML configuration file."""
        cfg = AgenticKBConfig.from_yaml(file_path)
        return cls(config=cfg, llm=llm, db=db, kb=kb)

    def _initialize_components(self) -> None:
        """Initialize and link subcomponents: logger, LLM provider, database adapter, security validator, and knowledgebase."""
        self.logger = get_logger(f"agentic_kb.{self.config.agent.name}")

        # 1. Initialize or inject LLM Provider
        if self._injected_llm is not None:
            self.llm = LLMProviderFactory.create(self._injected_llm)
        else:
            self.llm = LLMProviderFactory.create(self.config.llm)

        # 2. Initialize or inject Database Provider
        if self._injected_db is not None:
            self.db = DatabaseProviderFactory.create(self._injected_db)
        else:
            self.db = DatabaseProviderFactory.create(
                self.config.database,
                read_only=self.config.security.read_only,
                max_rows=self.config.security.max_rows,
                query_timeout_seconds=self.config.security.query_timeout_seconds,
            )

        # 3. Initialize Security Validator and Permission Engine
        if self.db.dialect_name == "mongodb":
            # Document database: queries are JSON aggregation pipelines, not SQL
            self.validator = MongoQueryValidator(
                allowed_collections=self.config.knowledgebase.allowed_tables,
                read_only=self.config.security.read_only,
                max_rows=self.config.security.max_rows,
                enforce_limit=self.config.security.enforce_limit,
            )
            self.permissions = MongoPermissionEngine(
                allowed_tables=self.config.knowledgebase.allowed_tables,
            )
        else:
            self.validator = SQLValidator(
                allowed_schemas=self.config.knowledgebase.allowed_schemas,
                allowed_tables=self.config.knowledgebase.allowed_tables,
                allowed_columns=self.config.knowledgebase.allowed_columns,
                read_only=self.config.security.read_only,
                max_rows=self.config.security.max_rows,
                enforce_limit=self.config.security.enforce_limit,
                dialect=self.db.dialect_name,
            )

            self.permissions = PermissionEngine(
                allowed_schemas=self.config.knowledgebase.allowed_schemas,
                allowed_tables=self.config.knowledgebase.allowed_tables,
                dialect=self.db.dialect_name,
            )

        # 4. Initialize KnowledgeBase
        if self._injected_kb is not None:
            self.kb = self._injected_kb
        else:
            self.kb = KnowledgeBase(
                config=self.config.knowledgebase,
                embedding_provider=MockEmbeddingProvider(),
            )

        # Index business rules if configured
        if self.config.knowledgebase.business_rules:
            self.kb.index_rules(self.config.knowledgebase.business_rules)

        # 5. Initialize SQL Agent Planner
        self.planner = SQLAgentPlanner(config=self.config)

        # 6. Initialize Cache Provider
        self.cache = CacheProviderFactory.create(self.config.cache)

        self.logger.info(
            f"Initialized AgenticKnowledgeBase: agent='{self.config.agent.name}', "
            f"llm_provider='{self.llm.provider_name}', model='{self.llm.model}', "
            f"db_dialect='{self.db.dialect_name}', "
            f"allowed_tables={len(self.config.knowledgebase.allowed_tables)}"
        )

    def _load_catalog(self) -> Optional[Dict[str, Any]]:
        """Load the reviewed catalog file (descriptions, sample values, relations) if configured."""
        path = self.config.knowledgebase.catalog_file
        if not path:
            return None
        catalog = load_catalog(Path(path))
        if catalog is None:
            self.logger.warning(
                f"catalog_file '{path}' not found - run `agentic-kb catalog generate` to create it."
            )
        return catalog

    def get_schema_metadata(self, use_cache: bool = True) -> DatabaseSchemaMetadata:
        """Discover database schema metadata filtered by allowed schemas and tables with caching."""
        cache_key = f"schema_meta:{','.join(sorted(self.config.knowledgebase.allowed_tables))}"
        catalog_path = self.config.knowledgebase.catalog_file
        if catalog_path and Path(catalog_path).exists():
            cache_key += f":{Path(catalog_path).stat().st_mtime_ns}"  # edits invalidate the cache
        if use_cache and self.config.cache.enabled:
            cached = self.cache.get(cache_key)
            if cached is not None:
                if isinstance(cached, DatabaseSchemaMetadata):
                    return cached
                if isinstance(cached, dict):
                    return DatabaseSchemaMetadata.model_validate(cached)

        meta = self.db.get_schema_metadata(
            allowed_schemas=self.config.knowledgebase.allowed_schemas,
            allowed_tables=self.config.knowledgebase.allowed_tables,
        )
        meta = apply_catalog(meta, self._load_catalog(), self.config.knowledgebase.table_descriptions)
        if self.config.cache.enabled:
            self.cache.set(cache_key, meta, ttl_seconds=self.config.cache.ttl_seconds)
        return meta

    def index_schema_metadata(self) -> int:
        """Index database schema metadata into the vector knowledgebase."""
        schema_meta = self.get_schema_metadata()
        return self.kb.index_schema(schema_meta)

    def index_business_terms(self, terms: List[BusinessTerm]) -> int:
        """Index custom business metric and entity definitions into the knowledgebase."""
        return self.kb.index_business_terms(terms)

    def ask(
        self,
        message: Union[str, ChatRequest],
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> ChatResponse:
        """
        Ask a question in natural language and receive a grounded answer.

        Synchronous execution pipeline.
        """
        if isinstance(message, ChatRequest):
            req = message
        else:
            req = ChatRequest(
                message=message,
                conversation_id=conversation_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )

        self.logger.info(
            f"Received ask request: '{req.message[:80]}...'",
            extra={"user_id": req.user_id, "tenant_id": req.tenant_id},
        )

        try:
            schema_metadata = self.get_schema_metadata()
            return self.planner.execute_plan(
                request=req,
                schema_metadata=schema_metadata,
                llm=self.llm,
                db=self.db,
                validator=self.validator,
                permissions=self.permissions,
                kb=self.kb,
            )
        except AgenticKBError:
            raise
        except Exception as e:
            self.logger.exception(f"Unhandled error during ask pipeline: {str(e)}")
            raise

    async def astream(
        self,
        message: Union[str, ChatRequest],
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response events and tokens via an async generator."""
        req = message if isinstance(message, ChatRequest) else ChatRequest(
            message=message,
            conversation_id=conversation_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue[Optional[StreamChunk]]" = asyncio.Queue()

        def _sink(event: str, data: Dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, StreamChunk(event=event, data=data))

        def _run() -> ChatResponse:
            # Copied context carries the sink into the worker thread
            token = set_event_sink(_sink)
            try:
                return self.ask(req)
            finally:
                reset_event_sink(token)

        task = asyncio.ensure_future(asyncio.to_thread(_run))
        task.add_done_callback(lambda _: loop.call_soon_threadsafe(queue.put_nowait, None))

        # Pipeline steps and LLM retry notices arrive live while the worker runs
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

        try:
            response = task.result()
        except Exception as e:
            self.logger.error(f"Streaming pipeline failed: {type(e).__name__}: {e}")
            yield StreamChunk(event="error", data=error_payload(e))
            return

        for word in response.answer.split(" "):
            yield StreamChunk(event="token", data={"text": word + " "})

        yield StreamChunk(
            event="done",
            data={
                "answer": response.answer,
                "request_id": response.request_id,
                "conversation_id": response.conversation_id,
                "metadata": response.metadata.model_dump(),
            },
        )

    def health_check(self) -> Dict[str, Any]:
        """Perform a comprehensive health check across LLM, Database, Knowledgebase, and Cache layers."""
        db_health = self.db.health_check()
        cache_healthy = self.cache.health_check() if hasattr(self, "cache") else True
        all_ok = db_health.get("status") in ("ok", "healthy") and cache_healthy

        return {
            "status": "ok" if all_ok else "degraded",
            "agent": self.config.agent.name,
            "version": self.config.agent.version,
            "llm": {
                "provider": self.llm.provider_name,
                "model": self.llm.model,
            },
            "database": db_health,
            "cache": {
                "status": "ok" if cache_healthy else "unreachable",
                "type": self.config.cache.type,
            },
            "knowledgebase": {
                "indexed_items": self.kb.get_indexed_count(),
            },
            "allowed_tables_count": len(self.config.knowledgebase.allowed_tables),
        }

    def close(self) -> None:
        """Close and dispose database connections."""
        if hasattr(self, "db") and self.db is not None:
            self.db.close()

    def __enter__(self) -> "AgenticKnowledgeBase":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
