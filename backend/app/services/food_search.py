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
    local = search_foods(db, user_id, query, limit, source=source)
    q = query.strip()
    # Un filtro local no se completa en segundo plano con resultados de otra fuente.
    if source not in ("all", "openfoodfacts") or not online or len(q) < MIN_ONLINE_CHARS:
        return local
    if len(local) >= ENOUGH_LOCAL or not online_search_allowed(q):
        return local
    try:
        if search_off_and_store(db, q):
            schedule_translation()
            return search_foods(db, user_id, query, limit, source=source)
    except Exception as e:  # OFF caído, 503, JSON inesperado... nunca rompe la búsqueda local
        db.rollback()
        log.warning("Búsqueda online en OFF fallida: %s", e)
    return local
