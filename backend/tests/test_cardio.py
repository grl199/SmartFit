import json
from datetime import date
from unittest.mock import patch

import pytest

from conftest import rnd
from test_training import llm


# ───────────── funciones puras ─────────────
def test_pace_speed_and_intensity():
    from app.services.cardio import format_pace, intensity_level, pace_min_km, speed_kmh
    assert pace_min_km(8.2, 45) == pytest.approx(5.4878, abs=1e-3) and format_pace(5.4878) == "5:29" and format_pace(None) == "—"
    assert speed_kmh(10, 60) == 10 and speed_kmh(None, 60) is None
    assert intensity_level("running", 20, 5, None, None) == "high"            # 4:00/km
    assert intensity_level("running", 60, 10, None, None) == "moderate"       # 6:00/km
    assert intensity_level("running", 70, 10, None, None) == "low"            # 7:00/km
    assert intensity_level("running", 60, 10, 600, None) == "high"            # 60 m/km de desnivel sube un nivel
    assert intensity_level("walking", 60, 3, None, None) == "low"             # 3 km/h
    assert intensity_level("walking", 60, 4.5, None, None) == "moderate"
    assert intensity_level("walking", 60, 6.5, None, None) == "high"
    assert intensity_level("running", 30, None, None, "high") == "high"       # sin distancia: la que estimó la IA
    assert intensity_level("running", 30, None, None, None) == "moderate"


def test_muscle_load_profiles():
    from app.services.cardio import muscle_load
    run = muscle_load("running", 45, 8.2)                                      # 5:29/km -> moderada: 45/6 = 7.5
    assert run["quadriceps"] == run["hamstrings"] == run["glutes"] == run["calves"] == pytest.approx(7.5)
    assert run["abs"] == run["lower_back"] == pytest.approx(3.75) and "chest" not in run
    walk = muscle_load("walking", 60, 4.2)                                     # moderada: 60/10 = 6
    assert walk["calves"] == pytest.approx(6.0) and walk["abductors"] == pytest.approx(3.0)
    assert muscle_load("cardio", 60) == {} and muscle_load("legs", 60) == {} and muscle_load("running", 0) == {}


# ───────────── API ─────────────
def run_payload(**over):
    return {"kind": "Correr 8 km", "category": "running", "duration_min": 45, "distance_km": 8.2,
            "elevation_gain_m": 120, "avg_hr_bpm": 152, **over}


def test_categories_exposed(client):
    cats = client.get("/meta/options").json()["workout_category"]
    assert cats["walking"] == "Andar" and cats["running"] == "Correr" and "cardio" in cats


def test_running_session_metrics_calories_and_muscles(client, onboarded):
    h, calls = onboarded["headers"], []
    with patch("app.services.calories.chat_text", llm(9.0, "moderate", calls)):
        w = client.post("/workouts", headers=h, json=run_payload(notes="Salida suave")).json()
    assert (w["distance_km"], w["elevation_gain_m"], w["avg_hr_bpm"]) == (8.2, 120, 152)
    assert w["pace_min_km"] == 5.49 and w["speed_kmh"] == 10.93                       # derivados de distancia y duración
    assert w["kcal_burned"] == round(9.0 * 80 * 0.75) and w["exercises"] == []
    prompt = calls[0][1]["content"]
    assert "Distancia: 8.2 km (ritmo medio 5:29 min/km" in prompt and "Desnivel positivo: 120 m" in prompt and "152 ppm" in prompt
    assert "solo se conoce el tipo y la duración" not in prompt                         # con distancia, hay datos de sobra
    m = client.get("/training/muscles", params={"days": 7}, headers=h).json()
    assert m["sessions"] == 1
    for muscle in ("quadriceps", "hamstrings", "glutes", "calves"):
        assert m["muscles"][muscle]["cardio_sets"] == 7.5 and m["muscles"][muscle]["strength_sets"] == 0 and m["muscles"][muscle]["sets"] == 7.5
    assert m["muscles"]["abs"]["sets"] == 3.8 and m["muscles"]["chest"]["sets"] == 0 and "Correr" in m["muscles"]["calves"]["exercises"]


def test_walking_session_with_steps(client, onboarded):
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm(3.5, "low")):
        w = client.post("/workouts", headers=h, json={"kind": "Paseo", "category": "walking", "duration_min": 60, "distance_km": 4.2, "steps": 6100}).json()
    assert w["steps"] == 6100 and w["speed_kmh"] == 4.2 and w["pace_min_km"] == 14.29
    m = client.get("/training/muscles", headers=h).json()["muscles"]
    assert m["calves"]["cardio_sets"] == 6.0 and m["abductors"]["cardio_sets"] == 3.0


def test_strength_and_cardio_add_up(client, onboarded):
    h = onboarded["headers"]
    sq = next(e["id"] for e in client.get("/exercises", params={"q": "Extensión de piernas"}, headers=h).json())
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json={"kind": "Pierna", "category": "legs", "duration_min": 40,
                                                  "sets": [{"exercise_id": sq, "reps": 12, "weight_kg": 50}] * 4})
        client.post("/workouts", headers=h, json=run_payload())
    q = client.get("/training/muscles", headers=h).json()["muscles"]["quadriceps"]
    assert (q["strength_sets"], q["cardio_sets"], q["sets"]) == (4, 7.5, 11.5) and q["volume_kg"] == 4 * 12 * 50


def test_generic_cardio_does_not_light_muscles(client, onboarded):
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json={"kind": "Bici", "category": "cardio", "duration_min": 60})
    m = client.get("/training/muscles", headers=h).json()
    assert m["sessions"] == 0 and all(v["sets"] == 0 for v in m["muscles"].values())


def test_cardio_validation(client, onboarded):
    h = onboarded["headers"]
    for bad in ({"distance_km": 0}, {"distance_km": -3}, {"avg_hr_bpm": 10}, {"steps": -1}, {"elevation_gain_m": -5}):
        assert client.post("/workouts", headers=h, json=run_payload(**bad, estimate_calories=False)).status_code == 422, bad
    ok = client.post("/workouts", headers=h, json={"kind": "Paseo", "category": "walking", "duration_min": 30, "estimate_calories": False})
    assert ok.status_code == 201 and ok.json()["pace_min_km"] is None and ok.json()["speed_kmh"] is None   # sin distancia no hay ritmo


def test_day_overview_and_rag_mention_distance_and_pace(client, onboarded):
    from app.db import SessionLocal
    from app.services.rag import build_daily_summary
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm(9.0)):
        client.post("/workouts", headers=h, json=run_payload())
    day = client.get("/dashboard/day", headers=h).json()["workouts"][0]
    assert day["distance_km"] == 8.2 and day["elevation_gain_m"] == 120
    with SessionLocal() as db:
        summary = build_daily_summary(db, onboarded["id"], date.today())
    assert "8.2 km a 5:29 min/km, +120 m de desnivel" in summary


def test_agent_tool_log_includes_cardio_metrics_in_muscles(client, onboarded):
    from app.agent.tools import ToolContext, run_tool
    from app.db import SessionLocal
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=onboarded["headers"], json=run_payload())
    with SessionLocal() as db:
        out = json.loads(run_tool(ToolContext(db, onboarded["id"]), "get_workout_log",
                                  json.dumps({"start_date": date.today().isoformat(), "end_date": date.today().isoformat()})))
    assert out["weighted_sets_per_muscle"]["calves"] == 7.5 and out["sessions"][0]["category"] == "running"
