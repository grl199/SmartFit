"""Agua (F06), actividad (F07), check-in (F08) y resumen de progreso (F09)."""
from datetime import date, timedelta
from unittest.mock import patch

from conftest import onboard_new_user
from test_training import ex_id

TODAY = date.today


def d(n):
    return (TODAY() - timedelta(days=n)).isoformat()


# ───────────── agua ─────────────
def test_water_quick_log_summary_delete_and_goal(client):
    u = onboard_new_user(client); h = u["headers"]
    for ml in (250, 500, 150):
        assert client.post("/water", json={"quantity_ml": ml, "source": "quick"}, headers=h).status_code == 201
    r = client.post("/water", json={"quantity_ml": 330, "log_date": d(1)}, headers=h).json()
    s = client.get("/water/summary", params={"days": 3}, headers=h).json()
    assert s["goal_ml"] == 2000 and s["today_ml"] == 900 and s["today_pct"] == 45 and len(s["days"]) == 3
    assert [x["ml"] for x in s["days"]] == [0, 330, 900] and s["days_goal_met"] == 0
    assert client.get("/dashboard/day", headers=h).json()["water_ml"] == 900          # visible en la pantalla principal
    t = client.get("/targets", headers=h).json()
    t["water_ml"] = 3000
    assert client.put("/targets", json=t, headers=h).json()["water_ml"] == 3000
    t.pop("water_ml")                                                                 # omitido = sin cambios
    assert client.put("/targets", json=t, headers=h).json()["water_ml"] == 3000
    assert client.get("/water/summary", headers=h).json()["today_pct"] == 30
    assert client.delete(f"/water/{r['id']}", headers=h).status_code == 204
    assert client.delete(f"/water/{r['id']}", headers=h).status_code == 404
    assert client.post("/water", json={"quantity_ml": 0}, headers=h).status_code == 422
    assert client.post("/water", json={"quantity_ml": 250, "log_date": (TODAY() + timedelta(days=2)).isoformat()}, headers=h).status_code == 422
    assert client.delete(f"/water/{r['id']}", headers=onboard_new_user(client)["headers"]).status_code == 404


# ───────────── check-in ─────────────
def test_checkin_upsert_private_and_validated(client):
    u = onboard_new_user(client); h = u["headers"]
    body = {"mood": 4, "energy_level": 4, "stress_level": 2, "notes": "Me he encontrado con energía"}
    assert client.put(f"/checkins/{d(0)}", json=body, headers=h).status_code == 200
    again = client.put(f"/checkins/{d(0)}", json={"mood": 5}, headers=h).json()           # edición del mismo día, no duplica
    assert again["mood"] == 5 and again["energy_level"] is None
    assert len(client.get("/checkins", headers=h).json()) == 1
    assert client.put(f"/checkins/{d(0)}", json={"mood": 6}, headers=h).status_code == 422
    assert client.put(f"/checkins/{(TODAY() + timedelta(days=1)).isoformat()}", json={"mood": 3}, headers=h).status_code == 422
    other = onboard_new_user(client)
    assert client.get("/checkins", headers=other["headers"]).json() == []
    assert client.delete(f"/checkins/{d(0)}", headers=other["headers"]).status_code == 404
    assert client.delete(f"/checkins/{d(0)}", headers=h).status_code == 204


# ───────────── actividad ─────────────
def test_activity_manual_sync_idempotent_dedup_and_consent(client):
    u = onboard_new_user(client); h = u["headers"]
    item = {"activity_date": d(0), "steps": 7000, "distance_km": 5.1, "external_id": "abc"}
    assert client.post("/activity/sync", json={"source": "health_connect", "items": [item]}, headers=h).status_code == 403   # sin consentimiento
    assert client.post("/activity/connections", json={"provider": "health_connect"}, headers=h).status_code == 201
    for _ in range(3):                                                                                                        # idempotente
        assert client.post("/activity/sync", json={"source": "health_connect", "items": [item]}, headers=h).json()["synced_days"] == 1
    client.put("/activity", json={"steps": 9500}, headers=h)                                                                  # otra fuente, mismo día
    day = client.get("/activity", headers=h).json()[0]
    assert day["steps"] == 9500 and day["sources"] == ["health_connect", "manual"]      # no se suman: máximo entre fuentes
    s = client.get("/activity/summary", headers=h).json()
    assert s["goal"] == 8000 and s["today_steps"] == 9500 and s["today_pct"] == 119 and s["days_goal_met"] == 1
    bad = {"source": "health_connect", "items": [{"activity_date": (TODAY() + timedelta(days=1)).isoformat(), "steps": 1}]}
    assert client.post("/activity/sync", json=bad, headers=h).status_code == 422
    assert client.post("/activity/sync", json={"source": "fitbit", "items": []}, headers=h).status_code == 422
    # revocar: se corta la entrada; con delete_data se borra lo importado
    assert client.delete("/activity/connections/health_connect", params={"delete_data": True}, headers=h).status_code == 204
    assert client.post("/activity/sync", json={"source": "health_connect", "items": [item]}, headers=h).status_code == 403
    assert client.get("/activity", headers=h).json()[0]["sources"] == ["manual"]
    conns = {c["provider"]: c for c in client.get("/activity/connections", headers=h).json()}
    assert conns["health_connect"]["connected"] is False and conns["google_health"]["configured"] is False


