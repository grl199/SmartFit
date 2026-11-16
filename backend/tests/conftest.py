"""Los tests de API necesitan Postgres+pgvector. Define TEST_DATABASE_URL (una BD DISTINTA de la de desarrollo):
    TEST_DATABASE_URL=postgresql+psycopg://health:health@localhost:5432/health_test pytest
Sin ella, esos tests se saltan y solo corren los puros."""
import os
import random
import string

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB  # antes de importar app.*
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-test")
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["TRANSLATE_NAMES"] = "false"  # nada de hilos en segundo plano en los tests; la traducción se prueba llamándola directamente
os.environ.pop("BOOTSTRAP_USERNAME", None)
os.environ.pop("BOOTSTRAP_PASSWORD", None)


def rnd(n=8, digits=False):
    return "".join(random.choices(string.digits if digits else string.ascii_lowercase, k=n))


@pytest.fixture(scope="session")
def client():
    if not TEST_DB:
        pytest.skip("Define TEST_DATABASE_URL para ejecutar los tests de API")
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import rag

    with patch.object(rag, "embed", lambda t: [[0.01] * 1536 for _ in t]), TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_state():
    from app import security
    from app.services import openfoodfacts as off
    security._fails.clear()
    off._recent_queries.clear()
    off._limiter._hits.clear()


def register(client, name=None, password="contraseña-segura-1"):
    name = name or f"user_{rnd()}"
    r = client.post("/auth/register", json={"name": name, "password": password})
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    return {"name": name, "password": password, "id": r.json()["user"]["id"],
            "headers": {"Authorization": f"Bearer {tok}"}}


ONBOARDING = dict(sex="male", birth_date="1990-05-10", height_cm=180, weight_kg=80, activity_level="moderate",
                  goal="gain_muscle", experience_level="intermediate", available_training_days=4,
                  dietary_restrictions="sin lactosa", context_notes="Lesión de hombro")

GOOD_PLAN = {"kcal": 2900, "protein_g": 160, "carbs_g": 380, "fat_g": 80, "fiber_g": 35, "workouts_per_week": 4,
             "training_plan": "Lunes pecho/tríceps. Martes espalda/bíceps. Jueves pierna. Viernes hombro. Progresión de cargas.",
             "rationale": "Superávit moderado sobre el gasto total para ganar músculo con proteína alta."}


def onboard_new_user(client):
    """Registra un usuario y completa su onboarding (LLM simulado)."""
    import json
    from unittest.mock import patch
    u = register(client)
    with patch("app.services.plan.chat_text", lambda m, json_mode=False: json.dumps(GOOD_PLAN)):
        r = client.post("/onboarding", json=ONBOARDING, headers=u["headers"])
    assert r.status_code == 200, r.text
    return u


@pytest.fixture
def onboarded(client):
    return onboard_new_user(client)
