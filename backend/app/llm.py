"""Clientes de OpenRouter y OpenAI para chat y embeddings."""
from functools import lru_cache

from openai import OpenAI

from .config import get_settings
from .vault import get_openai_api_key


@lru_cache
def get_openai_client() -> OpenAI:
    return OpenAI(api_key=get_openai_api_key())


@lru_cache
def get_openrouter_client() -> OpenAI:
    s = get_settings()
    if not s.openrouter_api_key:
        raise RuntimeError("Falta OPENROUTER_API_KEY en backend/.env")
    return OpenAI(
        api_key=s.openrouter_api_key,
        base_url=s.openrouter_base_url,
        timeout=s.openrouter_timeout,
        max_retries=2,
    )


def get_chat_client() -> OpenAI:
    provider = get_settings().ai_provider.strip().lower()
    if provider == "openrouter":
        return get_openrouter_client()
    if provider == "openai":
        return get_openai_client()
    raise ValueError(f"AI_PROVIDER no válido: {provider!r}. Usa 'openrouter' o 'openai'.")


# Compatibilidad con código existente que importe get_client().
def get_client() -> OpenAI:
    return get_openai_client()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Genera embeddings y verifica que coincidan con la dimensión de pgvector."""
    if not texts:
        return []

    s = get_settings()
    provider = s.ai_provider.strip().lower()
    if provider == "openai":
        client = get_openai_client()
        model = s.embedding_model
    elif provider == "openrouter":
        client = get_openrouter_client()
        model = s.openrouter_embedding_model
    else:
        raise ValueError(f"AI_PROVIDER no válido: {provider!r}. Usa 'openrouter' o 'openai'.")

    response = client.embeddings.create(model=model, input=texts)
    vectors = [item.embedding for item in response.data]
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"El modelo de embeddings {model!r} devolvió {len(vectors)} vectores "
            f"para {len(texts)} textos."
        )
    for vector in vectors:
        if len(vector) != s.embedding_dim:
            raise RuntimeError(
                f"El modelo de embeddings {model!r} devolvió dimensión {len(vector)}; "
                f"pgvector espera {s.embedding_dim}."
            )
    return vectors