# ───────────── resumen de progreso ─────────────
def _train(client, h, ex, kg, day, reps=10, fail=False):
    r = client.post("/workouts", json={"kind": "Pecho", "category": "strength", "duration_min": 40, "estimate_calories": False, "performed_on": day,
                                       "sets": [{"exercise_id": ex, "reps": reps, "weight_kg": kg, "reached_failure": fail}] * 3}, headers=h)
    assert r.status_code == 201, r.text


def test_insights_not_enough_data(client):
    u = onboard_new_user(client)
    r = client.get("/progress/insights", params={"days": 7}, headers=u["headers"]).json()
    assert r["enough_data"] is False and "datos suficientes" in r["summary"] and r["achievements"] == []


def test_insights_verifiable_achievements_and_comparison(client):
    u = onboard_new_user(client); h = u["headers"]
    bench = ex_id(client, h, "Press banca con barra")
    _train(client, h, bench, 40, d(20))                     # histórico anterior a ambos periodos
    _train(client, h, bench, 42.5, d(9))                    # periodo anterior (7 días: días 7-13 atrás)
    _train(client, h, bench, 50, d(5))                      # periodo actual: récord y mejora
    _train(client, h, bench, 50, d(2))
    food = client.get("/foods/search", params={"q": "Hummus", "online": False}, headers=h).json()[0]
    for n in (1, 2, 3):
        client.post("/logs", json={"food_id": food["id"], "grams": 100, "log_date": d(n)}, headers=h)
    client.post("/water", json={"quantity_ml": 2500}, headers=h)
    client.put(f"/checkins/{d(0)}", json={"mood": 4, "notes": "SECRETO-PRIVADO"}, headers=h)
    r = client.get("/progress/insights", params={"days": 7}, headers=h).json()
    assert r["enough_data"] and r["training"]["sessions"] == 2 and r["training"]["prev_sessions"] == 1
    assert r["training"]["personal_records"] == [{"exercise": "Press banca con barra", "weight_kg": 50.0, "previous_best_kg": 42.5}]
    assert r["training"]["improved"][0]["from_kg"] == 42.5 and r["nutrition"]["days_logged"] == 3
    text = " ".join(r["achievements"])
    assert "2 entrenamientos, frente a 1" in text and "Nuevo récord en Press banca con barra: 50 kg" in text and "agua" in text
    assert r["wellbeing"]["checkin_mood_avg"] == 4 and "SECRETO-PRIVADO" not in str(r)           # notas privadas fuera
    assert any("proteína" in p for p in r["pending"])                                             # hummus: lejos del objetivo de proteína


def test_insights_ai_only_rewrites_and_falls_back(client):
    u = onboard_new_user(client); h = u["headers"]
    _train(client, h, ex_id(client, h, "Press banca con barra"), 50, d(1))
    seen = {}

    def fake(messages, json_mode=False):
        seen["payload"] = messages[1]["content"]
        return "Buen trabajo esta semana."
    with patch("app.routers.insights.chat_text", fake):
        r = client.get("/progress/insights", params={"days": 7, "ai": True}, headers=h).json()
    assert r["ai_summary"] == "Buen trabajo esta semana." and r["summary"] and "SECRETO" not in seen["payload"] and '"notes"' not in seen["payload"]
    with patch("app.routers.insights.chat_text", side_effect=RuntimeError("sin IA")):
        r = client.get("/progress/insights", params={"days": 7, "ai": True}, headers=h).json()
    assert r["ai_summary"] is None and r["summary"]                  # sin IA sigue habiendo resumen
    assert client.get("/progress/insights", params={"days": 1}, headers=h).status_code == 422


def test_account_deletion_removes_new_data(client):
    u = onboard_new_user(client); h = u["headers"]
    client.post("/water", json={"quantity_ml": 250}, headers=h)
    client.put(f"/checkins/{d(0)}", json={"mood": 3}, headers=h)
    client.put("/activity", json={"steps": 100}, headers=h)
    client.post("/activity/connections", json={"provider": "samsung_health"}, headers=h)
    pan = client.get("/foods/search", params={"q": "Pan de molde", "online": False}, headers=h).json()[0]["id"]
    client.post("/recipes", json={"name": "mía", "ingredients": [{"food_id": pan, "quantity_g": 50}]}, headers=h)
    mine = client.post("/foods", json={"name": "propio", "kcal": 1}, headers=h).json()
    client.post(f"/foods/{mine['id']}/servings", json={"unit_name": "u", "grams_per_unit": 5}, headers=h)
    assert client.request("DELETE", "/auth/me", json={"password": u["password"]}, headers=h).status_code == 204
