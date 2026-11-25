"""Búsqueda híbrida: primero Postgres (instantánea, con el catálogo cargado por ingesta batch), y Open Food Facts solo si hace falta."""
import logging

from sqlalchemy.orm import Session

from ..models import Food
from .nutrition import search_foods
from .names import schedule_translation
from .openfoodfacts import online_search_allowed, search_off_and_store

log = logging.getLogger(__name__)
MIN_ONLINE_CHARS = 2


def search_hybrid(
    db: Session, user_id: int, query: str, limit: int = 10, online: bool = True, source: str = "all",
) -> list[Food]:
    effective_source = "catalog" if source == "generic" else source
    local = search_foods(db, user_id, query, limit * 2 if source == "all" else limit, source=effective_source)
    q = query.strip()
    # El filtro exclusivo de OFF sigue consultando la fuente externa aunque haya pocas o varias coincidencias locales;
    # en "all" se mezclan resultados genéricos, personales y de marca.
    if source not in ("all", "openfoodfacts") or not online or len(q) < MIN_ONLINE_CHARS:
        return _limit(local, limit, effective_source)
    if not online_search_allowed(q):
        return _limit(_mix(local, limit) if source == "all" else local, limit, effective_source)
    try:
        added = search_off_and_store(db, q)
        if added:
            schedule_translation()
        refreshed = search_foods(db, user_id, query, limit * 2 if source == "all" else limit, source=source)
        return _limit(_mix(refreshed, limit) if source == "all" else refreshed, limit, effective_source)
    except Exception as e:  # OFF caído, 503, JSON inesperado... nunca rompe la búsqueda local
        db.rollback()
        log.warning("Búsqueda online en OFF fallida: %s", e)
    return _limit(_mix(local, limit) if source == "all" else local, limit, source)


def _mix(items: list[Food], limit: int) -> list[Food]:
    """Alterna alimentos genéricos/personales con productos de marca para que ambas familias aparezcan."""
    generic = [f for f in items if f.source != "openfoodfacts"]
    branded = [f for f in items if f.source == "openfoodfacts"]
    mixed: list[Food] = []
    while (generic or branded) and len(mixed) < limit:
        for pool, count in ((generic, 2), (branded, 1)):
            for _ in range(count):
                if pool and len(mixed) < limit:
                    mixed.append(pool.pop(0))
    return mixed


def _limit(items: list[Food], limit: int, source: str) -> list[Food]:
    return _mix(items, limit) if source == "all" else items[:limit]
