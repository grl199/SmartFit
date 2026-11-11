"""Memoria a largo plazo: embeddings en pgvector.

El proveedor de embeddings sigue AI_PROVIDER: Hugging Face evita llamadas de
embeddings a OpenAI cuando está seleccionado.
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..llm import embed_texts
from ..models import FoodLog, MemoryChunk
from .nutrition import day_overview

log = logging.getLogger(__name__)
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MEALS = {"breakfast": "Desayuno", "lunch": "Comida", "snack": "Merienda/snack", "dinner": "Cena"}


def embed(texts: list[str]) -> list[list[float]]:
    return embed_texts(texts)


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
    for entry in ov["entries"]:
        by_meal.setdefault(MEALS.get(entry["meal"], entry["meal"]), []).append(
            f"{entry['food']} {entry['grams']:.0f} g"
        )
    lines += [f"{meal}: {', '.join(items)}." for meal, items in by_meal.items()]
    for workout in ov["workouts"]:
        lines.append(f"Entrenamiento: {workout['kind']}, {workout['duration_min']} min.")
    return "\n".join(lines)


def _upsert(db: Session, user_id: int, kind: str, content: str, ref_date: date | None) -> None:
    vector = embed([content])[0]
    stmt = insert(MemoryChunk).values(
        user_id=user_id, kind=kind, ref_date=ref_date, content=content, embedding=vector
    )
    if ref_date is not None:
        stmt = stmt.on_conflict_do_update(
            constraint="uq_memory_user_kind_date",
            set_={"content": content, "embedding": vector},
        )
    db.execute(stmt)
    db.commit()


def index_day(db: Session, user_id: int, day: date) -> bool:
    summary = build_daily_summary(db, user_id, day)
    if summary is None:
        return False
    _upsert(db, user_id, "daily_summary", summary, day)
    return True


def index_day_task(user_id: int, day: date) -> None:
    """Para BackgroundTasks: sesión propia y sin romper la petición si el proveedor falla."""
    try:
        with SessionLocal() as db:
            index_day(db, user_id, day)
    except Exception:
        log.exception("Fallo indexando %s", day)


def reindex_all(db: Session, user_id: int) -> int:
    days = db.scalars(
        select(FoodLog.log_date).where(FoodLog.user_id == user_id).distinct()
    ).all()
    return sum(index_day(db, user_id, day) for day in days)


def add_note(db: Session, user_id: int, text: str) -> None:
    _upsert(db, user_id, "note", text, None)


def search_memory(db: Session, user_id: int, query: str, k: int = 5) -> list[dict]:
    query_vector = embed([query])[0]
    distance = MemoryChunk.embedding.cosine_distance(query_vector).label("dist")
    rows = db.execute(
        select(MemoryChunk, distance).where(MemoryChunk.user_id == user_id)
        .order_by(distance).limit(k)
    ).all()
    return [
        {"kind": memory.kind, "date": memory.ref_date.isoformat() if memory.ref_date else None,
         "content": memory.content, "similarity": round(1 - dist, 3)}
        for memory, dist in rows
    ]
