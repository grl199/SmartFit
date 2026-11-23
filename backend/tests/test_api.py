import json
from typing import get_args
from unittest.mock import patch

import httpx

from conftest import GOOD_PLAN, ONBOARDING, register, rnd


# ───────────── enums ↔ schemas ─────────────
def test_literals_match_enums():
    from app import enums, schemas
    assert set(get_args(schemas.SexCode)) == set(enums.SEX)
    assert set(get_args(schemas.ActivityCode)) == set(enums.ACTIVITY_LEVEL) == set(enums.ACTIVITY_FACTOR)
    assert set(get_args(schemas.GoalCode)) == set(enums.GOAL)
    assert set(get_args(schemas.ExperienceCode)) == set(enums.EXPERIENCE_LEVEL)
    assert set(get_args(schemas.MuscleCode)) == set(enums.MUSCLE_GROUP)
    assert set(get_args(schemas.EquipmentCode)) == set(enums.EQUIPMENT)
    assert set(get_args(schemas.WorkoutCategory)) == set(enums.WORKOUT_CATEGORY)
    assert set(get_args(schemas.ExerciseKind)) == set(enums.EXERCISE_KIND)


def test_every_table_and_column_is_documented():
    from app.db import Base
    from app import models  # noqa: F401
    for t in Base.metadata.tables.values():
        assert t.comment, f"tabla {t.name} sin comentario"
        for c in t.columns:
            assert c.comment, f"{t.name}.{c.name} sin comentario"


