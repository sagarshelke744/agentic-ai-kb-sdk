"""MongoDB support: query validation, tenant scoping, provider (mongomock) and end-to-end agent run."""

import json
from datetime import datetime, timezone

import pytest

mongomock = pytest.importorskip("mongomock")
pytest.importorskip("pymongo")

from agentic_kb.agent.agent import AgenticKnowledgeBase  # noqa: E402
from agentic_kb.database.mongodb import MongoDBProvider  # noqa: E402
from agentic_kb.exceptions.errors import (  # noqa: E402
    PermissionDeniedError,
    SecurityError,
    SQLValidationError,
)
from agentic_kb.llm.mock import MockLLMProvider  # noqa: E402
from agentic_kb.security.mongo_validator import (  # noqa: E402
    MongoPermissionEngine,
    MongoQueryValidator,
    parse_query,
)


def q(collection="orders", pipeline=None):
    return json.dumps({"collection": collection, "pipeline": pipeline if pipeline is not None else []})


# ------------------------------------------------------------------ validator
def v(**kw):
    return MongoQueryValidator(allowed_collections=["shop.orders", "customers"], max_rows=100, **kw)


def test_valid_pipeline_gets_default_limit():
    res = v().validate(q(pipeline=[{"$match": {"status": "paid"}}]))
    assert res.is_valid and res.tables_used == ["orders"]
    assert parse_query(res.cleaned_sql)["pipeline"][-1] == {"$limit": 100}


def test_oversized_limit_is_capped():
    res = v().validate(q(pipeline=[{"$limit": 5000}]))
    assert parse_query(res.cleaned_sql)["pipeline"][-1] == {"$limit": 100}


def test_small_limit_is_kept():
    res = v().validate(q(pipeline=[{"$limit": 5}]))
    assert parse_query(res.cleaned_sql)["pipeline"] == [{"$limit": 5}]


@pytest.mark.parametrize(
    "stage",
    [
        {"$out": "stolen"},
        {"$merge": {"into": "x"}},
        {"$unionWith": "customers"},
        {"$graphLookup": {"from": "customers"}},
        {"$collStats": {}},
    ],
)
def test_write_and_internal_stages_are_rejected(stage):
    assert not v().validate(q(pipeline=[stage])).is_valid


@pytest.mark.parametrize(
    "pipeline",
    [
        [{"$match": {"$where": "sleep(5000)"}}],
        [{"$addFields": {"x": {"$function": {"body": "function(){}", "args": [], "lang": "js"}}}}],
        [{"$group": {"_id": None, "x": {"$accumulator": {}}}}],
    ],
)
def test_javascript_operators_are_rejected_anywhere(pipeline):
    assert not v().validate(q(pipeline=pipeline)).is_valid


def test_collection_allow_list():
    assert not v().validate(q(collection="secrets")).is_valid
    assert v().validate(q(collection="shop.orders")).is_valid  # database-qualified form is accepted


def test_lookup_target_must_be_allowed_including_nested():
    ok = [{"$lookup": {"from": "customers", "localField": "cid", "foreignField": "_id", "as": "c"}}]
    bad = [{"$lookup": {"from": "secrets", "localField": "cid", "foreignField": "_id", "as": "c"}}]
    nested = [{"$facet": {"a": [{"$lookup": {"from": "secrets", "pipeline": [], "as": "s"}}]}}]
    assert v().validate(q(pipeline=ok)).is_valid
    assert not v().validate(q(pipeline=bad)).is_valid
    assert not v().validate(q(pipeline=nested)).is_valid


def test_malformed_input_is_reported_not_raised():
    assert not v().validate("not json").is_valid
    assert not v().validate("[]").is_valid
    assert not v().validate("").is_valid
    assert not v().validate(json.dumps({"pipeline": []})).is_valid
    assert not v().validate(q(pipeline=[{"$match": {}, "$sort": {}}])).is_valid  # two operators in one stage


def test_extended_json_dates_survive_round_trip():
    pipe = [{"$match": {"created": {"$gte": {"$date": "2024-01-01T00:00:00Z"}}}}]
    res = v().validate(q(pipeline=pipe))
    assert res.is_valid
    created = parse_query(res.cleaned_sql)["pipeline"][0]["$match"]["created"]["$gte"]
    assert isinstance(created, datetime)


