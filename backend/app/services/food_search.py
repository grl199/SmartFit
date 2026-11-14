"""Búsqueda híbrida: primero Postgres (instantánea), y Open Food Facts solo si hace falta."""
import logging

from sqlalchemy.orm import Session

from ..models import Food
from .nutrition import search_foods
from .openfoodfacts import online_search_allowed, search_off_and_store

log = logging.getLogger(__name__)
MIN_ONLINE_CHARS = 3
ENOUGH_LOCAL = 5  # con tantos resultados locales no se consulta OFF


def search_hybrid(db: Session, user_id: int, query: str, limit: int = 10, online: bool = True) -> list[Food]:
    local = search_foods(db, user_id, query, limit)
    q = query.strip()
    if not online or len(q) < MIN_ONLINE_CHARS or len(local) >= ENOUGH_LOCAL or not online_search_allowed(q):
        return local
    try:
        if search_off_and_store(db, q):
            return search_foods(db, user_id, query, limit)  # ya persistidos: vuelve a leer de BD
    except Exception as e:  # OFF caído, 503, JSON inesperado... nunca rompe la búsqueda local
        db.rollback()
        log.warning("Búsqueda online en OFF fallida: %s", e)
    return local