# ───────────── auth ─────────────
def test_expo_web_cors_preflight(client):
    origin = "http://localhost:8081"
    response = client.options(
        "/auth/session/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_register_login_and_validation(client):
    u = register(client)
    assert client.post("/auth/register", json={"name": u["name"].upper(), "password": "otra-contraseña-1"}).status_code == 409
    assert client.post("/auth/register", json={"name": "ab", "password": "contraseña-segura-1"}).status_code == 422
    assert client.post("/auth/register", json={"name": f"x_{rnd()}", "password": "corta"}).status_code == 422
    ok = client.post("/auth/login", json={"name": u["name"].upper(), "password": u["password"]})  # sin distinguir mayúsculas
    assert ok.status_code == 200 and ok.json()["user"]["onboarding_completed"] is False
    bad = client.post("/auth/login", json={"name": u["name"], "password": "incorrecta-123"})
    ghost = client.post("/auth/login", json={"name": f"nadie_{rnd()}", "password": "incorrecta-123"})
    assert bad.status_code == ghost.status_code == 401 and bad.json() == ghost.json()  # no revela si existe


def test_login_throttle(client):
    u = register(client)
    for _ in range(5):
        assert client.post("/auth/login", json={"name": u["name"], "password": "incorrecta-123"}).status_code == 401
    assert client.post("/auth/login", json={"name": u["name"], "password": u["password"]}).status_code == 429


def test_protected_routes(client):
    assert client.get("/dashboard/day").status_code == 401
    assert client.get("/dashboard/day", headers={"Authorization": "Bearer basura"}).status_code == 401
    u = register(client)
    r = client.get("/dashboard/day", headers=u["headers"])  # autenticado pero sin onboarding
    assert r.status_code == 403 and r.json()["detail"] == "onboarding_required"
    assert client.get("/profile", headers=u["headers"]).status_code == 200  # el perfil sí es accesible


def test_registration_can_be_disabled(client):
    from app.config import get_settings
    with patch.object(get_settings(), "allow_registration", False):
        assert client.post("/auth/register", json={"name": f"u_{rnd()}", "password": "contraseña-segura-1"}).status_code == 403


# ───────────── onboarding con LLM ─────────────
def test_onboarding_ok_unlocks_app(client):
    u = register(client)
    calls = []
    def fake(messages, json_mode=False):
        calls.append(messages)
        return "Aquí tienes:\n```json\n" + json.dumps(GOOD_PLAN) + "\n```"  # con ruido alrededor
    with patch("app.services.plan.chat_text", fake):
        r = client.post("/onboarding", json=ONBOARDING, headers=u["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["targets"]["source"] == "llm" and body["targets"]["kcal"] == 2900
    from datetime import date
    from app.clock import age_on as _age
    bmr = 10 * 80 + 6.25 * 180 - 5 * _age(date(1990, 5, 10)) + 5   # Mifflin-St Jeor (hombre), calculado por código
    assert body["bmr"] == round(bmr) and body["tdee"] == round(bmr * 1.55)
    assert "TDEE" in calls[0][1]["content"] or "Gasto total" in calls[0][1]["content"]
    assert client.get("/auth/me", headers=u["headers"]).json()["onboarding_completed"] is True
    assert client.get("/dashboard/day", headers=u["headers"]).status_code == 200
    assert client.get("/targets", headers=u["headers"]).json()["training_plan"].startswith("Lunes")
    assert client.get("/profile", headers=u["headers"]).json()["goal"] == "gain_muscle"


def test_onboarding_retries_invalid_plan_then_succeeds(client):
    u = register(client)
    answers = iter(["no es json", json.dumps(GOOD_PLAN)])
    with patch("app.services.plan.chat_text", lambda m, json_mode=False: next(answers)):
        assert client.post("/onboarding", json=ONBOARDING, headers=u["headers"]).status_code == 200


def test_onboarding_rejects_unsafe_llm_output_and_stays_incomplete(client):
    u = register(client)
    unsafe = {**GOOD_PLAN, "kcal": 900, "carbs_g": 50}  # 900 kcal: por debajo del suelo
    with patch("app.services.plan.chat_text", lambda m, json_mode=False: json.dumps(unsafe)):
        r = client.post("/onboarding", json=ONBOARDING, headers=u["headers"])
    assert r.status_code == 502
    assert client.get("/auth/me", headers=u["headers"]).json()["onboarding_completed"] is False
    assert client.get("/profile", headers=u["headers"]).json()["goal"] == "gain_muscle"  # el perfil sí se guardó: se puede reintentar


def test_onboarding_validation(client):
    u = register(client)
    h = u["headers"]
    assert client.post("/onboarding", json={**ONBOARDING, "birth_date": "2015-01-01"}, headers=h).status_code == 422  # menor
    assert client.post("/onboarding", json={**ONBOARDING, "goal": "ponerme_cachas"}, headers=h).status_code == 422   # fuera de lista
    assert client.post("/onboarding", json={**ONBOARDING, "activity_level": "mucho"}, headers=h).status_code == 422
    assert client.post("/onboarding", json={k: v for k, v in ONBOARDING.items() if k != "weight_kg"}, headers=h).status_code == 422


def test_no_deficit_goal_when_underweight(client):
    u = register(client)
    body = {**ONBOARDING, "goal": "lose_fat", "weight_kg": 50, "height_cm": 180}  # IMC 15,4
    with patch("app.services.plan.chat_text", lambda m, json_mode=False: json.dumps(GOOD_PLAN)) as llm:
        r = client.post("/onboarding", json=body, headers=u["headers"])
    assert r.status_code == 422 and "IMC" in r.json()["detail"]


def test_regenerate_targets(client, onboarded):
    new = {**GOOD_PLAN, "kcal": 3000, "carbs_g": 405}
    with patch("app.services.plan.chat_text", lambda m, json_mode=False: json.dumps(new)):
        r = client.post("/targets/generate", headers=onboarded["headers"])
    assert r.status_code == 200 and r.json()["targets"]["kcal"] == 3000


def test_manual_targets_edit_keeps_plan(client, onboarded):
    cur = client.get("/targets", headers=onboarded["headers"]).json()
    r = client.put("/targets", headers=onboarded["headers"], json={**{k: cur[k] for k in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "workouts_per_week")}, "kcal": 2700})
    assert r.json()["source"] == "manual" and r.json()["training_plan"] and r.json()["kcal"] == 2700


# ───────────── prompt del agente ─────────────
def test_system_prompt_contains_profile(client, onboarded):
    from app.agent.prompts import build_system_prompt
    from app.db import SessionLocal
    with SessionLocal() as db:
        prompt = build_system_prompt(db, onboarded["id"])
    for expected in (onboarded["name"], "Hombre", "Edad:", "180 cm", "80.0 kg", "IMC: 24.7", "Ganar músculo", "Intermedio",
                     "4/semana", "sin lactosa", "Lesión de hombro", "gasto total diario", "2900 kcal", "Lunes pecho"):
        assert expected in prompt, expected


# ───────────── borrar cuenta + aislamiento ─────────────
def test_delete_account_and_isolation(client, onboarded):
    a, b = onboarded, register(client)
    food = client.post("/foods", headers=a["headers"], json={"name": f"Privado {rnd()}", "kcal": 100, "protein_g": 5}).json()
    assert client.post("/logs", headers=a["headers"], json={"food_id": food["id"], "grams": 100}).status_code == 201

    # B (aún sin onboarding) no accede; con onboarding tampoco ve lo de A
    with patch("app.services.plan.chat_text", lambda m, json_mode=False: json.dumps(GOOD_PLAN)):
        client.post("/onboarding", json=ONBOARDING, headers=b["headers"])
    assert client.get("/foods/search", params={"q": "Privado", "online": False}, headers=b["headers"]).json() == []
    assert client.post("/logs", headers=b["headers"], json={"food_id": food["id"], "grams": 10}).status_code == 404

    assert client.request("DELETE", "/auth/me", headers=a["headers"], json={"password": "mala-contraseña"}).status_code == 401
    assert client.request("DELETE", "/auth/me", headers=a["headers"], json={"password": a["password"]}).status_code == 204
    assert client.get("/auth/me", headers=a["headers"]).status_code == 401              # el token deja de valer al instante
    assert client.post("/auth/login", json={"name": a["name"], "password": a["password"]}).status_code == 401
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Food, FoodLog
    with SessionLocal() as db:
        assert db.scalar(select(Food).where(Food.user_id == a["id"])) is None
        assert db.scalar(select(FoodLog).where(FoodLog.user_id == a["id"])) is None
    assert client.get("/auth/me", headers=b["headers"]).status_code == 200                # B intacto


# ───────────── códigos de barras largos (p. ej. Mercadona, 24 dígitos) ─────────────
LONG = "232839950000100350003502"
# Datos reales de https://es.openfoodfacts.org/producto/232839950000100350003502 (por 100 g)
BIZCOCHO = {"product_name": "Bizcocho de yogur", "brands": "Hacendado", "nutriments": {
    "energy_100g": 1643, "energy-kcal_100g": 394, "fat_100g": 19, "saturated-fat_100g": 2.9, "carbohydrates_100g": 49,
    "sugars_100g": 25, "fiber_100g": 1.1, "proteins_100g": 6.3, "salt_100g": 1.4, "sodium_100g": 0.56}}


def _product_fake(code, calls):
    def fake_get(url, **kw):
        calls.append(url)
        req = httpx.Request("GET", url)
        if f"/{code}.json" in url:
            return httpx.Response(200, json={"status": 1, "product": BIZCOCHO}, request=req)
        return httpx.Response(404, json={"status": 0}, request=req)
    return fake_get


def test_long_barcode_is_looked_up_in_off_and_persisted(client, onboarded):
    h, calls = onboarded["headers"], []
    code = LONG[:-6] + rnd(6, digits=True)  # único por ejecución (barcode es UNIQUE)
    with patch("app.services.openfoodfacts.httpx.get", _product_fake(code, calls)):
        first = client.get(f"/foods/barcode/{code}", headers=h).json()
        assert first["status"] == "openfoodfacts" and len(calls) == 1                # SÍ se consulta OFF con 24 dígitos
        f = first["food"]
        assert (f["name"], f["brand"], f["barcode"]) == ("Bizcocho de yogur", "Hacendado", code)
        assert (f["kcal"], f["protein_g"], f["carbs_g"], f["fat_g"], f["sugars_g"], f["fiber_g"]) == (394, 6.3, 49, 19, 25, 1.1)
        assert f["sodium_mg"] == 560 and f["sat_fat_g"] == 2.9
        again = client.get(f"/foods/barcode/{code}", headers=h).json()                # segunda vez: de Postgres
        assert again["status"] == "db" and again["food"]["id"] == f["id"] and len(calls) == 1
        # un código largo que OFF no conoce -> not_found (y no se inventa nada)
        unknown = LONG[:-6] + rnd(6, digits=True)
        assert client.get(f"/foods/barcode/{unknown}", headers=h).json()["status"] == "not_found"
    assert client.get("/foods/barcode/123", headers=h).status_code == 422             # demasiado corto


def test_long_barcode_can_be_created_manually(client, onboarded):
    h, code = onboarded["headers"], LONG[:-6] + rnd(6, digits=True)
    made = client.post("/foods", headers=h, json={"name": "Pechuga (tienda)", "barcode": code, "kcal": 110, "protein_g": 23}).json()
    with patch("app.services.openfoodfacts.httpx.get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamar a OFF"))):
        got = client.get(f"/foods/barcode/{code}", headers=h).json()
    assert got["status"] == "db" and got["food"]["id"] == made["id"]


