"""Lógica de entrenamiento: volumen por músculo, historial y progresión por ejercicio."""
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import enums
from ..models import Exercise, Workout, WorkoutSet


def estimated_1rm(weight: float | None, reps: int) -> float | None:
    """Fórmula de Epley. Solo tiene sentido con peso externo y ≤ 12 repeticiones."""
    if not weight or weight <= 0 or reps <= 0 or reps > 12:
        return None
    return round(weight * (1 + reps / 30), 1) if reps > 1 else round(weight, 1)


def muscle_summary(db: Session, user_id: int, start: date, end: date) -> dict:
    """Series ponderadas por músculo (principal = 1, cada secundario = 0,5) y volumen (kg x reps)."""
    rows = db.execute(
        select(WorkoutSet, Workout.performed_on).join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(WorkoutSet.user_id == user_id, Workout.performed_on.between(start, end))
    ).all()
    out = {m: {"sets": 0.0, "volume_kg": 0.0, "exercises": set()} for m in enums.MUSCLE_GROUP}
    sessions = set()
    for s, day in rows:
        sessions.add((day, s.workout_id))
        ex = s.exercise
        vol = (s.weight_kg or 0) * s.reps
        targets = [(ex.primary_muscle, 1.0)] + [(m, enums.SECONDARY_WEIGHT) for m in (ex.secondary_muscles or [])]
        for muscle, w in targets:
            if muscle in out:
                out[muscle]["sets"] += w
                out[muscle]["volume_kg"] += vol * w
                out[muscle]["exercises"].add(ex.name)
    return {
        "start": start.isoformat(), "end": end.isoformat(), "sessions": len({w for _, w in sessions}),
        "muscles": {m: {"sets": round(v["sets"], 1), "volume_kg": round(v["volume_kg"]), "exercises": sorted(v["exercises"])}
                    for m, v in out.items()},
    }


def _sets_by_workout(db: Session, user_id: int, exercise_id: int):
    rows = db.execute(
        select(WorkoutSet, Workout.performed_on).join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(WorkoutSet.user_id == user_id, WorkoutSet.exercise_id == exercise_id)
        .order_by(Workout.performed_on.desc(), WorkoutSet.workout_id.desc(), WorkoutSet.set_number)
    ).all()
    grouped: dict[int, dict] = {}
    for s, day in rows:
        g = grouped.setdefault(s.workout_id, {"workout_id": s.workout_id, "date": day, "sets": []})
        g["sets"].append(s)
    return list(grouped.values())  # más reciente primero


def exercise_history(db: Session, user_id: int, exercise_id: int, limit: int = 10) -> list[dict]:
    return [{"workout_id": g["workout_id"], "date": g["date"].isoformat(),
             "sets": [{"set_number": s.set_number, "reps": s.reps, "weight_kg": s.weight_kg, "rpe": s.rpe} for s in g["sets"]]}
            for g in _sets_by_workout(db, user_id, exercise_id)[:limit]]


def exercise_progress(db: Session, user_id: int, exercise_id: int) -> list[dict]:
    """Por sesión: mejor peso, mejor 1RM estimado y volumen total. Orden cronológico."""
    out = []
    for g in reversed(_sets_by_workout(db, user_id, exercise_id)):
        weights = [s.weight_kg for s in g["sets"] if s.weight_kg]
        orms = [e for s in g["sets"] if (e := estimated_1rm(s.weight_kg, s.reps))]
        out.append({"date": g["date"].isoformat(), "best_weight_kg": max(weights) if weights else None,
                    "est_1rm_kg": max(orms) if orms else None, "sets": len(g["sets"]),
                    "volume_kg": round(sum((s.weight_kg or 0) * s.reps for s in g["sets"]))})
    return out


def workout_sets_summary(sets: list[WorkoutSet]) -> list[dict]:
    """Agrupa las series de una sesión por ejercicio (orden de aparición)."""
    groups: dict[int, dict] = {}
    for s in sorted(sets, key=lambda x: (x.id)):
        g = groups.setdefault(s.exercise_id, {"exercise_id": s.exercise_id, "exercise": s.exercise.name,
                                              "primary_muscle": s.exercise.primary_muscle, "sets": []})
        g["sets"].append({"set_number": s.set_number, "reps": s.reps, "weight_kg": s.weight_kg, "rpe": s.rpe})
    return list(groups.values())


def visible_exercises(db: Session, user_id: int, category: str | None = None, q: str | None = None,
                      used_only: bool = False) -> list[Exercise]:
    from sqlalchemy import func, or_
    stmt = select(Exercise).where(or_(Exercise.user_id.is_(None), Exercise.user_id == user_id))
    if category and category in enums.CATEGORY_MUSCLES:
        muscles = enums.CATEGORY_MUSCLES[category]
        if not muscles:
            return []
        stmt = stmt.where(Exercise.primary_muscle.in_(muscles))
    if q:
        stmt = stmt.where(func.unaccent(Exercise.name).ilike(func.unaccent(f"%{q.strip()}%")))
    if used_only:
        used = select(WorkoutSet.exercise_id).where(WorkoutSet.user_id == user_id).distinct()
        stmt = stmt.where(Exercise.id.in_(used))
    return list(db.scalars(stmt.order_by(Exercise.primary_muscle, Exercise.name)))
