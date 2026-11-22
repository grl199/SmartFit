import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..llm import chat_text
from ..models import Exercise, ExerciseContent, TrainingPlan, TrainingPlanDay, UserTarget
from ..services import exercise_content as content_svc
from ..services import training_plan as plans

log = logging.getLogger(__name__)
router = APIRouter(tags=["plan"])


class GenerateIn(BaseModel):
    use_ai: bool = True


class DayExerciseIn(BaseModel):
    exercise_id: int
    sets: int = Field(3, ge=1, le=8)
    reps_min: int = Field(8, ge=1, le=50)
    reps_max: int = Field(12, ge=1, le=50)
    rest_s: int | None = Field(None, ge=0, le=600)
    notes: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def _range(self):
        if self.reps_min > self.reps_max:
            raise ValueError("reps_min no puede superar reps_max")
        return self


class DayIn(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=120)
    exercises: list[DayExerciseIn] = Field(max_length=12)


class ContentIn(BaseModel):
    description: str | None = Field(None, max_length=1500)
    start_position: str | None = Field(None, max_length=800)
    instructions: list[str] = Field(default=[], max_length=15)
    common_mistakes: list[str] = Field(default=[], max_length=10)
    image_url: str | None = Field(None, max_length=500, pattern=r"^https://")
    video_url: str | None = Field(None, max_length=500, pattern=r"^https://")
    media_type: str | None = Field(None, pattern=r"^(image|gif|video)$")
    media_credit: str | None = Field(None, max_length=300)


def _visible(db: Session, ex_id: int, uid: int) -> Exercise:
    ex = db.get(Exercise, ex_id)
    if not ex or ex.user_id not in (None, uid):
        raise HTTPException(404, "Ejercicio no encontrado")
    return ex


# ───────────── plan estructurado ─────────────
@router.get("/plan")
def get_plan(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Plan activo estructurado (o None) + el texto del plan antiguo, para planes creados antes de existir la estructura."""
    plan = plans.active_plan(db, uid)
    t = db.get(UserTarget, uid)
    data = plans.serialize_plan(plan, db) if plan else None
    return {"has_plan": plan is not None, "plan": data, "legacy_markdown": t.training_plan if t else None,
            "suggested_day_id": plans.suggested_day_id(db, plan, data) if plan else None}


@router.post("/plan/generate")
def generate(body: GenerateIn | None = None, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """(Re)genera el plan estructurado: la IA propone con ejercicios reales del catálogo y, si falla, se usan reglas por código."""
    try:
        plans.generate_plan(db, uid, chat=chat_text, use_ai=(body.use_ai if body else True))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return get_plan(db, uid)


@router.put("/plan/days/{day_id}")
def edit_day(day_id: int, body: DayIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Sustituye los ejercicios de un día (añadir, quitar, cambiar series/reps o sustituir un ejercicio por otro)."""
    day = db.get(TrainingPlanDay, day_id)
    plan = db.get(TrainingPlan, day.plan_id) if day else None
    if not day or plan.user_id != uid:
        raise HTTPException(404, "Día no encontrado")
    ids = {e.exercise_id for e in body.exercises}
    valid = set(db.scalars(select(Exercise.id).where(Exercise.id.in_(ids), (Exercise.user_id.is_(None)) | (Exercise.user_id == uid))))
    if ids - valid:
        raise HTTPException(422, f"Ejercicios no válidos: {sorted(ids - valid)}")
    plans.replace_day(db, day, body.label, [plans.PlanExerciseSpec(**e.model_dump()) for e in body.exercises])
    plan.source = "manual"
    db.commit()
    return get_plan(db, uid)


# ───────────── contenido didáctico ─────────────
@router.put("/exercises/{exercise_id}/content")
def put_exercise_content(exercise_id: int, body: ContentIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Solo en ejercicios propios: el contenido del catálogo compartido no se edita."""
    ex = _visible(db, exercise_id, uid)
    if ex.user_id != uid:
        raise HTTPException(403, "Solo puedes editar la ficha de tus propios ejercicios")
    row = db.get(ExerciseContent, ex.id) or ExerciseContent(exercise_id=ex.id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    return content_svc.content_for(db, ex)
