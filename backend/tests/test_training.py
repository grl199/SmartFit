import json
from datetime import date, timedelta
from unittest.mock import patch

from conftest import onboard_new_user, rnd


def llm(met=5.0, intensity="moderate", calls=None):
    def fake(messages, json_mode=False):
        if calls is not None:
            calls.append(messages)
        return json.dumps({"intensity": intensity, "met": met, "note": "Sesión de fuerza moderada con descansos."})
    return fake


def ex_id(client, h, name):
    return next(e["id"] for e in client.get("/exercises", params={"q": name}, headers=h).json())


def legs_payload(client, h, **over):
    sq, ext = ex_id(client, h, "Sentadilla con barra"), ex_id(client, h, "Extensión de piernas")
    return {"kind": "Pierna", "category": "strength", "duration_min": 60,
            "sets": [{"exercise_id": sq, "reps": 8, "weight_kg": 80}, {"exercise_id": sq, "reps": 8, "weight_kg": 80},
                     {"exercise_id": sq, "reps": 6, "weight_kg": 85},
                     {"exercise_id": ext, "reps": 12, "weight_kg": 50}], **over}


# ───────────── catálogo ─────────────
def test_catalog_seeded_and_filtered(client, onboarded):
    h = onboarded["headers"]
    names = {e["name"] for e in client.get("/exercises", headers=h).json()}
    for n in ("Extensión de piernas (cuádriceps)", "Máquina de aductores", "Máquina de abductores", "Sentadilla con barra",
              "Peso muerto convencional", "Press banca con barra", "Jalón al pecho", "Plancha", "Swing con pesa rusa"):
        assert n in names, n
    quads = client.get("/exercises", params={"muscles": "quadriceps"}, headers=h).json()
    assert quads and all(e["primary_muscle"] == "quadriceps" for e in quads)
    assert [e["name"] for e in client.get("/exercises", params={"q": "aductores", "kind": "strength"}, headers=h).json()] == ["Máquina de aductores"]  # sin acentos


def test_seed_is_idempotent(client):
    from app.db import SessionLocal
    from app.services.exercise_catalog import seed_catalog
    with SessionLocal() as db:
        assert seed_catalog(db) == 0


def test_custom_exercises(client, onboarded):
    h, tag = onboarded["headers"], rnd(6)
    made = client.post("/exercises", headers=h, json={"name": f"Remo Pendlay {tag}", "primary_muscle": "upper_back",
                                                      "secondary_muscles": ["lats", "upper_back", "biceps"], "equipment": "barbell"})
    assert made.status_code == 201 and made.json()["secondary_muscles"] == ["lats", "biceps"]  # quita duplicados y el principal
    assert made.json()["equipment"] == ["barbell"] and made.json()["kind"] == "strength"       # un texto suelto se admite como lista
    assert client.post("/exercises", headers=h, json={"name": f"REMO pendlay {tag}", "primary_muscle": "lats"}).status_code == 409
    assert client.post("/exercises", headers=h, json={"name": "sentadilla CON barra", "primary_muscle": "quadriceps"}).status_code == 409
    assert client.post("/exercises", headers=h, json={"name": "Raro", "primary_muscle": "alas"}).status_code == 422
    other = onboard_new_user(client)
    assert client.get("/exercises", params={"q": tag}, headers=other["headers"]).json() == []  # privado


# ───────────── sesiones, series y calorías ─────────────
def test_workout_with_sets_and_llm_calories(client, onboarded):
    h, calls = onboarded["headers"], []
    with patch("app.services.calories.chat_text", llm(5.0, calls=calls)):
        r = client.post("/workouts", headers=h, json=legs_payload(client, h))
    assert r.status_code == 201, r.text
    w = r.json()
    assert w["kcal_burned"] == 400 and w["kcal_source"] == "llm" and w["met"] == 5.0 and w["intensity"] == "moderate"  # 5 MET x 80 kg x 1 h
    assert [(e["exercise"], [s["set_number"] for s in e["sets"]]) for e in w["exercises"]] == [
        ("Sentadilla con barra", [1, 2, 3]), ("Extensión de piernas (cuádriceps)", [1])]
    prompt = calls[0][1]["content"]
    assert "Sentadilla con barra" in prompt and "8x80kg" in prompt and "Peso corporal: 80.0 kg" in prompt and "Fuerza" in prompt and "Pierna" in prompt


