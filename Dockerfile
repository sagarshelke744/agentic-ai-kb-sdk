# ==============================================================================
# Multi-Stage Production Dockerfile for Agentic KnowledgeBase SDK Platform
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build Frontend React Widget & Standalone Distribution
# ------------------------------------------------------------------------------
FROM node:18-alpine AS frontend-builder

WORKDIR /build

COPY frontend/react-widget/package*.json ./
RUN npm install

COPY frontend/react-widget/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Python Backend Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user for container security
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/bash -m appuser

# Install Python package and dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application source code and configurations
COPY src/ ./src/
COPY configs/ ./configs/

# Copy compiled frontend distribution from Stage 1
COPY --from=frontend-builder /build/dist/ ./frontend/react-widget/dist/

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["uvicorn", "agentic_kb.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
