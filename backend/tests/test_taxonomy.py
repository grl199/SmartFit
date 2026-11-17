from datetime import date
from unittest.mock import patch

from conftest import onboard_new_user, rnd
from test_training import llm

UPPER = ["Abdominales", "Antebrazo", "Bíceps", "Cuello", "Dorsales", "Espalda baja", "Espalda superior", "Hombros", "Pecho", "Trapecio", "Tríceps"]
LOWER = ["Abductores", "Aductores", "Cuádriceps", "Glúteos", "Isquiotibiales", "Pantorrillas"]
EQUIPMENT = ["Ninguno (peso corporal)", "Banda de resistencia", "Banda de suspensión (TRX)", "Barra", "Mancuerna", "Disco", "Máquina",
             "Pesa rusa", "Rueda", "Balón medicinal", "Banco(s)", "Cajones", "Otros"]


def exs(client, h, **params):
    return client.get("/exercises", params=params, headers=h).json()


# ───────────── la jerarquía pedida ─────────────
def test_taxonomy_matches_the_requested_lists():
    from app import enums
    assert [enums.MUSCLE_GROUP[m] for m in enums.MUSCLE_REGIONS["upper"]["muscles"]] == UPPER
    assert [enums.MUSCLE_GROUP[m] for m in enums.MUSCLE_REGIONS["lower"]["muscles"]] == LOWER
    assert enums.MUSCLE_REGIONS["upper"]["label"] == "Tren superior" and enums.MUSCLE_REGIONS["lower"]["label"] == "Tren inferior"
    assert list(enums.EQUIPMENT.values()) == EQUIPMENT and set(enums.EQUIPMENT_ICONS) == set(enums.EQUIPMENT)
    assert all(enums.EQUIPMENT_ICONS.values())
    t = enums.WORKOUT_TYPES
    assert list(t) == ["strength", "cardio", "full_body", "stretching"]
    assert t["cardio"]["categories"] == ["walking", "running", "sport"]           # cardio = andar, correr y otros deportes
    assert {c for v in t.values() for c in v["categories"]} == set(enums.WORKOUT_CATEGORY)
    assert {"football", "tennis", "swimming"} <= set(enums.SPORTS) and set(enums.SPORT_ICONS) == set(enums.SPORTS)
    assert "obliques" not in enums.MUSCLE_GROUP


def test_options_endpoint_exposes_the_hierarchy(client):
    o = client.get("/meta/options").json()
    assert o["muscle_regions"]["upper"]["muscles"][0] == "abs" and o["equipment_icons"]["kettlebell"]
    assert set(o["workout_types"]) == {"strength", "cardio", "full_body", "stretching"} and "sports" in o


def test_catalog_covers_every_muscle_and_equipment():
    from app import enums
    from app.services.exercise_catalog import CATALOG
    for m in enums.MUSCLE_GROUP:
        assert any(c[1] == "strength" and c[2] == m for c in CATALOG), f"sin fuerza: {m}"
        assert any(c[1] == "stretching" and c[2] == m for c in CATALOG), f"sin estiramiento: {m}"
    for e in enums.EQUIPMENT:
        assert any(e in c[4] for c in CATALOG), f"sin ejercicios: {e}"


# ───────────── filtros por grupo muscular y equipamiento ─────────────
def test_filter_by_muscle_groups(client, onboarded):
    h = onboarded["headers"]
    quads = exs(client, h, muscles="quadriceps", kind="strength")
    assert quads and all(e["primary_muscle"] == "quadriceps" and e["kind"] == "strength" for e in quads)
    both = exs(client, h, muscles="biceps,triceps", kind="strength")
    assert {e["primary_muscle"] for e in both} == {"biceps", "triceps"}
    wide = exs(client, h, muscles="glutes", kind="strength", include_secondary="true")
    assert len(wide) > len(exs(client, h, muscles="glutes", kind="strength"))                # incluye los que lo trabajan como secundario
    assert any(e["primary_muscle"] == "quadriceps" and "glutes" in e["secondary_muscles"] for e in wide)
    assert exs(client, h, muscles="neck", kind="strength") and exs(client, h, muscles="traps", kind="strength")
    assert exs(client, h, muscles="inventado") == exs(client, h)                              # valores desconocidos se ignoran


def test_filter_by_equipment(client, onboarded):
    h = onboarded["headers"]
    kb = exs(client, h, equipment="kettlebell")
    assert kb and all("kettlebell" in e["equipment"] for e in kb)
    union = {e["id"] for e in exs(client, h, equipment="barbell,dumbbell")}
    assert union == {e["id"] for e in exs(client, h, equipment="barbell")} | {e["id"] for e in exs(client, h, equipment="dumbbell")}
    for eq in ("resistance_band", "suspension", "plate", "wheel", "medicine_ball", "bench", "box", "none", "machine"):
        assert exs(client, h, equipment=eq), eq
    # combinado: músculo + equipamiento
    chest_band = {e["name"] for e in exs(client, h, muscles="chest", equipment="resistance_band")}
    assert chest_band == {"Press de pecho con banda"}
    assert "Press banca con barra" in {e["name"] for e in exs(client, h, muscles="chest", equipment="bench")}


