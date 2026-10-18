# Agentic KnowledgeBase SDK (`agentic-kb`)

## Complete Step-by-Step Guide to Run, Test, and Deploy

Production-ready Agentic AI database knowledgebase platform that securely connects conversational AI to enterprise databases with AST-level SQL guardrails, semantic metrics retrieval, FastAPI SSE streaming, and embeddable React/JS widgets.

---

## Architecture Overview

```text
User Question
     │
     ▼
React Chatbot / Embeddable Widget / Client App
     │
     ▼
FastAPI Server (/api/v1/chat/stream)
     │
     ▼
SQLAgentPlanner (Sanitization & Intent Detection)
     │
     ▼
KnowledgeBase (Semantic Business Terms & Vector Retrieval)
     │
     ▼
LLMProvider (SQL Generation via OpenAI / Azure / Gemini / Custom)
     │
     ▼
SQLValidator (AST Allowlist, Operation Bounds, LIMIT Enforcement)
     │
     ▼
PermissionEngine (Row-Level Security Tenant/User Predicates)
     │
     ▼
DatabaseProvider (Read-Only Connection Pool Execution)
     │
     ▼
Response LLM (Grounded Natural Language Answer & Citations)
```

---

## Prerequisites

Before starting, ensure you have the following installed:

- **Python**: `3.10`, `3.11`, or `3.12`
- **Node.js**: `v18+` and `npm 10+`
- **Docker & Docker Compose** (Optional, for containerized multi-service deployment)
- **Git**

---

## Step 1: Environment Setup

### 1.1. Clone Repository & Setup Python Virtual Environment

```bash
# Clone the repository
git clone https://github.com/your-org/agentic-ai-kb-sdk.git
cd agentic-ai-kb-sdk

# Create Python virtual environment
python -m venv .venv

# Activate virtual environment:
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (cmd):
.venv\Scripts\activate.bat
# On Linux / macOS:
source .venv/bin/activate

# Upgrade pip and install package with development dependencies
pip install --upgrade pip
pip install -e ".[dev]"
```

### 1.2. Install Frontend Dependencies

```bash
cd frontend/react-widget
npm install
cd ../..
```

---

## Step 2: Running Automated Tests

Run the full verification suites to confirm backend and frontend integrity.

### 2.1. Backend Python Test Suite (67 Tests)

Run all unit, integration, caching, metrics, and AST security tests:

```bash
# On Windows:
.venv\Scripts\pytest -v

# On Linux/macOS:
pytest -v
```

Expected output:

```text
============================= 67 passed in ~5s =============================
```

Tested layers:

- **AST SQL Security**: Single-statement enforcement, DML/DDL blocking, table/schema/column allowlists, join complexity limits, row limits.
- **LLM Abstraction**: Mock deterministic provider, Custom callable injection, Multi-provider fallback failover, Exponential backoff & jitter retries.
- **Database Layer**: Read-only SQLite in-memory mock, PostgreSQL connection pooling & statement timeouts.
- **Knowledgebase Layer**: Normalized metadata, Vector similarity search, Semantic business terms.
- **API & Observability**: FastAPI REST routes, SSE streaming, Request ID tracing, Rate limiting, Prometheus `/metrics` scraping.
- **Caching**: In-memory TTL cache, Redis client with automatic zero-downtime in-memory fallback.

### 2.2. Frontend Build & Typecheck

```bash
cd frontend/react-widget
npm run build
cd ../..
```

This compiles:

- `dist/agentic-kb.js` (ES Module for `@agentic-kb/react`)
- `dist/agentic-kb.umd.cjs` (CommonJS / UMD bundle)
- `dist/agentic-kb-widget.iife.js` (Standalone browser script with bundled React)
- `dist/style.css` (Glassmorphic dark/light scoped stylesheet)
- `dist/index.d.ts` (Full TypeScript declaration tree)

---

## Step 3: Run the Python SDK Directly (Script Mode)

You can run the SDK programmatically in your own Python applications without running any HTTP servers:

