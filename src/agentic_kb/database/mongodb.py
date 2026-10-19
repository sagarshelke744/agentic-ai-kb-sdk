"""MongoDB database provider (aggregation pipelines) powered by PyMongo."""

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.models import (
    ColumnMetadata,
    DatabaseSchemaMetadata,
    QueryResult,
    TableMetadata,
)
from agentic_kb.exceptions.errors import (
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseTimeoutError,
    QueryExecutionError,
    SecurityError,
)
from agentic_kb.models.config import DatabaseConfig
from agentic_kb.observability.logging import get_logger
from agentic_kb.security.mongo_validator import check_pipeline_safety, parse_query

logger = get_logger("agentic_kb.database.mongodb")

MAX_FIELD_DEPTH = 4
MAX_FIELDS_PER_COLLECTION = 200


def _bson_type_name(value: Any) -> str:
    """Compact, LLM-friendly type name for a BSON value."""
    from bson import Decimal128, ObjectId

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, (Decimal128, Decimal)):
        return "decimal"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (datetime, date)):
        return "date"
    if isinstance(value, ObjectId):
        return "objectId"
    if isinstance(value, UUID):
        return "uuid"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (bytes, bytearray)):
        return "binary"
    if isinstance(value, list):
        inner = sorted({_bson_type_name(v) for v in value if v is not None})
        return f"array<{'|'.join(inner)}>" if inner else "array"
    return type(value).__name__


def _to_plain(value: Any) -> Any:
    """Convert BSON values into JSON-friendly Python values."""
    from bson import Decimal128, ObjectId

    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<binary {len(value)} bytes>"
    return value


def _flatten(doc: Dict[str, Any], prefix: str = "", depth: int = 0) -> Dict[str, str]:
    """Flatten a document into {dotted.path: type_name}; arrays of objects expose their children."""
    out: Dict[str, str] = {}
    for key, value in doc.items():
        path = f"{prefix}{key}"
        out[path] = _bson_type_name(value)
        if depth + 1 >= MAX_FIELD_DEPTH:
            continue
        if isinstance(value, dict):
            out.update(_flatten(value, path + ".", depth + 1))
        elif isinstance(value, list):
            for item in value[:5]:
                if isinstance(item, dict):
                    out.update(_flatten(item, path + ".", depth + 1))
    return out


