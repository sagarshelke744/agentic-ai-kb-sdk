# Integrating Agentic KB SDK into Your Project

Let your users ask questions about your database in plain English. You supply the DB credentials and an LLM
API key; the SDK discovers the schema, has the LLM write a **read-only, validated** SQL query, runs it, and
answers in natural language.

```
question ─► intent ─► schema selection ─► SQL generation ─► validation ─► execution ─► answer
                                            (LLM)        (read-only,    (your DB)    (LLM)
                                                          allow-list)
```

Three ways to use it — pick one:

| Mode | Use when |
|---|---|
| [A. Python library](#a-use-as-a-python-library) | You call it from your own backend code |
| [B. REST API + streaming](#b-run-it-as-an-api-service) | You want a separate service your frontend talks to |
| [C. Chat widget](#c-add-the-chat-widget-to-your-frontend) | You want a ready-made chat UI on top of mode B |

---

## 1. Prerequisites

- Python **3.11+**
- A database the SDK can reach: **PostgreSQL, MySQL / MariaDB, SQL Server or MongoDB** (see [Supported databases](#supported-databases))
- One LLM API key: **Gemini**, **Groq**, **OpenAI** or **Azure OpenAI**
- *(Optional)* Redis for caching / conversation memory — falls back to in-memory if unavailable
- *(Widget only)* Node 18+

> **Use a read-only DB user.** The SDK enforces read-only SQL itself, but a least-privilege database account
> is your second line of defence.

## 2. Install

Install the SDK plus the extra for **your** database and LLM — only the drivers you use are required:

```bash
# from GitHub (replace with the PyPI name once published)
pip install "agentic-kb[postgres,gemini,api] @ git+https://github.com/sagarshelke744/agentic-ai-kb-sdk.git"
```

| Extra | Installs | Needed for |
|---|---|---|
| `postgres` | SQLAlchemy, psycopg2, asyncpg | PostgreSQL |
| `mysql` | SQLAlchemy, PyMySQL, cryptography | MySQL / MariaDB |
| `sqlserver` | SQLAlchemy, pymssql | SQL Server / Azure SQL |
| `mongodb` | PyMongo | MongoDB |
| `gemini` | google-generativeai | Gemini LLM |
| `llm` | openai | OpenAI, Azure OpenAI and Groq |
| `redis` | redis | Redis cache |
| `api` | FastAPI, uvicorn, SSE | REST API + widget backend |

Combine them: `agentic-kb[mysql,llm,redis,api]`. If a driver is missing, the SDK tells you which extra to install.

## 3. Configure

### 3.1 Secrets → `.env`

The SDK loads `.env` automatically (needs `python-dotenv`). Never commit this file.

```dotenv
# --- LLM: set the key for the provider you use ---
GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENAI_API_KEY=...

# --- Database ---
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydb
DB_USER=readonly_user
DB_PASSWORD=...

# --- Optional ---
REDIS_HOST=localhost
API_KEY=choose-a-long-random-string   # if set, the REST API requires header X-API-Key
```

### 3.2 Behaviour → `agentic.yaml`

```yaml
agent:
  name: my-assistant
  description: Answers questions about our data

llm:
  provider: gemini                 # gemini | groq | openai | azure
  model: gemini-3.5-flash          # groq: llama-3.3-70b-versatile · openai: gpt-4o
  api_key_env: GEMINI_API_KEY      # name of the env var holding the key
  temperature: 0.0
  # base_url: https://my-gateway/v1   # optional: OpenAI-compatible gateway / proxy (groq, openai)

database:
  type: postgresql                 # postgresql | mysql | sqlserver | mongodb  (see "Supported databases")
  host: ${DB_HOST:-localhost}
  port: 5432                       # optional: defaults to 5432 / 3306 / 1433 / 27017 by type
  database: ${DB_NAME}
  username: ${DB_USER}
  password_env: DB_PASSWORD        # name of the env var holding the password

knowledgebase:
  allowed_schemas: [public]
  allowed_tables:                  # the LLM can ONLY see/query these
    - public.orders
    - public.customers
  catalog_file: catalog.yaml       # optional, see "Auto-generate the schema catalog" below
  table_descriptions:              # optional: you can skip this once you use the catalog
    public.orders: "Customer orders with status, total amount and order date."
    public.customers: "Registered customers with name, email and region."

security:
  read_only: true
  max_rows: 1000
  query_timeout_seconds: 30

response:
  show_sql: false                  # true while debugging to see generated SQL
  include_sources: true

cache:
  enabled: false                   # true + type: redis for production
  type: memory
  ttl_seconds: 300
```

Tips for good answers:
- Only list tables users actually need in `allowed_tables` — less schema, better SQL, tighter security.
- Write a one-line `table_descriptions` entry per table.
- Mixed-case columns (e.g. `carNo`) are handled automatically on PostgreSQL — the SDK quotes them for you.

Ready-made examples live in `configs/` (`example.yaml` = Gemini, `groq.yaml` = Groq).

---

## Supported databases

Switch databases by changing `database.type` (plus the matching extra from section 2). Ready-made configs
live in `configs/`.

| Database | `type` | Config | Notes |
|---|---|---|---|
| PostgreSQL | `postgresql` (`postgres`) | `example.yaml` | Read-only session + server-side statement timeout enforced |
| MySQL / MariaDB | `mysql` (`mariadb`) | `mysql.yaml` | "Schema" = database name. Read-only session + execution-time limit |
| SQL Server / Azure SQL | `sqlserver` (`mssql`) | `sqlserver.yaml` | T-SQL (`TOP`, `[brackets]`). No read-only session, so use a `db_datareader`-only login |
| MongoDB | `mongodb` (`mongo`) | `mongodb.yaml` | Collections instead of tables; LLM writes aggregation pipelines. Use a user with only the `read` role |

Connection options common to all:

```yaml
database:
  type: mysql
  host: db.example.com
  database: shop
  username: kb_reader
  password_env: MYSQL_PASSWORD      # passwords with @ : / # are fine - they are escaped for you
  url_env: DATABASE_URL             # OR give one full URL/URI (overrides host/port/user/password)
  options: { charset: utf8mb4 }     # extra driver options (MongoDB: URI options such as tls: true)
```

Allow-lists use `schema.table` for SQL databases (`shop.orders`, `dbo.orders`, `public.orders`) and
`database.collection` (or just `collection`) for MongoDB.

**How MongoDB differs.** There is no fixed schema, so the SDK *samples* up to 100 documents per collection and
infers field names and types, flattening nested objects to dotted paths (`customer.tier`, `items.sku`).
The LLM answers with a JSON aggregation pipeline, for example:

```json
{"collection": "orders", "pipeline": [{"$match": {"status": "paid"}}, {"$group": {"_id": null, "revenue": {"$sum": "$total"}}}]}
```

which is checked before it runs: only read-only stages are allowed (`$match`, `$group`, `$lookup`, `$unwind`, ...),
`$out` / `$merge` / `$function` / `$where` are rejected anywhere in the pipeline, `$lookup` can only target allowed
collections, and a `$limit` is always applied. `tenant_id` / `user_id` row-level security is injected as a
leading `$match` — including inside `$lookup`. `catalog generate` works for MongoDB too, but only the
LLM-written descriptions part (value profiling and relation inference are SQL-only).

**Try each locally** (sample `shop` data and a read-only user are created for you):

```bash
docker compose -f docker-compose.databases.yml up -d mysql          # or: mongo   |   mssql mssql-init
agentic-kb check -c configs/mysql.yaml
agentic-kb catalog generate -c configs/mysql.yaml
agentic-kb serve -c configs/mysql.yaml
```

Add a database of your own with `DatabaseProviderFactory.register("name", YourProvider)` (subclass
`BaseDatabaseProvider`, or `SQLAlchemyProvider` for anything SQLAlchemy can reach).

---

## 4. Auto-generate the schema catalog (recommended)

You don't have to describe your tables. The SDK already reads columns, types, keys, foreign keys and DB
comments straight from the database. The **catalog** adds what the database can't say, automatically:

| Added by the catalog | How |
|---|---|
| **Allowed values** of enum-like columns (`status: paid, pending`) | profiles distinct values of low-cardinality columns |
| **Ranges** of numbers / dates | `MIN` / `MAX` per column |
| **Relations** that have no FK constraint (`customerId -> users.id`) | name match, confirmed by checking the values really exist in the other table |
| **Descriptions** for tables / columns that have no DB comment | written once by your LLM |

```bash
# 1. generate (reads your DB, writes catalog.yaml)
agentic-kb catalog generate -c agentic.yaml

# 2. REVIEW catalog.yaml once  (see below)

# 3. preview exactly what the LLM will see
agentic-kb catalog show -c agentic.yaml
```

`catalog_file: catalog.yaml` in your config is all that's needed to use it. Flags:

| Flag | Effect |
|---|---|
| `-o path` | Output file (default: `knowledgebase.catalog_file`, else `catalog.yaml`) |
| `--no-llm` | Don't call the LLM; only profiling + inference |
| `--no-samples` | Don't read any data: no value profiling and no sample rows sent to the LLM |
| `--overwrite` | Throw away existing descriptions / relations and regenerate everything |

### Reviewing the file

Anything written automatically is marked `needs_review: true`, and the command prints the list:

```yaml
public.orders:
  description: Customer orders with status and total.   # auto-written
  needs_review: true
  columns:
    status:
      type: VARCHAR
      values: [paid, pending, refunded]                 # profiled fact, refreshed on every run
      description: Payment state. paid = money received # you edited this -> kept on regenerate
    customerId:
      type: INTEGER
  relations:
    - column: customerId
      references: public.users.id
      inferred: true
      needs_review: true
```

1. Fix any wrong text, then delete the `needs_review` line.
2. Add meaning only you know (what status codes mean, units, currencies).
3. Delete inferred relations that are wrong; add missing ones by hand (`column` + `references: schema.table.column`).
4. Run `agentic-kb catalog show` to see the final schema text sent to the LLM.

**Regenerating is safe:** your edited descriptions and relations are kept; profiled facts (`values`, `range`,
`row_count`) are refreshed. After a migration, just run `generate` again. The runtime also reloads the file
when it changes.

### Privacy

Profiling reads data, and sample values / 3 sample rows per table are sent to your LLM provider when
descriptions are generated. Columns matching `knowledgebase.catalog_exclude_columns` are **never** read or sent.
The default list covers `*password*`, `*token*`, `*email*`, `*phone*`, `*mobile*`, `*card*`, `*address*`, etc.
Extend it for your data, or use `--no-samples` / `--no-llm` to keep data off the wire entirely.
Treat `catalog.yaml` like data: review it before committing it to a public repo.

---

## A. Use as a Python library

```python
from agentic_kb import AgenticKnowledgeBase

agent = AgenticKnowledgeBase.from_yaml("agentic.yaml")

print(agent.health_check())                       # verify LLM + DB + cache

res = agent.ask("How many orders were placed last month?")
print(res.answer)                                 # natural-language answer
print(res.metadata.sources)                       # tables used
print(res.metadata.sql)                           # only if response.show_sql: true

agent.close()
```

Multi-turn chat and multi-tenant calls:

```python
res = agent.ask(
    "And how many of those were cancelled?",
    conversation_id="user-42-session-1",   # keeps chat history
    user_id="42",
    tenant_id="acme",                      # row-level-security hook
)
```

Async streaming (steps → tokens → done):

```python
async for chunk in agent.astream("Top 5 customers by revenue"):
    print(chunk.event, chunk.data)   # step | retry | token | done | error
```

Config in code instead of YAML:

```python
agent = AgenticKnowledgeBase(
    llm={"provider": "groq", "model": "llama-3.3-70b-versatile", "api_key_env": "GROQ_API_KEY"},
    database={"type": "postgresql", "host": "localhost", "database": "mydb",
              "username": "readonly_user", "password_env": "DB_PASSWORD"},
    knowledgebase={"allowed_tables": ["public.orders"]},
)
```

### Plug in your own provider

```python
from agentic_kb.llm import BaseLLMProvider, LLMProviderFactory

class MyLLM(BaseLLMProvider): ...          # implement generate / generate_structured / stream
LLMProviderFactory.register("my_llm", MyLLM)
# then: llm: { provider: my_llm }
```

You can also pass ready-made instances: `AgenticKnowledgeBase(config=..., llm=my_llm, db=my_db)`.

---

## B. Run it as an API service

**Standalone (CLI):**

```bash
agentic-kb check -c agentic.yaml                       # health check
agentic-kb serve -c agentic.yaml --host 0.0.0.0 --port 8000
```

**Or mount it inside your existing FastAPI app:**

```python
from fastapi import FastAPI
from agentic_kb import AgenticKnowledgeBase
from agentic_kb.api.routes import create_api_router

app = FastAPI()
agent = AgenticKnowledgeBase.from_yaml("agentic.yaml")
app.include_router(create_api_router(agent))     # adds /api/v1/*

@app.on_event("shutdown")
def _close(): agent.close()
```

> Mounting only the router skips the SDK's CORS, rate-limit and request-ID middleware and error handlers.
> Use `agentic_kb.api.app.create_app(agent=agent)` if you want the full stack as its own app.

### Endpoints (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | Ask a question, get the full answer as JSON |
| POST | `/chat/stream` | Same, as Server-Sent Events (live progress) |
| GET | `/health`, `/ready` | Liveness / readiness (DB, LLM, cache) |
| GET | `/knowledgebase/status` | Indexed schema info |
| POST | `/knowledgebase/sync` | Re-index schema |
| GET | `/metrics` | Prometheus metrics |
| GET | `/docs` | Swagger UI |

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"message": "How many customers do we have by region?", "conversation_id": "abc"}'
```

### Streaming events (`/chat/stream`)

Each event has an SSE `event:` name and a JSON `data:` body (which also repeats the name as `type`).

| event | data |
|---|---|
| `step` | `{step, message}` — pipeline progress, e.g. "Generating SQL query" |
| `retry` | `{attempt, max_retries, wait_seconds}` — LLM rate-limited, retrying |
| `token` | `{text}` — answer text, word by word |
| `done` | `{answer, request_id, metadata}` — finished |
| `error` | `{code, message, retryable, retry_after}` — failed (see below) |

A stream always ends with exactly one `done` **or** one `error`.

### Handling errors

| `code` | Meaning | What to do |
|---|---|---|
| `LLMRateLimitError` | Provider limit hit. `retry_after` = seconds to wait | If `retryable` is true, retry after the wait. If false (daily quota), tell the user / switch model or key |
| `LLMTimeoutError` | Provider too slow | Retry |
| `SQLValidationError` | Generated SQL was blocked by the safety rules | Rephrase the question |
| `PermissionDeniedError` | Table/column not allowed | Check `allowed_tables` |
| `PromptInjectionError` | Input rejected by the sanitizer | Rephrase |

`message` is always safe to show to end users (no stack traces or SQL internals).
For non-streaming `/chat`, the same errors return HTTP 400/403/429/504/500 with `user_safe_message`.

### Production checklist

- [ ] Set `API_KEY` so clients must send `X-API-Key`
- [ ] Restrict CORS — the default in `create_app` is `allow_origins=["*"]`
- [ ] Use a **read-only** DB user and a minimal `allowed_tables`
- [ ] Enable Redis cache (`cache.type: redis`)
- [ ] Keep `response.show_sql: false`
- [ ] Put the service behind HTTPS
- [ ] Watch LLM provider quotas (free tiers are small — Gemini free tier is ~20 requests/day/model)

---

## C. Add the chat widget to your frontend

The widget (React, also shipped as a standalone script) talks to mode B and shows live execution steps,
retry notices, sources, and a **Retry** button on recoverable errors.

**Build it once** (the `dist/` folder is not committed):

```bash
cd frontend/react-widget
npm install
npm run build        # outputs dist/agentic-kb-widget.iife.js and dist/style.css
```

**Any website (plain HTML / Vue / Angular / legacy apps):**

```html
<link rel="stylesheet" href="/static/agentic-kb/style.css">
<script src="/static/agentic-kb/agentic-kb-widget.iife.js"></script>
<script>
  AgenticKB.init({
    apiUrl: "https://your-api-host",     // the service from mode B
    apiKey: "same value as API_KEY",     // omit if API_KEY auth is off
    assistantName: "Data Assistant",
    theme: "auto",                       // dark | light | auto
    position: "bottom-right",
    showSources: true,
    showExecutionSteps: true,
    enableStreaming: true,
    suggestedPrompts: ["How many orders this month?", "Top 5 customers by revenue"],
    userId: "42",                        // optional, forwarded for row-level security
    tenantId: "acme"                     // optional
  });
</script>
```

**React app:**

```bash
npm install ./path/to/agentic-ai-kb-sdk/frontend/react-widget
```

```tsx
import { AgenticChatbot } from "@agentic-kb/react";
import "@agentic-kb/react/style.css";

<AgenticChatbot apiUrl="https://your-api-host" apiKey={key} isFloating />
```

> Don't ship a secret `API_KEY` to public browsers. For public sites, put your own backend/proxy in front
> that adds the key, and point `apiUrl` at that.

---

## Quick local test (5 minutes)

```bash
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[postgres,llm,api]" google-generativeai
cp .env.example .env                                  # fill in keys + DB creds
agentic-kb check -c configs/example.yaml              # expect status "ok"
agentic-kb serve -c configs/example.yaml              # http://localhost:8000/docs
```

Then try the widget: build it (section C), run `python -m http.server 8080` in the repo root and open
`http://localhost:8080/examples/widget_demo.html`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `column "carno" does not exist` | Fixed in this SDK (auto-quoting). Make sure the table is in `allowed_tables` so its schema is known |
| "rate limit" / "usage quota reached" | Provider limit. Wait, switch `model:`, switch provider, or use a billed key |
| `Unknown dialect 'postgresql'` | Old version — update the SDK |
| 400 `SQL Validation Failed` | The model produced a non-SELECT or a disallowed table; rephrase or widen `allowed_tables` |
| `The 'mysql' driver is not installed` | `pip install agentic-kb[mysql]` (same for `sqlserver`, `mongodb`) |
| MySQL: `Unknown table 'orders'` | Use `database.table` names (`shop.orders`); in MySQL the schema *is* the database |
| SQL Server: `Incorrect syntax near 'user'` | Reserved-word table; the SDK brackets it automatically, so make sure the table is in `allowed_tables` |
| `password authentication failed` | `.env` DB creds point at a different Postgres than you expect (check which one listens on 5432) |
| Gemini / Redis `ImportError` | `pip install google-generativeai` / `pip install redis` |
| Widget shows no live steps | Rebuild it (`npm run build`) — old bundles can't read the stream |
| 401 Invalid API key | `API_KEY` is set on the server; send `X-API-Key` |
| Wrong filter values (e.g. `'Active'` vs `'ACTIVE'`) or missed joins | Run `agentic-kb catalog generate` and review the file (section 4) |
| First answer is slow | Each question makes ~3 LLM calls; use a faster model (e.g. `gemini-3.5-flash`, Groq) |
