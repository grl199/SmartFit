"""Traducción por lotes (una sola vez) de los nombres en inglés de una fuente importada, con la IA.

Es un paso EXPLÍCITO y reanudable (`name_es_done` marca lo ya hecho): la ingesta no lanza llamadas a la IA por su cuenta. El nombre original se
conserva en `extra.original_name` y sigue siendo buscable."""
from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..llm import chat_text
from ..models import Food
from ..services.names import _extract_json

log = logging.getLogger(__name__)

SYSTEM = """\
Eres nutricionista en España. Recibirás descripciones de alimentos GENÉRICOS de la base USDA (en inglés, formato «Alimento, \
característica, preparación»). Devuelve para cada una el nombre natural en español de España que usaría una persona en una app de nutrición.

Reglas:
- Alimento primero y detalles después, breve: «Chicken, broilers or fryers, breast, meat only, cooked, roasted» -> «Pechuga de pollo asada».
- Conserva lo que cambia los nutrientes (crudo/cocido, con/sin piel, entero/desnatado, enlatado, en almíbar...). Elimina códigos técnicos.
- No inventes ni mezcles alimentos. Si no sabes traducirlo con seguridad, devuelve el original sin cambios.
- Máximo 80 caracteres, sin saltos de línea.
Entrada: JSON [{"i": n, "name": "..."}]. Responde SOLO con JSON: {"names": ["...", ...]} en el mismo orden y con la misma longitud.
"""


def _pending_query(source: str):
    return select(Food).where(Food.source == source, Food.user_id.is_(None), ~Food.extra.has_key("name_es_done")).order_by(Food.id)


def pending(db: Session, source: str = "usda") -> int:
    return db.scalar(select(func.count()).select_from(_pending_query(source).subquery())) or 0


def translate_batch(items: list[str]) -> list[str]:
    payload = json.dumps([{"i": i, "name": n} for i, n in enumerate(items)], ensure_ascii=False)
    names = _extract_json(chat_text([{"role": "system", "content": SYSTEM}, {"role": "user", "content": payload}], json_mode=True)).get("names")
    if not isinstance(names, list) or len(names) != len(items):
        raise ValueError("el modelo devolvió un número distinto de nombres")
    return [n.strip() if isinstance(n, str) and 2 <= len(n.strip()) <= 120 and "\n" not in n else orig for n, orig in zip(names, items)]


def translate_source(db: Session, source: str = "usda", limit: int | None = None, batch: int = 25, progress=lambda done, total: None) -> int:
    """Traduce hasta `limit` alimentos pendientes. Cada lote se guarda al terminar: si se corta, se reanuda donde se quedó."""
    total = min(pending(db, source), limit) if limit else pending(db, source)
    done = 0
    while done < total:
        foods = list(db.scalars(_pending_query(source).limit(min(batch, total - done))))
        if not foods:
            break
        for food, new in zip(foods, translate_batch([f.name for f in foods])):
            extra = dict(food.extra or {})
            extra["name_es_done"] = True
            if new and new.lower() != food.name.lower():
                extra.setdefault("original_name", food.name)
                food.name = new
            food.extra = extra                   # reasignar: JSONB no detecta mutaciones in situ
            db.add(food)
        db.commit()
        done += len(foods)
        progress(done, total)
    return done
