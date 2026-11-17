"""Catálogo base de ejercicios (compartido). Se siembra y se sincroniza al arrancar (idempotente).

Cada entrada: (nombre, tipo, músculo principal, [secundarios], [equipamiento]).
  tipo: strength | full_body | stretching.   equipamiento: claves de enums.EQUIPMENT.
Los nombres no deben cambiar entre versiones (la sincronización actualiza atributos, no renombra)."""
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Exercise

log = logging.getLogger(__name__)
S, F, T = "strength", "full_body", "stretching"

CATALOG: list[tuple[str, str, str, list[str], list[str]]] = [
    # ───────── Fuerza · tren inferior ─────────
    ("Sentadilla con barra", S, "quadriceps", ["glutes", "hamstrings", "adductors", "lower_back"], ["barbell"]),
    ("Sentadilla frontal", S, "quadriceps", ["glutes", "abs"], ["barbell"]),
    ("Prensa de piernas", S, "quadriceps", ["glutes", "adductors"], ["machine"]),
    ("Extensión de piernas (cuádriceps)", S, "quadriceps", [], ["machine"]),
    ("Zancadas con mancuernas", S, "quadriceps", ["glutes", "hamstrings"], ["dumbbell"]),
    ("Sentadilla búlgara", S, "quadriceps", ["glutes", "adductors"], ["dumbbell", "bench"]),
    ("Sentadilla goblet con pesa rusa", S, "quadriceps", ["glutes", "abs"], ["kettlebell"]),
    ("Sentadilla con peso corporal", S, "quadriceps", ["glutes"], ["none"]),
    ("Zancadas con peso corporal", S, "quadriceps", ["glutes", "hamstrings"], ["none"]),
    ("Sentadilla con banda de resistencia", S, "quadriceps", ["glutes", "abductors"], ["resistance_band"]),
    ("Sentadilla en TRX", S, "quadriceps", ["glutes"], ["suspension"]),
    ("Step-up en cajón", S, "quadriceps", ["glutes"], ["box", "dumbbell"]),
    ("Salto al cajón", S, "quadriceps", ["glutes", "calves"], ["box"]),
    ("Peso muerto convencional", S, "hamstrings", ["glutes", "lower_back", "lats", "upper_back", "traps", "forearms"], ["barbell"]),
    ("Peso muerto rumano", S, "hamstrings", ["glutes", "lower_back"], ["barbell"]),
    ("Peso muerto con pesa rusa", S, "hamstrings", ["glutes", "lower_back", "forearms"], ["kettlebell"]),
    ("Curl femoral tumbado", S, "hamstrings", ["calves"], ["machine"]),
    ("Curl femoral sentado", S, "hamstrings", [], ["machine"]),
    ("Hip thrust", S, "glutes", ["hamstrings", "adductors"], ["barbell", "bench"]),
    ("Puente de glúteo", S, "glutes", ["hamstrings"], ["none"]),
    ("Puente de glúteo con banda", S, "glutes", ["abductors", "hamstrings"], ["resistance_band"]),
    ("Patada de glúteo en polea", S, "glutes", ["hamstrings"], ["machine"]),
    ("Máquina de aductores", S, "adductors", [], ["machine"]),
    ("Máquina de abductores", S, "abductors", ["glutes"], ["machine"]),
    ("Caminata lateral con banda", S, "abductors", ["glutes"], ["resistance_band"]),
    ("Elevación de gemelos de pie", S, "calves", [], ["machine"]),
    ("Elevación de gemelos sentado", S, "calves", [], ["machine"]),
    ("Elevación de gemelos con peso corporal", S, "calves", [], ["none"]),
    # ───────── Fuerza · pecho, hombro, tríceps ─────────
    ("Press banca con barra", S, "chest", ["triceps", "shoulders"], ["barbell", "bench"]),
    ("Press banca inclinado con mancuernas", S, "chest", ["shoulders", "triceps"], ["dumbbell", "bench"]),
    ("Aperturas con mancuernas", S, "chest", ["shoulders"], ["dumbbell", "bench"]),
    ("Cruces en polea", S, "chest", ["shoulders"], ["machine"]),
    ("Press de pecho en máquina", S, "chest", ["triceps", "shoulders"], ["machine"]),
    ("Fondos en paralelas", S, "chest", ["triceps", "shoulders"], ["none"]),
    ("Flexiones", S, "chest", ["triceps", "shoulders", "abs"], ["none"]),
    ("Flexiones en TRX", S, "chest", ["triceps", "shoulders", "abs"], ["suspension"]),
    ("Press de pecho con banda", S, "chest", ["triceps", "shoulders"], ["resistance_band"]),
    ("Press militar con barra", S, "shoulders", ["triceps", "traps"], ["barbell"]),
    ("Press de hombros con mancuernas", S, "shoulders", ["triceps"], ["dumbbell"]),
    ("Press de hombros con pesa rusa", S, "shoulders", ["triceps", "abs"], ["kettlebell"]),
    ("Elevaciones laterales", S, "shoulders", [], ["dumbbell"]),
    ("Elevación frontal con disco", S, "shoulders", ["chest"], ["plate"]),
    ("Pájaros (deltoide posterior)", S, "shoulders", ["upper_back"], ["dumbbell"]),
    ("Extensión de tríceps en polea", S, "triceps", [], ["machine"]),
    ("Press francés", S, "triceps", [], ["barbell", "bench"]),
    ("Extensión de tríceps con banda", S, "triceps", [], ["resistance_band"]),
    ("Extensión de tríceps en TRX", S, "triceps", ["shoulders"], ["suspension"]),
    ("Fondos en banco", S, "triceps", ["chest", "shoulders"], ["bench"]),
    # ───────── Fuerza · espalda y bíceps ─────────
    ("Dominadas", S, "lats", ["biceps", "upper_back", "forearms"], ["other"]),
    ("Jalón al pecho", S, "lats", ["biceps", "upper_back"], ["machine"]),
    ("Remo con barra", S, "upper_back", ["lats", "biceps", "lower_back", "traps"], ["barbell"]),
    ("Remo en polea baja", S, "upper_back", ["lats", "biceps"], ["machine"]),
    ("Remo con mancuerna", S, "lats", ["upper_back", "biceps"], ["dumbbell", "bench"]),
    ("Remo con pesa rusa", S, "lats", ["upper_back", "biceps"], ["kettlebell"]),
    ("Remo en TRX", S, "upper_back", ["lats", "biceps"], ["suspension"]),
    ("Remo con banda", S, "upper_back", ["lats", "biceps"], ["resistance_band"]),
    ("Face pull", S, "upper_back", ["shoulders", "traps"], ["machine"]),
    ("Apertura con banda (pull apart)", S, "upper_back", ["shoulders"], ["resistance_band"]),
    ("Encogimientos de hombros", S, "traps", ["forearms"], ["dumbbell"]),
    ("Curl de bíceps con barra", S, "biceps", ["forearms"], ["barbell"]),
    ("Curl martillo", S, "biceps", ["forearms"], ["dumbbell"]),
    ("Curl predicador", S, "biceps", [], ["machine"]),
    ("Curl de bíceps con banda", S, "biceps", ["forearms"], ["resistance_band"]),
    ("Curl de bíceps en TRX", S, "biceps", ["forearms"], ["suspension"]),
    ("Curl de muñeca", S, "forearms", [], ["dumbbell"]),
    ("Hiperextensiones lumbares", S, "lower_back", ["glutes", "hamstrings"], ["other"]),
    ("Buenos días con barra", S, "lower_back", ["glutes", "hamstrings"], ["barbell"]),
    ("Flexión de cuello con banda", S, "neck", [], ["resistance_band"]),
    ("Extensión de cuello con disco", S, "neck", ["traps"], ["plate"]),
    # ───────── Fuerza · abdominales ─────────
    ("Plancha", S, "abs", ["lower_back"], ["none"]),
    ("Crunch abdominal", S, "abs", [], ["none"]),
    ("Elevación de piernas colgado", S, "abs", ["forearms"], ["other"]),
    ("Rueda abdominal", S, "abs", ["lats", "shoulders"], ["wheel"]),
    ("Giros rusos", S, "abs", [], ["none"]),
    ("Giros rusos con disco", S, "abs", [], ["plate"]),
    ("Giros rusos con balón medicinal", S, "abs", [], ["medicine_ball"]),
    ("Crunch en polea", S, "abs", [], ["machine"]),
    ("Plancha en TRX", S, "abs", ["shoulders"], ["suspension"]),
    # ───────── Cuerpo entero ─────────
    ("Burpees", F, "quadriceps", ["chest", "shoulders", "triceps", "abs", "glutes"], ["none"]),
    ("Mountain climbers", F, "abs", ["shoulders", "quadriceps", "chest"], ["none"]),
    ("Saltos de tijera", F, "calves", ["shoulders", "glutes", "quadriceps"], ["none"]),
    ("Thruster con mancuernas", F, "quadriceps", ["shoulders", "glutes", "triceps"], ["dumbbell"]),
    ("Swing con pesa rusa", F, "glutes", ["hamstrings", "lower_back", "shoulders", "abs", "forearms"], ["kettlebell"]),
    ("Turkish get-up", F, "shoulders", ["abs", "glutes", "quadriceps", "triceps"], ["kettlebell"]),
    ("Clean con barra", F, "traps", ["quadriceps", "glutes", "hamstrings", "shoulders", "forearms", "lower_back"], ["barbell"]),
    ("Wall ball", F, "quadriceps", ["shoulders", "glutes", "triceps", "abs"], ["medicine_ball"]),
    ("Lanzamiento de balón medicinal", F, "abs", ["shoulders", "chest", "lats"], ["medicine_ball"]),
    ("Paseo del granjero", F, "forearms", ["traps", "abs", "glutes"], ["dumbbell", "kettlebell"]),
    ("Salto al cajón con aterrizaje", F, "quadriceps", ["glutes", "calves", "abs"], ["box"]),
    # ───────── Estiramientos ─────────
    ("Estiramiento de cuádriceps", T, "quadriceps", [], ["none"]),
    ("Estiramiento de isquiotibiales", T, "hamstrings", [], ["none"]),
    ("Estiramiento de pantorrillas", T, "calves", [], ["none"]),
    ("Estiramiento de aductores (mariposa)", T, "adductors", [], ["none"]),
    ("Estiramiento de glúteos (paloma)", T, "glutes", [], ["none"]),
    ("Estiramiento de abductores (banda iliotibial)", T, "abductors", [], ["none"]),
    ("Estiramiento de pecho en puerta", T, "chest", [], ["none"]),
    ("Estiramiento de dorsales (postura del niño)", T, "lats", [], ["none"]),
    ("Estiramiento de hombros (brazo cruzado)", T, "shoulders", [], ["none"]),
    ("Estiramiento de bíceps", T, "biceps", [], ["none"]),
    ("Estiramiento de tríceps (sobre la cabeza)", T, "triceps", [], ["none"]),
    ("Estiramiento de antebrazos", T, "forearms", [], ["none"]),
    ("Estiramiento de cuello lateral", T, "neck", [], ["none"]),
    ("Estiramiento de trapecio", T, "traps", [], ["none"]),
    ("Estiramiento de espalda baja (rodillas al pecho)", T, "lower_back", [], ["none"]),
    ("Estiramiento de abdominales (cobra)", T, "abs", [], ["none"]),
    ("Estiramiento de espalda superior (gato-vaca)", T, "upper_back", [], ["none"]),
]


