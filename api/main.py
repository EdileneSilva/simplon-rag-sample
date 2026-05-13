import uvicorn

from rag.config.settings import get_settings
from rag.observability import setup_logging

# Initialiser le logging JSON structuré AVANT la création de l'app,
# pour que tous les loggers (FastAPI, SQLAlchemy, LangChain…) héritent
# de la configuration dès le démarrage.
setup_logging()

from rag.api.app import create_app  # noqa: E402  (import après setup_logging intentionnel)

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=True,
        # Désactiver les handlers uvicorn par défaut : notre setup_logging
        # a déjà configuré le root logger avec le format JSON.
        log_config=None,
    )