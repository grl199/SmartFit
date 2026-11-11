from types import SimpleNamespace

import pytest

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
