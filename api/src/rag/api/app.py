from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

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
    # Middleware — RequestIdMiddleware en premier pour que le request_id
    # soit disponible dans tous les middlewares suivants ET dans les métriques.
    # -----------------------------------------------------------------------
    app.add_middleware(RequestIdMiddleware)

    # -----------------------------------------------------------------------
    # Endpoint /metrics — scrappé par Prometheus toutes les 15 s.
    # Exposé hors du préfixe /api/v1 intentionnellement : c'est une interface
    # d'infrastructure, pas une API métier.
    # -----------------------------------------------------------------------
    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(ingestion.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(eval.router, prefix="/api/v1")

    return app