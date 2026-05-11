# Technical Guide

Detailed guide for technical implementation aspects.

## Tech Stack

| Category | Technology | Version |
|----------|------------|---------|
| Language | Python | >= 3.14 |
| Package Manager | uv | latest |
| LLM Framework | LangChain | >= 0.3 |
| Agent Framework | LangGraph | >= 0.2 |
| LLM | Mistral AI | mistral-large-latest |
| Embeddings | Mistral AI | mistral-embed (1024 dims) |
| Vector Store | PostgreSQL + pgvector | HNSW cosine |
| ORM | SQLAlchemy (async) | >= 2.0 |
| Migrations | Alembic | >= 1.13 |
| API | FastAPI | >= 0.115 |
| RAG Evaluation | Ragas | >= 0.4.3 |
| Git Hooks | pre-commit | >= 3.0 |
| Markdown Lint | pymarkdownlnt | >= 0.9 |
| Release | python-semantic-release | >= 10.0 |

---

## Architecture

### Ingestion Pipeline

```text
PDF File
    │
    ▼
[SHA-256 Hash] ──► Dedup check (UNIQUE file_hash)
    │ (new document only)
    ▼
[PDF Loader] ──► pypdf → list[str] per page
    │
    ▼
[Chunker] ──► RecursiveCharacterTextSplitter (512 tokens / 64 overlap)
    │
    ▼
[Embeddings] ──► MistralAIEmbeddings (mistral-embed, 1024 dims)
    │
    ▼
[Store] ──► documents + document_chunks (PostgreSQL + pgvector)
```

### LangGraph Agent

```text
START → load_history → guard_route ──[out_of_scope]──────────────────────────────────────────────► save_turn → END
                                   ──[needs_retrieval=True]──► retrieve ──► generate → evaluate ──► save_turn → END
                                   ──[needs_retrieval=False]──────────────► generate → evaluate ──► save_turn → END
                                                                                       │
                                                                      [rewrite] ◄──────┤ (max AGENT_MAX_RETRIES)
                                                                          │            │
                                                                          └──► retrieve [escalate] ──► escalate → save_turn → END
```

- **`load_history`** — fetches past messages from DB into LangChain message objects
- **`guard_route`** — single LLM call (`mistral-small-latest`, JSON) that decides scope and retrieval simultaneously:
  - out-of-scope → sets rejection answer, short-circuits to `save_turn`
  - in-scope + retrieval needed → continues to `retrieve`
  - in-scope + no retrieval needed → continues to `generate`
- **`retrieve`** — cosine similarity search via pgvector `<=>` operator; uses `rewrite_suggestion` as query on retry
- **`generate`** — calls Mistral (`mistral-large-latest`) with context
- **`evaluate`** — single LLM call (`mistral-small-latest`, JSON) scoring the answer 0–10:
  - score ≥ 7 → `answer`: send to user
  - score 4–6 → `rewrite`: retry retrieval with reformulated query (up to `AGENT_MAX_RETRIES`)
  - score < 4 → `escalate`: hand off to human support
- **`escalate`** — sets a human-escalation answer when the evaluator cannot find a satisfactory response
- **`save_turn`** — persists user + assistant messages to DB

### RAG Query Flow

```text
User Message
    │
    ▼
[load_history] ──► Conversation DB
    │
    ▼
[guard_route] ──► Mistral small (in scope? needs KB?)
    │
    ├── Out of scope ──────────────────────────────────────────────────────────────────────┐
    │                                                                                       │
    ├── In scope, no retrieval ──────────────────────────────────────────────────────────┐ │
    │                                                                                     │ │
    └── In scope, retrieval ──► [retrieve] ──► pgvector cosine search                   │ │
                                    │                                                     │ │
                                    ▼                                                     │ │
                              [generate] ◄────────────────────────────────────────────────┘ │
                                    │                                                        │
                                    ▼                                                        │
                              [evaluate] ──► Mistral small (score 0–10)                     │
                                    │                                                        │
                                    ├── score ≥ 7 ──► [save_turn] ◄──────────────────────────┘
                                    │                      │
                                    ├── score 4–6 ──► [retrieve] (rewrite, max retries)
                                    │
                                    └── score < 4 ──► [escalate] ──► [save_turn]
                                                            │
                                                            ▼
                                                   Response + sources
```

---

## Database

### Schema

All tables live in the **`rag`** PostgreSQL schema (not `public`).
This is enforced at three levels:

- `init.sql` — creates the schema and sets it as the default `search_path`
- `settings.py` — `postgres_schema = "rag"` (overridable via `POSTGRES_SCHEMA`)
- `db/base.py` — `MetaData(schema=settings.postgres_schema)` applied to all models

**Migration 0001 — documents**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE rag.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,  -- SHA-256, idempotent dedup
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE rag.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(1024),
    chunk_index INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX document_chunks_embedding_idx
    ON rag.document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Migration 0002 — conversations**

