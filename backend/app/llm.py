"""Clientes de OpenRouter, OpenAI y Gemini para chat y embeddings."""
from functools import lru_cache
import math

from google import genai
from google.genai import types
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




@lru_cache
def get_gemini_embeddings_client():
    """Cliente nativo para embeddings Gemini (separado del cliente OpenAI-compatible de chat)."""
    s = get_settings()
    if not s.gemini_api_key:
        raise RuntimeError("Falta GEMINI_API_KEY para generar embeddings Gemini.")
    return genai.Client(api_key=s.gemini_api_key)


@lru_cache
def get_gemini_client() -> OpenAI:
    """Cliente Chat Completions compatible con Gemini Developer API."""
    s = get_settings()
    if not s.gemini_api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. En Cloud Run, monta el secreto de Secret Manager con ese nombre de variable."
        )
    return OpenAI(
        api_key=s.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=120.0,
        max_retries=2,
    )


def get_chat_client() -> OpenAI:
    provider = get_settings().ai_provider.strip().lower()
    if provider == "openrouter":
        return get_openrouter_client()
    if provider == "openai":
        return get_openai_client()
    if provider == "gemini":
        return get_gemini_client()
    raise ValueError(f"AI_PROVIDER no válido: {provider!r}. Usa 'openrouter', 'openai' o 'gemini'.")


# Compatibilidad con código existente que importe get_client().
def get_client() -> OpenAI:
    return get_openai_client()


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Genera embeddings y verifica que coincidan con la dimensión de pgvector."""
    if not texts:
        return []

    s = get_settings()
    chat_provider = s.ai_provider.strip().lower()
    provider = s.embedding_provider.strip().lower()
    if provider == "auto":
        if chat_provider in ("openai", "openrouter"):
            provider = chat_provider
        elif chat_provider == "gemini":
            # Conserva el espacio vectorial anterior. No mezclar embeddings Gemini con los ya indexados.
            if s.openrouter_api_key:
                provider = "openrouter"
            elif s.openai_api_key or s.vault_addr:
                provider = "openai"
            else:
                raise RuntimeError(
                    "Gemini está configurado para chat, pero no hay credenciales para conservar los embeddings actuales. "
                    "Configura EMBEDDING_PROVIDER=gemini (y ejecuta POST /rag/reindex una vez) o mantén OPENROUTER_API_KEY "
                    "u OPENAI_API_KEY/Vault para conservar el índice existente."
                )
        else:
            raise ValueError(f"AI_PROVIDER no válido: {chat_provider!r}.")
    if provider == "gemini":
        client = get_gemini_embeddings_client()
        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=s.embedding_dim,
        )
        response = client.models.embed_content(
            model=s.gemini_embedding_model,
            contents=texts,
            config=config,
        )
        vectors = [item.values for item in (response.embeddings or [])]
        # Gemini Embedding 001 no normaliza automáticamente cuando se reduce la dimensión.
        # Normalizamos localmente; pgvector utiliza cosine_distance en el RAG.
        normalized = []
        for vector in vectors:
            norm = math.sqrt(sum(value * value for value in vector))
            if not norm:
                raise RuntimeError("Gemini devolvió un embedding nulo.")
            normalized.append([value / norm for value in vector])
        vectors = normalized
        model = s.gemini_embedding_model
    elif provider == "openai":
        client = get_openai_client()
        model = s.embedding_model
        response = client.embeddings.create(model=model, input=texts)
        vectors = [item.embedding for item in response.data]
    elif provider == "openrouter":
        client = get_openrouter_client()
        model = s.openrouter_embedding_model
        response = client.embeddings.create(model=model, input=texts)
        vectors = [item.embedding for item in response.data]
    else:
        raise ValueError("EMBEDDING_PROVIDER debe ser 'auto', 'openrouter', 'openai' o 'gemini'.")
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


def chat_text(messages: list[dict], json_mode: bool = False) -> str:
    """Llamada simple de chat (sin herramientas) con el proveedor configurado. Devuelve el texto."""
    s = get_settings()
    provider = s.ai_provider.strip().lower()
    client = get_chat_client()
    kwargs: dict = {"messages": messages, "temperature": 0.2}
    if provider == "openrouter":
        kwargs["model"] = s.openrouter_model
        # No se fuerza JSON en todos los modelos gratuitos de OpenRouter.
    elif provider == "openai":
        kwargs["model"] = s.openai_model
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
    elif provider == "gemini":
        kwargs["model"] = s.gemini_model
        kwargs["service_tier"] = s.gemini_service_tier
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
    else:
        raise ValueError(f"AI_PROVIDER no válido: {provider!r}.")
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