def seed_catalog(db: Session) -> int:
    """Inserta los ejercicios compartidos que falten y actualiza los atributos de los existentes (tipo, músculos,
    equipamiento) para que sigan al catálogo. No toca los ejercicios de los usuarios. Devuelve cuántos añadió."""
    existing = {e.name.lower(): e for e in db.scalars(select(Exercise).where(Exercise.user_id.is_(None)))}
    added = updated = 0
    for name, kind, primary, secondary, equipment in CATALOG:
        ex = existing.get(name.lower())
        if ex is None:
            db.add(Exercise(user_id=None, name=name, kind=kind, primary_muscle=primary, secondary_muscles=secondary, equipment=equipment))
            added += 1
        elif (ex.kind, ex.primary_muscle, ex.secondary_muscles, ex.equipment) != (kind, primary, secondary, equipment):
            ex.kind, ex.primary_muscle, ex.secondary_muscles, ex.equipment = kind, primary, secondary, equipment
            db.add(ex)
            updated += 1
    try:
        db.commit()
    except IntegrityError:  # otro proceso sembró a la vez (p. ej. el reloader de uvicorn)
        db.rollback()
        log.info("Catálogo sembrado por otro proceso")
        return 0
    if added or updated:
        log.info("Catálogo de ejercicios: %s añadidos, %s actualizados", added, updated)
    return added