def test_calories_scale_with_weight_and_duration_in_code(client, onboarded):
    """La IA solo decide el MET; kcal = MET x kg x horas lo calcula el código."""
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm(4.0)):
        r = client.post("/workouts", headers=h, json={"kind": "Fuerza", "category": "strength", "duration_min": 90}).json()
    assert r["kcal_burned"] == round(4.0 * 80 * 1.5)


def test_manual_kcal_and_opt_out_skip_the_llm(client, onboarded):
    h = onboarded["headers"]
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamar al LLM"))
    with patch("app.services.calories.chat_text", boom):
        manual = client.post("/workouts", headers=h, json={"kind": "Bici", "category": "sport", "duration_min": 45, "kcal_burned": 350}).json()
        skipped = client.post("/workouts", headers=h, json={"kind": "Yoga", "duration_min": 30, "estimate_calories": False}).json()
    assert manual["kcal_burned"] == 350 and manual["kcal_source"] == "manual"
    assert skipped["kcal_burned"] is None and skipped["kcal_source"] is None


def test_workout_saved_even_if_llm_fails(client, onboarded):
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm(met=40.0)):          # MET imposible, dos intentos
        r = client.post("/workouts", headers=h, json={"kind": "Carrera", "category": "running", "duration_min": 30})
    assert r.status_code == 201 and r.json()["kcal_burned"] is None and "reintentarlo" in r.json()["kcal_note"]
    with patch("app.services.calories.chat_text", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("sin red"))):
        assert client.post("/workouts", headers=h, json={"kind": "Carrera", "duration_min": 30}).status_code == 201
    # reintento desde el historial
    wid = r.json()["id"]
    with patch("app.services.calories.chat_text", llm(9.0, "high")):
        again = client.post(f"/workouts/{wid}/estimate-calories", headers=h)
    assert again.status_code == 200 and again.json()["kcal_burned"] == round(9.0 * 80 * 0.5) and again.json()["intensity"] == "high"


def test_no_weight_means_no_estimate_but_session_saved(client, onboarded):
    from sqlalchemy import delete
    from app.db import SessionLocal
    from app.models import BodyMetric
    with SessionLocal() as db:
        db.execute(delete(BodyMetric).where(BodyMetric.user_id == onboarded["id"]))
        db.commit()
    with patch("app.services.calories.chat_text", llm()):
        r = client.post("/workouts", headers=onboarded["headers"], json={"kind": "Pesas", "duration_min": 50}).json()
    assert r["kcal_burned"] is None and "peso" in r["kcal_note"].lower()


def test_workout_validation_and_isolation(client, onboarded):
    h = onboarded["headers"]
    sq = ex_id(client, h, "Sentadilla con barra")
    assert client.post("/workouts", headers=h, json={"kind": "X", "duration_min": 30, "sets": [{"exercise_id": sq, "reps": 0}]}).status_code == 422
    assert client.post("/workouts", headers=h, json={"kind": "X", "duration_min": 30, "category": "yoga"}).status_code == 422
    assert client.post("/workouts", headers=h, json={"kind": "X", "duration_min": 30, "sets": [{"exercise_id": 99999999, "reps": 5}]}).status_code == 422
    # ejercicio privado de otro usuario
    other = onboard_new_user(client)
    mine = client.post("/exercises", headers=h, json={"name": f"Privado {rnd()}", "primary_muscle": "chest"}).json()
    assert client.post("/workouts", headers=other["headers"], json={"kind": "X", "duration_min": 30, "estimate_calories": False,
                                                                   "sets": [{"exercise_id": mine["id"], "reps": 5}]}).status_code == 422
    with patch("app.services.calories.chat_text", llm()):
        w = client.post("/workouts", headers=h, json={"kind": "Mía", "duration_min": 30}).json()
    assert client.get(f"/workouts/{w['id']}", headers=other["headers"]).status_code == 404
    assert client.delete(f"/workouts/{w['id']}", headers=other["headers"]).status_code == 404
    assert client.post(f"/workouts/{w['id']}/estimate-calories", headers=other["headers"]).status_code == 404


