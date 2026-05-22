# Simplon RAG Sample

<!-- markdownlint-disable -->
<p align="center">
  <strong>Sample RAG support chatbot — powered by RAG, LangChain, and local Ollama models</strong>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" />
  </a>
  <a href="https://python-semantic-release.readthedocs.io/">
    <img src="https://img.shields.io/badge/semantic--release-python-e10079?logo=semantic-release" alt="semantic-release: python" />
  </a>
</p>
<!-- markdownlint-restore -->

---

Intelligent support chatbot example, built on a Retrieval-Augmented Generation (RAG) architecture
using LangChain, LangGraph, PostgreSQL/pgvector for vector storage, and local Ollama models for
both embeddings and LLM inference.

## Features

- **Document Ingestion** - PDF upload with SHA-256 deduplication, chunking, and embedding
- **RAG Pipeline** - Semantic retrieval via pgvector cosine similarity + LLM generation
- **LangGraph Agent** - Stateful multi-step graph: routing, retrieval, generation, history
- **Local Ollama** - `mxbai-embed-large` (1024 dims) for embeddings, `mistral-small3.2` for
  generation and `mistral:latest` for fast guard/eval calls
- **PostgreSQL + pgvector** - HNSW index for fast approximate nearest-neighbour search
- **FastAPI REST API** - 8 endpoints under `/api/v1` for ingestion, chat, and evaluation
- **Ragas Evaluation** - Faithfulness, answer relevancy, and context recall metrics

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python >= 3.14 |
| Package Manager | uv |
| LLM Framework | LangChain + LangGraph |
| LLM / Embeddings | Ollama (local) |
| Vector Store | PostgreSQL + pgvector |
| ORM / Migrations | SQLAlchemy (async) + Alembic |
| API | FastAPI + uvicorn |
| RAG Evaluation | Ragas |

## Quickstart with Docker

The fastest way to spin up the full stack (PostgreSQL + API + Streamlit UI):

```bash
# 1. Start Ollama on the host and pull the required models (one-time)
ollama serve &
ollama pull mistral-small3.2
ollama pull mistral:latest
ollama pull mxbai-embed-large

# 2. Configure the environment
cp api/.env.example api/.env
# Edit api/.env if you want to point at a non-default Ollama host or use different models

# 3. Start the stack in development mode (hot reload, source bind mounts)
docker compose up -d

# 3. Open the UI
open http://localhost:8501       # Streamlit chat
# API docs:    http://localhost:8000/docs
# API health:  http://localhost:8000/api/v1/health

# 4. Tear down
docker compose down              # keep data
docker compose down -v           # also drop the postgres volume
```

For a production-like build (multi-worker uvicorn, no source mounts, postgres
port hidden from the host):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Local installation (without Docker)

```bash
# Copy and configure environment
cp api/.env.example api/.env
# Edit api/.env with your DB connection and (optionally) Ollama host/models
# Make sure Ollama is running locally: `ollama serve`
# And the models are pulled:
#   ollama pull mistral-small3.2 && ollama pull mistral:latest && ollama pull mxbai-embed-large

# Install API dependencies
cd api
uv sync --extra dev          # dev tools included

# Apply database migrations (requires a running PostgreSQL with pgvector)
uv run alembic upgrade head
cd ..

# Install frontend dependencies
cd frontend
uv sync
cd ..

# Install git hooks
pre-commit install
```

## Usage (local)

```bash
# Run API (from api/)
cd api && uv run python main.py
# API available at http://localhost:8000/api/v1

# Run the Streamlit chat UI (from frontend/)
cd frontend && uv run streamlit run src/app/app.py
# UI available at http://localhost:8501
```

### CLI Tools

Standalone entry points for ingestion and evaluation, runnable without the API
(useful for cron, CI, or one-off scripts). Run from `api/`.

```bash
cd api

# Ingest every PDF in data/docs/ (idempotent via SHA-256)
uv run python -m rag.cli.ingest
uv run python -m rag.cli.ingest --docs-dir path/to/pdfs

# Run Ragas evaluation against data/evaluation/samples.json
uv run python -m rag.cli.eval
uv run python -m rag.cli.eval --samples path/to/samples.json
```

## Development

```bash
# Run API tests (from api/)
cd api && uv run pytest

# Lint all files (from repo root)
uv run pymarkdownlnt scan --recurse .
uv run yamllint .

# Commit (Conventional Commits format)
git commit -m "feat: ..."
```


# GCP Deployment — Simplon RAG Sample

## GCP Services Used

