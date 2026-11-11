import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import NUTRIENTS, BodyMetric, Food, FoodLog, UserTarget, Workout

TARGET_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def today_local() -> date:
    return now_local().date()


def scale(food, grams: float) -> dict[str, float]:
    """Nutrientes consumidos = valor_por_100g * gramos / 100."""
    k = grams / 100
    return {n: round((getattr(food, n) or 0) * k, 2) for n in NUTRIENTS}


def guess_meal(hour: int) -> str:
    return "breakfast" if hour < 11 else "lunch" if hour < 16 else "snack" if hour < 19 else "dinner"


def create_log(db: Session, user_id: int, food: Food, grams: float,
               meal: str | None = None, log_date: date | None = None) -> FoodLog:
    now = now_local()
    if log_date and log_date != now.date():
        logged_at = datetime.combine(log_date, time(12, 0), tzinfo=now.tzinfo)
    else:
        logged_at, log_date = now, now.date()
    log = FoodLog(
        user_id=user_id, food_id=food.id, logged_at=logged_at, log_date=log_date, grams=grams,
        meal=meal or guess_meal(logged_at.hour), **scale(food, grams),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def search_foods(db: Session, user_id: int, query: str, limit: int = 10) -> list[Food]:
    """Todos los tokens deben aparecer en nombre o marca (sin acentos ni mayúsculas).
    Los alimentos que el usuario ya ha consumido salen primero."""
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    if not tokens:
        return []
    conds = [
        or_(func.unaccent(Food.name).ilike(func.unaccent(f"%{t}%")),
            func.unaccent(func.coalesce(Food.brand, "")).ilike(func.unaccent(f"%{t}%")))
        for t in tokens
    ]
    used = (select(FoodLog.food_id, func.count().label("n")).where(FoodLog.user_id == user_id)
            .group_by(FoodLog.food_id).subquery())
    q = (select(Food).outerjoin(used, used.c.food_id == Food.id)
         .where(or_(Food.user_id.is_(None), Food.user_id == user_id), *conds)
         .order_by(func.coalesce(used.c.n, 0).desc(), func.length(Food.name)).limit(limit))
    return list(db.scalars(q))


def frequent_foods(db: Session, user_id: int, days: int = 60, limit: int = 12) -> list[dict]:
    since = now_local() - timedelta(days=days)
    rows = db.execute(
        select(FoodLog.food_id, func.count().label("times"), func.avg(FoodLog.grams).label("avg_g"),
               func.max(FoodLog.logged_at).label("last"))
        .where(FoodLog.user_id == user_id, FoodLog.logged_at >= since)
        .group_by(FoodLog.food_id)
        .order_by(func.count().desc(), func.max(FoodLog.logged_at).desc()).limit(limit)
    ).all()
    foods = {f.id: f for f in db.scalars(select(Food).where(Food.id.in_([r.food_id for r in rows])))}
    return [
        {"food": foods[r.food_id], "times": r.times,
         "typical_grams": max(5.0, round(float(r.avg_g) / 5) * 5), "last_logged": r.last}
        for r in rows
    ]


def _sums():
    return [func.coalesce(func.sum(getattr(FoodLog, n)), 0).label(n) for n in NUTRIENTS]


def day_totals(db: Session, user_id: int, day: date) -> dict[str, float]:
    row = db.execute(select(*_sums()).where(FoodLog.user_id == user_id, FoodLog.log_date == day)).one()
    return {n: round(float(getattr(row, n)), 1) for n in NUTRIENTS}


def daily_series(db: Session, user_id: int, start: date, end: date) -> list[dict]:
    """Solo días con registros (un día sin registros no es un día de 0 kcal, es un día sin datos)."""
    rows = db.execute(
        select(FoodLog.log_date, *_sums())
        .where(FoodLog.user_id == user_id, FoodLog.log_date.between(start, end))
        .group_by(FoodLog.log_date).order_by(FoodLog.log_date)
    ).all()
    return [{"log_date": r.log_date.isoformat(), **{n: round(float(getattr(r, n)), 1) for n in NUTRIENTS}}
            for r in rows]


def get_targets(db: Session, user_id: int) -> dict:
    t = db.get(UserTarget, user_id)
    d = {f: getattr(t, f) for f in TARGET_FIELDS} if t else {}
    d["workouts_per_week"] = t.workouts_per_week if t else 3
    return d


def workouts_between(db: Session, user_id: int, start: date, end: date) -> list[Workout]:
    return list(db.scalars(
        select(Workout).where(Workout.user_id == user_id, Workout.performed_on.between(start, end))
        .order_by(Workout.performed_on)))


def latest_weight(db: Session, user_id: int) -> BodyMetric | None:
    return db.scalar(select(BodyMetric).where(BodyMetric.user_id == user_id)
                     .order_by(BodyMetric.measured_on.desc()).limit(1))


def day_overview(db: Session, user_id: int, day: date) -> dict:
    logs = db.scalars(select(FoodLog).where(FoodLog.user_id == user_id, FoodLog.log_date == day)
                      .order_by(FoodLog.logged_at)).all()
    return {
        "date": day.isoformat(),
        "totals": day_totals(db, user_id, day),
        "targets": get_targets(db, user_id),
        "entries": [{
            "id": l.id, "time": l.logged_at.astimezone(ZoneInfo(get_settings().timezone)).strftime("%H:%M"),
            "meal": l.meal, "food": l.food.name, "brand": l.food.brand, "grams": l.grams,
            "kcal": l.kcal, "protein_g": l.protein_g, "carbs_g": l.carbs_g, "fat_g": l.fat_g,
        } for l in logs],
        "workouts": [{"id": w.id, "kind": w.kind, "duration_min": w.duration_min,
                      "kcal_burned": w.kcal_burned} for w in workouts_between(db, user_id, day, day)],
    }
