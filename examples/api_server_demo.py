"""Example demonstrating FastAPI application server creation and endpoint testing."""

from starlette.testclient import TestClient
from agentic_kb import (
    AgenticKnowledgeBase,
    MockDatabaseProvider,
    MockLLMProvider,
)
from agentic_kb.api.app import create_app


def main():
    print("=== Initializing Agentic KnowledgeBase FastAPI App ===")

    # In-memory database with financial data
    db = MockDatabaseProvider(
        database_name="finance_db",
        initial_tables={
            "transactions": [
                {"id": "TXN-1", "merchant": "Cloud Hosting", "amount": 120.0, "status": "settled"},
                {"id": "TXN-2", "merchant": "Office Supplies", "amount": 45.0, "status": "settled"},
            ]
        },
    )

    llm = MockLLMProvider(
        responses=[
            '{"requires_database": true, "reasoning": "Compute settled transaction sum", "relevant_tables": ["transactions"]}',
            '{"sql": "SELECT SUM(amount) AS total FROM transactions WHERE status = \'settled\'", "explanation": "Sum settled amounts"}',
            "Total settled spend is $165.00 across 2 transactions.",
        ]
    )

    agent = AgenticKnowledgeBase(
        llm=llm,
        db=db,
        database={
            "type": "sqlite",
            "database": "finance_db",
            "host": "localhost",
            "username": "ai_user",
        },
        knowledgebase={
            "allowed_tables": ["transactions"],
        },
        response={
            "show_sql": True,
        },
    )

    # Create the production FastAPI app
    app = create_app(agent=agent)

    # Use TestClient to demonstrate HTTP API calls
    with TestClient(app) as client:
        print("\n1. Health Check (GET /api/v1/health):")
        res = client.get("/api/v1/health")
        print(f"Status Code: {res.status_code}, Response: {res.json()}")

        print("\n2. Readiness Check (GET /api/v1/ready):")
        res_ready = client.get("/api/v1/ready")
        print(f"Status Code: {res_ready.status_code}, Response: {res_ready.json()}")

        print("\n3. Ask Chat Question (POST /api/v1/chat):")
        chat_payload = {"message": "What is our total settled spend?"}
        chat_res = client.post("/api/v1/chat", json=chat_payload)
        print(f"Status Code: {chat_res.status_code}")
        body = chat_res.json()
        print(f"Answer: {body['answer']}")
        print(f"SQL: {body['metadata']['sql']}")
        print(f"Request ID: {body['request_id']}")

        print("\n4. Knowledgebase Status (GET /api/v1/knowledgebase/status):")
        kb_res = client.get("/api/v1/knowledgebase/status")
        print(f"Status: {kb_res.json()}")

        print("\n5. Client Config (GET /api/v1/config):")
        cfg_res = client.get("/api/v1/config")
        print(f"Config: {cfg_res.json()}")

    agent.close()


if __name__ == "__main__":
    main()