| Service | Role |
|---|---|
| **Artifact Registry** | Stores versioned Docker images for the API and frontend, tagged by commit SHA to ensure full deployment traceability. |
| **Cloud Run** | Runs the API (FastAPI) and Frontend (Streamlit) containers in managed serverless mode, with automatic scaling to zero when idle. |
| **Cloud SQL (PostgreSQL 16)** | Hosts the relational and vector database (pgvector extension) used to store conversations and corpus embeddings. |
| **Cloud Storage (GCS)** | Stores the document corpus (PDFs) used for RAG ingestion, decoupled from Docker images so documents can be updated without redeployment. |
| **Secret Manager** | Securely manages application secrets (Mistral API key, DB password, JWT key); values are injected into Cloud Run at container startup and never appear in plain text in the config. |
| **IAM** | Controls access rights between GCP services following the principle of least privilege, via a dedicated service account for the Cloud Run runtime. |
| **Cloud Logging** | Centralizes and indexes structured JSON logs emitted by the API and frontend, searchable by `request_id`, `severity`, and Cloud Run labels. |

---

## IAM Roles — Service Account `simplon-rag-cloudrun`

The service account `simplon-rag-cloudrun@simplon-rag-263.iam.gserviceaccount.com` is used by both Cloud Run services (API and Frontend).

| Role | Scope | Justification |
|---|---|---|
| `roles/artifactregistry.writer` | Project | Allows pushing built Docker images to Artifact Registry. **Why not `artifactregistry.admin`?** That role would allow deleting entire repositories — the runtime only needs to write images, never to administrate the registry. |
| `roles/cloudsql.client` | Project | Allows the Cloud SQL Auth Proxy embedded in Cloud Run to authenticate against the PostgreSQL instance. Without this role, the connection is refused at the network level before even attempting the password. **Why not `cloudsql.admin`?** That role would allow creating and deleting instances and databases — unnecessary and dangerous for an application runtime. |
| `roles/logging.logWriter` | Project | Allows writing structured JSON logs to Cloud Logging. Without this role, container stdout logs do not appear in the GCP console. **Why not `logging.admin`?** The runtime only needs to write logs, not read, export, or modify log sinks. |
| `roles/storage.objectViewer` | Bucket `simplon-rag-263` | Allows reading PDF files from the corpus for ingestion and RAG responses. Bound to the bucket only, not the project. **Why not `storage.objectAdmin`?** That role would allow deleting objects and modifying bucket ACLs — the runtime never needs that. |
| `roles/storage.objectCreator` | Bucket `simplon-rag-263` | Allows writing new documents uploaded via the API ingestion endpoint. **Why not `storage.objectAdmin`?** Same reason: the runtime writes but never deletes; deletion is a separate administrative operation. |
| `roles/secretmanager.secretAccessor` | Per secret individually | Allows reading secret values at container startup (DB password, Mistral API key, JWT key). Bound per secret, not at the project level. **Why not at the project level?** A project-level binding would grant access to all GCP secrets in the project, including those of other potential services. |

> The roles `artifactregistry.serviceAgent`, `containerregistry.ServiceAgent`, `pubsub.serviceAgent`, and `run.serviceAgent` are service accounts managed automatically by GCP and are not assigned manually.

---

## Cloud Run Revision Rollback Procedure

Cloud Run retains all deployed revisions. A rollback means redirecting 100% of traffic to a previous revision — no image rebuild required, completed in under 30 seconds.

### 1. Identify the target revision

```bash
gcloud run revisions list \
  --service=simplon-rag-api \
  --region=europe-west1 \
  --project=simplon-rag-263
```

The output lists all revisions with their date, current traffic percentage, and status (`ACTIVE` / `FAILED`).

### 2. Switch traffic

```bash
gcloud run services update-traffic simplon-rag-api \
  --region=europe-west1 \
  --to-revisions=simplon-rag-api-00002-xyz=100 \
  --project=simplon-rag-263
```

Replace `simplon-rag-api-00002-xyz` with the revision name identified in the previous step.

### 3. Verify

```bash
# Confirm traffic has been switched
gcloud run services describe simplon-rag-api \
  --region=europe-west1 \
  --project=simplon-rag-263 \
  --format="value(status.traffic)"

# Check logs in real time
gcloud beta run services logs tail simplon-rag-api \
  --region=europe-west1 \
  --project=simplon-rag-263
```

### Key points

- The rollback **does not require rebuilding the image** — Cloud Run reuses the image from the target revision already present in Artifact Registry.
- If startup fails due to a missing environment variable, the revision enters a `FAILED` state and Cloud Run sends it no traffic — the previous revision continues serving requests until the rollback is complete.
- For the **frontend**, use the same procedure replacing `simplon-rag-api` with `simplon-rag-frontend`.

## Documentation

| File | Description |
|------|-------------|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution guidelines |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |

## License

MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Maxime Lenne**
