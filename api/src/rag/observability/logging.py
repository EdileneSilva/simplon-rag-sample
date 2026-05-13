"""
Observability — Logging structuré JSON + propagation du request_id.

Responsabilités :
- setup_logging()       : configure python-json-logger sur le root logger
- RequestIdFilter       : injecte le request_id courant dans chaque LogRecord
- RequestIdMiddleware   : génère un UUID v4 par requête HTTP et le stocke dans
                          le ContextVar, puis l'expose dans l'en-tête X-Request-Id

RGPD : aucun champ de contenu conversationnel (user_message, answer, chunks)
       ne doit transiter par le logger. Seuls des champs structurés non-nominatifs
       (request_id, conversation_id, latency_ms, décisions catégorielles) sont
       autorisés.
"""

import logging
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# ContextVar — partagé entre le middleware et tous les modules de l'application
# ---------------------------------------------------------------------------

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


# ---------------------------------------------------------------------------
# Filtre logging — injecte le request_id dans chaque LogRecord
# ---------------------------------------------------------------------------

class RequestIdFilter(logging.Filter):
    """Ajoute le champ ``request_id`` à chaque enregistrement de log.

    Le filtre est attaché au StreamHandler ; il lit le ContextVar à l'instant
    de l'émission du log, ce qui garantit la propagation correcte dans un
    contexte asyncio (chaque tâche hérite d'une copie du contexte).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True


# ---------------------------------------------------------------------------
# Configuration du root logger
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO") -> None:
    """Initialise le logging JSON structuré pour toute l'application.

    À appeler une seule fois, au démarrage du processus (avant la création
    de l'app FastAPI), pour que tous les loggers héritent de la configuration.

    Format JSON produit (exemple) :
        {
          "timestamp": "2025-05-13T08:42:01.123456",
          "level": "INFO",
          "logger": "rag.rag.agent.nodes",
          "message": "guard_route.decision",
          "request_id": "550e8400-e29b-41d4-a716-446655440000",
          "conversation_id": "3fa85f64-...",
          "in_scope": true,
          "category": "admission",
          "latency_ms": 342.7
        }
    """
    handler = logging.StreamHandler()

    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
        },
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.setLevel(level)
    # Supprimer les handlers existants (par ex. le handler par défaut de Python
    # ou ceux ajoutés par uvicorn lors d'un rechargement).
    root.handlers.clear()
    root.addHandler(handler)

    # Propager le filtre request_id aux loggers uvicorn déjà créés
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        # Ne pas ajouter de doublon
        if not any(isinstance(f, RequestIdFilter) for f in uv_logger.filters):
            uv_logger.addFilter(RequestIdFilter())


# ---------------------------------------------------------------------------
# Middleware FastAPI/Starlette
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Génère un UUID v4 pour chaque requête HTTP entrante.

    - Stocke le request_id dans ``request_id_var`` (ContextVar asyncio).
    - Expose le request_id dans l'en-tête de réponse ``X-Request-Id``.
    - Réinitialise le ContextVar après la réponse (reset du token Starlette).

    Note : BaseHTTPMiddleware crée une sous-tâche asyncio par requête, qui
    hérite automatiquement du contexte parent. Le reset via token garantit
    qu'aucune fuite de request_id ne se produit entre requêtes.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        req_id = str(uuid.uuid4())
        token = request_id_var.set(req_id)

        logger = logging.getLogger(__name__)
        logger.info(
            "request.start",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
            },
        )

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request.unhandled_exception",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                },
            )
            raise
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-Id"] = req_id
        logger.info(
            "request.end",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
            },
        )
        return response