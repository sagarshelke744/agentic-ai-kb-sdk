"""Query validation and row-level security for MongoDB aggregation pipelines.

The LLM produces a single JSON object::

    {"collection": "orders", "pipeline": [{"$match": {"status": "paid"}}, {"$group": {...}}]}

which is checked against a read-only stage allow-list, a collection allow-list and a row cap before it
reaches the database. Dates / ObjectIds use MongoDB Extended JSON (`{"$date": "..."}`, `{"$oid": "..."}`).
"""

import copy
from typing import Any, Dict, List, Optional, Set, Tuple

from agentic_kb.exceptions.errors import PermissionDeniedError, SQLValidationError
from agentic_kb.observability.logging import get_logger
from agentic_kb.security.sql_validator import SQLValidationResult

logger = get_logger("agentic_kb.security.mongo_validator")

#: Read-only aggregation stages the agent may use
ALLOWED_STAGES: Set[str] = {
    "$match", "$project", "$group", "$sort", "$limit", "$skip", "$unwind", "$lookup", "$addFields",
    "$set", "$unset", "$count", "$facet", "$bucket", "$bucketAuto", "$sample", "$replaceRoot",
    "$replaceWith", "$sortByCount",
}

#: Operators that write data, run server-side JavaScript or expose server internals - rejected anywhere
FORBIDDEN_OPERATORS: Set[str] = {
    "$out", "$merge", "$function", "$accumulator", "$where", "$unionWith", "$graphLookup",
    "$currentOp", "$listSessions", "$listLocalSessions", "$collStats", "$indexStats",
    "$planCacheStats", "$changeStream", "$listSearchIndexes", "$search", "$searchMeta",
}


def _json():
    try:
        from bson import json_util
    except ImportError as e:  # pragma: no cover - depends on optional install
        from agentic_kb.exceptions.errors import ConfigurationError

        raise ConfigurationError(
            "MongoDB support requires 'pymongo'. Install it with `pip install agentic-kb[mongodb]`."
        ) from e
    return json_util


def parse_query(query: str) -> Dict[str, Any]:
    """Parse the JSON query (Extended JSON aware). Raises ValueError on malformed input."""
    text = query.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    obj = _json().loads(text)
    if not isinstance(obj, dict):
        raise ValueError("Query must be a JSON object with 'collection' and 'pipeline'.")
    return obj


def dump_query(obj: Dict[str, Any]) -> str:
    json_util = _json()
    return json_util.dumps(obj, json_options=json_util.RELAXED_JSON_OPTIONS)