def test_text_search_finds_long_code_products(client, onboarded):
    h, tag = onboarded["headers"], rnd(10)
    code = LONG[:-6] + rnd(6, digits=True)
    def fake(url, **kw):
        req = httpx.Request("GET", url)
        hit = {"code": code, "product_name": f"Bizcocho {tag} yogur", "brands": "Hacendado", "nutriments": BIZCOCHO["nutriments"]}
        return httpx.Response(200, json={"hits": [hit]}, request=req)
    with patch("app.services.openfoodfacts.httpx.get", fake):
        r = client.get("/foods/search", params={"q": tag}, headers=h).json()
    assert len(r) == 1 and r[0]["barcode"] == code and r[0]["kcal"] == 394 and r[0]["brand"] == "Hacendado"


# ───────────── búsqueda híbrida con OFF simulado ─────────────
def _off_fake(tag, calls):
    def fake_get(url, **kw):
        calls.append(url)
        req = httpx.Request("GET", url)
        if "search.openfoodfacts.org" in url:
            hits = [{"code": f"84{rnd(11, True)}", "product_name": f"Skyr {tag} natural {i}", "brands": "Marca,Otra",
                     "nutriments": {"energy-kcal_100g": 63, "proteins_100g": 11, "carbohydrates_100g": 3.5, "fat_100g": 0.2}}
                    for i in range(3)]
            hits.append({"code": f"84{rnd(11, True)}", "product_name": f"Skyr {tag} sin datos", "brands": "X", "nutriments": {}})
            hits.append({"code": "", "product_name": "sin código"})
            return httpx.Response(200, json={"hits": hits, "count": 5}, request=req)
        return httpx.Response(200, request=req, json={"status": 1, "product": {"product_name": "Enriquecido", "nutriments": {"proteins_100g": 9, "energy-kcal_100g": 70}}})
    return fake_get


