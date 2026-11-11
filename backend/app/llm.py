"""Clientes de proveedores LLM y embeddings.

OpenAI se mantiene intacto como alternativa. Hugging Face usa su router
OpenAI-compatible para chat y el endpoint hf-inference para embeddings.
"""
from functools import lru_cache

import httpx
from openai import OpenAI

from .config import get_settings
from .vault import get_openai_api_key


@lru_cache
def get_openai_client() -> OpenAI:
    return OpenAI(api_key=get_openai_api_key())


@lru_cache
def get_huggingface_client() -> OpenAI:
    s = get_settings()
    if not s.huggingface_api_key:
        raise RuntimeError(
            "Falta HUGGINGFACE_API_KEY. Crea un token en https://huggingface.co/settings/tokens"
        )
    return OpenAI(
        api_key=s.huggingface_api_key,
        base_url=s.huggingface_base_url,
        timeout=s.huggingface_timeout,
        max_retries=2,
    )


def get_chat_client() -> OpenAI:
    provider = get_settings().ai_provider.strip().lower()
    if provider == "huggingface":
        return get_huggingface_client()
    if provider == "openai":
        return get_openai_client()
    raise ValueError(f"AI_PROVIDER no válido: {provider!r}. Usa 'openai' o 'huggingface'.")


# Compatibilidad con código existente que importe get_client().
def get_client() -> OpenAI:
    return get_openai_client()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Genera embeddings con el proveedor activo y mantiene la dimensión pgvector.

    El modelo multilingüe de Hugging Face devuelve 384 dimensiones; se completa
    con ceros hasta EMBEDDING_DIM. Esto conserva la columna vectorial existente
    (1536) y la similitud coseno no cambia al añadir dimensiones nulas.
    """
    if not texts:
        return []

    s = get_settings()
    provider = s.ai_provider.strip().lower()
    if provider == "openai":
        response = get_openai_client().embeddings.create(
            model=s.embedding_model, input=texts
        )
        return [item.embedding for item in response.data]

    if provider != "huggingface":
        raise ValueError(f"AI_PROVIDER no válido: {provider!r}")

    if not s.huggingface_api_key:
        raise RuntimeError("Falta HUGGINGFACE_API_KEY para generar embeddings.")

    url = (
        "https://router.huggingface.co/hf-inference/models/"
        + s.huggingface_embedding_model
    )
    headers = {"Authorization": f"Bearer {s.huggingface_api_key}"}
    vectors: list[list[float]] = []
    with httpx.Client(timeout=s.huggingface_timeout) as client:
        for value in texts:
            response = client.post(
                url,
                headers=headers,
                json={"inputs": value, "options": {"wait_for_model": True}},
            )
            if response.is_error:
                raise RuntimeError(
                    f"Hugging Face embeddings ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            payload = response.json()
            # feature-extraction suele devolver [tokens, dimensiones].
            while payload and isinstance(payload[0], list) and payload and isinstance(payload[0][0], list):
                payload = payload[0]
            if payload and isinstance(payload[0], list):
                width = len(payload[0])
                vector = [sum(float(token[i]) for token in payload) / len(payload)
                          for i in range(width)]
            else:
                vector = [float(x) for x in payload]

            target_dim = s.embedding_dim
            if len(vector) > target_dim:
                vector = vector[:target_dim]
            elif len(vector) < target_dim:
                vector.extend([0.0] * (target_dim - len(vector)))
            vectors.append(vector)
    return vectors
