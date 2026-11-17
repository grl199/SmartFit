import json
from pathlib import Path
from unittest.mock import patch

import httpx

from conftest import rnd
from test_api import BIZCOCHO, LONG

# Producto real de la captura del usuario (Lidl, Milbona)
COTTAGE = {"product_name": "Milbona Cottage Cheese – 200 g", "brands": "Milbona", "quantity": "200 g",
           "generic_name_es": "Queso fresco granulado (mínimo 20% M.G./E.S.)",
           "nutriments": {"energy-kcal_100g": 98, "proteins_100g": 11, "carbohydrates_100g": 3.4, "fat_100g": 4.3}}


def _get(code, calls=None, product=COTTAGE):
    def fake(url, **kw):
        (calls if calls is not None else []).append(url)
        req = httpx.Request("GET", url)
        if f"/{code}.json" in url:
            return httpx.Response(200, json={"status": 1, "product": product}, request=req)
        return httpx.Response(404, json={"status": 0}, request=req)
    return fake


def test_clean_name_cases():
    from app.services.names import clean_name
    assert clean_name("Milbona Cottage Cheese – 200 g", "Milbona", "200 g") == "Cottage Cheese"
    assert clean_name("Bizcocho de yogur", "Hacendado") == "Bizcocho de yogur"
    assert clean_name("Atún claro 3 x 80 g", "Calvo") == "Atún claro"
    assert clean_name("Leche entera 1 L", "Pascual") == "Leche entera"
    assert clean_name("Hacendado", "Hacendado") == "Hacendado"          # no se queda sin nombre
    assert clean_name("", None) == ""


def test_restricted_barcodes():
    from app.barcodes import is_restricted_barcode as r
    assert r(LONG) and r("2000000000008") and r("0212345678905")
    assert not r("8410076472106") and not r("4006381333931") and not r("12345678") and not r(None) and not r("abc")


def test_off_product_gets_clean_name_generic_name_and_ambiguity_flag(client, onboarded):
    h, code = onboarded["headers"], "2" + rnd(12, digits=True)          # empieza por 2 -> circulación restringida
    with patch("app.services.openfoodfacts.httpx.get", _get(code)):
        f = client.get(f"/foods/barcode/{code}", headers=h).json()["food"]
    assert f["name"] == "Cottage Cheese" and f["brand"] == "Milbona" and f["original_name"] == "Milbona Cottage Cheese – 200 g"
    assert f["generic_name"].startswith("Queso fresco granulado") and f["barcode_ambiguous"] is True
    normal = client.post("/foods", headers=h, json={"name": "Manual", "barcode": "84" + rnd(11, True), "kcal": 1}).json()
    assert normal["barcode_ambiguous"] is False and normal["generic_name"] is None
    # la búsqueda local entiende el nombre limpio, la marca, el nombre original y la denominación en español
    for q in ("cottage", "milbona", "granulado", "Cottage Cheese 200"):
        assert any(x["id"] == f["id"] for x in client.get("/foods/search", params={"q": q, "online": False}, headers=h).json()), q


def test_search_hits_are_cleaned_too(client, onboarded):
    h, tag, code = onboarded["headers"], rnd(10), "2" + rnd(12, True)
    def fake(url, **kw):
        hit = {"code": code, "product_name": f"Hacendado Yogur {tag} – 4 x 125 g", "brands": "Hacendado", "nutriments": BIZCOCHO["nutriments"]}
        return httpx.Response(200, json={"hits": [hit]}, request=httpx.Request("GET", url))
    with patch("app.services.openfoodfacts.httpx.get", fake):
        r = client.get("/foods/search", params={"q": tag}, headers=h).json()
    assert r[0]["name"] == f"Yogur {tag}" and r[0]["original_name"].startswith("Hacendado Yogur") and r[0]["barcode_ambiguous"] is True


