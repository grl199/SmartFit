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
