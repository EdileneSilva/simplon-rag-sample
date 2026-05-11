# AI Agents Guide

Complete guide for AI assistants working on this repository.

## Documentation Index

| File | Purpose | Description |
|------|---------|-------------|
| [`AGENTS.md`](./AGENTS.md) | AI Guide | This file - conventions and rules for AI agents |
| [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) | Architecture | Directory and file organization |
| [`CONVENTIONS.md`](./CONVENTIONS.md) | Code style | Naming conventions, code style, git |
| [`TECHNICAL_GUIDE.md`](./TECHNICAL_GUIDE.md) | Implementation | Stack, CI/CD, performance, tests |
| [`FEATURES.md`](./FEATURES.md) | Features | Epics, user stories, feature status |
| [`TASKS.md`](./TASKS.md) | Tasks | Task tracking and backlog |

---

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python >= 3.14 |
| Package Manager | uv |
| LLM Framework | LangChain + LangGraph |
| LLM | Mistral AI (mistral-large-latest) |
| Embeddings | Mistral AI (mistral-embed, 1024 dims) |
| Vector Store | PostgreSQL + pgvector (HNSW cosine) |
| ORM | SQLAlchemy async (asyncpg driver) |
| Migrations | Alembic |
| API | FastAPI + uvicorn |
| RAG Evaluation | Ragas |
| Git Hooks | pre-commit |
| Commit Convention | Conventional Commits |
| Linting | pymarkdownlnt, yamllint |
| CI/CD | GitHub Actions |

### Available Commands

```bash
# Full stack via Docker (from repo root)
docker compose up -d                                  # dev: hot reload, sources mounted
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
                                                      # prod: multi-worker, no source mount
docker compose logs -f <service>                      # tail logs (api, frontend, postgres)
docker compose exec api alembic upgrade head          # run a migration in-container
docker compose down                                   # stop (preserve pgdata)
docker compose down -v                                # stop + reset DB volume

# API (FastAPI) — local install, from api/
cd api
uv sync                       # Install/sync API dependencies
uv sync --extra dev           # Install with dev tools
uv run python main.py         # Run the API
uv run pytest                 # Run API tests
uv add <package>              # Add a dependency

# Standalone CLI entry points (no FastAPI required) — from api/
uv run python -m rag.cli.ingest   # Ingest PDFs from ../data/docs/
uv run python -m rag.cli.eval     # Run Ragas eval on ../data/evaluation/samples.json

# Frontend (Streamlit) — from frontend/
cd frontend
uv sync
uv run streamlit run src/app/app.py

# Linting (from repo root)
uv run pymarkdownlnt scan --recurse .  # Lint markdown
uv run pymarkdownlnt fix --recurse .   # Auto-fix markdown
uv run yamllint .                      # Lint YAML

# Git hooks
pre-commit install    # Install pre-commit and commit-msg hooks
```

---

## File Summaries

### PROJECT_STRUCTURE.md

Python project structure. Key points:

- Source: `src/rag/` (config, db, api, cli, observability, evaluation)
  and `src/rag/rag/` (agent, embeddings, ingestion, retriever)
- Migrations: `data/alembic/versions/`
- DB init scripts: `data/db/init/init.sql`
- Root: `pyproject.toml`, `uv.lock`, `main.py`, `CLAUDE.md`, `README.md`
- `rag_eval/`: RAG evaluation playground (do not modify)

### CONVENTIONS.md

Development conventions. Key points:

- **Naming**: files snake_case, classes PascalCase, functions snake_case, constants UPPER_SNAKE_CASE
- **Git branches**: feature/fix/refactor/docs
- **Commits**: Conventional Commits convention

### TECHNICAL_GUIDE.md

Technical implementation guide. Key points:

- **Stack**: Python, uv, LangChain, LangGraph, PostgreSQL/pgvector, Mistral, FastAPI, Alembic
- **API**: 8 endpoints under `/api/v1` (health, documents, conversations, eval)
- **LangGraph**: `load_history → route → [retrieve] → generate → save_turn`
- **CI/CD**: GitHub Actions workflows (lint on push/PR)
- **Pre-commit**: runs pymarkdownlnt and yamllint automatically

### FEATURES.md

Feature management. Key points:

- All 4 epics implemented (Document Ingestion, RAG Pipeline, Support Chatbot, RAG Evaluation)
- Technical features table with implementation status
- API endpoint index by epic

### TASKS.md

Project tracking. Key points:

- Current sprint, Backlog, Completed
- Markdown checklist format

---

## AI Agent Specific Rules

### Language Rule

**All written content must be in English**, regardless of the user's prompt language:

- Documentation (markdown files, comments)
- Commit messages
- Tasks and subtasks
- Epics and user stories
- Code comments and docstrings
- Variable and function names
- Error messages and logs

### Commit Convention

This project uses **Conventional Commits**:

`<type>(scope): <description>`

Examples:

- `feat: Add document ingestion pipeline`
- `fix(retriever): Fix pgvector connection timeout`
- `docs: Update README`

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

### Fundamental Principles

1. **Read before modifying** - Always read a file before proposing changes
2. **Consult documentation** - Check relevant docs/ files before any task
3. **Respect existing patterns** - Follow the style and conventions already in place
4. **Minimize changes** - Only modify what is necessary
5. **Document changes** - Update docs if behavior changes

### Code Generation Preferences

| Language | Preferences |
|----------|-------------|
| **Python** | Type hints, dataclasses, explicit error handling, no `Any` unless justified |
| **Markdown** | Follow markdownlint rules, no trailing spaces |
| **YAML** | Follow yamllint rules, consistent indentation |

### Pre-commit Checklist

- [ ] Code passes linting (`uv run pymarkdownlnt scan --recurse .` and `uv run yamllint .`)
- [ ] Python type hints present on new functions
- [ ] Documentation updated if necessary
- [ ] Commit uses Conventional Commits format
- [ ] No secrets or sensitive data (API keys, DB passwords)

### Behaviors to Avoid

- Do not create unnecessary files
- Do not add dependencies without justification
- Do not modify project structure without discussion
- Do not ignore linting errors
- Do not comment out dead code, delete it
- Do not hardcode API keys or credentials

### Priorities

1. **Functionality** - Code must work correctly
2. **Readability** - Code must be understandable
3. **Consistency** - Follow existing patterns
4. **Simplicity** - Avoid over-engineering

---

*Last updated: 2026-05-05 — added `src/rag/cli/` standalone entry points (`ingest`, `eval`).*
