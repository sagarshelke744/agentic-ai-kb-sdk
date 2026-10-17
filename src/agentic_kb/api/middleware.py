"""FastAPI middleware: Request ID tracing, rate limiting, and security dependencies."""

import os
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Propagate or generate X-Request-ID for distributed tracing across all HTTP requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Attach request_id to request state
        request.state.request_id = req_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class InMemoryRateLimiter:
    """Sliding-window rate limiter per client IP or API key."""

    def __init__(self, requests_per_minute: int = 120):
        self.rpm = requests_per_minute
        self.window_seconds = 60.0
        self._history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        # Clean older timestamps
        self._history[client_key] = [
            t for t in self._history[client_key] if t > window_start
        ]
        if len(self._history[client_key]) >= self.rpm:
            return False
        self._history[client_key].append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce request rate limits returning HTTP 429 when exceeded."""

    def __init__(self, app, rate_limiter: Optional[InMemoryRateLimiter] = None):
        super().__init__(app)
        self.limiter = rate_limiter or InMemoryRateLimiter()

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract client identifier: API key header or client IP
        client_key = (
            request.headers.get("X-API-Key")
            or (request.client.host if request.client else "unknown")
        )

        if not self.limiter.is_allowed(client_key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "user_safe_message": "Too many requests. Please slow down and try again shortly.",
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


def verify_api_key_header(request: Request) -> Optional[str]:
    """
    Optional security validator checking X-API-Key or Bearer token
    against configured API_KEY or API_SECRET environment variables.
    """
    configured_key = os.getenv("API_KEY")
    if not configured_key:
        # Authentication disabled if no API_KEY environment variable is configured
        return None

    # Check X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key == configured_key:
        return api_key

    # Check Authorization: Bearer <token> header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token == configured_key:
            return token

    return None