```python
from agentic_kb import AgenticKnowledgeBase

# 1. Load configuration from YAML (with automatic ${ENV_VAR} interpolation)
agent = AgenticKnowledgeBase.from_yaml("configs/example.yaml")

# 2. Ask a natural language question
response = agent.ask(
    message="What were our total sales last month?",
    user_id="analyst_01",
    tenant_id="enterprise_corp"
)

# 3. Inspect grounded answer & transparent audit metadata
print("Answer:", response.answer)
print("Database Used:", response.metadata.get("database_used"))
print("Tables Referenced:", response.metadata.get("tables_used"))
print("Execution Steps:", response.metadata.get("steps"))
```

Run the provided example:

```bash
python examples/basic_agent.py
```

---

## Step 4: Run the FastAPI Server Locally

Start the backend API server using the built-in CLI:

```bash
agentic-kb serve --config configs/example.yaml --port 8000 --reload
```

Or using `uvicorn`:

```bash
uvicorn agentic_kb.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

The server starts at `http://localhost:8000`:

- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Liveness Probe**: `http://localhost:8000/api/v1/health`
- **Readiness Probe**: `http://localhost:8000/api/v1/ready`
- **Prometheus Metrics**: `http://localhost:8000/metrics`

---

## Step 5: Test API Endpoints with `curl`

Open another terminal and test the live endpoints:

### 5.1. Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Response:

```json
{"status":"ok","agent":"Enterprise Knowledge Assistant","version":"1.0.0"}
```

### 5.2. Synchronous Chat (`POST /api/v1/chat`)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What were our total sales last month?"}'
```

Response:

```json
{
  "answer": "Mock generated answer for query: What were our total sales last month?",
  "request_id": "97e682d3-c40d-45da-9c87-8ff7a1cbb092",
  "metadata": {
    "database_used": true,
    "tables_used": ["sales.orders"]
  }
}
```

### 5.3. Real-Time Streaming Chat (`POST /api/v1/chat/stream`)

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Show sales in Q3"}'
```

Streams Server-Sent Events (SSE):

```text
event: step
data: {"name": "sanitizing_input"}

event: step
data: {"name": "intent_detection"}

event: token
data: {"text": "Total "}

event: token
data: {"text": "sales "}

event: done
data: {"metadata": {"database_used": true}}
```

### 5.4. Prometheus Metrics Scraping

```bash
curl http://localhost:8000/metrics
```

Outputs standard Prometheus metrics:

```text
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/v1/chat",status="200"} 1.0
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{endpoint="/api/v1/chat",le="0.1"} 1
```

---

## Step 6: Run & Test the React Frontend UI

Run the Vite development playground:

```bash
cd frontend/react-widget
npm run dev
```

Open `http://localhost:3000` in your browser.

**What you will see:**

- An interactive dashboard with live widget configuration controls (change API URL, switch between Dark/Light mode, toggle SSE streaming, show/hide reasoning steps).
- A floating chat launcher button in the bottom-right corner with a pulsing breathing glow.
- Click the button to open the glassmorphic chat modal, select suggested queries, or ask custom questions.
- Step-by-step reasoning progress accordion and cited database table badges (`sales.orders`).

---

## Step 7: Test the Embeddable Standalone Widget (Phase 9)

You can embed the chatbot into any plain HTML page, Vue, or Angular application with zero React dependencies:

```bash
# Open the provided standalone HTML demo in your browser:
# On Windows:
start examples/widget_demo.html
# On macOS:
open examples/widget_demo.html
# On Linux:
xdg-open examples/widget_demo.html
```

Notice the widget loads completely from the compiled IIFE script:

```html
<!-- 1. Include styles -->
<link rel="stylesheet" href="../frontend/react-widget/dist/style.css" />

<!-- 2. Include standalone script (React bundled inside) -->
<script src="../frontend/react-widget/dist/agentic-kb-widget.iife.js"></script>

<!-- 3. Initialize anywhere -->
<script>
  AgenticKB.init({
    apiUrl: "http://localhost:8000",
    assistantName: "Enterprise Data Assistant",
    theme: "dark",
    position: "bottom-right",
    enableStreaming: true,
    showSources: true,
    showExecutionSteps: true
  });
</script>
```

