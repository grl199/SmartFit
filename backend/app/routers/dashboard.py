from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..services.nutrition import daily_series, day_overview, get_targets, today_local

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/day")
def day(day: date | None = Query(None, alias="date"), db: Session = Depends(get_db),
        uid: int = Depends(current_user_id)):
    return day_overview(db, uid, day or today_local())


@router.get("/range")
def range_(days: int = Query(14, ge=1, le=180), db: Session = Depends(get_db),
           uid: int = Depends(current_user_id)):
    end = today_local()
    return {"start": (end - timedelta(days=days - 1)).isoformat(), "end": end.isoformat(),
            "targets": get_targets(db, uid),
            "days": daily_series(db, uid, end - timedelta(days=days - 1), end)}