# ───────────── volumen muscular ─────────────
def test_muscle_summary_weights_primary_and_secondary(client, onboarded):
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json=legs_payload(client, h))
    m = client.get("/training/muscles", params={"days": 7}, headers=h).json()
    q, g = m["muscles"]["quadriceps"], m["muscles"]["glutes"]
    assert m["sessions"] == 1
    assert q["sets"] == 3 + 1                     # 3 series de sentadilla (principal) + 1 de extensión (principal)
    assert g["sets"] == 1.5 and m["muscles"]["hamstrings"]["sets"] == 1.5   # 3 series x 0,5 (secundario de la sentadilla)
    assert q["volume_kg"] == 80 * 8 * 2 + 85 * 6 + 50 * 12
    assert m["muscles"]["chest"]["sets"] == 0 and "Sentadilla con barra" in q["exercises"]
    from conftest import register
    assert client.get("/training/muscles", params={"days": 7}, headers=register(client)["headers"]).status_code == 403  # sin onboarding


def test_history_progress_and_1rm(client, onboarded):
    h = onboarded["headers"]
    pb = ex_id(client, h, "Press banca con barra")
    def session(day, w, reps):
        client.post("/workouts", headers=h, json={"kind": "Empuje", "category": "strength", "duration_min": 50, "performed_on": day.isoformat(),
                                                  "estimate_calories": False, "sets": [{"exercise_id": pb, "reps": reps, "weight_kg": w}] * 3})
    today = date.today()
    session(today - timedelta(days=6), 70, 8)
    session(today - timedelta(days=1), 100, 5)
    hist = client.get(f"/exercises/{pb}/history", headers=h).json()
    assert [x["date"] for x in hist] == [(today - timedelta(days=1)).isoformat(), (today - timedelta(days=6)).isoformat()]  # reciente primero
    assert hist[0]["sets"][0] == {"set_number": 1, "reps": 5, "weight_kg": 100, "rpe": None, "reached_failure": None}
    prog = client.get(f"/exercises/{pb}/progress", headers=h).json()
    assert [p["best_weight_kg"] for p in prog] == [70, 100]                      # cronológico
    assert prog[1]["est_1rm_kg"] == round(100 * (1 + 5 / 30), 1) and prog[1]["volume_kg"] == 1500 and prog[1]["sets"] == 3
    assert any(e["id"] == pb for e in client.get("/exercises", params={"used": True}, headers=h).json())
    assert client.get("/exercises/99999999/history", headers=h).status_code == 404


def test_delete_workout_removes_its_sets(client, onboarded):
    h = onboarded["headers"]
    with patch("app.services.calories.chat_text", llm()):
        w = client.post("/workouts", headers=h, json=legs_payload(client, h)).json()
    assert client.delete(f"/workouts/{w['id']}", headers=h).status_code == 204
    assert client.get("/training/muscles", headers=h).json()["muscles"]["quadriceps"]["sets"] == 0


def test_day_overview_agent_tool_and_account_deletion(client, onboarded):
    from app.agent.tools import ToolContext, run_tool
    from app.db import SessionLocal
    from sqlalchemy import select
    from app.models import Exercise, WorkoutSet
    h = onboarded["headers"]
    mine = client.post("/exercises", headers=h, json={"name": f"Custom {rnd()}", "primary_muscle": "calves"}).json()
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json={**legs_payload(client, h), "sets": legs_payload(client, h)["sets"] + [{"exercise_id": mine["id"], "reps": 15}]})
    day = client.get("/dashboard/day", headers=h).json()["workouts"][0]
    assert day["category"] == "strength" and day["kcal_burned"] == 400 and "Sentadilla con barra" in day["exercises"]
    with SessionLocal() as db:
        out = json.loads(run_tool(ToolContext(db, onboarded["id"]), "get_workout_log",
                                  json.dumps({"start_date": date.today().isoformat(), "end_date": date.today().isoformat()})))
    assert out["sessions"][0]["exercises"][0]["exercise"] == "Sentadilla con barra" and out["weighted_sets_per_muscle"]["quadriceps"] == 4
    from app.services.rag import build_daily_summary
    with SessionLocal() as db:
        summary = build_daily_summary(db, onboarded["id"], date.today())
    assert "Entrenamiento: Pierna, 60 min, ~400 kcal (Sentadilla con barra" in summary   # el RAG conoce los ejercicios
    assert client.request("DELETE", "/auth/me", headers=h, json={"password": onboarded["password"]}).status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(WorkoutSet).where(WorkoutSet.user_id == onboarded["id"])) is None
        assert db.scalar(select(Exercise).where(Exercise.user_id == onboarded["id"])) is None
