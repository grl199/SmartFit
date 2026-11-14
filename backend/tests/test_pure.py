from types import SimpleNamespace

import pytest

from app import llm
from app.agent.agent import _run_chat_completions
from app.models import NUTRIENTS
from app.services.nutrition import guess_meal, scale
from app.services.openfoodfacts import normalize_barcode, parse_off_product


def test_scale_per_100g():
    food = SimpleNamespace(**{**{n: 0 for n in NUTRIENTS}, "kcal": 250, "protein_g": 10, "fat_g": None})
    out = scale(food, 150)
    assert out["kcal"] == 375 and out["protein_g"] == 15 and out["fat_g"] == 0


def test_normalize_barcode():
    assert normalize_barcode("8 410 076 472 106") == "8410076472106"
    assert normalize_barcode("012345678905") == "0012345678905"  # UPC-A -> EAN-13
    with pytest.raises(ValueError):
        normalize_barcode("123")


def test_parse_off_kj_and_salt_fallback():
    p = parse_off_product({"nutriments": {"energy_100g": 418.4, "proteins_100g": 3, "salt_100g": 2.5}})
    assert p["kcal"] == 100 and p["sodium_mg"] == 1000
    assert parse_off_product({"nutriments": {}}) is None


def test_guess_meal():
    assert [guess_meal(h) for h in (8, 13, 17, 21)] == ["breakfast", "lunch", "snack", "dinner"]


def test_openrouter_chat_completions():
    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="Hola", tool_calls=None)
                )]
            )

    completions = FakeCompletions()
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    used = []

    reply = _run_chat_completions(
        client, "openai/gpt-oss-20b:free", "system", [], "hola",
        SimpleNamespace(), used,
    )

    assert reply == "Hola"
    assert completions.kwargs["model"] == "openai/gpt-oss-20b:free"
    assert completions.kwargs["messages"][-1] == {"role": "user", "content": "hola"}
    assert completions.kwargs["tools"]


def test_openrouter_embeddings_use_configured_model_and_dimension(monkeypatch):
    class FakeEmbeddings:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
            )

    embeddings = FakeEmbeddings()
    monkeypatch.setattr(
        llm, "get_settings",
        lambda: SimpleNamespace(
            ai_provider="openrouter",
            openrouter_embedding_model="test/embeddings",
            embedding_dim=3,
        ),
    )
    monkeypatch.setattr(
        llm, "get_openrouter_client",
        lambda: SimpleNamespace(embeddings=embeddings),
    )

    assert llm.embed_texts(["texto"]) == [[0.1, 0.2, 0.3]]
    assert embeddings.kwargs == {"model": "test/embeddings", "input": ["texto"]}


def test_openrouter_embeddings_reject_dimension_mismatch(monkeypatch):
    monkeypatch.setattr(
        llm, "get_settings",
        lambda: SimpleNamespace(
            ai_provider="openrouter",
            openrouter_embedding_model="test/embeddings",
            embedding_dim=3,
        ),
    )
    monkeypatch.setattr(
        llm, "get_openrouter_client",
        lambda: SimpleNamespace(embeddings=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2])]
            )
        )),
    )

    with pytest.raises(RuntimeError, match="pgvector espera 3"):
        llm.embed_texts(["texto"])
