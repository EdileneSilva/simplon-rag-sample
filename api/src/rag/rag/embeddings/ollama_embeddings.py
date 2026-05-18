from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from rag.config.settings import get_settings


@lru_cache
def get_embeddings() -> OllamaEmbeddings:
    settings = get_settings()
    return OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
    )


async def embed_documents(texts: list[str]) -> list[list[float]]:
    return await get_embeddings().aembed_documents(texts)


async def embed_query(text: str) -> list[float]:
    return await get_embeddings().aembed_query(text)
