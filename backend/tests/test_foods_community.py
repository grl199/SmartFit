import httpx
from unittest.mock import patch

from conftest import onboard_new_user, rnd
from test_names import _get

OFF_DOWN = lambda url, **kw: httpx.Response(404, json={"status": 0}, request=httpx.Request("GET", url))


def make(client, h, name, code=None, kcal=400, p=7.0, c=48.0, f=20.0, **extra):
    r = client.post("/foods", headers=h, json={"name": name, "barcode": code, "kcal": kcal, "protein_g": p, "carbs_g": c, "fat_g": f, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def ean() -> str:
    return "80" + rnd(11, digits=True)        # EAN-13 italiano, no ambiguo


def lookup(client, h, code):
    with patch("app.services.openfoodfacts.httpx.get", OFF_DOWN):
        return client.get(f"/foods/barcode/{code}", headers=h).json()


# ───────────── búsqueda tolerante ─────────────
def test_fuzzy_search_finds_spelling_and_language_variants(client, onboarded):
    """Caso real: el usuario escribe «pistacho» y el producto se llama «Pistacchio» (italiano)."""
    from app.db import SessionLocal
    from app.models import Food
    from app.services.nutrition import search_foods
    h, tag = onboarded["headers"], rnd(8)
    with SessionLocal() as db:
        db.add(Food(user_id=None, name=f"Pandoro Maxiciok Pistacchio e Nocciola {tag}", brand="Balocco", barcode=ean(), source="openfoodfacts", kcal=420, protein_g=7, carbs_g=48, fat_g=20))
        db.commit()
        assert search_foods(db, onboarded["id"], f"pandoro maxiciok pistacho nocciola {tag}", fuzzy=False) == []      # la búsqueda exacta NO lo encuentra
    r = client.get("/foods/search", params={"q": f"pandoro maxiciok pistacho nocciola {tag}", "online": False}, headers=h).json()
    assert r and r[0]["name"] == f"Pandoro Maxiciok Pistacchio e Nocciola {tag}"                                      # la tolerante sí (y el suyo, el primero)
    for typo in ("pandorp maxiciok", "pandoro maxicok", "pandorp maxicok"):                                              # erratas (sim. 0,6-0,8)
        found = client.get("/foods/search", params={"q": typo, "online": False}, headers=h).json()
        assert any(tag in x["name"] for x in found), typo
    assert client.get("/foods/search", params={"q": f"zzzz qqqq xxxx {rnd(6)}", "online": False}, headers=h).json() == []  # y no inventa


def test_search_edge_cases(client, onboarded):
    h, tag = onboarded["headers"], rnd(6)
    make(client, h, f"Piña natural {tag}")
    assert len(client.get("/foods/search", params={"q": f"pina {tag}", "online": False}, headers=h).json()) == 1   # sin acentos
    for nasty in ("100%", "_", "%", "a_b", "\\", "'; drop table foods; --"):
        assert client.get("/foods/search", params={"q": nasty, "online": False}, headers=h).status_code == 200, nasty
    assert len(client.get("/foods/search", params={"q": "%%%", "online": False}, headers=h).json()) < 5    # % no es comodín


def test_fuzzy_never_exposes_other_users_private_foods(client, onboarded):
    h, tag = onboarded["headers"], rnd(8)
    make(client, h, f"Turrón secreto {tag}")
    other = onboard_new_user(client)["headers"]
    for q in (f"turron secreto {tag}", f"turrn secrto {tag}"):
        assert client.get("/foods/search", params={"q": q, "online": False}, headers=other).json() == []


# ───────────── privacidad por propietario (fallo corregido) ─────────────
def test_barcode_lookup_never_returns_another_users_private_food(client, onboarded):
    a, code = onboarded, ean()
    secret = make(client, a["headers"], "Mi producto privado", code)
    b = onboard_new_user(client)
    res = lookup(client, b["headers"], code)
    assert res["status"] == "not_found" and res["food"] is None                      # antes devolvía el producto de A
    assert lookup(client, a["headers"], code)["food"]["id"] == secret["id"]          # A sí lo ve
    mine = make(client, b["headers"], "Mi versión", code)                              # y B puede tener el mismo código (antes: error 500)
    assert lookup(client, b["headers"], code)["food"]["id"] == mine["id"]
    dup = client.post("/foods", headers=a["headers"], json={"name": "Repetido", "barcode": code, "kcal": 10})
    assert dup.status_code == 409                                                       # pero no dos veces el mismo usuario


def test_agent_tool_respects_ownership(client, onboarded):
    import json
    from app.agent.tools import ToolContext, run_tool
    from app.db import SessionLocal
    code = ean()
    make(client, onboarded["headers"], "Solo mío", code)
    other = onboard_new_user(client)
    with SessionLocal() as db, patch("app.services.openfoodfacts.httpx.get", OFF_DOWN):
        out = json.loads(run_tool(ToolContext(db, other["id"]), "lookup_barcode", json.dumps({"barcode": code})))
        created = json.loads(run_tool(ToolContext(db, other["id"]), "create_food", json.dumps(
            {"name": "Propio de B", "kcal": 100, "protein_g": 5, "carbs_g": 15, "fat_g": 2, "barcode": code})))
    assert out["status"] == "not_found" and created["status"] == "created"             # el create_food de B no choca con el de A


# ───────────── catálogo comunitario ─────────────
def test_sharing_validation(client, onboarded):
    h = onboarded["headers"]
    no_code = make(client, h, "Sin código")
    assert client.post(f"/foods/{no_code['id']}/share", headers=h).status_code == 422
    amb = make(client, h, "Código de tienda", "2" + rnd(12, True))
    r = client.post(f"/foods/{amb['id']}/share", headers=h)
    assert r.status_code == 422 and "empiezan por 2" in r.json()["detail"]
    bad = make(client, h, "No cuadra", ean(), kcal=900, p=1, c=1, f=1)
    assert "no cuadran" in client.post(f"/foods/{bad['id']}/share", headers=h).json()["detail"]
    # con share=true al crear, si no cumple no se guarda nada
    tag = rnd(8)
    r = client.post("/foods", headers=h, json={"name": f"Rechazado {tag}", "barcode": "2" + rnd(12, True), "kcal": 100, "protein_g": 5, "carbs_g": 15, "fat_g": 2, "share": True})
    assert r.status_code == 422 and client.get("/foods/search", params={"q": f"Rechazado {tag}", "online": False}, headers=h).json() == []
    assert client.post("/foods/999999/share", headers=h).status_code == 404


def test_community_food_is_published_only_after_independent_confirmation(client, onboarded):
    a, code, tag = onboarded, ean(), rnd(6)
    fa = make(client, a["headers"], f"Pandoro {tag}", code, kcal=420, p=7, c=48, f=20, brand="Balocco")
    r = client.post(f"/foods/{fa['id']}/share", headers=a["headers"]).json()
    assert r == {"status": "pending", "published": False}
    client.post(f"/foods/{fa['id']}/share", headers=a["headers"])                       # compartir dos veces no equivale a dos usuarios
    b, c_ = onboard_new_user(client), onboard_new_user(client)
    assert lookup(client, c_["headers"], code)["food"] is None                         # todavía nadie más lo ve
    # B tiene datos MUY distintos: no hay consenso
    fb = make(client, b["headers"], f"Pandoro {tag}", code, kcal=210, p=3, c=24, f=10, share=True)
    assert lookup(client, c_["headers"], code)["food"] is None
    # un tercero confirma con valores concordantes con A (±10 %)
    d = onboard_new_user(client)
    fd = make(client, d["headers"], f"Pandoro {tag}", code, kcal=425, p=7.2, c=47.0, f=20.5, share=True)
    shared = lookup(client, c_["headers"], code)
    assert shared["status"] == "db" and shared["food"]["source"] == "community" and shared["food"]["user_id"] is None
    assert shared["food"]["confirmed_by"] == 2 and shared["food"]["brand"] == "Balocco"
    assert abs(shared["food"]["kcal"] - 422.5) < 1                                     # mediana de A y D
    assert shared["food"]["protein_g"] == 7.1 and "share_status" in shared["food"]
    mine = lambda who, fid: next(x for x in client.get("/foods/search", params={"q": f"Pandoro {tag}", "online": False}, headers=who["headers"]).json() if x["id"] == fid)
    assert mine(a, fa["id"])["share_status"] == "verified" and mine(d, fd["id"])["share_status"] == "verified"
    assert client.get(f"/foods/{fb['id']}", headers=b["headers"]).json()["share_status"] == "pending"   # B queda aparte
    # ya publicado: un usuario nuevo lo encuentra por texto y lo ve con el distintivo
    news = onboard_new_user(client)
    found = client.get("/foods/search", params={"q": f"Pandoro {tag}", "online": False}, headers=news["headers"]).json()
    assert found[0]["source"] == "community" and found[0]["name"] == f"Pandoro {tag}"      # la coincidencia exacta va antes que las parecidas


def test_pending_can_be_withdrawn_verified_cannot(client, onboarded):
    h, code = onboarded["headers"], ean()
    f = make(client, h, "Retirable", code)
    client.post(f"/foods/{f['id']}/share", headers=h)
    assert client.delete(f"/foods/{f['id']}/share", headers=h).json() == {"status": "private"}
    other = onboard_new_user(client)
    assert client.delete(f"/foods/{f['id']}/share", headers=other["headers"]).status_code == 404
    client.post(f"/foods/{f['id']}/share", headers=h)
    make(client, other["headers"], "Retirable", code, share=True)                      # consenso -> publicado
    assert client.delete(f"/foods/{f['id']}/share", headers=h).json() == {"status": "verified"}


def test_existing_shared_product_blocks_duplicates_and_open_food_facts_wins(client, onboarded):
    """Si OFF ya tiene el producto, no se crea uno comunitario aparte."""
    h, code = onboarded["headers"], ean()
    with patch("app.services.openfoodfacts.httpx.get", _get(code)):
        off = client.get(f"/foods/barcode/{code}", headers=h).json()["food"]
    assert off["source"] == "openfoodfacts"
    other = onboard_new_user(client)
    make(client, h, "Mío", code, kcal=98, p=11, c=3.4, f=4.3, share=True)
    make(client, other["headers"], "Mío", code, kcal=98, p=11, c=3.4, f=4.3, share=True)
    assert lookup(client, onboard_new_user(client)["headers"], code)["food"]["source"] == "openfoodfacts"