```sql
CREATE TABLE rag.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE rag.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Alembic Migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"

# Rollback one step
alembic downgrade -1
```

### Connection

Configure via environment variables (see [Environment Variables](#environment-variables)).
`database_url` is built automatically from `POSTGRES_*` vars:

```
postgresql+asyncpg://user:password@host:port/dbname
```

The active schema is set via `POSTGRES_SCHEMA` (default `rag`) and applied
to all SQLAlchemy models through `MetaData(schema=...)`. Alembic migrations also
target this schema.

---

## API Reference

Base path: `/api/v1`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/documents/ingest` | Upload PDF (multipart), returns `{document_id, chunks_created, already_existed}` |
| `GET` | `/documents` | List ingested documents |
| `DELETE` | `/documents/{id}` | Delete document and all its chunks |
| `POST` | `/conversations` | Create a new conversation |
| `POST` | `/conversations/{id}/messages` | Send a message, returns answer + sources + trace_id |
| `GET` | `/conversations/{id}/messages` | Full conversation history |
| `POST` | `/eval/run` | Trigger a Ragas evaluation |

---

## Evaluation

Ragas metrics, triggered either via `POST /api/v1/eval/run` or via the standalone
`rag.cli.eval` entry point (see [CLI](#cli) below):

- **Faithfulness** — answer is grounded in retrieved context
- **Answer Relevancy** — answer addresses the question
- **Context Recall** — retrieved context covers the ground truth

---

## CLI

Standalone entry points under `src/rag/cli/`. They share a lazy async DB
session helper (`cli/_runner.py`) and run **without booting FastAPI**, making
them suitable for cron jobs, CI, or local one-off runs.

### `rag.cli.ingest`

```bash
uv run python -m rag.cli.ingest [--docs-dir PATH]
```

- Default `--docs-dir`: `data/docs/`
- Reuses `rag/ingestion/pipeline.ingest_pdf` (idempotent via SHA-256)
- Per-file logging: `[OK]`, `[SKIP]`, `[ERROR]`
- Always exits `0` (errors are logged, never fatal)

### `rag.cli.eval`

```bash
uv run python -m rag.cli.eval [--samples PATH]
```

- Default `--samples`: `data/evaluation/samples.json`
- Reuses `evaluation/ragas_pipeline.run_evaluation`
- Prints `faithfulness`, `answer_relevancy`, `context_recall` scores to stdout

| Exit code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | `samples.json` missing or empty |
| `2` | DB / LLM / runtime error |

### Cron Example

```cron
# Daily ingestion at 02:00
0 2 * * * cd /app && uv run python -m rag.cli.ingest >> /var/log/dsd-ingest.log 2>&1

# Weekly evaluation on Monday at 03:00
0 3 * * 1 cd /app && uv run python -m rag.cli.eval >> /var/log/dsd-eval.log 2>&1
```

---

## Docker Setup

The project ships a full Docker stack: PostgreSQL (pgvector), the FastAPI API,
and the Streamlit frontend. Two compose files cover the dev/prod split:

| File | Role |
|------|------|
| `docker-compose.yml` | Base + **dev**: source bind mounts, hot reload (`uvicorn --reload`, `streamlit --server.runOnSave`), all ports exposed on `localhost`. |
| `docker-compose.prod.yml` | **Prod overlay**: multi-worker API, no source mounts, PostgreSQL port hidden from the host, `restart: always`. |

Each application has a multi-stage `Dockerfile` with two targets:

- `dev` — full deps (including dev tools), uvicorn `--reload` / Streamlit `runOnSave`.
- `prod` — only runtime deps, source baked into the image, multi-worker uvicorn,
  Streamlit `--server.headless=true`. For the API, a slim runtime stage copies
  `/opt/venv` from a `prod-builder` stage so the final image carries no compilers.

### Services

| Service | Image / Build | Ports (dev) | Notes |
|---------|---------------|-------------|-------|
| `postgres` | `pgvector/pgvector:pg16` | `5432:5432` | Healthcheck via `pg_isready`. `init.sql` mounted into `/docker-entrypoint-initdb.d/`. |
| `api` | `./api` (target `dev`/`prod`) | `8000:8000` | `depends_on: postgres healthy`. Entrypoint runs `alembic upgrade head` then `exec "$@"`. Healthcheck on `/api/v1/health`. |
| `frontend` | `./frontend` (target `dev`/`prod`) | `8501:8501` | `depends_on: api healthy`. Calls API via `RAG_API_URL=http://api:8000`. |

### Configuration

- The API reads `api/.env` via `env_file:` (loads `MISTRAL_API_KEY` and Postgres
  credentials).
- The compose file overrides `POSTGRES_HOST=postgres` and
  `POSTGRES_PORT=5432` so the API targets the postgres service inside the
  network rather than `localhost`.
- The frontend receives `RAG_API_URL=http://api:8000` directly from the compose
  `environment:` block.

### Volumes

| Volume | Purpose |
|--------|---------|
| `pgdata` | PostgreSQL data directory (persistent across `docker compose down`). |
| `api_data_docs` | Ingestion drop zone (`/app/data/docs`). |
| `api_data_eval` | Evaluation samples (`/app/data/evaluation`). |

`docker compose down -v` drops all three volumes and forces `init.sql` to
re-run on the next boot.

### Common Commands

```bash
# Dev
docker compose up -d                                                   # start
docker compose logs -f api                                             # tail API logs
docker compose exec api uv run pytest                                  # run tests in-container
docker compose exec postgres psql -U rag_user -d rag                   # psql shell
docker compose down                                                    # stop (keep data)

# Prod
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Full reset (drops DB)
docker compose down -v
```

### Secrets

In dev, `MISTRAL_API_KEY` lives in the gitignored `api/.env`. In a real
deployment, inject it via your platform's secret manager (Docker Swarm
secrets, Kubernetes Secrets, AWS SSM…) rather than baking it into the image
or committing it to git.

---

## CI/CD

### Lint Workflow

The project runs linting on every push and PR to `develop` and `main`:

```yaml
# .github/workflows/lint.yml
name: Lint

on:
  push:
    branches: [develop, main]
  pull_request:
    branches: [develop, main]
```

---

## Git Hooks

Managed by **pre-commit** (`.pre-commit-config.yaml`). Install once with:

```bash
pre-commit install
```

### Pre-commit Hook

Runs automatically on staged files before each commit:

- `pymarkdownlnt scan` — lint staged `.md` files
- `yamllint` — lint staged `.yml`/`.yaml` files

## Dependency Management

### Python (uv)

```bash
uv add <package>          # Add a runtime dependency
uv add --dev <package>    # Add a dev dependency
uv sync                   # Install all dependencies
uv lock                   # Update lock file
```

### Dev Tools (uv)

```bash
uv sync --extra dev       # Install all dev tools
```

### Renovate

Renovate is configured to:

- Group minor and patch updates
- Auto-merge patches for devDependencies
- Run updates on Monday morning (Europe/Paris timezone)

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MISTRAL_API_KEY` | Mistral AI API key | — |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | Database name | `rag` |
| `POSTGRES_USER` | Database user | — |
| `POSTGRES_PASSWORD` | Database password | — |
| `POSTGRES_SCHEMA` | PostgreSQL schema | `rag` |
| `APP_ENV` | Environment name | `development` |
| `APP_LOG_LEVEL` | Log level | `INFO` |
| `APP_PORT` | Server port | `8000` |
| `CHUNK_SIZE` | Text chunk size (tokens) | `512` |
| `CHUNK_OVERLAP` | Chunk overlap (tokens) | `64` |
| `RETRIEVAL_TOP_K` | Number of chunks retrieved | `5` |
| `WEB_MAX_PAGES` | Max pages crawled per URL | `100` |
| `PRODUCT_NAME` | Product name used in agent prompts | `Altair` |
| `AGENT_MAX_RETRIES` | Max evaluate→rewrite cycles before escalation | `2` |

---

## Available Scripts

```bash
# Python
uv sync                   # Install/sync dependencies
uv run python main.py     # Run the application
uv run pytest             # Run tests
uv run pytest tests/unit  # Unit tests only
uv run pytest tests/integration  # Integration tests only

# Standalone CLI entry points (no FastAPI required)
uv run python -m rag.cli.ingest                  # Ingest PDFs from data/docs/
uv run python -m rag.cli.eval                    # Run Ragas eval on data/evaluation/samples.json

# Migrations
alembic upgrade head      # Apply all migrations

# Dev tooling
uv sync --extra dev                        # Install dev tools
uv run pymarkdownlnt scan --recurse .      # Lint all markdown
uv run pymarkdownlnt fix --recurse .       # Auto-fix markdown
uv run yamllint .                          # Lint YAML files
pre-commit install                         # Set up git hooks
git commit                                 # Create a commit
```

---

## Development Workflow

### Daily Process

1. **Pull** - `git pull origin develop`
2. **Branch** - `git checkout -b feat/description`
3. **Develop** - Make changes following conventions
4. **Test** - `uv run pytest`
5. **Lint** - `uv run pymarkdownlnt scan --recurse . && uv run yamllint .`
6. **Commit** - `git commit -m "feat: ..."` (Conventional Commits)
7. **Push** - `git push origin feat/description`
8. **PR** - Create pull request to `develop`

### Pre-commit Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run pymarkdownlnt scan --recurse .` passes
- [ ] `uv run yamllint .` passes
- [ ] Documentation updated if needed
- [ ] Commit uses Conventional Commits format
- [ ] No sensitive data committed (API keys, passwords)

---

*Last updated: 2026-05-05 — added CLI section (`rag.cli.ingest`, `rag.cli.eval`).*
