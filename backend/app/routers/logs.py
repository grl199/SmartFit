from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import Food, FoodLog
from ..schemas import FrequentFood, LogCreate, LogOut
from ..services.nutrition import create_log, frequent_foods, today_local
from ..services.rag import index_day_task

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=LogOut, status_code=201)
def add_log(body: LogCreate, bg: BackgroundTasks, db: Session = Depends(get_db),
            uid: int = Depends(current_user_id)):
    food = db.get(Food, body.food_id)
    if not food or food.user_id not in (None, uid):
        raise HTTPException(404, "Alimento no encontrado")
    log = create_log(db, uid, food, body.grams, body.meal, body.log_date)
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
