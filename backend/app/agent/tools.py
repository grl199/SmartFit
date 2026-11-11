"""Function tools expuestas al modelo (formato Responses API) + dispatcher."""
import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NUTRIENTS, BodyMetric, Food
from ..services import rag
from ..services.nutrition import (
    create_log, daily_series, day_overview, get_targets, search_foods, today_local, workouts_between,
)
from ..services.openfoodfacts import normalize_barcode, resolve_barcode


@dataclass
class ToolContext:
    db: Session
    user_id: int


def _fn(name: str, description: str, properties: dict, required: tuple = ()) -> dict:
    return {"type": "function", "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(required), "additionalProperties": False}}


_DATE = {"type": "string", "description": "Fecha ISO YYYY-MM-DD"}
_NUM = {"type": "number"}

FUNCTION_TOOLS = [
    _fn("get_day_summary", "Totales, objetivos, comidas registradas y entrenos de un día.",
        {"date": {**_DATE, "description": "YYYY-MM-DD; si se omite, hoy"}}),
    _fn("get_period_summary",
        "Totales por día, medias (solo de días con registros), entrenos y pesos en un rango de fechas.",
        {"start_date": _DATE, "end_date": _DATE}, ("start_date", "end_date")),
    _fn("search_foods", "Busca alimentos en la base de datos local por nombre o marca.",
        {"query": {"type": "string"}}, ("query",)),
    _fn("lookup_barcode",
        "Busca un producto por código de barras (BD local y luego Open Food Facts). Devuelve nutrientes por 100 g.",
        {"barcode": {"type": "string"}}, ("barcode",)),
    _fn("create_food",
        "Guarda un alimento en la BD (p. ej. con datos encontrados en la web). Valores POR 100 g.",
        {"name": {"type": "string"}, "brand": {"type": "string"}, "barcode": {"type": "string"},
         "kcal": _NUM, "protein_g": _NUM, "carbs_g": _NUM, "fat_g": _NUM, "sugars_g": _NUM,
         "sat_fat_g": _NUM, "fiber_g": _NUM, "sodium_mg": _NUM,
         "source_url": {"type": "string", "description": "URL de donde salen los datos"}},
        ("name", "kcal", "protein_g", "carbs_g", "fat_g")),
    _fn("log_food", "Registra que el usuario ha consumido `grams` gramos de un alimento. Confirma antes con el usuario.",
        {"food_id": {"type": "integer"}, "grams": _NUM,
         "meal": {"type": "string", "enum": ["breakfast", "lunch", "snack", "dinner"]},
         "date": {**_DATE, "description": "Si se omite, hoy"}}, ("food_id", "grams")),
    _fn("search_history",
        "Búsqueda semántica en la memoria del usuario (resúmenes diarios antiguos y notas guardadas).",
        {"query": {"type": "string"}, "k": {"type": "integer", "description": "1-10, por defecto 5"}}, ("query",)),
    _fn("remember", "Guarda una nota duradera sobre el usuario (alergias, preferencias, lesiones...).",
        {"note": {"type": "string"}}, ("note",)),
]


def _food_dict(f: Food) -> dict:
    return {"id": f.id, "name": f.name, "brand": f.brand, "barcode": f.barcode, "source": f.source,
            "serving_g": f.serving_g, "per_100g": {n: getattr(f, n) for n in NUTRIENTS}}


def _d(s: str | None) -> date:
    return date.fromisoformat(s) if s else today_local()


def get_day_summary(ctx: ToolContext, date: str | None = None) -> dict:
    return day_overview(ctx.db, ctx.user_id, _d(date))


def get_period_summary(ctx: ToolContext, start_date: str, end_date: str) -> dict:
    start, end = _d(start_date), _d(end_date)
    if (end - start).days > 366:
        raise ValueError("Rango máximo: 366 días")
    days = daily_series(ctx.db, ctx.user_id, start, end)
    n = len(days)
    avg = {k: round(sum(d[k] for d in days) / n, 1) for k in NUTRIENTS} if n else {}
    weights = ctx.db.scalars(select(BodyMetric).where(
        BodyMetric.user_id == ctx.user_id, BodyMetric.measured_on.between(start, end))
        .order_by(BodyMetric.measured_on)).all()
    return {
        "range": [start.isoformat(), end.isoformat()], "days_with_logs": n,
        "days_in_range": (end - start).days + 1, "daily_totals": days, "average_per_logged_day": avg,
        "targets": get_targets(ctx.db, ctx.user_id),
        "workouts": [{"date": w.performed_on.isoformat(), "kind": w.kind, "duration_min": w.duration_min}
                     for w in workouts_between(ctx.db, ctx.user_id, start, end)],
        "weights": [{"date": w.measured_on.isoformat(), "kg": w.weight_kg} for w in weights],
    }


def t_search_foods(ctx: ToolContext, query: str) -> dict:
    return {"results": [_food_dict(f) for f in search_foods(ctx.db, ctx.user_id, query, 8)]}


def lookup_barcode(ctx: ToolContext, barcode: str) -> dict:
    res = resolve_barcode(ctx.db, barcode)
    if res.food:
        return {"status": res.status, "food": _food_dict(res.food)}
    hint = {"incomplete": "El producto existe en Open Food Facts pero sin datos nutricionales; busca en la web.",
            "not_found": "No está en Open Food Facts; busca en la web.",
            "error": "Open Food Facts no responde; reintenta o busca en la web."}[res.status]
    return {"status": res.status, "name": res.name, "brand": res.brand, "hint": hint}


def create_food(ctx: ToolContext, name: str, kcal: float, protein_g: float, carbs_g: float, fat_g: float,
                brand: str | None = None, barcode: str | None = None, source_url: str | None = None,
                sugars_g: float = 0, sat_fat_g: float = 0, fiber_g: float = 0, sodium_mg: float = 0) -> dict:
    code = normalize_barcode(barcode) if barcode else None
    if code and (existing := ctx.db.scalar(select(Food).where(Food.barcode == code))):
        return {"status": "already_exists", "food": _food_dict(existing)}
    f = Food(user_id=ctx.user_id, name=name, brand=brand, barcode=code, source="web",
             kcal=kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, sugars_g=sugars_g,
             sat_fat_g=sat_fat_g, fiber_g=fiber_g, sodium_mg=sodium_mg,
             extra={"source_url": source_url} if source_url else {})
    ctx.db.add(f)
    ctx.db.commit()
    return {"status": "created", "food": _food_dict(f)}


def log_food(ctx: ToolContext, food_id: int, grams: float, meal: str | None = None,
             date: str | None = None) -> dict:
    food = ctx.db.get(Food, food_id)
    if not food or food.user_id not in (None, ctx.user_id):
        raise ValueError(f"Alimento {food_id} no existe")
    if not 0 < grams <= 5000:
        raise ValueError("Gramos fuera de rango")
    log = create_log(ctx.db, ctx.user_id, food, grams, meal, _d(date) if date else None)
    rag.index_day_task(ctx.user_id, log.log_date)
    return {"logged": {"food": food.name, "grams": grams, "meal": log.meal,
                       **{n: getattr(log, n) for n in NUTRIENTS}},
            "day_totals": day_overview(ctx.db, ctx.user_id, log.log_date)["totals"]}


def search_history(ctx: ToolContext, query: str, k: int = 5) -> dict:
    return {"results": rag.search_memory(ctx.db, ctx.user_id, query, max(1, min(k, 10)))}


def remember(ctx: ToolContext, note: str) -> dict:
    rag.add_note(ctx.db, ctx.user_id, note)
    return {"saved": True}


HANDLERS = {
    "get_day_summary": get_day_summary, "get_period_summary": get_period_summary,
    "search_foods": t_search_foods, "lookup_barcode": lookup_barcode, "create_food": create_food,
    "log_food": log_food, "search_history": search_history, "remember": remember,
}


def run_tool(ctx: ToolContext, name: str, raw_args: str) -> str:
    """Nunca lanza: los errores vuelven al modelo como JSON para que pueda corregirse."""
    try:
        result = HANDLERS[name](ctx, **json.loads(raw_args or "{}"))
    except Exception as e:  # noqa: BLE001
        ctx.db.rollback()
        result = {"error": f"{type(e).__name__}: {e}"}
    return json.dumps(result, ensure_ascii=False, default=str)
