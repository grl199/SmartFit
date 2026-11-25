from unittest.mock import patch

import httpx

from conftest import rnd
from test_api import BIZCOCHO, LONG

FULL = {**BIZCOCHO, "quantity": "800 g", "nutriscore_grade": "d", "nova_group": 4, "ecoscore_grade": "c",
        "image_front_small_url": "https://images.openfoodfacts.org/images/products/x/front.200.jpg",
        "allergens_tags": ["en:eggs", "en:gluten", "en:milk", "en:sulphur-dioxide-and-sulphites", "en:weird-thing"],
        "ingredients_text_es": "Huevo, azúcar, yogur, harina de trigo", "categories": "Bizcochos, Pasteles, Snacks dulces"}


def test_parse_off_meta_is_tolerant():
    from app.services.openfoodfacts import parse_off_meta
    m = parse_off_meta(FULL)
    assert (m["nutriscore_grade"], m["nova_group"], m["ecoscore_grade"], m["quantity"]) == ("d", 4, "c", "800 g")
    assert m["image_url"].endswith("front.200.jpg")
    assert m["extra"]["allergens"] == ["Huevos", "Gluten", "Leche", "Sulfitos", "Weird thing"]
    assert m["extra"]["categories"] == ["Bizcochos", "Pasteles", "Snacks dulces"] and m["extra"]["ingredients"].startswith("Huevo")
    empty = parse_off_meta({"nutriscore_grade": "unknown", "nova_group": "x", "ecoscore_grade": "not-applicable"})
    assert empty["nutriscore_grade"] is None and empty["nova_group"] is None and empty["ecoscore_grade"] is None and empty["extra"] == {}
    assert parse_off_meta({"environmental_score_grade": "B"})["ecoscore_grade"] == "b"


def _product_get(code, calls, product=FULL):
    def fake(url, **kw):
        calls.append(url)
        req = httpx.Request("GET", url)
        if f"/{code}.json" in url:
            return httpx.Response(200, json={"status": 1, "product": product}, request=req)
        return httpx.Response(404, json={"status": 0}, request=req)
    return fake


def test_barcode_lookup_persists_metadata_and_shows_in_api(client, onboarded):
    h, calls, code = onboarded["headers"], [], LONG[:-6] + rnd(6, digits=True)
    with patch("app.services.openfoodfacts.httpx.get", _product_get(code, calls)):
        f = client.get(f"/foods/barcode/{code}", headers=h).json()["food"]
        assert (f["nutriscore_grade"], f["nova_group"], f["ecoscore_grade"], f["quantity"]) == ("d", 4, "c", "800 g")
        assert f["allergens"][:3] == ["Huevos", "Gluten", "Leche"] and f["image_url"] and "yogur" in f["ingredients"]
        n = len(calls)
        got = client.get(f"/foods/{f['id']}", headers=h).json()           # ya completo: no vuelve a llamar a OFF
        assert got["nova_group"] == 4 and len(calls) == n
    search = client.get("/foods/search", params={"q": f["name"], "online": False}, headers=h).json()
    assert any(x["barcode"] == code and x["nutriscore_grade"] == "d" for x in search)


def test_lazy_enrichment_on_selection(client, onboarded):
    h, tag, calls, code = onboarded["headers"], rnd(10), [], LONG[:-6] + rnd(6, digits=True)
    def search_fake(url, **kw):  # el buscador NO trae metadatos (solo código, nombre y nutrientes)
        if "search.openfoodfacts.org" in url:
            hit = {"code": code, "product_name": f"Bizcocho {tag}", "brands": "Hacendado", "nutriments": BIZCOCHO["nutriments"]}
            return httpx.Response(200, json={"hits": [hit]}, request=httpx.Request("GET", url))
        return _product_get(code, calls)(url, **kw)
    with patch("app.services.openfoodfacts.httpx.get", search_fake):
        found = client.get("/foods/search", params={"q": tag}, headers=h).json()[0]
        assert found["nutriscore_grade"] is None and found["allergens"] == []
        full = client.get(f"/foods/{found['id']}", headers=h).json()      # al seleccionar se completa
        assert full["nutriscore_grade"] == "d" and "Gluten" in full["allergens"] and full["image_url"]
        client.get(f"/foods/{found['id']}", headers=h)
    assert len(calls) == 1                                                  # una sola consulta de producto en total


