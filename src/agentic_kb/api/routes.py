"""FastAPI REST routes for chat, streaming, sessions, and knowledgebase sync."""

import json
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from agentic_kb.agent.agent import AgenticKnowledgeBase
from agentic_kb.api.middleware import verify_api_key_header
from agentic_kb.models.request import ChatRequest
from agentic_kb.models.response import ChatResponse
from agentic_kb.observability.logging import get_logger
from agentic_kb.observability.metrics import MetricsTimer, metrics_collector
from fastapi.responses import PlainTextResponse

logger = get_logger("agentic_kb.api.routes")


def create_api_router(agent: AgenticKnowledgeBase) -> APIRouter:
    """Create and configure the FastAPI router bound to an AgenticKnowledgeBase instance."""
    router = APIRouter(prefix="/api/v1")

    # In-memory session store (conversation history)
    sessions: Dict[str, List[Dict[str, Any]]] = {}

    @router.post(
        "/chat",
        response_model=ChatResponse,
        summary="Ask question",
        description="Synchronous conversational endpoint returning grounded answer and execution metadata.",
    )
    async def chat(request: ChatRequest, req: Request) -> ChatResponse:
        # Check API key if required
        if verify_api_key_header(req) is False:
            metrics_collector.inc_counter("http_requests_total", labels={"endpoint": "/api/v1/chat", "status": "401"})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        with MetricsTimer("http_request_duration_seconds", labels={"endpoint": "/api/v1/chat"}):
            response = agent.ask(request)
            metrics_collector.inc_counter("http_requests_total", labels={"endpoint": "/api/v1/chat", "status": "200"})

        # Record into session if conversation_id was provided
        if request.conversation_id:
            if request.conversation_id not in sessions:
                sessions[request.conversation_id] = []
            sessions[request.conversation_id].append({
                "role": "user",
                "content": request.message,
            })
            sessions[request.conversation_id].append({
                "role": "assistant",
                "content": response.answer,
            })

        return response

    @router.post(
        "/chat/stream",
        summary="Stream chat response",
        description="Server-Sent Events (SSE) streaming endpoint delivering status steps and answer tokens.",
    )
    async def chat_stream(request: ChatRequest, req: Request):
        if verify_api_key_header(req) is False:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        async def event_generator():
            try:
                async for chunk in agent.astream(request):
                    yield {
                        "event": chunk.event,
                        "data": json.dumps(chunk.data),
                    }
            except Exception as e:
                logger.error(f"Error during streaming response: {str(e)}")
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e), "user_safe_message": "An error occurred during streaming."}),
                }

        return EventSourceResponse(event_generator())

    @router.get(
        "/health",
        summary="Liveness probe",
        description="Lightweight ping returning server liveness.",
    )
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "agent": agent.config.agent.name,
            "version": agent.config.agent.version,
        }

    @router.get(
        "/ready",
        summary="Readiness probe",
        description="Comprehensive readiness check querying LLM, Database, and Knowledgebase.",
    )
    async def readiness() -> Dict[str, Any]:
        report = agent.health_check()
        status_code = status.HTTP_200_OK if report.get("status") == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        if status_code != status.HTTP_200_OK:
            raise HTTPException(status_code=status_code, detail=report)
        return report

    @router.get(
        "/knowledgebase/status",
        summary="Knowledgebase status",
        description="Inspect indexed tables, business terms, and vector store metrics.",
    )
    async def kb_status() -> Dict[str, Any]:
        return {
            "indexed_items": agent.kb.get_indexed_count(),
            "allowed_tables": agent.config.knowledgebase.allowed_tables,
            "allowed_schemas": agent.config.knowledgebase.allowed_schemas,
            "database_dialect": agent.db.dialect_name,
        }

    @router.post(
        "/knowledgebase/sync",
        summary="Synchronize knowledgebase",
        description="Trigger database schema reflection and update vector index.",
    )
    async def kb_sync() -> Dict[str, Any]:
        count = agent.index_schema_metadata()
        return {
            "status": "synced",
            "indexed_tables": count,
            "total_items": agent.kb.get_indexed_count(),
        }

    @router.post(
        "/sessions",
        summary="Create conversation session",
        description="Initialize a new conversation session ID.",
    )
    async def create_session() -> Dict[str, str]:
        session_id = str(uuid.uuid4())
        sessions[session_id] = []
        return {"session_id": session_id}

    @router.get(
        "/sessions/{session_id}",
        summary="Get session history",
        description="Retrieve message history for an active session.",
    )
    async def get_session(session_id: str) -> Dict[str, Any]:
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return {
            "session_id": session_id,
            "history": sessions[session_id],
        }

    @router.get(
        "/config",
        summary="Client configuration",
        description="Returns safe public agent metadata for frontends without revealing secrets.",
    )
    async def get_client_config() -> Dict[str, Any]:
        return {
            "name": agent.config.agent.name,
            "description": agent.config.agent.description,
            "version": agent.config.agent.version,
            "show_sql": agent.config.response.show_sql,
            "allowed_tables": agent.config.knowledgebase.allowed_tables,
        }

    @router.get(
        "/metrics",
        summary="Prometheus metrics",
        description="Scrape target returning Prometheus text exposition format metrics.",
        response_class=PlainTextResponse,
    )
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(metrics_collector.to_prometheus_text(), media_type="text/plain; version=0.0.4")

    return router