def test_validate_or_raise():
    with pytest.raises(SQLValidationError):
        v().validate_or_raise(q(pipeline=[{"$out": "x"}]))


# ------------------------------------------------------------------ tenant scoping
def test_rls_prepends_scope_match():
    eng = MongoPermissionEngine(allowed_tables=["orders"])
    out = parse_query(eng.apply_row_level_security(q(pipeline=[{"$sort": {"a": 1}}]), tenant_id="acme", user_id="7"))
    assert out["pipeline"][0] == {"$match": {"tenant_id": "acme", "user_id": "7"}}


def test_rls_scopes_simple_lookups_too():
    eng = MongoPermissionEngine()
    pipe = [{"$lookup": {"from": "customers", "localField": "cid", "foreignField": "_id", "as": "c"}}]
    out = parse_query(eng.apply_row_level_security(q(pipeline=pipe), tenant_id="acme"))
    lookup = out["pipeline"][1]["$lookup"]
    assert "localField" not in lookup and lookup["let"] == {"akb_join": "$cid"}
    assert lookup["pipeline"][0] == {"$match": {"tenant_id": "acme"}}
    assert lookup["pipeline"][1] == {"$match": {"$expr": {"$eq": ["$_id", "$$akb_join"]}}}


def test_rls_fails_closed_on_bad_input_and_noops_without_ids():
    eng = MongoPermissionEngine()
    with pytest.raises(PermissionDeniedError):
        eng.apply_row_level_security("garbage", tenant_id="acme")
    assert eng.apply_row_level_security("garbage") == "garbage"


def test_tenant_id_is_a_value_not_an_operator():
    eng = MongoPermissionEngine()
    out = parse_query(eng.apply_row_level_security(q(), tenant_id='{"$ne": null}'))
    assert out["pipeline"][0]["$match"]["tenant_id"] == '{"$ne": null}'  # stays a plain string


# ------------------------------------------------------------------ provider (mongomock)
@pytest.fixture
def mongo_db():
    client = mongomock.MongoClient(tz_aware=True)
    db = client["shop"]
    db.orders.insert_many(
        [
            {"status": "paid", "total": 120.5, "tenant_id": "acme", "customer": {"name": "Ann", "tier": "gold"},
             "items": [{"sku": "A", "qty": 2}], "created": datetime(2024, 3, 1, tzinfo=timezone.utc)},
            {"status": "paid", "total": 80, "tenant_id": "acme", "customer": {"name": "Bob", "tier": "silver"},
             "items": [{"sku": "B", "qty": 1}], "created": datetime(2024, 3, 2, tzinfo=timezone.utc)},
            {"status": "refunded", "total": 40, "tenant_id": "globex", "customer": {"name": "Cy", "tier": "gold"},
             "items": [], "created": datetime(2024, 3, 3, tzinfo=timezone.utc)},
        ]
    )
    db.customers.insert_one({"name": "Ann"})
    db.secrets.insert_one({"key": "s3cr3t"})
    provider = MongoDBProvider(client=client, config=None, query_timeout_seconds=5)
    provider.database_name = "shop"
    yield provider
    provider.close()


def test_schema_inference_flattens_nested_fields_and_types(mongo_db):
    meta = mongo_db.get_schema_metadata(allowed_tables=["shop.orders"])
    assert list(meta.tables) == ["shop.orders"]
    cols = {c.name: c for c in meta.tables["shop.orders"].columns}

    assert cols["_id"].is_primary_key and cols["_id"].data_type == "objectId"
    assert cols["total"].data_type == "double|int"
    assert cols["customer"].data_type == "object" and cols["customer.tier"].data_type == "string"
    assert cols["items"].data_type == "array<object>" and cols["items.sku"].data_type == "string"
    assert cols["created"].data_type == "date"
    assert meta.tables["shop.orders"].estimated_row_count == 3


def test_allow_list_hides_other_collections(mongo_db):
    assert "shop.secrets" not in mongo_db.get_schema_metadata(allowed_tables=["orders", "customers"]).tables


def test_execute_aggregation_returns_plain_python_rows(mongo_db):
    res = mongo_db.execute(
        q(pipeline=[{"$group": {"_id": "$status", "n": {"$sum": 1}, "sum": {"$sum": "$total"}}}, {"$sort": {"_id": 1}}])
    )
    assert res.rows == [{"_id": "paid", "n": 2, "sum": 200.5}, {"_id": "refunded", "n": 1, "sum": 40}]
    assert res.columns == ["_id", "n", "sum"]


