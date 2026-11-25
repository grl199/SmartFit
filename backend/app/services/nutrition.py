import re
import unicodedata
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from ..clock import now_local, today_local  # noqa: F401  (reexportados: otros módulos los importan de aquí)
from ..config import get_settings
from ..models import NUTRIENTS, BodyMetric, Exercise, Food, FoodLog, UserTarget, Workout, WorkoutSet

TARGET_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def scale(food, grams: float) -> dict[str, float]:
    """Nutrientes consumidos = valor_por_100g * gramos / 100."""
    k = grams / 100
    values = {}
    for nutrient in NUTRIENTS:
        per_100g = float(getattr(food, nutrient) or 0)
        # Defensive repair for legacy imports that stored sodium in µg or multiplied mg by 1000.
        if nutrient == "sodium_mg" and per_100g > 10000:
            per_100g /= 1000
        values[nutrient] = round(per_100g * k, 2)
    return values


def guess_meal(hour: int) -> str:
    """Clasifica automáticamente en las cinco comidas del día."""
    return (
        "breakfast" if hour < 10
        else "mid_morning" if hour < 12
        else "lunch" if hour < 16
        else "snack" if hour < 19
        else "dinner"
    )


def create_log(db: Session, user_id: int, food: Food, grams: float,
               meal: str | None = None, log_date: date | None = None, nutrients: dict[str, float] | None = None) -> FoodLog:
    """`nutrients` permite guardar una instantánea ya calculada (recetas con ingredientes modificados); si no, se escala por 100 g."""
    now = now_local()
    # Preserve the date chosen in the diary; logged_at is only the timestamp.
    entry_date = log_date if log_date is not None else now.date()
    logged_at = now if entry_date == now.date() else datetime.combine(entry_date, time(12, 0), tzinfo=now.tzinfo)
    log = FoodLog(
        user_id=user_id, food_id=food.id, logged_at=logged_at, log_date=entry_date, grams=grams,
        meal=meal or guess_meal(logged_at.hour), **(nutrients or scale(food, grams)),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _norm(text_: str) -> str:
    """Minúsculas y sin acentos (equivale a f_unaccent(lower(...)) de Postgres)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text_.lower()) if not unicodedata.combining(c))


def _like(token: str) -> str:
    return "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


FUZZY_THRESHOLD = 0.55  # similitud trigramas más permisiva para marcas, variantes y erratas


def search_foods(
    db: Session, user_id: int, query: str, limit: int = 10, fuzzy: bool = True, source: str = "all",
) -> list[Food]:
    """Busca alimentos (no recetas) y permite separar SmartFit, alimentos propios y Open Food Facts."""
    q_norm = _norm(query).strip()
    tokens = q_norm.split()
    if not tokens:
        return []
    if source == "catalog":
        scope = (Food.user_id.is_(None), Food.source == "catalog")
    elif source == "mine":
        scope = (Food.user_id == user_id, Food.source != "recipe")
    elif source == "openfoodfacts":
        scope = (Food.user_id.is_(None), Food.source == "openfoodfacts")
    else:
        scope = (or_(Food.user_id.is_(None), Food.user_id == user_id), Food.source != "recipe")
    used = (select(FoodLog.food_id, func.count().label("n")).where(FoodLog.user_id == user_id)
            .group_by(FoodLog.food_id).subquery())
    exact = list(db.scalars(
        select(Food).outerjoin(used, used.c.food_id == Food.id)
        .where(*scope, *[Food.search_text.ilike(_like(t), escape="\\") for t in tokens])
        .order_by(func.coalesce(used.c.n, 0).desc(), (func.coalesce(Food.user_id, 0) == user_id).desc(), func.length(Food.name)).limit(limit)))
    if not fuzzy or len(exact) >= limit or len(q_norm) < 4:
        return exact
    db.execute(text(f"SET LOCAL pg_trgm.word_similarity_threshold = {FUZZY_THRESHOLD}"))
    seen = [f.id for f in exact]
    similar = db.scalars(
        select(Food).where(*scope, Food.search_text.op("%>")(q_norm), Food.id.not_in(seen or [0]))
        .order_by(func.word_similarity(q_norm, Food.search_text).desc(), func.length(Food.name)).limit(limit - len(exact)))
    return exact + list(similar)


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
    d["water_ml"] = t.water_ml if t else 2000
    d["steps_goal"] = t.steps_goal if t else 8000
    return d


def workouts_between(db: Session, user_id: int, start: date, end: date) -> list[Workout]:
    return list(db.scalars(
        select(Workout).where(Workout.user_id == user_id, Workout.performed_on.between(start, end))
        .order_by(Workout.performed_on)))


def latest_weight(db: Session, user_id: int) -> BodyMetric | None:
    return db.scalar(select(BodyMetric).where(BodyMetric.user_id == user_id)
                     .order_by(BodyMetric.measured_on.desc(), BodyMetric.id.desc()).limit(1))  # mismo día: gana el último registrado


def _workouts_with_exercises(db: Session, user_id: int, day: date) -> list[dict]:
    ws = workouts_between(db, user_id, day, day)
    names: dict[int, list[str]] = {}
    if ws:
        for wid, name in db.execute(select(WorkoutSet.workout_id, Exercise.name).join(Exercise, Exercise.id == WorkoutSet.exercise_id)
                                    .where(WorkoutSet.workout_id.in_([w.id for w in ws])).order_by(WorkoutSet.id)):
            if name not in names.setdefault(wid, []):
                names[wid].append(name)
    return [{"id": w.id, "kind": w.kind, "category": w.category, "duration_min": w.duration_min,
             "kcal_burned": w.kcal_burned, "exercises": names.get(w.id, []),
             "distance_km": w.distance_km, "steps": w.steps, "elevation_gain_m": w.elevation_gain_m} for w in ws]


def water_ml_on(db: Session, user_id: int, day: date) -> int:
    from ..models import HydrationLog
    return int(db.scalar(select(func.coalesce(func.sum(HydrationLog.quantity_ml), 0)).where(
        HydrationLog.user_id == user_id, HydrationLog.log_date == day)) or 0)


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
            "kcal": l.kcal, "protein_g": l.protein_g, "carbs_g": l.carbs_g, "sugars_g": l.sugars_g,
            "fat_g": l.fat_g, "sat_fat_g": l.sat_fat_g, "fiber_g": l.fiber_g, "sodium_mg": l.sodium_mg,
        } for l in logs],
        "workouts": _workouts_with_exercises(db, user_id, day),
        "water_ml": water_ml_on(db, user_id, day),
    }
