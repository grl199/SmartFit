"""Plan estructurado (Feature 10) y fichas didácticas (Feature 02)."""
import json
from unittest.mock import patch

from conftest import onboard_new_user
from test_training import ex_id


def test_onboarding_creates_structured_plan_with_real_catalog_ids(client, onboarded):
    h = onboarded["headers"]
    r = client.get("/plan", headers=h).json()
    assert r["has_plan"] and r["legacy_markdown"]            # el texto antiguo se conserva
    plan = r["plan"]
    assert plan["source"] == "auto" and len(plan["days"]) >= 1  # la IA simulada devolvió otra cosa -> plan B por código
    ids = {e["exercise_id"] for d in plan["days"] for e in d["exercises"]}
    catalog = {e["id"] for e in client.get("/exercises", params={"kind": "strength"}, headers=h).json()}
    assert ids and ids <= catalog
    assert r["suggested_day_id"] == plan["days"][0]["id"]


def test_llm_plan_is_validated_and_invented_ids_are_rejected(client, onboarded):
    h = onboarded["headers"]
    bench = ex_id(client, h, "Press banca con barra")
    good = {"name": "Mi plan", "days": [{"label": f"Día {i}", "exercises": [
        {"exercise_id": bench, "sets": 4, "reps_min": 6, "reps_max": 8, "rest_s": 120}]} for i in range(4)]}
    t = client.get("/targets", headers=h).json()["workouts_per_week"]
    good["days"] = good["days"][:1] * t
    with patch("app.routers.plan.chat_text", lambda m, json_mode=False: json.dumps(good)):
        p = client.post("/plan/generate", headers=h).json()["plan"]
    assert p["source"] == "llm" and p["name"] == "Mi plan" and p["days"][0]["exercises"][0]["sets"] == 4
    bad = json.loads(json.dumps(good)); bad["days"][0]["exercises"][0]["exercise_id"] = 99999999
    with patch("app.routers.plan.chat_text", lambda m, json_mode=False: json.dumps(bad)):
        p = client.post("/plan/generate", headers=h).json()["plan"]
    assert p["source"] == "auto"                              # id inventado -> rechazado -> plan B
    with patch("app.routers.plan.chat_text", side_effect=RuntimeError("sin IA")):
        assert client.post("/plan/generate", headers=h).json()["plan"]["source"] == "auto"   # sin IA sigue funcionando
    assert client.post("/plan/generate", json={"use_ai": False}, headers=h).status_code == 200


def test_only_one_active_plan_and_edit_day(client):
    u = onboard_new_user(client); h = u["headers"]
    first = client.get("/plan", headers=h).json()["plan"]
    second = client.post("/plan/generate", json={"use_ai": False}, headers=h).json()["plan"]
    assert second["id"] != first["id"] and client.get("/plan", headers=h).json()["plan"]["id"] == second["id"]
    day = second["days"][0]
    squat = ex_id(client, h, "Sentadilla con barra")
    body = {"label": "Mi día de pierna", "exercises": [{"exercise_id": squat, "sets": 5, "reps_min": 5, "reps_max": 5, "rest_s": 180}]}
    out = client.put(f"/plan/days/{day['id']}", json=body, headers=h).json()
    d = next(x for x in out["plan"]["days"] if x["id"] == day["id"])
    assert d["label"] == "Mi día de pierna" and [e["sets"] for e in d["exercises"]] == [5] and out["plan"]["source"] == "manual"
    bad = {"exercises": [{"exercise_id": 99999999}]}
    assert client.put(f"/plan/days/{day['id']}", json=bad, headers=h).status_code == 422
    assert client.put(f"/plan/days/{day['id']}", json={"exercises": [{"exercise_id": squat, "reps_min": 12, "reps_max": 8}]}, headers=h).status_code == 422
    other = onboard_new_user(client)
    assert client.put(f"/plan/days/{day['id']}", json=body, headers=other["headers"]).status_code == 404


def test_suggested_day_rotates_with_strength_sessions(client):
    u = onboard_new_user(client); h = u["headers"]
    plan = client.post("/plan/generate", json={"use_ai": False}, headers=h).json()["plan"]
    if len(plan["days"]) < 2:
        return
    bench = ex_id(client, h, "Press banca con barra")
    client.post("/workouts", json={"kind": "Fuerza", "category": "strength", "duration_min": 30, "estimate_calories": False,
                                   "sets": [{"exercise_id": bench, "reps": 8, "weight_kg": 50}]}, headers=h)
    assert client.get("/plan", headers=h).json()["suggested_day_id"] == plan["days"][1]["id"]


def test_exercise_content_detailed_generic_and_private_edit(client, onboarded):
    h = onboarded["headers"]
    bench = ex_id(client, h, "Press banca con barra")
    c = client.get(f"/exercises/{bench}/content", headers=h).json()
    assert c["has_detailed_guide"] and len(c["instructions"]) >= 3 and c["common_mistakes"] and c["image_url"] is None
    generic = ex_id(client, h, "Giros rusos")
    g = client.get(f"/exercises/{generic}/content", headers=h).json()
    assert g["has_detailed_guide"] is False and g["description"]
    assert client.put(f"/exercises/{bench}/content", json={"description": "x"}, headers=h).status_code == 403   # catálogo compartido
    mine = client.post("/exercises", json={"name": "Mi ejercicio raro", "kind": "strength", "primary_muscle": "chest"}, headers=h).json()
    ok = client.put(f"/exercises/{mine['id']}/content", headers=h,
                    json={"description": "Mío", "instructions": ["Paso 1"], "image_url": "https://example.com/a.gif", "media_type": "gif"})
    assert ok.status_code == 200 and ok.json()["has_detailed_guide"] and ok.json()["media_type"] == "gif"
    assert client.put(f"/exercises/{mine['id']}/content", json={"image_url": "http://inseguro"}, headers=h).status_code == 422
    assert client.get(f"/exercises/{mine['id']}/content", headers=onboard_new_user(client)["headers"]).status_code == 404
