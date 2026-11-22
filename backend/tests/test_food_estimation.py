import pytest

from app.services.food_estimation import normalize_estimate


def _item(**overrides):
    value = {
        "name": "Tomate",
        "grams": 100,
        "kcal_per_100g": 18,
        "protein_g_per_100g": 0.9,
        "carbs_g_per_100g": 3.9,
        "sugars_g_per_100g": 2.6,
        "fat_g_per_100g": 0.2,
        "sat_fat_g_per_100g": 0,
        "fiber_g_per_100g": 1.2,
        "sodium_mg_per_100g": 5,
        "confidence": "medium",
    }
    value.update(overrides)
    return value


def test_normalize_estimate_calculates_totals_from_ingredient_rows():
    result = normalize_estimate({
        "name": "Ensalada sencilla",
        "items": [_item(), _item(name="Aceite", grams=10, kcal_per_100g=884, protein_g_per_100g=0,
                                   carbs_g_per_100g=0, sugars_g_per_100g=0, fat_g_per_100g=100,
                                   sat_fat_g_per_100g=14, fiber_g_per_100g=0, sodium_mg_per_100g=2)],
        "assumptions": ["Una cucharada pequeña de aceite"],
    })

    assert result["total_grams"] == 110
    assert result["totals"]["kcal"] == pytest.approx(106.4)
    assert result["per_100g"]["kcal_per_100g"] == pytest.approx(96.73)
    assert result["confidence"] == "low"


def test_normalize_estimate_rejects_inconsistent_macros():
    with pytest.raises(ValueError, match="macronutrientes"):
        normalize_estimate({"items": [_item(protein_g_per_100g=50, carbs_g_per_100g=50, fat_g_per_100g=20)]})


def test_normalize_estimate_rejects_more_than_25_ingredients():
    with pytest.raises(ValueError, match="entre 1 y 25"):
        normalize_estimate({"items": [_item() for _ in range(26)]})
