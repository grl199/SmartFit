"""Búsqueda híbrida: primero Postgres (instantánea, con el catálogo cargado por ingesta batch), y Open Food Facts solo si hace falta."""
import logging

from sqlalchemy.orm import Session

from ..models import Food
from .nutrition import search_foods
from .names import schedule_translation
from .openfoodfacts import online_search_allowed, search_off_and_store

log = logging.getLogger(__name__)
MIN_ONLINE_CHARS = 3
ENOUGH_LOCAL = 5  # con tantos resultados locales no se consulta OFF


def search_hybrid(
    db: Session, user_id: int, query: str, limit: int = 10, online: bool = True, source: str = "all",
) -> list[Food]:
    local = search_foods(db, user_id, query, limit * 2 if source == "all" else limit, source=source)
    q = query.strip()
    # Los filtros explícitos se respetan. En "all" mezclamos ingredientes y productos comerciales;
    # en el filtro exclusivo de OFF seguimos evitando consultas si ya hay suficientes coincidencias.
    if source not in ("all", "openfoodfacts") or not online or len(q) < MIN_ONLINE_CHARS:
        return _limit(local, limit, source)
    if (source == "openfoodfacts" and len(local) >= ENOUGH_LOCAL) or not online_search_allowed(q):
        return _limit(_mix(local, limit) if source == "all" else local, limit, source)
    try:
        added = search_off_and_store(db, q)
        if added:
            schedule_translation()
        refreshed = search_foods(db, user_id, query, limit * 2 if source == "all" else limit, source=source)
        return _limit(_mix(refreshed, limit) if source == "all" else refreshed, limit, source)
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
