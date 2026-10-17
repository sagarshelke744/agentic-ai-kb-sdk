"""FastAPI application factory, global exception handling, and CORS configuration."""

from typing import Optional
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentic_kb.agent.agent import AgenticKnowledgeBase
from agentic_kb.api.middleware import RateLimitMiddleware, RequestIDMiddleware
from agentic_kb.api.routes import create_api_router
from agentic_kb.exceptions.errors import (
    AgenticKBError,
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseTimeoutError,
    LLMRateLimitError,
    LLMTimeoutError,
    PermissionDeniedError,
    PromptInjectionError,
    SQLValidationError,
    SecurityError,
)
from agentic_kb.observability.logging import get_logger

logger = get_logger("agentic_kb.api")


def create_app(
    agent: Optional[AgenticKnowledgeBase] = None,
    config_path: Optional[str] = None,
) -> FastAPI:
    """
    Construct and configure the production FastAPI application.

    Can be initialized with an existing AgenticKnowledgeBase instance
    or loaded from a YAML configuration file path.
    """
    if agent is None:
        cfg = config_path or "configs/example.yaml"
        agent = AgenticKnowledgeBase.from_yaml(cfg)

    app = FastAPI(
        title=f"{agent.config.agent.name} API",
        description="Agentic AI Database Knowledgebase API platform",
        version=agent.config.agent.version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 1. CORS Configuration (enables React widget and external frontend integrations)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Rate Limiting and Request ID Tracing Middleware
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # 3. Global Exception Handlers (safe error responses without stack trace leaks)
    @app.exception_handler(AgenticKBError)
    async def agentic_kb_error_handler(request: Request, exc: AgenticKBError):
        req_id = getattr(request.state, "request_id", None)
        logger.warning(f"Handled AgenticKBError [{type(exc).__name__}]: {exc.message}")

        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(exc, (PromptInjectionError, SQLValidationError)):
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, PermissionDeniedError):
            status_code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, (DatabaseTimeoutError, LLMTimeoutError)):
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        elif isinstance(exc, DatabaseConnectionError):
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif isinstance(exc, LLMRateLimitError):
            status_code = status.HTTP_429_TOO_MANY_REQUESTS

        return JSONResponse(
            status_code=status_code,
            content={
                "error": type(exc).__name__,
                "user_safe_message": exc.user_safe_message,
                "request_id": req_id,
            },
        )

    # 4. Attach API routes
    router = create_api_router(agent)
    app.include_router(router)

    # Root informational route
    @app.get("/", summary="Root status")
    async def root():
        return {
            "name": agent.config.agent.name,
            "version": agent.config.agent.version,
            "docs": "/docs",
            "api": "/api/v1",
        }

    # Root Prometheus scrape endpoint
    @app.get("/metrics", summary="Prometheus metrics scrape endpoint", include_in_schema=False)
    async def metrics():
        from agentic_kb.observability.metrics import metrics_collector
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(metrics_collector.to_prometheus_text(), media_type="text/plain; version=0.0.4")

    return app
