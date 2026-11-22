from unittest.mock import patch

import pytest


def _headers(onboarded):
    return onboarded["headers"]


def _component(name, grams, **overrides):
    row = {
        "name": name,
        "grams": grams,
        "kcal_per_100g": 18,
        "protein_g_per_100g": 0.9,
        "carbs_g_per_100g": 3.9,
        "sugars_g_per_100g": 2.6,
        "fat_g_per_100g": 0.2,
        "sat_fat_g_per_100g": 0.0,
        "fiber_g_per_100g": 1.2,
        "sodium_mg_per_100g": 5,
        "confidence": "medium",
    }
    row.update(overrides)
    return row


def test_description_estimate_returns_a_reviewable_proposal_without_logging(client, onboarded):
    proposal = {
        "name": "Ensalada sencilla",
        "items": [_component("Tomate", 100)],
        "assumptions": ["Una ración individual"],
        "total_grams": 100,
        "totals": {"kcal": 18},
        "per_100g": {"kcal_per_100g": 18},
        "confidence": "low",
    }
    with patch("app.routers.foods.estimate_meal", return_value=proposal):
        response = client.post(
            "/foods/estimate",
            headers=_headers(onboarded),
            data={"description": "Tomate y lechuga"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["name"] == "Tomate"
    assert response.json()["method"] == "description"


def test_confirm_estimated_food_recalculates_totals_from_components(client, onboarded):
    components = [
        _component("Tomate", 100),
        _component(
            "Aceite de oliva",
            10,
            kcal_per_100g=884,
            protein_g_per_100g=0,
            carbs_g_per_100g=0,
            sugars_g_per_100g=0,
            fat_g_per_100g=100,
            sat_fat_g_per_100g=13.8,
            fiber_g_per_100g=0,
            sodium_mg_per_100g=2,
        ),
    ]
    response = client.post(
        "/foods/estimate-log",
        headers=_headers(onboarded),
        json={
            "name": "Ensalada de tomate",
            "grams": 110,
            "method": "description",
            "description": "Tomate con aceite",
            # Se envían valores falsos deliberadamente: el backend debe recalcularlos.
            "kcal": 0,
            "protein_g": 0,
            "carbs_g": 0,
            "sugars_g": 0,
            "fat_g": 0,
            "sat_fat_g": 0,
            "fiber_g": 0,
            "sodium_mg": 0,
            "components": components,
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["log"]["kcal"] == pytest.approx(106.4)
    assert result["food"]["confidence"] == "low"
    assert result["food"]["kcal"] == pytest.approx(96.73)


def test_manual_calorie_entry_preserves_total_kcal(client, onboarded):
    response = client.post(
        "/foods/manual-log",
        headers=_headers(onboarded),
        json={"name": "Ensalada de restaurante", "grams": 250, "kcal": 400},
    )
    assert response.status_code == 201, response.text
    assert response.json()["log"]["kcal"] == pytest.approx(400)
    assert response.json()["food"]["confidence"] == "low"


def test_voice_note_transcription_returns_text_without_logging(client, onboarded):
    with patch("app.routers.foods.transcribe_audio", return_value="Pollo con arroz y aceite de oliva") as transcribe:
        response = client.post(
            "/foods/transcribe-audio",
            headers=_headers(onboarded),
            files={"audio": ("receta.wav", b"fake-audio", "audio/wav")},
        )
    assert response.status_code == 200, response.text
    assert response.json()["transcript"] == "Pollo con arroz y aceite de oliva"
    transcribe.assert_called_once()


def test_audio_transcript_can_be_estimated_and_keeps_audio_method(client, onboarded):
    proposal = {
        "name": "Pollo con arroz",
        "items": [_component("Arroz cocido", 100)],
        "assumptions": [],
        "total_grams": 100,
        "totals": {"kcal": 130},
        "per_100g": {"kcal_per_100g": 130},
        "confidence": "low",
    }
    with patch("app.routers.foods.estimate_meal", return_value=proposal):
        response = client.post(
            "/foods/estimate",
            headers=_headers(onboarded),
            data={"description": "Arroz cocido con pollo", "method": "audio"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["method"] == "audio"
