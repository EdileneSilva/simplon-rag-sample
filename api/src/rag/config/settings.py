from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mistral AI
    mistral_api_key: str

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "rag"
    postgres_user: str = "rag_user"
    postgres_password: str
    postgres_schema: str = "rag"

    # Application
    app_env: str = "development"
    app_log_level: str = "INFO"
    app_port: int = 8000

    # CORS — comma-separated origins allowed to call the API from a browser.
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # RAG tuning
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 5

    # Web loader
    web_max_pages: int = 100

    # Agent
    product_name: str = "Dev IA"
    agent_max_retries: int = 2

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
