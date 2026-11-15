import logging
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import BodyMetric, Exercise, Workout, WorkoutSet
from ..schemas import (
    ExerciseIn, ExerciseOut, WeightIn, WeightOut, WorkoutDetail, WorkoutExerciseOut, WorkoutIn,
)
from ..services import training as tsvc
from ..services.calories import CaloriesNotEstimable, estimate_workout_calories
from ..services.nutrition import today_local
from ..services.rag import index_day_task

log = logging.getLogger(__name__)
router = APIRouter(tags=["training"])


# ───────────── helpers ─────────────
def _details(db: Session, workouts: list[Workout]) -> list[WorkoutDetail]:
    by_workout: dict[int, list[WorkoutSet]] = defaultdict(list)
    if workouts:
        for s in db.scalars(select(WorkoutSet).where(WorkoutSet.workout_id.in_([w.id for w in workouts])).order_by(WorkoutSet.id)):
            by_workout[s.workout_id].append(s)
    out = []
    for w in workouts:
        d = WorkoutDetail.model_validate(w)
        d.exercises = [WorkoutExerciseOut(**g) for g in tsvc.workout_sets_summary(by_workout[w.id])]
        out.append(d)
    return out


def _own_workout(db: Session, wid: int, uid: int) -> Workout:
    w = db.get(Workout, wid)
    if not w or w.user_id != uid:
        raise HTTPException(404, "Sesión no encontrada")
    return w


def _try_estimate(db: Session, w: Workout) -> None:
    """Estima calorías con la IA sin bloquear el guardado: si falla, la sesión queda guardada con una nota."""
    try:
        estimate_workout_calories(db, w)
    except CaloriesNotEstimable as e:
        w.kcal_note = str(e)
    except Exception:  # noqa: BLE001  (red, clave, límite del proveedor, respuesta inválida...)
        log.exception("Fallo estimando calorías")
        w.kcal_note = "No se pudieron estimar las calorías con la IA ahora mismo. Puedes reintentarlo desde el historial."
    db.add(w)
    db.commit()