# ───────────── traducción con IA ─────────────
def _only_pending(*names_and_ids):
    """Marca como ya procesados todos los productos de OFF existentes para aislar el test."""
    from sqlalchemy import text
    from app.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("UPDATE foods SET extra = extra || '{\"name_es_done\": true}'::jsonb WHERE source = 'openfoodfacts'"))
        db.commit()


def _translator(mapping, seen=None):
    def fake(messages, json_mode=False):
        items = json.loads(messages[1]["content"])
        if seen is not None:
            seen.extend(items)
        return json.dumps({"names": [mapping.get(i["name"], i["name"]) for i in items]})
    return fake


def test_translation_updates_names_and_keeps_original(client, onboarded):
    from app.db import SessionLocal
    from app.services.names import pending_count, translate_pending_names
    h, code = onboarded["headers"], "84" + rnd(11, True)
    _only_pending()
    with patch("app.services.openfoodfacts.httpx.get", _get(code)):
        food = client.get(f"/foods/barcode/{code}", headers=h).json()["food"]
    assert food["name"] == "Cottage Cheese"
    seen = []
    with SessionLocal() as db:
        assert pending_count(db) == 1
        with patch("app.services.names.chat_text", _translator({"Cottage Cheese": "Queso cottage"}, seen)):
            assert translate_pending_names(db) == 1 and translate_pending_names(db) == 0    # idempotente
    assert seen == [{"i": 0, "name": "Cottage Cheese", "brand": "Milbona", "generic_name": "Queso fresco granulado (mínimo 20% M.G./E.S.)"}]
    got = client.get(f"/foods/{food['id']}", headers=h).json()
    assert got["name"] == "Queso cottage" and got["original_name"] == "Milbona Cottage Cheese – 200 g"
    for q in ("queso cottage", "cottage cheese", "milbona"):                                # sigue encontrándose por ambos nombres
        assert any(x["id"] == food["id"] for x in client.get("/foods/search", params={"q": q, "online": False}, headers=h).json()), q


def test_translation_failures_leave_items_pending(client, onboarded):
    from app.db import SessionLocal
    from app.services.names import pending_count, translate_pending_names
    h, code = onboarded["headers"], "84" + rnd(11, True)
    _only_pending()
    with patch("app.services.openfoodfacts.httpx.get", _get(code)):
        fid = client.get(f"/foods/barcode/{code}", headers=h).json()["food"]["id"]
    with SessionLocal() as db:
        with patch("app.services.names.chat_text", lambda m, json_mode=False: json.dumps({"names": []})):     # longitud incorrecta
            try:
                translate_pending_names(db)
                raise AssertionError("debía fallar")
            except ValueError:
                pass
        assert pending_count(db) == 1
        with patch("app.services.names.chat_text", lambda m, json_mode=False: json.dumps({"names": ["x" * 300]})):   # nombre absurdo
            translate_pending_names(db)
    assert client.get(f"/foods/{fid}", headers=h).json()["name"] == "Cottage Cheese"      # sin cambios tras fallos y nombre absurdo


def test_translate_endpoint(client, onboarded):
    h, code = onboarded["headers"], "84" + rnd(11, True)
    _only_pending()
    with patch("app.services.openfoodfacts.httpx.get", _get(code)):
        client.get(f"/foods/barcode/{code}", headers=h)
    with patch("app.services.names.chat_text", lambda m, json_mode=False: (_ for _ in ()).throw(ConnectionError("sin red"))):
        assert client.post("/foods/translate-names", headers=h).status_code == 502
    with patch("app.services.names.chat_text", _translator({"Cottage Cheese": "Queso cottage"})):
        assert client.post("/foods/translate-names", headers=h).json() == {"translated": 1, "pending": 0}


def test_theme_menu_is_not_hidden():
    """Regresión: toolbarMode = "minimal" ocultaba el menú de Streamlit donde se cambia entre modo claro y oscuro."""
    cfg = (Path(__file__).parents[2] / "frontend" / ".streamlit" / "config.toml").read_text()
    assert "toolbarMode" not in cfg or "minimal" not in cfg
