from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import BodyMetric, Workout
from ..schemas import WeightIn, WeightOut, WorkoutIn, WorkoutOut
from ..services.nutrition import today_local

router = APIRouter(tags=["training"])


@router.post("/workouts", response_model=WorkoutOut, status_code=201)
def add_workout(body: WorkoutIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    data = body.model_dump()
    data["performed_on"] = data["performed_on"] or today_local()
    w = Workout(user_id=uid, **data)
    db.add(w)
    db.commit()
    return w


@router.get("/workouts", response_model=list[WorkoutOut])
def list_workouts(days: int = Query(30, le=365), db: Session = Depends(get_db),
                  uid: int = Depends(current_user_id)):
    since = today_local() - timedelta(days=days)
    return db.scalars(select(Workout).where(Workout.user_id == uid, Workout.performed_on >= since)
                      .order_by(Workout.performed_on.desc(), Workout.id.desc())).all()


@router.delete("/workouts/{wid}", status_code=204)
def delete_workout(wid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    w = db.get(Workout, wid)
    if not w or w.user_id != uid:
        raise HTTPException(404, "No encontrado")
    db.delete(w)
    db.commit()


@router.post("/metrics/weight", response_model=WeightOut, status_code=201)
def add_weight(body: WeightIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    data = body.model_dump()
    data["measured_on"] = data["measured_on"] or today_local()
    m = BodyMetric(user_id=uid, **data)
    db.add(m)
    db.commit()
    return m


@router.get("/metrics/weight", response_model=list[WeightOut])
def list_weight(days: int = Query(180, le=3650), db: Session = Depends(get_db),
                uid: int = Depends(current_user_id)):
    since = today_local() - timedelta(days=days)
    return db.scalars(select(BodyMetric).where(BodyMetric.user_id == uid, BodyMetric.measured_on >= since)
                      .order_by(BodyMetric.measured_on)).all()
