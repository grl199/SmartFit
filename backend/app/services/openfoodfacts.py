import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Food

log = logging.getLogger(__name__)
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
OFF_FIELDS = "code,product_name,product_name_es,brands,nutriments,serving_quantity"


@dataclass
class BarcodeResult:
    status: str  # db | openfoodfacts | incomplete | not_found | error
    food: Food | None = None
    name: str | None = None
    brand: str | None = None


def normalize_barcode(raw: str) -> str:
    """Solo dígitos, 8-32. UPC-A (12) se normaliza a EAN-13. Se admiten otras longitudes: OFF también guarda
    códigos de tienda/peso variable (p. ej. los de 24 dígitos de Mercadona), que se consultan igual."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12:
        digits = "0" + digits
    if not 8 <= len(digits) <= 32:
        raise ValueError(f"Código de barras no válido (8-32 dígitos): {raw!r}")
    return digits


def _num(n: dict, key: str) -> float | None:
    try:
        return float(n[key])
    except (KeyError, TypeError, ValueError):
        return None


def parse_off_product(product: dict) -> dict | None:
    """Convierte el JSON de OFF a nuestras columnas (por 100 g). None si no hay datos nutricionales."""
    n = product.get("nutriments") or {}
    kcal = _num(n, "energy-kcal_100g")
    if kcal is None and (kj := _num(n, "energy_100g")) is not None:
        kcal = kj / 4.184
    protein, carbs, fat = _num(n, "proteins_100g"), _num(n, "carbohydrates_100g"), _num(n, "fat_100g")
    if kcal is None and protein is None and carbs is None and fat is None:
        return None
    sodium_g = _num(n, "sodium_100g")
    if sodium_g is None and (salt := _num(n, "salt_100g")) is not None:
        sodium_g = salt / 2.5
    return dict(
        kcal=round(kcal or 0, 1), protein_g=protein or 0, carbs_g=carbs or 0,
        sugars_g=_num(n, "sugars_100g") or 0, fat_g=fat or 0,
        sat_fat_g=_num(n, "saturated-fat_100g") or 0, fiber_g=_num(n, "fiber_100g") or 0,
        sodium_mg=round((sodium_g or 0) * 1000, 1),
    )


def resolve_barcode(db: Session, raw: str) -> BarcodeResult:
    """BD local -> Open Food Facts -> (el agente completa con web_search si hace falta)."""
    code = normalize_barcode(raw)
    if food := db.scalar(select(Food).where(Food.barcode == code)):
        return BarcodeResult("db", food, food.name, food.brand)

    try:
        r = httpx.get(
            OFF_URL.format(code=code), params={"fields": OFF_FIELDS}, timeout=10,
            headers={"User-Agent": get_settings().off_user_agent}, follow_redirects=True,
        )
    except httpx.HTTPError as e:
        log.warning("OFF no disponible: %s", e)
        return BarcodeResult("error")
    if r.status_code == 404 or (r.is_success and r.json().get("status") != 1):
        return BarcodeResult("not_found")
    if not r.is_success:
        return BarcodeResult("error")

    p = r.json()["product"]
    name = p.get("product_name_es") or p.get("product_name") or f"Producto {code}"
    brand = (p.get("brands") or "").split(",")[0].strip() or None
    nutrients = parse_off_product(p)
    if nutrients is None:
        return BarcodeResult("incomplete", None, name, brand)

    serving = _num(p, "serving_quantity")
    food = Food(name=name, brand=brand, barcode=code, source="openfoodfacts", serving_g=serving, **nutrients)
    db.add(food)
    db.commit()
    return BarcodeResult("openfoodfacts", food, name, brand)


# ───────────────────────── Búsqueda por texto (search-a-licious) ─────────────────────────
# OFF limita las búsquedas a 10/min/IP, así que: límite propio, caché de consultas recientes y
# persistencia de todo lo encontrado en Postgres (la siguiente búsqueda ya es local).
SEARCH_FIELDS = "code,product_name,brands,nutriments,serving_quantity"
MAX_ENRICH = 6  # si un hit no trae nutrientes, se completa con la API de producto (100/min) como máximo para N hits


class _RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute, self._hits, self._lock = per_minute, deque(), threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._hits and now - self._hits[0] > 60:
                self._hits.popleft()
            if len(self._hits) >= self.per_minute:
                return False
            self._hits.append(now)
            return True


_limiter = _RateLimiter(get_settings().off_search_per_minute)
_recent_queries: dict[str, float] = {}
RECENT_TTL_S = 6 * 3600


def _nutriments_flat(raw) -> dict:
    """Acepta las formas que puede devolver el índice: dict plano `*_100g`, dict de dicts con "100g",
    o lista de {name, 100g}. Devuelve un dict plano estilo producto OFF."""
    if isinstance(raw, list):
        raw = {str(i.get("name")): i for i in raw if isinstance(i, dict)}
    if not isinstance(raw, dict):
        return {}
    flat = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            if v.get("100g") is not None:
                flat[f"{k}_100g"] = v["100g"]
        else:
            flat[k] = v
    return flat


def parse_search_hit(hit: dict) -> dict | None:
    """Hit del buscador -> {code, name, brand, serving_g, nutrients|None}. None si no sirve (sin código o nombre)."""
    code = re.sub(r"\D", "", str(hit.get("code") or ""))
    name = hit.get("product_name")
    if isinstance(name, dict):  # a veces viene por idioma
        name = name.get("es") or name.get("main") or next(iter(name.values()), None)
    if not code or not name:
        return None
    brands = hit.get("brands")
    brand = (brands[0] if isinstance(brands, list) and brands else str(brands or "").split(",")[0]).strip() or None
    try:
        norm = normalize_barcode(code)
    except ValueError:
        return None
    return {"code": norm, "name": str(name).strip(), "brand": brand, "serving_g": _num(hit, "serving_quantity"),
            "nutrients": parse_off_product({"nutriments": _nutriments_flat(hit.get("nutriments"))})}


def _store(db: Session, item: dict) -> bool:
    stmt = (pg_insert(Food).values(name=item["name"], brand=item["brand"], barcode=item["code"],
                                   source="openfoodfacts", serving_g=item["serving_g"], extra={}, **item["nutrients"])
            .on_conflict_do_nothing(index_elements=["barcode"]).returning(Food.id))
    return db.execute(stmt).scalar() is not None  # rowcount no es fiable con ON CONFLICT (-1 en psycopg)


def search_off_and_store(db: Session, query: str, page_size: int = 10) -> int:
    """Busca en OFF y guarda en `foods` los productos con datos nutricionales. Devuelve cuántos son nuevos."""
    s = get_settings()
    r = httpx.get(s.off_search_url, params={"q": query, "page_size": page_size, "langs": "es,en", "fields": SEARCH_FIELDS},
                  headers={"User-Agent": s.off_user_agent}, timeout=8, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    new = enriched = 0
    for hit in data.get("hits") or data.get("products") or []:
        item = parse_search_hit(hit)
        if not item:
            continue
        if item["nutrients"] is None and enriched < MAX_ENRICH:  # el índice no trajo nutrientes: pide el producto
            enriched += 1
            full = httpx.get(OFF_URL.format(code=item["code"]), params={"fields": OFF_FIELDS},
                             headers={"User-Agent": s.off_user_agent}, timeout=8)
            if full.is_success and full.json().get("status") == 1:
                item["nutrients"] = parse_off_product(full.json()["product"])
        if item["nutrients"] is not None:
            new += _store(db, item)
    db.commit()
    return new


def online_search_allowed(query: str) -> bool:
    """Consulta online solo si es nueva (6 h) y hay cupo; marca la consulta como hecha."""
    key = re.sub(r"\s+", " ", query.strip().lower())
    now = time.monotonic()
    if now - _recent_queries.get(key, -RECENT_TTL_S) < RECENT_TTL_S:
        return False
    if not _limiter.allow():
        return False
    _recent_queries[key] = now
    if len(_recent_queries) > 2000:  # poda simple
        for k, t in list(_recent_queries.items()):
            if now - t > RECENT_TTL_S:
                del _recent_queries[k]
    return True
