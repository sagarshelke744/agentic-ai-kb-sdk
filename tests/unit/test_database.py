"""Unit tests for Phase 3: Database Layer (PostgreSQL provider, Mock provider, reflection, safety limits)."""

import pytest
from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.factory import DatabaseProviderFactory
from agentic_kb.database.mock import MockDatabaseProvider
from agentic_kb.database.models import ColumnMetadata, TableMetadata
from agentic_kb.database.postgres import PostgreSQLProvider
from agentic_kb.exceptions.errors import (
    ConfigurationError,
    DatabaseConnectionError,
    SecurityError,
)
from agentic_kb.agent.agent import AgenticKnowledgeBase
from agentic_kb.llm.mock import MockLLMProvider


@pytest.fixture
def mock_db():
    initial_data = {
        "sales_orders": [
            {"id": "1", "customer_id": "101", "total_amount": "250.00", "status": "completed"},
            {"id": "2", "customer_id": "102", "total_amount": "499.50", "status": "pending"},
            {"id": "3", "customer_id": "101", "total_amount": "75.25", "status": "completed"},
        ],
        "customers": [
            {"id": "101", "name": "Acme Corp", "country": "USA"},
            {"id": "102", "name": "Global Tech", "country": "Germany"},
        ],
    }
    table_descriptions = {
        "sales_orders": "Customer sales transactions and totals",
        "customers": "Customer profiles and countries",
    }
    db = MockDatabaseProvider(
        database_name="test_sales",
        initial_tables=initial_data,
        table_descriptions=table_descriptions,
    )
    yield db
    db.close()


def test_mock_database_query_execution(mock_db):
    res = mock_db.execute("SELECT id, customer_id, total_amount FROM sales_orders WHERE status = 'completed'")
    assert res.row_count == 2
    assert res.columns == ["id", "customer_id", "total_amount"]
    assert res.rows[0]["id"] == "1"
    assert res.is_truncated is False
    assert res.duration_ms >= 0


def test_mock_database_max_rows_truncation(mock_db):
    res = mock_db.execute("SELECT * FROM sales_orders", max_rows=1)
    assert res.row_count == 1
    assert res.is_truncated is True


def test_mock_database_read_only_protection(mock_db):
    with pytest.raises(SecurityError, match="Read-only violation"):
        mock_db.execute("INSERT INTO sales_orders (id) VALUES ('999')")

    with pytest.raises(SecurityError, match="Read-only violation"):
        mock_db.execute("DROP TABLE customers")

    with pytest.raises(SecurityError, match="Read-only violation"):
        mock_db.execute("UPDATE customers SET name = 'Hacked'")


def test_mock_database_schema_reflection(mock_db):
    catalog = mock_db.get_schema_metadata()
    assert catalog.dialect == "sqlite"
    assert "sales_orders" in catalog.tables
    assert "customers" in catalog.tables

    orders_table = catalog.get_table("sales_orders")
    assert orders_table is not None
    assert orders_table.description == "Customer sales transactions and totals"
    col_names = [c.name for c in orders_table.columns]
    assert "total_amount" in col_names

    # Test prompt context formatting
    context = catalog.to_prompt_context()
    assert "Table: sales_orders" in context
    assert "total_amount" in context


def test_database_provider_factory():
    provider = DatabaseProviderFactory.create({
        "type": "sqlite",
        "database": "analytics",
        "host": "localhost",
        "username": "user",
    })
    assert provider.dialect_name == "sqlite"
    health = provider.health_check()
    assert health["status"] == "healthy"
    provider.close()


def test_database_provider_factory_registration():
    class CustomDB(BaseDatabaseProvider):
        @property
        def dialect_name(self) -> str:
            return "custom_db"

        def execute(self, query, **kwargs):
            raise NotImplementedError

        async def aexecute(self, query, **kwargs):
            raise NotImplementedError

        def get_schema_metadata(self, **kwargs):
            raise NotImplementedError

        def health_check(self):
            return {"status": "healthy", "dialect": "custom_db"}

        def close(self):
            pass

    DatabaseProviderFactory.register("custom_db", CustomDB)
    assert "custom_db" in DatabaseProviderFactory.get_registered_providers()

    created = DatabaseProviderFactory.create({"type": "custom_db", "database": "db", "username": "u"})
    assert created.dialect_name == "custom_db"


def test_database_provider_factory_invalid():
    with pytest.raises(ConfigurationError, match="Unsupported database type"):
        DatabaseProviderFactory.create({"type": "nonexistent_dialect", "database": "db", "username": "u"})


def test_postgresql_provider_read_only_check():
    # Attempting to initialize PostgreSQL without valid credentials / connection
    with pytest.raises(DatabaseConnectionError):
        PostgreSQLProvider()


def test_agent_integration_with_database(mock_db):
    mock_llm = MockLLMProvider(
        responses=[
            # 1. Intent decision
            '{"requires_database": true, "reasoning": "Needs count from db", "relevant_tables": ["sales_orders"]}',
            # 2. SQL generation
            '{"sql": "SELECT COUNT(*) AS count FROM sales_orders WHERE status = \'completed\'", "explanation": "Count orders"}',
            # 3. Response synthesis
            "Total completed orders: 2",
        ]
    )
    agent = AgenticKnowledgeBase(
        llm=mock_llm,
        db=mock_db,
        database={
            "type": "sqlite",
            "host": "localhost",
            "database": "test_sales",
            "username": "user",
        },
        knowledgebase={
            "allowed_tables": ["sales_orders", "customers"]
        }
    )

    schema = agent.get_schema_metadata()
    assert "sales_orders" in schema.tables

    health = agent.health_check()
    assert health["status"] == "ok"
    assert health["database"]["status"] == "healthy"
    assert health["database"]["dialect"] == "sqlite"
    assert health["allowed_tables_count"] == 2

    res = agent.ask("How many completed orders?")
    assert "Total completed orders: 2" in res.answer
    assert res.metadata.database_used is True
    assert res.metadata.row_count == 1
    assert "sales_orders" in res.metadata.sources
    agent.close()