def test_filter_by_kind(client, onboarded):
    h = onboarded["headers"]
    stretch = exs(client, h, kind="stretching")
    assert {e["primary_muscle"] for e in stretch} == set(__import__("app.enums", fromlist=["x"]).MUSCLE_GROUP) and all(e["equipment"] == ["none"] for e in stretch)
    assert {e["name"] for e in exs(client, h, kind="full_body")} >= {"Burpees", "Swing con pesa rusa", "Turkish get-up"}
    assert all(e["kind"] == "strength" for e in exs(client, h, kind="strength"))


def test_custom_exercise_with_kind_and_equipment(client, onboarded):
    h, tag = onboarded["headers"], rnd(6)
    r = client.post("/exercises", headers=h, json={"name": f"Mi circuito {tag}", "kind": "full_body", "primary_muscle": "quadriceps",
                                                    "equipment": ["kettlebell", "box", "kettlebell"]})
    assert r.status_code == 201 and r.json()["equipment"] == ["kettlebell", "box"] and r.json()["kind"] == "full_body"
    assert client.post("/exercises", headers=h, json={"name": f"Sin material {tag}", "primary_muscle": "abs"}).json()["equipment"] == ["none"]
    assert client.post("/exercises", headers=h, json={"name": f"X {tag}", "primary_muscle": "abs", "equipment": ["laser"]}).status_code == 422
    assert client.post("/exercises", headers=h, json={"name": f"Y {tag}", "primary_muscle": "abs", "equipment": []}).status_code == 422
    assert any(e["name"] == f"Mi circuito {tag}" for e in exs(client, h, equipment="box"))


# ───────────── categorías de sesión ─────────────
def test_session_categories(client, onboarded):
    h = onboarded["headers"]
    base = {"kind": "x", "duration_min": 30, "estimate_calories": False}
    for ok in ("strength", "walking", "running", "sport", "full_body", "stretching"):
        assert client.post("/workouts", headers=h, json={**base, "category": ok}).status_code == 201, ok
    for old in ("legs", "push", "pull", "upper", "core", "cardio", "other"):
        assert client.post("/workouts", headers=h, json={**base, "category": old}).status_code == 422, old


def test_stretching_does_not_count_as_strength_volume(client, onboarded):
    h = onboarded["headers"]
    st = next(e["id"] for e in exs(client, h, kind="stretching", muscles="hamstrings"))
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json={"kind": "Estirar", "category": "stretching", "duration_min": 15, "sets": [{"exercise_id": st, "reps": 1}] * 3})
    m = client.get("/training/muscles", headers=h).json()
    assert m["sessions"] == 0 and m["muscles"]["hamstrings"]["sets"] == 0


def test_muscle_is_not_counted_twice_for_one_set(client, onboarded):
    from app.db import SessionLocal
    from app.models import Exercise
    h, uid = onboarded["headers"], onboarded["id"]
    with SessionLocal() as db:      # datos heredados: el músculo principal repetido como secundario
        ex = Exercise(user_id=uid, name=f"Duplicado {rnd()}", primary_muscle="abs", secondary_muscles=["abs", "chest"], equipment=["none"])
        db.add(ex)
        db.commit()
        ex_id = ex.id
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json={"kind": "Core", "category": "strength", "duration_min": 20, "sets": [{"exercise_id": ex_id, "reps": 10}] * 2})
    m = client.get("/training/muscles", headers=h).json()["muscles"]
    assert m["abs"]["sets"] == 2.0 and m["chest"]["sets"] == 1.0


def test_full_body_exercises_light_several_muscles(client, onboarded):
    h = onboarded["headers"]
    burpee = next(e["id"] for e in exs(client, h, q="Burpees"))
    with patch("app.services.calories.chat_text", llm()):
        client.post("/workouts", headers=h, json={"kind": "Cuerpo entero", "category": "full_body", "duration_min": 25, "sets": [{"exercise_id": burpee, "reps": 12}] * 3})
    m = client.get("/training/muscles", headers=h).json()["muscles"]
    assert m["quadriceps"]["sets"] == 3 and m["chest"]["sets"] == 1.5 and m["abs"]["sets"] == 1.5 and m["biceps"]["sets"] == 0


# ───────────── migración de datos antiguos ─────────────
def test_migration_remaps_legacy_taxonomy(client, onboarded):
    from sqlalchemy import select
    from app.db import SessionLocal, engine
    from app.migrations import run_migrations
    from app.models import Exercise, Workout
    uid = onboarded["id"]
    with SessionLocal() as db:
        ex = Exercise(user_id=uid, name=f"Viejo {rnd()}", primary_muscle="obliques", secondary_muscles=["obliques", "abs", "chest"], equipment=["none"])
        db.add(ex)
        db.add_all([Workout(user_id=uid, performed_on=date.today(), kind=k, category=c, duration_min=10)
                    for k, c in (("a", "legs"), ("b", "core"), ("c", "cardio"), ("d", "other"), ("e", "walking"), ("f", "full_body"))])
        db.commit()
        ex_id = ex.id
    for _ in range(2):                                              # idempotente
        with engine.begin() as conn:
            run_migrations(conn)
    with SessionLocal() as db:
        ex = db.get(Exercise, ex_id)
        assert ex.primary_muscle == "abs" and sorted(ex.secondary_muscles) == ["abs", "chest"]
        cats = {w.kind: w.category for w in db.scalars(select(Workout).where(Workout.user_id == uid))}
    assert cats == {"a": "strength", "b": "strength", "c": "sport", "d": "strength", "e": "walking", "f": "full_body"}