def _scan_forbidden(node: Any, found: Set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN_OPERATORS:
                found.add(key)
            _scan_forbidden(value, found)
    elif isinstance(node, list):
        for item in node:
            _scan_forbidden(item, found)


def check_pipeline_safety(pipeline: Any) -> List[str]:
    """Collection-agnostic safety checks shared by the validator and the database provider."""
    errors: List[str] = []
    if not isinstance(pipeline, list):
        return ["'pipeline' must be a list of stages."]
    for i, stage in enumerate(pipeline):
        if not isinstance(stage, dict) or len(stage) != 1:
            errors.append(f"Stage {i} must be an object with exactly one operator.")
            continue
        name = next(iter(stage))
        if name not in ALLOWED_STAGES:
            errors.append(f"Stage '{name}' is not permitted (read-only stages only).")
    found: Set[str] = set()
    _scan_forbidden(pipeline, found)
    for op in sorted(found):
        errors.append(f"Operator '{op}' is not permitted.")
    return errors


def _collection_names(allowed: Optional[List[str]]) -> Optional[Set[str]]:
    """Allowed collection names, matching either `collection` or `database.collection`."""
    if not allowed:
        return None
    names: Set[str] = set()
    for a in allowed:
        a = a.strip().lower()
        names.add(a)
        if "." in a:
            names.add(a.split(".", 1)[1])
    return names


class MongoQueryValidator:
    """Validates LLM-generated MongoDB aggregation queries. Mirrors the SQLValidator interface."""

    def __init__(
        self,
        allowed_collections: Optional[List[str]] = None,
        read_only: bool = True,
        max_rows: int = 1000,
        enforce_limit: bool = True,
        **_: Any,
    ):
        self.allowed = _collection_names(allowed_collections)
        self.read_only = read_only
        self.max_rows = max_rows
        self.enforce_limit = enforce_limit

    def _allowed(self, name: str) -> bool:
        if self.allowed is None:
            return True
        n = name.lower()
        return n in self.allowed or ("." in n and n.split(".", 1)[1] in self.allowed)

    def _collect_lookup_targets(self, pipeline: List[Any], errors: List[str], used: List[str]) -> None:
        """Validate `from` collections of $lookup stages, recursively (also inside $facet / sub-pipelines)."""
        for stage in pipeline:
            if not isinstance(stage, dict):
                continue
            if "$lookup" in stage and isinstance(stage["$lookup"], dict):
                spec = stage["$lookup"]
                target = spec.get("from")
                if not isinstance(target, str) or not self._allowed(target):
                    errors.append(f"$lookup from '{target}' is not an allowed collection.")
                else:
                    used.append(target.split(".", 1)[-1] if "." in target else target)
                sub = spec.get("pipeline")
                if isinstance(sub, list):
                    errors.extend(check_pipeline_safety(sub))
                    self._collect_lookup_targets(sub, errors, used)
            if "$facet" in stage and isinstance(stage["$facet"], dict):
                for sub in stage["$facet"].values():
                    if isinstance(sub, list):
                        errors.extend(check_pipeline_safety(sub))
                        self._collect_lookup_targets(sub, errors, used)

    def validate(self, query: str) -> SQLValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if not query or not query.strip():
            return SQLValidationResult(is_valid=False, errors=["Query is empty."])
        try:
            obj = parse_query(query)
        except Exception as e:
            return SQLValidationResult(is_valid=False, errors=[f"Query is not valid JSON: {e}"])

        collection = obj.get("collection")
        pipeline = obj.get("pipeline", [])
        if not isinstance(collection, str) or not collection:
            return SQLValidationResult(is_valid=False, errors=["Query needs a 'collection' name."])
        unknown_keys = set(obj) - {"collection", "pipeline"}
        if unknown_keys:
            errors.append(f"Unsupported query keys: {', '.join(sorted(unknown_keys))}.")

        if not self._allowed(collection):
            errors.append(f"Collection '{collection}' is not an allowed collection.")

        errors.extend(check_pipeline_safety(pipeline))
        used = [collection.split(".", 1)[-1] if self.allowed and "." in collection else collection]
        if isinstance(pipeline, list):
            self._collect_lookup_targets(pipeline, errors, used)

        if errors:
            return SQLValidationResult(is_valid=False, errors=errors, tables_used=used)

        pipeline = copy.deepcopy(pipeline)
        if self.enforce_limit:
            last = pipeline[-1] if pipeline else None
            if last is not None and "$limit" in last:
                try:
                    if int(last["$limit"]) > self.max_rows:
                        warnings.append(f"Capped requested $limit {last['$limit']} to maximum {self.max_rows}")
                        last["$limit"] = self.max_rows
                except (TypeError, ValueError):
                    errors.append("$limit must be an integer.")
            else:
                pipeline.append({"$limit": self.max_rows})
                warnings.append(f"Appended default $limit {self.max_rows}")

        cleaned = dump_query({"collection": collection, "pipeline": pipeline})
        return SQLValidationResult(
            is_valid=not errors,
            cleaned_sql=cleaned,
            tables_used=list(dict.fromkeys(used)),
            columns_used=[],
            operations=["AGGREGATE"],
            errors=errors,
            warnings=warnings,
        )

    def validate_or_raise(self, query: str) -> str:
        result = self.validate(query)
        if not result.is_valid:
            err_msg = "; ".join(result.errors)
            logger.warning(f"Mongo query validation blocked query: {err_msg}")
            raise SQLValidationError(
                message=f"Query Validation Failed: {err_msg}",
                sql=query,
                violation_type="security_policy",
            )
        return result.cleaned_sql


class MongoPermissionEngine:
    """Tenant / user row-level security for MongoDB pipelines. Mirrors the PermissionEngine interface."""

    def __init__(
        self,
        allowed_tables: Optional[List[str]] = None,
        tenant_column: str = "tenant_id",
        user_column: str = "user_id",
        **_: Any,
    ):
        self.allowed = _collection_names(allowed_tables)
        self.tenant_column = tenant_column
        self.user_column = user_column

    def check_table_access(self, table_name: str) -> None:
        if self.allowed is None:
            return
        n = table_name.lower()
        if n not in self.allowed and n.split(".", 1)[-1] not in self.allowed:
            raise PermissionDeniedError(resource=table_name)

    def _scope(self, tenant_id: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
        match: Dict[str, Any] = {}
        if tenant_id:
            match[self.tenant_column] = str(tenant_id)
        if user_id:
            match[self.user_column] = str(user_id)
        return match

    def _scope_lookups(self, pipeline: List[Any], scope: Dict[str, Any]) -> None:
        """Make every $lookup / $facet branch tenant-scoped too, so joins can't leak other tenants' rows."""
        for stage in pipeline:
            if not isinstance(stage, dict):
                continue
            spec = stage.get("$lookup")
            if isinstance(spec, dict):
                sub = spec.get("pipeline")
                if "localField" in spec and "foreignField" in spec:
                    # Rewrite the simple equality join into pipeline form so a scope $match can be added
                    spec["let"] = {**spec.get("let", {}), "akb_join": "$" + spec.pop("localField")}
                    foreign = spec.pop("foreignField")
                    sub = [{"$match": {"$expr": {"$eq": ["$" + foreign, "$$akb_join"]}}}] + list(spec.get("pipeline", []))
                spec["pipeline"] = [{"$match": dict(scope)}] + list(sub or [])
                self._scope_lookups(spec["pipeline"], scope)
            facet = stage.get("$facet")
            if isinstance(facet, dict):
                for name, sub in facet.items():
                    if isinstance(sub, list):
                        facet[name] = [{"$match": dict(scope)}] + sub
                        self._scope_lookups(facet[name], scope)

    def apply_row_level_security(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        if not tenant_id and not user_id:
            return query
        try:
            obj = parse_query(query)
            pipeline = obj.get("pipeline", [])
            if not isinstance(pipeline, list):
                raise ValueError("pipeline must be a list")
        except Exception as e:
            # Fail closed: never run unscoped when tenant/user isolation was requested
            raise PermissionDeniedError(
                resource="row-level security could not be applied to the query"
            ) from e

        scope = self._scope(tenant_id, user_id)
        self._scope_lookups(pipeline, scope)
        obj["pipeline"] = [{"$match": scope}] + pipeline
        return dump_query(obj)
