"""Integration tests for Prometheus /metrics endpoint and HTTP metrics tracking."""

from fastapi.testclient import TestClient
from agentic_kb.agent.agent import AgenticKnowledgeBase
from agentic_kb.api.app import create_app
from agentic_kb.database.mock import MockDatabaseProvider
from agentic_kb.llm.mock import MockLLMProvider


def test_metrics_endpoint_integration():
    mock_llm = MockLLMProvider()
    mock_db = MockDatabaseProvider(
        tables={
            "sales.orders": [
                {"id": 1, "customer_id": 101, "amount": 100.0, "status": "COMPLETED"},
            ]
        }
    )

    agent = AgenticKnowledgeBase(
        config={
            "agent": {"name": "MetricsTestAgent"},
            "database": {"provider": "postgresql", "host": "mock", "database": "test", "username": "u", "password": "p"},
            "knowledgebase": {"allowed_tables": ["sales.orders"]},
            "cache": {"enabled": True, "type": "memory"}
        },
        llm=mock_llm,
        db=mock_db,
    )

    app = create_app(agent=agent)
    client = TestClient(app)

    # 1. Check root /metrics endpoint
    res_root_metrics = client.get("/metrics")
    assert res_root_metrics.status_code == 200
    assert "text/plain" in res_root_metrics.headers["content-type"]

    # 2. Check /api/v1/metrics endpoint
    res_api_metrics = client.get("/api/v1/metrics")
    assert res_api_metrics.status_code == 200

    # 3. Perform a chat request to trigger metrics increment
    chat_res = client.post("/api/v1/chat", json={"message": "What were our total sales?"})
    assert chat_res.status_code == 200

    # 4. Verify metrics include http_requests_total with /api/v1/chat
    metrics_text = client.get("/metrics").text
    assert "http_requests_total" in metrics_text
    assert "/api/v1/chat" in metrics_text