---

## Step 8: Run the Complete Stack with Docker Compose

Run the entire containerized production environment (FastAPI backend + PostgreSQL 16 with `pgvector` + Redis 7 + Prometheus):

```bash
docker compose up -d --build
```

### Verify Running Containers:

```bash
docker compose ps
```

| Service                  | Container Name            | Port     | Description                                               |
| :----------------------- | :------------------------ | :------- | :-------------------------------------------------------- |
| **`agentic-kb`** | `agentic_kb_api`        | `8000` | FastAPI server with built-in frontend assets              |
| **`postgres`**   | `agentic_kb_postgres`   | `5432` | PostgreSQL 16 + `pgvector` + `ai_agent_readonly` user |
| **`redis`**      | `agentic_kb_redis`      | `6379` | Redis caching & conversation state storage                |
| **`prometheus`** | `agentic_kb_prometheus` | `9090` | Prometheus scraping `agentic-kb:8000/metrics`           |

### Check Service Health:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/metrics
```

Open Prometheus dashboard at:
`http://localhost:9090/targets` (shows `agentic-kb` in state `UP`).

### Stop Containers:

```bash
docker compose down
```

---

## Repository File Structure

```text
agentic-ai-kb-sdk/
├── configs/
│   ├── example.yaml              # Local development configuration
│   └── docker.yaml               # Docker multi-service container configuration
├── deploy/
│   ├── postgres/
│   │   └── init.sql              # Database init, schemas, pgvector, and read-only user
│   └── prometheus/
│       └── prometheus.yml        # Prometheus metrics scraping configuration
├── examples/
│   ├── basic_agent.py            # Python SDK usage example
│   └── widget_demo.html          # Plain HTML standalone widget demo (Phase 9)
├── frontend/
│   └── react-widget/             # React Chatbot & Embeddable Widget (Phase 8 & 9)
│       ├── src/
│       │   ├── components/       # Header, Message, InputBox, ChatWindow, etc.
│       │   ├── hooks/useChat.ts  # State management & SSE streaming hook
│       │   ├── services/api.ts   # FastAPI SSE client
│       │   ├── styles/widget.css # Scoped CSS design system (Dark & Light)
│       │   ├── embed.ts          # window.AgenticKB.init wrapper
│       │   └── index.ts          # @agentic-kb/react entrypoint
│       └── package.json
├── src/agentic_kb/               # Core Python SDK
│   ├── agent/                    # SQLAgentPlanner & AgenticKnowledgeBase coordinator
│   ├── api/                      # FastAPI app factory, routes, SSE, & middleware
│   ├── cache/                    # InMemoryCacheProvider & RedisCacheProvider
│   ├── database/                 # PostgreSQL, SQLAlchemy pool, SQLite mock
│   ├── exceptions/               # User-sanitized exception hierarchy
│   ├── knowledgebase/            # Business terms, embeddings, & vector retrieval
│   ├── llm/                      # OpenAI, Azure, Gemini, Custom callable, Fallback, Mock
│   ├── models/                   # Pydantic configuration and request/response models
│   ├── observability/            # Secret-masking logger & Prometheus metrics
│   └── security/                 # sqlglot AST validator, PII masker, & RLS engine
├── tests/
│   ├── integration/              # FastAPI & SSE streaming tests
│   ├── security/                 # AST injection & SQL security tests
│   └── unit/                     # Unit tests for LLM, DB, Cache, Metrics, KB
├── Dockerfile                    # Multi-stage production container build
├── docker-compose.yml            # Complete 4-service production stack
├── pyproject.toml                # Python package configuration
└── README.md                     # Master documentation & guide
```

---

## License

Apache-2.0
