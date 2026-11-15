"""Catálogo base de ejercicios (compartido). Se siembra al arrancar de forma idempotente."""
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Exercise

log = logging.getLogger(__name__)

# (nombre, músculo principal, [secundarios], material)
CATALOG: list[tuple[str, str, list[str], str]] = [
    # ── Pierna ──
    ("Sentadilla con barra", "quadriceps", ["glutes", "hamstrings", "adductors", "lower_back"], "barbell"),
    ("Sentadilla frontal", "quadriceps", ["glutes", "abs"], "barbell"),
    ("Prensa de piernas", "quadriceps", ["glutes", "adductors"], "machine"),
    ("Extensión de piernas (cuádriceps)", "quadriceps", [], "machine"),
    ("Zancadas con mancuernas", "quadriceps", ["glutes", "hamstrings"], "dumbbell"),
    ("Sentadilla búlgara", "quadriceps", ["glutes", "adductors"], "dumbbell"),
    ("Peso muerto convencional", "hamstrings", ["glutes", "lower_back", "lats", "upper_back", "forearms"], "barbell"),
    ("Peso muerto rumano", "hamstrings", ["glutes", "lower_back"], "barbell"),
    ("Curl femoral tumbado", "hamstrings", ["calves"], "machine"),
    ("Curl femoral sentado", "hamstrings", [], "machine"),
    ("Hip thrust", "glutes", ["hamstrings", "adductors"], "barbell"),
    ("Patada de glúteo en polea", "glutes", ["hamstrings"], "cable"),
    ("Máquina de aductores", "adductors", [], "machine"),
    ("Máquina de abductores", "abductors", ["glutes"], "machine"),
    ("Elevación de gemelos de pie", "calves", [], "machine"),
    ("Elevación de gemelos sentado", "calves", [], "machine"),
    # ── Empuje (pecho, hombro, tríceps) ──
    ("Press banca con barra", "chest", ["triceps", "shoulders"], "barbell"),
    ("Press banca inclinado con mancuernas", "chest", ["shoulders", "triceps"], "dumbbell"),
    ("Aperturas con mancuernas", "chest", ["shoulders"], "dumbbell"),
    ("Cruces en polea", "chest", ["shoulders"], "cable"),
    ("Fondos en paralelas", "chest", ["triceps", "shoulders"], "bodyweight"),
    ("Flexiones", "chest", ["triceps", "shoulders", "abs"], "bodyweight"),
    ("Press militar con barra", "shoulders", ["triceps", "upper_back"], "barbell"),
    ("Press de hombros con mancuernas", "shoulders", ["triceps"], "dumbbell"),
    ("Elevaciones laterales", "shoulders", [], "dumbbell"),
    ("Pájaros (deltoide posterior)", "shoulders", ["upper_back"], "dumbbell"),
    ("Extensión de tríceps en polea", "triceps", [], "cable"),
    ("Press francés", "triceps", [], "barbell"),
    # ── Tirón (espalda, bíceps) ──
    ("Dominadas", "lats", ["biceps", "upper_back", "forearms"], "bodyweight"),
    ("Jalón al pecho", "lats", ["biceps", "upper_back"], "cable"),
    ("Remo con barra", "upper_back", ["lats", "biceps", "lower_back"], "barbell"),
    ("Remo en polea baja", "upper_back", ["lats", "biceps"], "cable"),
    ("Remo con mancuerna", "lats", ["upper_back", "biceps"], "dumbbell"),
    ("Face pull", "upper_back", ["shoulders"], "cable"),
    ("Encogimientos de hombros", "upper_back", ["forearms"], "dumbbell"),
    ("Curl de bíceps con barra", "biceps", ["forearms"], "barbell"),
    ("Curl martillo", "biceps", ["forearms"], "dumbbell"),
    ("Curl predicador", "biceps", [], "machine"),
    ("Hiperextensiones lumbares", "lower_back", ["glutes", "hamstrings"], "bodyweight"),
    # ── Core ──
    ("Plancha", "abs", ["obliques", "lower_back"], "bodyweight"),
    ("Crunch abdominal", "abs", [], "bodyweight"),
    ("Elevación de piernas colgado", "abs", ["forearms"], "bodyweight"),
    ("Rueda abdominal", "abs", ["lats", "shoulders"], "other"),
    ("Giros rusos", "obliques", ["abs"], "other"),
    ("Crunch en polea", "abs", [], "cable"),
]


def seed_catalog(db: Session) -> int:
    """Inserta los ejercicios compartidos que falten (no toca los existentes). Devuelve cuántos añadió."""
    existing = {n.lower() for n in db.scalars(select(Exercise.name).where(Exercise.user_id.is_(None)))}
    added = 0
    for name, primary, secondary, equipment in CATALOG:
        if name.lower() in existing:
            continue
        db.add(Exercise(user_id=None, name=name, primary_muscle=primary, secondary_muscles=secondary, equipment=equipment))
        added += 1
    try:
        db.commit()
    except IntegrityError:  # otro proceso sembró a la vez (p. ej. el reloader de uvicorn)
        db.rollback()
        log.info("Catálogo sembrado por otro proceso")
        return 0
    if added:
        log.info("Catálogo de ejercicios: %s añadidos", added)
    return added
