"""Fallo/no fallo, tarjeta de última sesión, feedback tras entrenar y energía. Las reglas puras se prueban sin BD."""
from datetime import date, timedelta
from unittest.mock import patch

from app.clock import age_on
from app.services.workout_feedback import evaluate_exercise, suggested_increase
from conftest import onboard_new_user
from test_training import ex_id


def S(reps, kg, fail=None):
    return {"reps": reps, "weight_kg": kg, "reached_failure": fail}


# ───────────── reglas puras ─────────────
def test_first_time_and_empty():
    assert evaluate_exercise([S(10, 40, False)], None, None)["status"] == "first_time"
    assert evaluate_exercise([], [S(10, 40)], 40)["status"] == "insufficient_data"


def test_personal_record_needs_a_prior_mark():
    r = evaluate_exercise([S(8, 47.5, False)], [S(8, 45, False)], 45)
    assert r["status"] == "personal_record" and r["personal_record"] and r["suggested_weight_kg"] is None


def test_progression_only_with_complete_no_failure_data():
    prev = [S(10, 40), S(10, 40)]
    up = evaluate_exercise([S(10, 40, False), S(10, 40, False)], prev, 40)
    assert up["status"] == "progress" and up["suggested_weight_kg"] == 42.5
    # un dato de fallo ausente => NO se sugiere subir
    partial = evaluate_exercise([S(10, 40, False), S(10, 40, None)], prev, 40)
    assert partial["status"] == "maintain" and partial["suggested_weight_kg"] == 40
    # alguna serie al fallo => mantener
    failed = evaluate_exercise([S(10, 40, False), S(10, 40, True)], prev, 40)
    assert failed["status"] == "maintain" and failed["suggested_weight_kg"] == 40


def test_more_reps_same_weight_and_regressions():
    more = evaluate_exercise([S(12, 40, True), S(10, 40, True)], [S(10, 40), S(10, 40)], 40)
    assert more["status"] == "progress" and more["suggested_weight_kg"] == 40
    fewer = evaluate_exercise([S(8, 40, False)], [S(10, 40)], 40)
    assert fewer["status"] == "regression" and fewer["suggested_weight_kg"] == 40
    lighter = evaluate_exercise([S(10, 35, False)], [S(10, 40)], 40)
    assert lighter["status"] == "regression"
    heavier = evaluate_exercise([S(8, 42.5, True)], [S(10, 40)], 42.5)   # mejor marca = 42,5 → no es récord
    assert heavier["status"] == "progress" and not heavier["personal_record"]


def test_bodyweight_and_mixed():
    assert evaluate_exercise([S(15, None)], [S(12, None)], None)["status"] == "progress"
    assert evaluate_exercise([S(10, None)], [S(12, None)], None)["status"] == "regression"
    assert evaluate_exercise([S(10, 20)], [S(12, None)], None)["status"] == "insufficient_data"


def test_increment_steps():
    assert suggested_increase(40) == 42.5 and suggested_increase(100) == 105 and suggested_increase(57.3) == 60


def test_age_uses_given_day():
    assert age_on(date(2000, 3, 10), date(2026, 3, 9)) == 25 and age_on(date(2000, 3, 10), date(2026, 3, 10)) == 26


