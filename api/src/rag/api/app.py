from contextlib import asynccontextmanager

from fastapi import FastAPI

from rag.api.routers import chat, eval, health, ingestion
from rag.db.session import engine
from rag.observability import RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Simplon RAG Sample API",
        description="Sample RAG support chatbot API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # -----------------------------------------------------------------------
    # Middleware — ordre important : RequestIdMiddleware en premier pour que
    # le request_id soit disponible dans tous les middlewares suivants.
    # -----------------------------------------------------------------------
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(ingestion.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(eval.router, prefix="/api/v1")

    return app