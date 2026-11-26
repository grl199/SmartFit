from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..clock import now_local, today_local
from ..db import get_db
from ..deps import current_user_id
from ..models import ActivityConnection, DailyActivity, DailyCheckIn, HydrationLog
from ..services import habits as svc
from ..services.activity_providers import PROVIDERS, SOURCES, DailyActivityIn

router = APIRouter(tags=["habits"])
Score = Field(ge=1, le=5)


def _not_future(d: date) -> None:
    if d > today_local():
        raise HTTPException(422, "La fecha no puede ser futura")


# ═════════ Agua ═════════
class WaterIn(BaseModel):
    quantity_ml: int = Field(gt=0, le=5000)
    log_date: date | None = None
    source: str = Field("manual", pattern=r"^(manual|quick)$")


@router.post("/water", status_code=201)
def add_water(body: WaterIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    now = now_local()
    day = body.log_date or now.date()
    _not_future(day)
    row = HydrationLog(user_id=uid, logged_at=now, log_date=day, quantity_ml=body.quantity_ml, source=body.source)
    db.add(row)
    db.commit()
    return {"id": row.id, "log_date": day, "quantity_ml": row.quantity_ml, "source": row.source, "logged_at": row.logged_at,
            "today": svc.water_summary(db, uid, today_local(), 1)}


@router.get("/water")
def list_water(day: date | None = Query(None, alias="date"), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    rows = db.scalars(select(HydrationLog).where(HydrationLog.user_id == uid, HydrationLog.log_date == (day or today_local()))
                      .order_by(HydrationLog.logged_at)).all()
    return [{"id": r.id, "logged_at": r.logged_at, "log_date": r.log_date, "quantity_ml": r.quantity_ml, "source": r.source} for r in rows]


@router.get("/water/summary")
def water_summary(days: int = Query(7, ge=1, le=180), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return svc.water_summary(db, uid, today_local(), days)


@router.delete("/water/{wid}", status_code=204)
def delete_water(wid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    row = db.get(HydrationLog, wid)
    if not row or row.user_id != uid:
        raise HTTPException(404, "Registro no encontrado")
    db.delete(row)
    db.commit()


# ═════════ Check-in emocional (privado) ═════════
class CheckInIn(BaseModel):
    mood: int = Score
    energy_level: int | None = Field(None, ge=1, le=5)
    stress_level: int | None = Field(None, ge=1, le=5)
    sleep_quality: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=2000)


def _checkin_out(c: DailyCheckIn) -> dict:
    return {"date": c.checkin_date, "mood": c.mood, "energy_level": c.energy_level, "stress_level": c.stress_level,
            "sleep_quality": c.sleep_quality, "notes": c.notes}


@router.put("/checkins/{day}")
def put_checkin(day: date, body: CheckInIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Un registro por usuario y día: si ya existe se edita. Las notas son privadas y no se envían a la IA."""
    _not_future(day)
    row = db.scalar(select(DailyCheckIn).where(DailyCheckIn.user_id == uid, DailyCheckIn.checkin_date == day)) \
        or DailyCheckIn(user_id=uid, checkin_date=day)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    return _checkin_out(row)


@router.get("/checkins")
def list_checkins(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    start = today_local() - timedelta(days=days - 1)
    rows = db.scalars(select(DailyCheckIn).where(DailyCheckIn.user_id == uid, DailyCheckIn.checkin_date >= start)
                      .order_by(DailyCheckIn.checkin_date)).all()
    return [_checkin_out(r) for r in rows]


@router.delete("/checkins/{day}", status_code=204)
def delete_checkin(day: date, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    n = db.execute(delete(DailyCheckIn).where(DailyCheckIn.user_id == uid, DailyCheckIn.checkin_date == day)).rowcount
    db.commit()
    if not n:
        raise HTTPException(404, "No hay check-in ese día")


# ═════════ Actividad (pasos) ═════════
class ManualActivityIn(BaseModel):
    activity_date: date | None = None
    steps: int = Field(ge=0, le=200_000)
    distance_km: float | None = Field(None, ge=0, le=500)
    active_calories: float | None = Field(None, ge=0, le=20_000)


class SyncIn(BaseModel):
    source: str
    items: list[DailyActivityIn] = Field(max_length=400)


class ConnectIn(BaseModel):
    provider: str


def _upsert_activity(db: Session, uid: int, source: str, item: DailyActivityIn) -> DailyActivity:
    row = db.scalar(select(DailyActivity).where(DailyActivity.user_id == uid, DailyActivity.activity_date == item.activity_date,
                                                DailyActivity.source == source)) or DailyActivity(user_id=uid, activity_date=item.activity_date, source=source)
    row.steps, row.distance_km, row.active_calories, row.external_id = item.steps, item.distance_km, item.active_calories, item.external_id
    row.synced_at = now_local()
    db.add(row)
    return row


@router.put("/activity")
def put_activity(body: ManualActivityIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Registro manual de pasos de un día (se puede corregir reenviando el mismo día)."""
    day = body.activity_date or today_local()
    _not_future(day)
    _upsert_activity(db, uid, "manual", DailyActivityIn(activity_date=day, steps=body.steps, distance_km=body.distance_km,
                                                        active_calories=body.active_calories))
    db.commit()
    return svc.activity_summary(db, uid, today_local(), 7)


@router.post("/activity/sync")
def sync_activity(body: SyncIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Entrada normalizada desde un proveedor (p. ej. la app Android con Health Connect). Exige consentimiento vigente para esa
    fuente y es IDEMPOTENTE: reenviar el mismo día y fuente actualiza la fila, no la duplica."""
    if body.source not in PROVIDERS:
        raise HTTPException(422, f"Fuente no válida. Usa una de: {', '.join(PROVIDERS)}")
    conn = db.scalar(select(ActivityConnection).where(ActivityConnection.user_id == uid, ActivityConnection.provider == body.source))
    if not conn or conn.revoked_at is not None:
        raise HTTPException(403, "No hay consentimiento activo para esta fuente. Conéctala primero en tu perfil.")
    today = today_local()
    if any(i.activity_date > today for i in body.items):
        raise HTTPException(422, "Hay fechas futuras")
    seen: dict[date, DailyActivityIn] = {}
    for i in body.items:                       # si llegan duplicados del mismo día en el lote, gana el último
        seen[i.activity_date] = i
    for i in seen.values():
        _upsert_activity(db, uid, body.source, i)
    db.commit()
    return {"synced_days": len(seen)}


@router.get("/activity")
def list_activity(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    today = today_local()
    eff = svc.effective_steps(db, uid, today - timedelta(days=days - 1), today)
    return [{"date": d.isoformat(), **v} for d, v in sorted(eff.items())]


@router.get("/activity/summary")
def activity_summary(days: int = Query(7, ge=1, le=180), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return svc.activity_summary(db, uid, today_local(), days)


@router.get("/activity/connections")
def list_connections(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    rows = {c.provider: c for c in db.scalars(select(ActivityConnection).where(ActivityConnection.user_id == uid))}
    return [{"provider": k, **v, "connected": k in rows and rows[k].revoked_at is None,
             "consented_at": rows[k].consented_at if k in rows else None} for k, v in PROVIDERS.items()]


@router.post("/activity/connections", status_code=201)
def connect(body: ConnectIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Consentimiento explícito del usuario para recibir datos de esa fuente."""
    if body.provider not in PROVIDERS:
        raise HTTPException(422, "Proveedor no válido")
    row = db.scalar(select(ActivityConnection).where(ActivityConnection.user_id == uid, ActivityConnection.provider == body.provider)) \
        or ActivityConnection(user_id=uid, provider=body.provider)
    row.consented_at, row.revoked_at = now_local(), None
    db.add(row)
    db.commit()
    return {"provider": body.provider, "connected": True}


@router.delete("/activity/connections/{provider}", status_code=204)
def disconnect(provider: str, delete_data: bool = False, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Revoca el consentimiento. Con `delete_data=true` borra también lo ya importado de esa fuente."""
    if provider not in PROVIDERS:
        raise HTTPException(404, "Proveedor no válido")
    row = db.scalar(select(ActivityConnection).where(ActivityConnection.user_id == uid, ActivityConnection.provider == provider))
    if row:
        row.revoked_at = now_local()
    if delete_data:
        db.execute(delete(DailyActivity).where(DailyActivity.user_id == uid, DailyActivity.source == provider))
    db.commit()
