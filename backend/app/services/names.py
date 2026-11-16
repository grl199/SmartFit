"""Nombres de producto en español: limpieza determinista + traducción con IA en segundo plano.

Open Food Facts guarda el nombre comercial del envase («Milbona Cottage Cheese – 200 g»): mezcla marca y cantidad y
a menudo está en otro idioma. Aquí se (1) limpia, (2) usa la «denominación general» como pista y (3) traduce.
El nombre original se conserva en `extra.original_name` y también se usa al buscar."""
import json
import logging
import re
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm import chat_text
from ..models import Food

log = logging.getLogger(__name__)
BATCH = 20
_QTY = re.compile(r"[\s,\-–—]*\(?(?:\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s?(?:kg|g|gr|mg|ml|cl|l|ud|uds|unidades)\)?\.?\s*$", re.I)
_translating = threading.Lock()


def clean_name(name: str | None, brand: str | None = None, quantity: str | None = None) -> str:
    """«Milbona Cottage Cheese – 200 g» (marca Milbona) -> «Cottage Cheese». Nunca devuelve vacío."""
    original = (name or "").strip()
    n = original
    for _ in range(2):  # a veces hay dos sufijos de cantidad
        stripped = _QTY.sub("", n).strip(" -–—,")
        if stripped and stripped != n:
            n = stripped
    if brand:
        m = re.match(rf"^{re.escape(brand.strip())}[\s\-–—:,]+(.+)$", n, re.I)
        if m and len(m.group(1).strip()) >= 3:
            n = m.group(1).strip()
    return n or original


SYSTEM = """\
Eres un experto en productos de supermercado de España. Para cada producto recibirás su nombre actual, su marca y, \
si existe, su denominación general en español. Devuelve el NOMBRE COMÚN EN ESPAÑOL, corto y natural, como lo diría un \
cliente en España.

Reglas:
- Sin marca, sin cantidad ni tamaño de envase.
- Si ya está en español, déjalo igual. Conserva los anglicismos que se usan tal cual en España (cottage, bacon, ketchup…).
- Usa la denominación general como pista, pero no la copies si es larga o técnica (p. ej. «Queso fresco granulado (mínimo \
20% M.G./E.S.)» -> «Queso cottage»).
- No inventes: si dudas, devuelve el nombre actual.
- Devuelve SOLO un JSON, sin texto alrededor: {"names": ["...", "..."]} con el mismo orden y número de elementos que la entrada.
"""


def _extract_json(text: str) -> dict:
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b <= a:
        raise ValueError("sin JSON")
    return json.loads(text[a:b + 1])


def translate_names(items: list[dict]) -> list[str]:
    """items: [{name, brand, generic_name}] -> nombres en español (misma longitud). Lanza si la respuesta no es válida."""
    payload = json.dumps([{"i": i, **it} for i, it in enumerate(items)], ensure_ascii=False)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": payload}]
    names = _extract_json(chat_text(messages, json_mode=True)).get("names")
    if not isinstance(names, list) or len(names) != len(items):
        raise ValueError("el modelo devolvió un número distinto de nombres")
    return [n.strip() if isinstance(n, str) and 2 <= len(n.strip()) <= 120 and "\n" not in n else it["name"]
            for n, it in zip(names, items)]


def translate_pending_names(db: Session, limit: int = BATCH) -> int:
    """Traduce hasta `limit` productos de OFF aún no procesados. Devuelve cuántos procesó (0 = no quedaba nada)."""
    pending = list(db.scalars(
        select(Food).where(Food.source == "openfoodfacts", ~Food.extra.has_key("name_es_done")).order_by(Food.id).limit(limit)))
    if not pending:
        return 0
    new_names = translate_names([{"name": f.name, "brand": f.brand, "generic_name": f.generic_name} for f in pending])
    for food, new in zip(pending, new_names):
        extra = dict(food.extra or {})
        extra["name_es_done"] = True
        if new and new.lower() != food.name.lower():
            extra.setdefault("original_name", food.name)
            food.name = new
        food.extra = extra  # reasignar: JSONB no detecta mutaciones in situ
        db.add(food)
    db.commit()
    return len(pending)


def pending_count(db: Session) -> int:
    from sqlalchemy import func
    return db.scalar(select(func.count()).select_from(Food).where(
        Food.source == "openfoodfacts", ~Food.extra.has_key("name_es_done"))) or 0


def schedule_translation() -> None:
    """Lanza la traducción en un hilo (no bloquea la petición). Una sola a la vez; nunca propaga errores."""
    if not get_settings().translate_names or not _translating.acquire(blocking=False):
        return

    def run() -> None:
        try:
            from ..db import SessionLocal
            with SessionLocal() as db:
                for _ in range(3):
                    if not translate_pending_names(db):
                        break
        except Exception as e:  # noqa: BLE001
            log.warning("Traducción de nombres no completada: %s", e)
        finally:
            _translating.release()

    threading.Thread(target=run, daemon=True, name="translate-names").start()
