from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import Food, FoodLog, FoodServing
from ..schemas import FrequentFood, LogCreate, LogOut, LogUpdate
from ..services.nutrition import create_log, frequent_foods, scale, today_local
from ..services.rag import index_day_task

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=LogOut, status_code=201)
def add_log(body: LogCreate, bg: BackgroundTasks, db: Session = Depends(get_db),
            uid: int = Depends(current_user_id)):
    food = db.get(Food, body.food_id)
    if not food or food.user_id not in (None, uid):
        raise HTTPException(404, "Alimento no encontrado")
    grams = body.grams
    if body.serving_id is not None:   # unidades habituales -> gramos (la equivalencia es propia de cada alimento)
        sv = db.get(FoodServing, body.serving_id)
        if not sv or sv.food_id != food.id:
            raise HTTPException(404, "Unidad no encontrada para este alimento")
        grams = round(body.quantity * sv.grams_per_unit, 2)
        if grams > 5000:
            raise HTTPException(422, "La cantidad supera los 5000 g")
    log = create_log(db, uid, food, grams, body.meal, body.log_date)
    bg.add_task(index_day_task, uid, log.log_date)  # actualiza el resumen diario para el RAG
    return log


@router.get("", response_model=list[LogOut])
def list_logs(day: date | None = Query(None, alias="date"), db: Session = Depends(get_db),
              uid: int = Depends(current_user_id)):
    return db.scalars(select(FoodLog).where(FoodLog.user_id == uid, FoodLog.log_date == (day or today_local()))
                      .order_by(FoodLog.logged_at)).all()


@router.get("/frequent", response_model=list[FrequentFood])
def frequent(limit: int = Query(12, le=30), days: int = Query(60, le=365),
             db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return frequent_foods(db, uid, days, limit)



@router.put("/{log_id}", response_model=LogOut)
def update_log(log_id: int, body: LogUpdate, bg: BackgroundTasks,
               db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Edita cantidad y comida de una ingesta sin perder su identidad ni rehacerla."""
    log = db.get(FoodLog, log_id)
    if not log or log.user_id != uid:
        raise HTTPException(404, "Registro no encontrado")
    log.grams = body.grams
    log.meal = body.meal
    for key, value in scale(log.food, body.grams).items():
        setattr(log, key, value)
    db.add(log)
    db.commit()
    db.refresh(log)
    bg.add_task(index_day_task, uid, log.log_date)
    return log

@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: int, bg: BackgroundTasks, db: Session = Depends(get_db),
               uid: int = Depends(current_user_id)):
    log = db.get(FoodLog, log_id)
    if not log or log.user_id != uid:
        raise HTTPException(404, "Registro no encontrado")
    day = log.log_date
    db.delete(log)
    db.commit()
    bg.add_task(index_day_task, uid, day)