def test_hybrid_search_persists_and_caches(client, onboarded):
    h, tag, calls = onboarded["headers"], rnd(10), []
    with patch("app.services.openfoodfacts.httpx.get", _off_fake(tag, calls)):
        r = client.get("/foods/search", params={"q": tag}, headers=h).json()
        assert len(r) == 4 and all(f["source"] == "openfoodfacts" for f in r)       # 3 con datos + 1 enriquecido por producto
        n_calls = len(calls)
        assert n_calls >= 2 and r[0]["brand"] == "Marca"
        # segunda búsqueda: sale de Postgres, no vuelve a llamar a OFF
        assert len(client.get("/foods/search", params={"q": tag}, headers=h).json()) == 4
        assert len(calls) == n_calls
    # y sigue ahí sin red
    assert len(client.get("/foods/search", params={"q": tag, "online": False}, headers=h).json()) == 4


def test_hybrid_search_survives_off_failure_and_respects_flags(client, onboarded):
    h, tag = onboarded["headers"], rnd(10)
    def boom(url, **kw):
        raise httpx.ConnectError("offline")
    with patch("app.services.openfoodfacts.httpx.get", boom):
        assert client.get("/foods/search", params={"q": tag}, headers=h).json() == []     # no rompe
    calls = []
    with patch("app.services.openfoodfacts.httpx.get", _off_fake(rnd(10), calls)):
        client.get("/foods/search", params={"q": "ab"}, headers=h)                         # < 3 caracteres
        client.get("/foods/search", params={"q": rnd(10), "online": False}, headers=h)     # online desactivado
    assert calls == []


def test_search_rate_limit(client, onboarded):
    from app.services import openfoodfacts as off
    h, calls = onboarded["headers"], []
    with patch("app.services.openfoodfacts.httpx.get", _off_fake(rnd(10), calls)):
        for _ in range(off._limiter.per_minute + 4):
            client.get("/foods/search", params={"q": rnd(10)}, headers=h)
    assert sum("search.openfoodfacts.org" in c for c in calls) == off._limiter.per_minute


def test_unaccented_local_search(client, onboarded):
    h, tag = onboarded["headers"], rnd(6)
    client.post("/foods", headers=h, json={"name": f"Plátano {tag}", "kcal": 89})
    res = client.get("/foods/search", params={"q": f"platano {tag}", "online": False}, headers=h).json()
    assert res[0]["name"] == f"Plátano {tag}"   # el propio, primero (la búsqueda tolerante puede añadir el «Plátano» genérico del catálogo)
