"""
Observabilité — Logging structuré JSON + propagation du request_id
                + instrumentation métriques RED dans le middleware.

Responsabilités :
- setup_logging()       : configure python-json-logger sur le root logger
- RequestIdFilter       : injecte le request_id courant dans chaque LogRecord
- RequestIdMiddleware   : génère un UUID v4 par requête HTTP, le stocke dans
                          le ContextVar, expose X-Request-Id dans la réponse,
                          et enregistre les métriques RED Prometheus.

RGPD : aucun champ de contenu conversationnel (user_message, answer, chunks)
       ne doit transiter par le logger.
"""

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from rag.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    normalize_endpoint,
)

# ---------------------------------------------------------------------------
# ContextVar — partagé entre le middleware et tous les modules
# ---------------------------------------------------------------------------

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


# ---------------------------------------------------------------------------
# Filtre logging
# ---------------------------------------------------------------------------

class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True


# ---------------------------------------------------------------------------
# Configuration du root logger
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO") -> None:
    """Initialise le logging JSON structuré pour toute l'application."""
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
    root.handlers.clear()
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        if not any(isinstance(f, RequestIdFilter) for f in uv_logger.filters):
            uv_logger.addFilter(RequestIdFilter())


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Génère un request_id par requête, propage dans les logs et les métriques.

    Instrumentation RED :
    - http_requests_total{method, endpoint, status_code} — incrémenté à chaque fin
    - http_request_duration_seconds{method, endpoint} — observé à chaque fin

    Le healthcheck est instrumenté mais son request_id n'est pas loggué pour
    réduire le bruit (volume élevé, latence quasi-nulle).
    """

    SILENT_PATHS = {"/api/v1/health", "/metrics"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        req_id = str(uuid.uuid4())
        token = request_id_var.set(req_id)

        endpoint = normalize_endpoint(request.url.path)
        method = request.method
        silent = request.url.path in self.SILENT_PATHS

        logger = logging.getLogger(__name__)

        if not silent:
            logger.info(
                "request.start",
                extra={"http_method": method, "http_path": request.url.path},
            )

        t0 = time.perf_counter()

        try:
            response = await call_next(request)

            duration = time.perf_counter() - t0
            status = str(response.status_code)

            # --- Métriques RED ---
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code=status
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            response.headers["X-Request-Id"] = req_id

            if not silent:
                logger.info(
                    "request.end",
                    extra={
                        "http_method": method,
                        "http_path": request.url.path,
                        "http_status": response.status_code,
                        "duration_ms": round(duration * 1000, 2),
                    },
                )

            return response

        except Exception:
            duration = time.perf_counter() - t0
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code="500"
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            logger.exception(
                "request.unhandled_exception",
                extra={"http_method": method, "http_path": request.url.path},
            )
            raise

        finally:
            request_id_var.reset(token)