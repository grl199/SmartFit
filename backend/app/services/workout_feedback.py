"""Recomendaciones tras entrenar. 100 % determinista: no depende de la IA ni de que el proveedor esté disponible.

Para cada ejercicio de la sesión compara con la sesión anterior y con la mejor marca histórica y devuelve un veredicto:
  personal_record · progress · maintain · regression · first_time · insufficient_data

Reglas de prudencia (no se sube peso «a ciegas»):
  - Solo se sugiere subir carga si TODAS las series tienen el dato de fallo, ninguna llegó al fallo, se mantuvo el peso
    máximo y no bajaron las repeticiones totales. Con datos incompletos se mantiene la carga.
  - El incremento sugerido es pequeño (2,5 kg; 5 kg a partir de 100 kg).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Workout, WorkoutSet
from .training import _sets_by_workout

SMALL_STEP_KG, BIG_STEP_KG, BIG_STEP_FROM_KG = 2.5, 5.0, 100.0


def _top_weight(sets: list) -> float | None:
    ws = [s["weight_kg"] for s in sets if s.get("weight_kg")]
    return max(ws) if ws else None


def _total_reps(sets: list) -> int:
    return sum(s["reps"] for s in sets)


def suggested_increase(top: float) -> float:
    step = BIG_STEP_KG if top >= BIG_STEP_FROM_KG else SMALL_STEP_KG
    return round((top + step) * 2) / 2  # múltiplos de 0,5 kg


def _fmt(kg: float) -> str:
    return f"{kg:g} kg"


def evaluate_exercise(current: list[dict], previous: list[dict] | None, best_prior_weight: float | None) -> dict:
    """`current`/`previous`: series como dicts {reps, weight_kg, reached_failure}. Devuelve {status, message,
    suggested_weight_kg, personal_record}."""
    if not current:
        return {"status": "insufficient_data", "message": "No hay series registradas de este ejercicio.",
                "suggested_weight_kg": None, "personal_record": False}
    top, reps = _top_weight(current), _total_reps(current)

    if previous is None:
        return {"status": "first_time", "suggested_weight_kg": None, "personal_record": False,
                "message": "Primera vez que registras este ejercicio: lo usaremos como referencia para las próximas sesiones."}

    prev_top, prev_reps = _top_weight(previous), _total_reps(previous)

    # Récord personal de peso (solo si ya había una marca anterior con peso externo)
    if top and best_prior_weight and top > best_prior_weight:
        return {"status": "personal_record", "personal_record": True, "suggested_weight_kg": None,
                "message": f"¡Nuevo récord! Has superado tu mejor peso registrado en este ejercicio "
                           f"({_fmt(best_prior_weight)} → {_fmt(top)})."}

    # Sin peso externo en ninguna de las dos sesiones: se compara solo por repeticiones
    if not top and not prev_top:
        if reps > prev_reps:
            return {"status": "progress", "personal_record": False, "suggested_weight_kg": None,
                    "message": f"Has hecho más repeticiones que la última vez ({reps} frente a {prev_reps})."}
        if reps < prev_reps:
            return {"status": "regression", "personal_record": False, "suggested_weight_kg": None,
                    "message": f"Hoy has hecho menos repeticiones que la última vez ({reps} frente a {prev_reps}). "
                               "Prioriza la técnica."}
        return {"status": "maintain", "personal_record": False, "suggested_weight_kg": None,
                "message": "Has igualado las repeticiones de la última sesión. Continúa así."}

    # Hoy hay peso y antes no (o al revés): no son comparables de forma fiable
    if not top or not prev_top:
        return {"status": "insufficient_data", "personal_record": False, "suggested_weight_kg": None,
                "message": "La sesión anterior no es comparable (una con peso y otra sin él)."}

    if top > prev_top:
        return {"status": "progress", "personal_record": False, "suggested_weight_kg": None,
                "message": f"Has subido el peso respecto a la última sesión ({_fmt(prev_top)} → {_fmt(top)})."}

    if top < prev_top:
        return {"status": "regression", "personal_record": False, "suggested_weight_kg": top,
                "message": f"Hoy has usado menos peso que la última vez ({_fmt(top)} frente a {_fmt(prev_top)}). "
                           "Si no ha sido una descarga planificada, mantén este peso y prioriza la técnica."}

    # Mismo peso máximo: decide por repeticiones y fallo
    if reps < prev_reps:
        return {"status": "regression", "personal_record": False, "suggested_weight_kg": top,
                "message": f"Hoy has realizado menos repeticiones que en la última sesión ({reps} frente a {prev_reps}). "
                           f"Te recomendamos mantener {_fmt(top)} y priorizar la técnica."}

    failures = [s.get("reached_failure") for s in current]
    complete = all(f is not None for f in failures)
    if complete and not any(failures):
        nxt = suggested_increase(top)
        return {"status": "progress", "personal_record": False, "suggested_weight_kg": nxt,
                "message": "Has completado todas las series sin llegar al fallo y sin perder repeticiones. "
                           f"En la próxima sesión puedes valorar subir ligeramente el peso (por ejemplo, a {_fmt(nxt)})."}

    if reps > prev_reps:
        return {"status": "progress", "personal_record": False, "suggested_weight_kg": top,
                "message": f"Has mantenido el peso y has conseguido más repeticiones ({reps} frente a {prev_reps}). "
                           "Continúa trabajando con esta carga."}

    why = "alguna serie llegó al fallo" if complete else "faltan datos de fallo en algunas series"
    return {"status": "maintain", "personal_record": False, "suggested_weight_kg": top,
            "message": f"Mismo peso y mismas repeticiones que la última vez ({why}). "
                       f"Mantén {_fmt(top)} hasta hacerlo con margen."}


def _as_dict(s: WorkoutSet) -> dict:
    return {"reps": s.reps, "weight_kg": s.weight_kg, "reached_failure": s.reached_failure}


def workout_feedback(db: Session, workout: Workout) -> list[dict]:
    """Feedback por ejercicio de una sesión, comparando con lo anterior a ESTA sesión (por fecha e id).
    Los estiramientos no generan feedback."""
    sets = db.scalars(select(WorkoutSet).where(WorkoutSet.workout_id == workout.id).order_by(WorkoutSet.id)).all()
    by_ex: dict[int, list[WorkoutSet]] = defaultdict(list)
    for s in sets:
        by_ex[s.exercise_id].append(s)
    out = []
    for ex_id, ex_sets in by_ex.items():
        ex = ex_sets[0].exercise
        if ex.kind == "stretching":
            continue
        before = [g for g in _sets_by_workout(db, workout.user_id, ex_id)
                  if (g["date"], g["workout_id"]) < (workout.performed_on, workout.id)]
        previous = [_as_dict(s) for s in before[0]["sets"]] if before else None
        prior_ws = [s.weight_kg for g in before for s in g["sets"] if s.weight_kg]
        res = evaluate_exercise([_as_dict(s) for s in ex_sets], previous, max(prior_ws) if prior_ws else None)
        out.append({"exercise_id": ex_id, "exercise": ex.name,
                    "compared_with": before[0]["date"] if before else None, **res})
    return out


def last_session(db: Session, user_id: int, exercise_id: int) -> dict:
    """Tarjeta «Última sesión»: fecha, series, peso máximo, fallo y mejor peso histórico."""
    groups = _sets_by_workout(db, user_id, exercise_id)
    if not groups:
        return {"exercise_id": exercise_id, "has_history": False}
    last = groups[0]
    sets = last["sets"]
    flags = [s.reached_failure for s in sets if s.reached_failure is not None]
    best_w, best_d = None, None
    for g in groups:  # más reciente primero: en un empate gana la fecha más antigua (la marca se logró entonces)
        for s in g["sets"]:
            if s.weight_kg and (best_w is None or s.weight_kg > best_w or (s.weight_kg == best_w and g["date"] < best_d)):
                best_w, best_d = s.weight_kg, g["date"]
    return {"exercise_id": exercise_id, "has_history": True, "date": last["date"],
            "sets": [{"set_number": s.set_number, "reps": s.reps, "weight_kg": s.weight_kg,
                      "reached_failure": s.reached_failure} for s in sets],
            "max_weight_kg": _top_weight([_as_dict(s) for s in sets]), "total_reps": sum(s.reps for s in sets),
            "any_failure": any(flags) if flags else None, "best_weight_kg": best_w, "best_weight_date": best_d}
