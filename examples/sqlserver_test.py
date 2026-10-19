"""
SQL Server Live Test — DESKTOP-EF69CVF\\SQLEXPRESS / Sagar / dbo.employee
=========================================================================
Run from project root:
    python examples/sqlserver_test.py

Requirements:
    pip install -e ".[sqlserver]"
    pip install pyodbc
    ODBC Driver 17 for SQL Server must be installed (already verified on this machine)
"""

from agentic_kb import AgenticKnowledgeBase
from agentic_kb.database import DatabaseProviderFactory, SQLServerProvider
from agentic_kb.models.config import AgenticKBConfig, DatabaseConfig


# ─────────────────────────────────────────────────────────────
# SECTION 1: Direct Database Connection Test (no LLM needed)
# ─────────────────────────────────────────────────────────────
def test_database_connection():
    print("=" * 60)
    print("SECTION 1: Direct Database Connection")
    print("=" * 60)

    cfg = DatabaseConfig(
        type="sqlserver",
        host=r"DESKTOP-EF69CVF\SQLEXPRESS",
        port=1433,
        database="Sagar",
        username="",   # Windows Authentication — no password needed
        password="",
    )

    provider = SQLServerProvider(config=cfg, driver="pyodbc")

    # 1a. Health check
    print("\n[1a] Health Check:")
    health = provider.health_check()
    for k, v in health.items():
        print(f"     {k}: {v}")

    # 1b. Schema reflection
    print("\n[1b] Schema Metadata (dbo.employee):")
    meta = provider.get_schema_metadata(allowed_schemas=["dbo"])
    for tbl_name, tbl in meta.tables.items():
        print(f"     Table: {tbl_name}")
        for col in tbl.columns:
            pk  = " [PK]" if col.is_primary_key else ""
            fk  = f" [FK -> {col.foreign_table}.{col.foreign_column}]" if col.is_foreign_key else ""
            nullable = "" if col.is_nullable else " NOT NULL"
            print(f"       • {col.name}: {col.data_type}{nullable}{pk}{fk}")

    # 1c. Raw SELECT
    print("\n[1c] SELECT * FROM dbo.employee:")
    result = provider.execute("SELECT * FROM dbo.employee")
    print(f"     Columns : {result.columns}")
    print(f"     Row count: {result.row_count}")
    for row in result.rows:
        print(f"     {row}")

    # 1d. Read-only enforcement
    print("\n[1d] Read-only enforcement (INSERT should be blocked):")
    try:
        provider.execute("INSERT INTO dbo.employee VALUES (999, 'TEST', 'IT', 0, 'PUNE', '2024-01-01', 'Tester')")
        print("     ERROR: Insert was NOT blocked!")
    except Exception as e:
        print(f"     Correctly blocked: {type(e).__name__}: {e}")

    provider.close()
    print("\n     Database connection closed.\n")


# ─────────────────────────────────────────────────────────────
# SECTION 2: Factory Pattern Test (via YAML config)
# ─────────────────────────────────────────────────────────────
def test_factory_from_yaml():
    print("=" * 60)
    print("SECTION 2: Factory from configs/sqlserver.yaml")
    print("=" * 60)

    config = AgenticKBConfig.from_yaml("configs/sqlserver.yaml")
    db = DatabaseProviderFactory.create(config.database)

    print(f"\n     Provider : {type(db).__name__}")
    print(f"     Driver   : {db.driver}")
    print(f"     Database : {db.database_name}")
    print(f"     Dialect  : {db.dialect_name}")

    health = db.health_check()
    print(f"     Status   : {health['status']}  |  Latency: {health['latency_ms']}ms")

    db.close()
    print()


# ─────────────────────────────────────────────────────────────
# SECTION 3: Full Agent Chat Test (requires GROQ_API_KEY)
# ─────────────────────────────────────────────────────────────
def test_agent_chat():
    print("=" * 60)
    print("SECTION 3: Full Agent Chat (requires GROQ_API_KEY in .env)")
    print("=" * 60)

    import os
    if not os.getenv("GROQ_API_KEY"):
        print("\n     Skipped — GROQ_API_KEY not set in environment.\n"
              "     Set it in .env file to enable LLM chat.\n")
        return

    agent = AgenticKnowledgeBase.from_yaml("configs/sqlserver.yaml")

    questions = [
        "How many employees are there?",
        "Who earns the highest salary?",
        "List all employees in the HR department.",
        "What is the average salary by department?",
    ]

    for q in questions:
        print(f"\n     Q: {q}")
        try:
            response = agent.ask(q)
            print(f"     A: {response.answer}")
            if response.metadata and response.metadata.sql_query:
                print(f"     SQL: {response.metadata.sql_query}")
        except Exception as e:
            print(f"     Error: {type(e).__name__}: {e}")

    print()


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_database_connection()
    test_factory_from_yaml()
    test_agent_chat()
    print("All tests completed.")
