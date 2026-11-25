from types import SimpleNamespace as NS
from unittest.mock import patch

from app import llm


class _FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return NS(choices=[NS(message=NS(content='{"ok": true}'))])


class _FakeClient:
    def __init__(self):
        self.chat = NS(completions=_FakeCompletions())


def test_gemini_client_uses_google_openai_compat_endpoint(monkeypatch):
    captured = {}
    settings = NS(gemini_api_key="test-gemini-key")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm, "OpenAI", fake_openai)
    llm.get_gemini_client.cache_clear()
    try:
        llm.get_gemini_client()
    finally:
        llm.get_gemini_client.cache_clear()

    assert captured["api_key"] == "test-gemini-key"
    assert captured["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert captured["max_retries"] == 2


def test_get_chat_client_selects_gemini(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: NS(ai_provider="gemini"))
    expected = object()
    monkeypatch.setattr(llm, "get_gemini_client", lambda: expected)
    assert llm.get_chat_client() is expected


def test_gemini_chat_text_uses_configured_model_and_flex_tier(monkeypatch):
    fake = _FakeClient()
    settings = NS(
        ai_provider="gemini",
        gemini_model="gemini-3.1-flash-lite",
        gemini_service_tier="flex",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "get_chat_client", lambda: fake)

    answer = llm.chat_text([{"role": "user", "content": "Devuelve JSON"}], json_mode=True)

    assert answer == '{"ok": true}'
    assert fake.chat.completions.kwargs["model"] == "gemini-3.1-flash-lite"
    assert fake.chat.completions.kwargs["service_tier"] == "flex"
    assert fake.chat.completions.kwargs["response_format"] == {"type": "json_object"}



def test_gemini_embeddings_use_configured_dimensions_and_task_type(monkeypatch):
    captured = {}
    vectors = [[3.0, 4.0, 0.0]]

    class FakeModels:
        def embed_content(self, **kwargs):
            captured.update(kwargs)
            return NS(embeddings=[NS(values=vectors[0])])

    fake_client = NS(models=FakeModels())
    monkeypatch.setattr(llm, "get_settings", lambda: NS(
        ai_provider="gemini",
        embedding_provider="gemini",
        gemini_embedding_model="gemini-embedding-001",
        embedding_dim=3,
    ))
    monkeypatch.setattr(llm, "get_gemini_embeddings_client", lambda: fake_client)

    result = llm.embed_texts(["texto de prueba"], task_type="RETRIEVAL_QUERY")

    assert captured["model"] == "gemini-embedding-001"
    assert captured["contents"] == ["texto de prueba"]
    assert captured["config"].task_type == "RETRIEVAL_QUERY"
    assert captured["config"].output_dimensionality == 3
    assert result[0] == [0.6, 0.8, 0.0]



def test_gemini_flex_503_falls_back_to_standard():
    class ServiceUnavailable(Exception):
        status_code = 503

    class Completions:
        def __init__(self):
            self.requests = []

        def create(self, **kwargs):
            self.requests.append(kwargs)
            if kwargs.get("service_tier") == "flex":
                raise ServiceUnavailable("temporarily overloaded")
            return NS(result="respuesta")

    fake = NS(chat=NS(completions=Completions()))
    result = llm.create_chat_completion(
        fake,
        {"model": "gemini-3.1-flash-lite", "messages": [], "service_tier": "flex"},
        service_tier="flex",
    )

    assert result.result == "respuesta"
    assert [request["service_tier"] for request in fake.chat.completions.requests] == [
        "flex",
        "standard",
    ]


def test_gemini_standard_503_is_not_retried_as_flex():
    class ServiceUnavailable(Exception):
        status_code = 503

    class Completions:
        def create(self, **kwargs):
            raise ServiceUnavailable("temporarily overloaded")

    fake = NS(chat=NS(completions=Completions()))
    try:
        llm.create_chat_completion(
            fake,
            {"model": "gemini-3.1-flash-lite", "messages": [], "service_tier": "standard"},
            service_tier="standard",
        )
    except ServiceUnavailable:
        pass
    else:
        raise AssertionError("El error 503 de Standard debe propagarse sin bucle de fallback.")
