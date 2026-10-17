"""Example demonstrating Database Layer and Schema Discovery (Phase 3)."""

from agentic_kb import (
    AgenticKnowledgeBase,
    MockDatabaseProvider,
    MockLLMProvider,
)


def main():
    print("=== Initializing Agent with Database Layer ===")

    # Sample database with enterprise sales data
    sample_tables = {
        "sales_orders": [
            {"id": "ORD-1001", "customer_id": "CUST-1", "order_date": "2026-09-15", "amount": 12500.0, "status": "shipped"},
            {"id": "ORD-1002", "customer_id": "CUST-2", "order_date": "2026-09-20", "amount": 8300.0, "status": "shipped"},
            {"id": "ORD-1003", "customer_id": "CUST-1", "order_date": "2026-10-01", "amount": 4500.0, "status": "processing"},
        ],
        "products": [
            {"sku": "PROD-A", "name": "Enterprise Analytics Suite", "price": 4500.0, "category": "Software"},
            {"sku": "PROD-B", "name": "Dedicated AI Support", "price": 2000.0, "category": "Services"},
        ],
        "customers": [
            {"id": "CUST-1", "company": "Apex Global", "tier": "Enterprise", "region": "APAC"},
            {"id": "CUST-2", "company": "Beacon Industries", "tier": "Standard", "region": "EMEA"},
        ],
    }

    table_descriptions = {
        "sales_orders": "Customer sales transactions, timestamps, order status, and amounts",
        "products": "Product catalog containing item SKUs, descriptions, categories, and unit pricing",
        "customers": "Customer business accounts, contract tier, and regional assignment",
    }

    db_provider = MockDatabaseProvider(
        database_name="enterprise_sales",
        initial_tables=sample_tables,
        table_descriptions=table_descriptions,
    )

    agent = AgenticKnowledgeBase(
        llm=MockLLMProvider(default_response="Total revenue is $25,300 across 3 orders."),
        db=db_provider,
        database={
            "type": "sqlite",
            "host": "localhost",
            "database": "enterprise_sales",
            "username": "ai_agent_user",
        },
        knowledgebase={
            "allowed_tables": ["sales_orders", "products", "customers"],
        },
    )

    print("\n1. Health Check:")
    print(agent.health_check())

    print("\n2. Discovered Database Schema Metadata:")
    schema = agent.get_schema_metadata()
    print(f"Dialect: {schema.dialect}, Database: {schema.database_name}")
    print(f"Total Discovered Tables: {len(schema.tables)}")

    for full_name, table in schema.tables.items():
        print(f"\n  * Table: {full_name} ({table.description or 'No description'})")
        for col in table.columns:
            pk_badge = " [PK]" if col.is_primary_key else ""
            print(f"      - {col.name}: {col.data_type}{pk_badge}")

    print("\n3. Generated Prompt Context for LLM SQL Generation:")
    print("--------------------------------------------------")
    print(schema.to_prompt_context())
    print("--------------------------------------------------")

    print("\n4. Safe Read-Only Query Execution:")
    query = "SELECT status, COUNT(*) AS count, SUM(amount) AS total FROM sales_orders GROUP BY status"
    res = agent.db.execute(query)
    print(f"Executed Query: {res.query}")
    print(f"Execution Time: {res.duration_ms}ms")
    print(f"Rows Returned: {res.row_count}")
    print("Result Rows:", res.rows)

    agent.close()


if __name__ == "__main__":
    main()
