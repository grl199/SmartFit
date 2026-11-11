"""Memoria a largo plazo: embeddings en pgvector.

Qué se indexa (y para qué):
  - daily_summary: un texto por día (comidas + totales vs objetivo + entreno) -> preguntas cualitativas/
    fuzzy sobre el pasado ("¿cuándo comí fuera?", "¿cómo fue mi semana de viaje?").
  - note: hechos duraderos que el agente guarda con la tool `remember` (intolerancias, preferencias...).
Las preguntas NUMÉRICAS exactas se resuelven con SQL (tools get_day_summary / get_period_summary), no con RAG.
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..llm import get_client
from ..models import FoodLog, MemoryChunk
from .nutrition import day_overview

log = logging.getLogger(__name__)
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MEALS = {"breakfast": "Desayuno", "lunch": "Comida", "snack": "Merienda/snack", "dinner": "Cena"}


def embed(texts: list[str]) -> list[list[float]]:
    resp = get_client().embeddings.create(model=get_settings().embedding_model, input=texts)
    return [d.embedding for d in resp.data]


def build_daily_summary(db: Session, user_id: int, day: date) -> str | None:
    ov = day_overview(db, user_id, day)
    if not ov["entries"] and not ov["workouts"]:
        return None
    t, g = ov["totals"], ov["targets"]
    lines = [f"Resumen del {day.isoformat()} ({WEEKDAYS[day.weekday()]}).",
             f"Total: {t['kcal']:.0f} kcal (objetivo {g.get('kcal', 0):.0f}), proteína {t['protein_g']:.0f} g "
             f"(objetivo {g.get('protein_g', 0):.0f}), hidratos {t['carbs_g']:.0f} g, grasa {t['fat_g']:.0f} g, "
             f"fibra {t['fiber_g']:.0f} g."]
    by_meal: dict[str, list[str]] = {}
    for e in ov["entries"]:
        by_meal.setdefault(MEALS.get(e["meal"], e["meal"]), []).append(f"{e['food']} {e['grams']:.0f} g")
    lines += [f"{m}: {', '.join(items)}." for m, items in by_meal.items()]
    for w in ov["workouts"]:
        lines.append(f"Entrenamiento: {w['kind']}, {w['duration_min']} min.")
    return "\n".join(lines)


def _upsert(db: Session, user_id: int, kind: str, content: str, ref_date: date | None) -> None:
    vec = embed([content])[0]
    stmt = insert(MemoryChunk).values(user_id=user_id, kind=kind, ref_date=ref_date, content=content, embedding=vec)
    if ref_date is not None:
        stmt = stmt.on_conflict_do_update(constraint="uq_memory_user_kind_date",
                                          set_={"content": content, "embedding": vec})
    db.execute(stmt)
    db.commit()


def index_day(db: Session, user_id: int, day: date) -> bool:
    text = build_daily_summary(db, user_id, day)
    if text is None:
        return False
    _upsert(db, user_id, "daily_summary", text, day)
    return True


def index_day_task(user_id: int, day: date) -> None:
    """Para BackgroundTasks: sesión propia y sin romper la petición si OpenAI falla."""
    try:
        with SessionLocal() as db:
            index_day(db, user_id, day)
    except Exception:
        log.exception("Fallo indexando %s", day)


def reindex_all(db: Session, user_id: int) -> int:
    days = db.scalars(select(FoodLog.log_date).where(FoodLog.user_id == user_id).distinct()).all()
    return sum(index_day(db, user_id, d) for d in days)


def add_note(db: Session, user_id: int, text: str) -> None:
    _upsert(db, user_id, "note", text, None)


def search_memory(db: Session, user_id: int, query: str, k: int = 5) -> list[dict]:
    qv = embed([query])[0]
    dist = MemoryChunk.embedding.cosine_distance(qv).label("dist")
    rows = db.execute(select(MemoryChunk, dist).where(MemoryChunk.user_id == user_id)
                      .order_by(dist).limit(k)).all()
    return [{"kind": m.kind, "date": m.ref_date.isoformat() if m.ref_date else None,
             "content": m.content, "similarity": round(1 - d, 3)} for m, d in rows]