# ───────────── API ─────────────
def _post(client, h, sets, day=None, **kw):
    payload = {"kind": "Pecho", "category": "strength", "duration_min": 45, "estimate_calories": False, "sets": sets, **kw}
    if day:
        payload["performed_on"] = day.isoformat()
    r = client.post("/workouts", json=payload, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_failure_flag_roundtrip_keeps_legacy_rpe(client, onboarded):
    h, bench = onboarded["headers"], ex_id(client, onboarded["headers"], "Press banca con barra")
    w = _post(client, h, [{"exercise_id": bench, "reps": 8, "weight_kg": 60, "reached_failure": True},
                          {"exercise_id": bench, "reps": 8, "weight_kg": 60, "rpe": 8},   # RPE antiguo, aún aceptado
                          {"exercise_id": bench, "reps": 8, "weight_kg": 60}])
    sets = w["exercises"][0]["sets"]
    assert [s["reached_failure"] for s in sets] == [True, None, None]
    assert sets[1]["rpe"] == 8 and sets[0]["rpe"] is None          # el RPE no se convierte en fallo
    hist = client.get(f"/exercises/{bench}/history", headers=h).json()
    assert hist[0]["sets"][0]["reached_failure"] is True


def test_last_session_card(client, onboarded):
    h, row = onboarded["headers"], ex_id(client, onboarded["headers"], "Press banca con barra")
    assert client.get(f"/exercises/{row}/last-session", headers=h).json()["has_history"] is False
    d1, d2 = date.today() - timedelta(days=14), date.today() - timedelta(days=7)
    _post(client, h, [{"exercise_id": row, "reps": 5, "weight_kg": 70, "reached_failure": True}], day=d1)
    _post(client, h, [{"exercise_id": row, "reps": 12, "weight_kg": 40, "reached_failure": False},
                      {"exercise_id": row, "reps": 8, "weight_kg": 45, "reached_failure": True}], day=d2)
    c = client.get(f"/exercises/{row}/last-session", headers=h).json()
    assert c["has_history"] and c["date"] == d2.isoformat() and c["max_weight_kg"] == 45 and c["total_reps"] == 20
    assert c["any_failure"] is True and c["best_weight_kg"] == 70 and c["best_weight_date"] == d1.isoformat()
    assert [s["set_number"] for s in c["sets"]] == [1, 2]


def test_feedback_after_saving_and_in_history(client, onboarded):
    h, bench = onboarded["headers"], ex_id(client, onboarded["headers"], "Press banca con barra")
    first = _post(client, h, [{"exercise_id": bench, "reps": 10, "weight_kg": 40, "reached_failure": False}] * 2,
                  day=date.today() - timedelta(days=7))
    assert [f["status"] for f in first["feedback"]] == ["first_time"]
    second = _post(client, h, [{"exercise_id": bench, "reps": 10, "weight_kg": 40, "reached_failure": False}] * 2)
    f = second["feedback"][0]
    assert f["status"] == "progress" and f["suggested_weight_kg"] == 42.5 and f["compared_with"]
    record = _post(client, h, [{"exercise_id": bench, "reps": 6, "weight_kg": 50, "reached_failure": True}])
    assert record["feedback"][0]["status"] == "personal_record"
    # consultable después desde el historial; la sesión antigua se compara con lo anterior a ELLA, no con lo posterior
    again = client.get(f"/workouts/{first['id']}", headers=h).json()
    assert again["feedback"][0]["status"] == "first_time"


def test_feedback_skips_stretching_and_failure_never_blocks_saving(client, onboarded):
    h = onboarded["headers"]
    stretch = next(e["id"] for e in client.get("/exercises", params={"kind": "stretching"}, headers=h).json())
    w = _post(client, h, [{"exercise_id": stretch, "reps": 1}], category="stretching")
    assert w["feedback"] == []
    bench = ex_id(client, h, "Press banca con barra")
    with patch("app.services.workout_feedback.workout_feedback", side_effect=RuntimeError("boom")):
        w = _post(client, h, [{"exercise_id": bench, "reps": 8, "weight_kg": 50}])
    assert w["id"] and w["feedback"] == []


def test_last_session_is_private(client, onboarded):
    h, bench = onboarded["headers"], ex_id(client, onboarded["headers"], "Press banca con barra")
    _post(client, h, [{"exercise_id": bench, "reps": 8, "weight_kg": 50}])
    other = onboard_new_user(client)
    assert client.get(f"/exercises/{bench}/last-session", headers=other["headers"]).json()["has_history"] is False


def test_energy_endpoint(client):
    u = onboard_new_user(client)
    e = client.get("/profile/energy", headers=u["headers"]).json()
    assert e["missing"] == [] and e["weight_kg"] == 80
    # Mifflin-St Jeor (hombre, 80 kg, 180 cm) con la edad real
    assert e["age"] == age_on(date(1990, 5, 10))
    assert e["bmr"] == round(10 * 80 + 6.25 * 180 - 5 * e["age"] + 5) and e["tdee"] > e["bmr"]
    # se actualiza sin IA al registrar un peso nuevo
    client.post("/metrics/weight", json={"weight_kg": 85}, headers=u["headers"])
    e2 = client.get("/profile/energy", headers=u["headers"]).json()
    assert e2["bmr"] == e["bmr"] + 50 and e2["weight_kg"] == 85
    # y al cambiar la fecha de nacimiento
    p = client.get("/profile", headers=u["headers"]).json()
    p["birth_date"] = "1980-05-10"
    assert client.put("/profile", json=p, headers=u["headers"]).status_code == 200
    e3 = client.get("/profile/energy", headers=u["headers"]).json()
    assert e3["age"] == age_on(date(1980, 5, 10)) and e3["bmr"] < e2["bmr"]