class MongoDBProvider(BaseDatabaseProvider):
    """
    MongoDB provider. "Tables" are collections and "columns" are (dotted) field paths, inferred by
    sampling documents. Queries are JSON aggregation pipelines
    (`{"collection": "...", "pipeline": [...]}`) validated against a read-only allow-list.

    MongoDB has no read-only session mode, so connect with a user holding only the `read` role.
    """

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        connection_url: Optional[str] = None,
        read_only: bool = True,
        max_rows: int = 1000,
        query_timeout_seconds: float = 30.0,
        sample_size: int = 100,
        client: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(
            read_only=read_only,
            max_rows=max_rows,
            query_timeout_seconds=query_timeout_seconds,
            **kwargs,
        )
        self.config = config
        self._url = connection_url or (config.get_connection_url() if config else None)
        if not self._url and client is None:
            raise DatabaseConnectionError("MongoDB connection URL, DatabaseConfig or client must be provided.")
        self.database_name = config.database if config else "test"
        self.sample_size = sample_size
        self._client: Optional[Any] = client  # an existing MongoClient may be injected

    @property
    def dialect_name(self) -> str:
        return "mongodb"

    # ------------------------------------------------------------------ connection
    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from pymongo import MongoClient
            except ImportError as e:
                raise ConfigurationError(
                    "MongoDB support requires 'pymongo'. Install it with `pip install agentic-kb[mongodb]`."
                ) from e
            timeout_ms = int((self.config.connection_timeout_seconds if self.config else 10) * 1000)
            try:
                self._client = MongoClient(
                    self._url,
                    serverSelectionTimeoutMS=timeout_ms,
                    connectTimeoutMS=timeout_ms,
                    socketTimeoutMS=int(self.query_timeout_seconds * 1000) + 5000,
                    appname="agentic-kb",
                    tz_aware=True,
                )
            except Exception as e:
                raise DatabaseConnectionError(f"Failed to create MongoDB client: {e}") from e
        return self._client

    def _db(self) -> Any:
        return self._get_client()[self.database_name]

    # ------------------------------------------------------------------ execution
    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        limit = max_rows or self.max_rows
        timeout = timeout_seconds or self.query_timeout_seconds

        try:
            obj = parse_query(query)
        except Exception as e:
            raise QueryExecutionError(f"Query is not valid JSON: {e}") from e
        collection = obj.get("collection")
        pipeline = obj.get("pipeline", [])
        if not isinstance(collection, str) or not collection:
            raise QueryExecutionError("Query needs a 'collection' name.")

        # Defence in depth: the agent already validated, but never run write/JS operators
        if self.read_only:
            problems = check_pipeline_safety(pipeline)
            if problems:
                raise SecurityError("Read-only policy violation: " + "; ".join(problems))

        start = time.time()
        try:
            cursor = self._db()[collection].aggregate(
                pipeline, maxTimeMS=int(timeout * 1000), allowDiskUse=False
            )
            raw_docs: List[Dict[str, Any]] = []
            for doc in cursor:
                raw_docs.append(doc)
                if len(raw_docs) > limit:
                    break
        except Exception as e:
            msg = str(e).lower()
            if "exceeded time limit" in msg or "maxtimems" in msg or "timed out" in msg:
                raise DatabaseTimeoutError(timeout_seconds=timeout) from e
            if "serverselectiontimeout" in type(e).__name__.lower() or "connection refused" in msg:
                raise DatabaseConnectionError(f"Database unavailable: {e}") from e
            raise QueryExecutionError(f"Query execution error: {e}") from e

        is_truncated = len(raw_docs) > limit
        rows = [_to_plain(d) for d in raw_docs[:limit]]
        columns: List[str] = []
        for r in rows:
            for k in r:
                if k not in columns:
                    columns.append(k)
        if "_id" in columns:
            columns.remove("_id")
            columns.insert(0, "_id")

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            duration_ms=round((time.time() - start) * 1000, 2),
            is_truncated=is_truncated,
            query=query,
        )

    async def aexecute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        max_rows: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> QueryResult:
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(query, params=params, max_rows=max_rows, timeout_seconds=timeout_seconds),
        )

    # ------------------------------------------------------------------ schema inference
    def get_schema_metadata(
        self,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
    ) -> DatabaseSchemaMetadata:
        """Infer collections and field types by sampling documents."""
        db_name = self.database_name
        if allowed_schemas and db_name.lower() not in {s.lower() for s in allowed_schemas}:
            return DatabaseSchemaMetadata(dialect=self.dialect_name, database_name=db_name, tables={})

        try:
            db = self._db()
            names = sorted(db.list_collection_names())
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to list MongoDB collections: {e}") from e

        allowed_lower = {t.lower() for t in (allowed_tables or [])}
        tables: Dict[str, TableMetadata] = {}

        for name in names:
            if name.startswith("system."):
                continue
            full_name = f"{db_name}.{name}"
            if allowed_lower and full_name.lower() not in allowed_lower and name.lower() not in allowed_lower:
                continue
            try:
                coll = db[name]
                sample = list(coll.aggregate([{"$sample": {"size": self.sample_size}}], maxTimeMS=15000))
                try:
                    estimated = coll.estimated_document_count()
                except Exception:
                    estimated = None
                try:
                    indexes = list(coll.index_information().keys())
                except Exception:
                    indexes = []
            except Exception as e:
                logger.warning(f"Failed to sample collection '{name}': {e}")
                continue

            seen: Dict[str, Dict[str, int]] = {}  # path -> {type: count}
            for doc in sample:
                for path, typ in _flatten(doc).items():
                    seen.setdefault(path, {})
                    seen[path][typ] = seen[path].get(typ, 0) + 1

            columns: List[ColumnMetadata] = []
            for path in sorted(seen, key=lambda p: (p != "_id", p))[:MAX_FIELDS_PER_COLLECTION]:
                types = seen[path]
                non_null = sorted(t for t in types if t != "null")
                if any(t.startswith("array<") for t in non_null):
                    non_null = [t for t in non_null if t != "array"]  # empty arrays add no information
                present = sum(types.values())
                columns.append(
                    ColumnMetadata(
                        name=path,
                        data_type="|".join(non_null) or "null",
                        is_nullable=path != "_id" and (present < len(sample) or "null" in types),
                        is_primary_key=path == "_id",
                    )
                )

            tables[full_name] = TableMetadata(
                schema_name=db_name,
                table_name=name,
                full_name=full_name,
                columns=columns,
                primary_keys=["_id"] if "_id" in seen else [],
                indexes=indexes,
                estimated_row_count=estimated,
            )

        return DatabaseSchemaMetadata(dialect=self.dialect_name, database_name=db_name, tables=tables)

    # ------------------------------------------------------------------ lifecycle
    def health_check(self) -> Dict[str, Any]:
        start = time.time()
        try:
            self._get_client().admin.command("ping")
            return {
                "status": "healthy",
                "dialect": self.dialect_name,
                "database": self.database_name,
                "latency_ms": round((time.time() - start) * 1000, 2),
                "connection": "ok",
            }
        except Exception as e:
            return {"status": "unhealthy", "dialect": self.dialect_name, "error": str(e)}

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