def test_enrichment_failure_never_breaks_the_food_card(client, onboarded):
    h, code = onboarded["headers"], LONG[:-6] + rnd(6, digits=True)
    made = client.post("/foods", headers=h, json={"name": f"Manual {rnd()}", "barcode": code, "kcal": 100}).json()
    assert client.get(f"/foods/{made['id']}", headers=h).status_code == 200                # manual: no se consulta
    tag = rnd(10)
    def flaky(url, **kw):
        if "search.openfoodfacts.org" in url:
            hit = {"code": code[:-3] + rnd(3, True), "product_name": f"X {tag}", "nutriments": BIZCOCHO["nutriments"]}
            return httpx.Response(200, json={"hits": [hit]}, request=httpx.Request("GET", url))
        raise httpx.ConnectError("offline")
    with patch("app.services.openfoodfacts.httpx.get", flaky):
        f = client.get("/foods/search", params={"q": tag}, headers=h).json()[0]
        assert client.get(f"/foods/{f['id']}", headers=h).status_code == 200
    assert client.get("/foods/99999999", headers=h).status_code == 404

def test_text_search_hit_includes_product_image_and_processing_metadata():
    from app.services.openfoodfacts import SEARCH_FIELDS, parse_search_hit

    hit = {
        "code": "8412345678901",
        "product_name": "Yogur proteico natural",
        "brands": "Marca Ejemplo",
        "quantity": "150 g",
        "image_front_small_url": "https://images.openfoodfacts.org/images/products/x/front.200.jpg",
        "nutriscore_grade": "a",
        "nova_group": 4,
        "nutriments": {"energy-kcal_100g": 63, "proteins_100g": 10, "carbohydrates_100g": 4, "fat_100g": 0.2},
    }
    parsed = parse_search_hit(hit)
    assert parsed is not None
    assert parsed["meta"]["image_url"].endswith("front.200.jpg")
    assert parsed["meta"]["nutriscore_grade"] == "a"
    assert parsed["meta"]["nova_group"] == 4
    assert "image_front_small_url" in SEARCH_FIELDS
    assert "nutriscore_grade" in SEARCH_FIELDS




def test_parse_off_serving_unit_requires_explicit_count_and_uses_hacendado_piece_name():
    from app.services.openfoodfacts import parse_serving_unit

    unit = parse_serving_unit("2 pieces (30 g)", 30, "Regañás Hacendado")
    assert unit["unit_name"] == "regañá"
    assert unit["unit_name_plural"] == "regañás"
    assert unit["grams_per_unit"] == 15

    reversed_format = parse_serving_unit("30 g (2 pieces)", None, "Regañás Hacendado")
    assert reversed_format["grams_per_unit"] == 15

    # A plain serving weight is not enough to infer how many regañás it contains.
    assert parse_serving_unit("30 g", 30, "Regañás Hacendado") is None
    assert parse_serving_unit("150 ml", 150, "Bebida") is None
    assert parse_serving_unit(None, 30, "Regañás Hacendado") is None


def test_off_labels_and_serving_size_are_exposed_as_metadata():
    from app.services.openfoodfacts import parse_off_meta

    metadata = parse_off_meta({
        "labels_tags": ["en:high-protein", "es:sin-gluten"],
        "serving_size": "2 pieces (30 g)",
    })
    assert metadata["extra"]["labels"] == ["High protein", "Sin gluten"]
    assert metadata["extra"]["serving_size"] == "2 pieces (30 g)"