def test_execute_serializes_objectid_and_dates(mongo_db):
    row = mongo_db.execute(q(pipeline=[{"$match": {"status": "refunded"}}])).rows[0]
    assert isinstance(row["_id"], str) and row["created"].startswith("2024-03-03")


def test_execute_truncates_to_max_rows(mongo_db):
    res = mongo_db.execute(q(pipeline=[]), max_rows=2)
    assert res.row_count == 2 and res.is_truncated


def test_provider_refuses_write_stages_even_if_called_directly(mongo_db):
    with pytest.raises(SecurityError):
        mongo_db.execute(q(pipeline=[{"$out": "copy"}]))
    assert "copy" not in mongo_db._db().list_collection_names()


def test_health_check(mongo_db):
    assert mongo_db.health_check()["status"] == "healthy"


# ------------------------------------------------------------------ end to end through the agent
def _agent(mongo_db, llm):
    return AgenticKnowledgeBase(
        llm=llm,
        db=mongo_db,
        database={"type": "mongodb", "database": "shop", "host": "localhost"},
        knowledgebase={"allowed_tables": ["shop.orders"]},
        cache={"enabled": False},
        response={"show_sql": True},
    )


def test_agent_answers_from_mongodb_end_to_end(mongo_db):
    plan = {
        "requires_database": True, "reasoning": "count paid orders", "relevant_tables": ["shop.orders"],
    }
    query = {"collection": "orders", "pipeline": [{"$match": {"status": "paid"}}, {"$count": "paid_orders"}]}
    llm = MockLLMProvider(
        responses=[json.dumps(plan), json.dumps({"sql": query, "explanation": "count"}), "There are 2 paid orders."]
    )
    agent = _agent(mongo_db, llm)
    res = agent.ask("How many paid orders are there?")

    assert res.answer == "There are 2 paid orders."
    assert res.metadata.database_used and res.metadata.row_count == 1
    assert res.metadata.sources == ["orders"]
    assert parse_query(res.metadata.sql)["pipeline"][-1] == {"$limit": 1000}  # row cap appended by the validator


def test_agent_scopes_queries_to_the_tenant(mongo_db):
    plan = {"requires_database": True, "reasoning": "r", "relevant_tables": ["shop.orders"]}
    query = {"collection": "orders", "pipeline": [{"$count": "n"}]}
    llm = MockLLMProvider(responses=[json.dumps(plan), json.dumps({"sql": query}), "ok"])
    agent = _agent(mongo_db, llm)
    res = agent.ask("How many orders?", tenant_id="globex")

    sent = parse_query(res.metadata.sql)
    assert sent["pipeline"][0] == {"$match": {"tenant_id": "globex"}}


def test_agent_blocks_a_malicious_generated_query(mongo_db):
    plan = {"requires_database": True, "reasoning": "r", "relevant_tables": ["shop.orders"]}
    evil = {"collection": "orders", "pipeline": [{"$out": "stolen"}]}
    llm = MockLLMProvider(responses=[json.dumps(plan), json.dumps({"sql": evil})])
    agent = _agent(mongo_db, llm)
    with pytest.raises(SQLValidationError):
        agent.ask("copy everything")
    assert "stolen" not in mongo_db._db().list_collection_names()


# ------------------------------------------------------------------ catalog on MongoDB
def test_catalog_for_mongodb_skips_sql_profiling_but_keeps_descriptions(mongo_db):
    from agentic_kb.knowledgebase.catalog import CatalogBuilder

    schema = mongo_db.get_schema_metadata(allowed_tables=["shop.orders"])
    llm = MockLLMProvider(
        default_response='{"table_description": "Customer orders.", "columns": {"status": "Order state"}}'
    )
    logs = []
    builder = CatalogBuilder(db=mongo_db, schema=schema, llm=llm, log=logs.append)
    cat = builder.build(profile_values=True, use_llm=True)

    orders = cat["tables"]["shop.orders"]
    assert orders["description"] == "Customer orders." and orders["row_count"] == 3
    assert orders["columns"]["status"]["description"] == "Order state"
    assert "values" not in orders["columns"]["status"] and "relations" not in orders
    assert any("MongoDB" in line for line in logs)