# ───────────── ejercicios ─────────────
@router.get("/exercises", response_model=list[ExerciseOut])
def list_exercises(category: str | None = None, q: str | None = None, used: bool = False,
                   db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Catálogo compartido + propios. `category` filtra por los músculos de ese tipo de sesión; `used` solo los ya entrenados."""
    return tsvc.visible_exercises(db, uid, category, q, used)


@router.post("/exercises", response_model=ExerciseOut, status_code=201)
def create_exercise(body: ExerciseIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    clash = db.scalar(select(Exercise.id).where(func.lower(Exercise.name) == body.name.strip().lower(),
                                                or_(Exercise.user_id.is_(None), Exercise.user_id == uid)))
    if clash:
        raise HTTPException(409, "Ya existe un ejercicio con ese nombre")
    ex = Exercise(user_id=uid, name=body.name.strip(), primary_muscle=body.primary_muscle,
                  secondary_muscles=[m for m in dict.fromkeys(body.secondary_muscles) if m != body.primary_muscle],
                  equipment=body.equipment)
    db.add(ex)
    db.commit()
    return ex


def _visible_exercise(db: Session, ex_id: int, uid: int) -> Exercise:
    ex = db.get(Exercise, ex_id)
    if not ex or ex.user_id not in (None, uid):
        raise HTTPException(404, "Ejercicio no encontrado")
    return ex


@router.get("/exercises/{exercise_id}/history")
def exercise_history(exercise_id: int, limit: int = Query(10, ge=1, le=50),
                     db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Últimas sesiones en las que se hizo este ejercicio (más reciente primero), para precargar series."""
    _visible_exercise(db, exercise_id, uid)
    return tsvc.exercise_history(db, uid, exercise_id, limit)


@router.get("/exercises/{exercise_id}/progress")
def exercise_progress(exercise_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    _visible_exercise(db, exercise_id, uid)
    return tsvc.exercise_progress(db, uid, exercise_id)


# ───────────── sesiones ─────────────
@router.post("/workouts", response_model=WorkoutDetail, status_code=201)
def add_workout(body: WorkoutIn, bg: BackgroundTasks, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    ex_ids = {s.exercise_id for s in body.sets}
    if ex_ids:
        valid = set(db.scalars(select(Exercise.id).where(Exercise.id.in_(ex_ids), or_(Exercise.user_id.is_(None), Exercise.user_id == uid))))
        if ex_ids - valid:
            raise HTTPException(422, f"Ejercicios no válidos: {sorted(ex_ids - valid)}")
    w = Workout(user_id=uid, performed_on=body.performed_on or today_local(), kind=body.kind.strip(), category=body.category,
                duration_min=body.duration_min, notes=body.notes, kcal_burned=body.kcal_burned,
                kcal_source="manual" if body.kcal_burned is not None else None)
    db.add(w)
    db.flush()
    counters: dict[int, int] = defaultdict(int)
    for s in body.sets:
        counters[s.exercise_id] += 1
        db.add(WorkoutSet(user_id=uid, workout_id=w.id, exercise_id=s.exercise_id, set_number=counters[s.exercise_id],
                          reps=s.reps, weight_kg=s.weight_kg or None, rpe=s.rpe))
    db.commit()
    if body.kcal_burned is None and body.estimate_calories:
        _try_estimate(db, w)
    bg.add_task(index_day_task, uid, w.performed_on)
    return _details(db, [w])[0]


@router.get("/workouts", response_model=list[WorkoutDetail])
def list_workouts(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    since = today_local() - timedelta(days=days)
    ws = db.scalars(select(Workout).where(Workout.user_id == uid, Workout.performed_on >= since)
                    .order_by(Workout.performed_on.desc(), Workout.id.desc())).all()
    return _details(db, list(ws))


@router.get("/workouts/{wid}", response_model=WorkoutDetail)
def get_workout(wid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return _details(db, [_own_workout(db, wid, uid)])[0]


@router.post("/workouts/{wid}/estimate-calories", response_model=WorkoutDetail)
def reestimate(wid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Vuelve a estimar con la IA las calorías de una sesión (sustituye una estimación previa o una manual)."""
    w = _own_workout(db, wid, uid)
    try:
        estimate_workout_calories(db, w)
    except CaloriesNotEstimable as e:
        raise HTTPException(422, str(e))
    except Exception:  # noqa: BLE001
        log.exception("Fallo estimando calorías")
        raise HTTPException(502, "No se pudo contactar con el modelo de IA. Inténtalo de nuevo en unos segundos.")
    return _details(db, [w])[0]


@router.delete("/workouts/{wid}", status_code=204)
def delete_workout(wid: int, bg: BackgroundTasks, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    w = _own_workout(db, wid, uid)
    day = w.performed_on
    db.execute(delete(WorkoutSet).where(WorkoutSet.workout_id == wid))
    db.delete(w)
    db.commit()
    bg.add_task(index_day_task, uid, day)


@router.get("/training/muscles")
def muscles(days: int = Query(7, ge=1, le=365), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Series ponderadas y volumen por grupo muscular en los últimos `days` días (hoy incluido)."""
    end = today_local()
    return tsvc.muscle_summary(db, uid, end - timedelta(days=days - 1), end)


# ───────────── peso corporal ─────────────
@router.post("/metrics/weight", response_model=WeightOut, status_code=201)
def add_weight(body: WeightIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    data = body.model_dump()
    data["measured_on"] = data["measured_on"] or today_local()
    m = BodyMetric(user_id=uid, **data)
    db.add(m)
    db.commit()
    return m


@router.get("/metrics/weight", response_model=list[WeightOut])
def list_weight(days: int = Query(180, le=3650), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    since = today_local() - timedelta(days=days)
    return db.scalars(select(BodyMetric).where(BodyMetric.user_id == uid, BodyMetric.measured_on >= since)
                      .order_by(BodyMetric.measured_on)).all()
