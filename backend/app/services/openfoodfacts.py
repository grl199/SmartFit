import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass

import httpx
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Food, FoodServing
from .names import clean_name, schedule_translation

log = logging.getLogger(__name__)
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
OFF_FIELDS = ("code,product_name,product_name_es,brands,nutriments,serving_quantity,quantity,nutriscore_grade,nova_group,"
              "ecoscore_grade,environmental_score_grade,image_front_small_url,image_front_url,allergens_tags,"
              "ingredients_text_es,ingredients_text,categories,labels,labels_tags,generic_name_es,generic_name,serving_size")

ALLERGENS_ES = {
    "gluten": "Gluten", "milk": "Leche", "eggs": "Huevos", "nuts": "Frutos secos", "peanuts": "Cacahuetes",
    "soybeans": "Soja", "fish": "Pescado", "crustaceans": "Crustáceos", "molluscs": "Moluscos", "celery": "Apio",
    "mustard": "Mostaza", "sesame-seeds": "Sésamo", "sulphur-dioxide-and-sulphites": "Sulfitos", "lupin": "Altramuces",
}


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


def _grade(v) -> str | None:
    v = str(v or "").strip().lower()
    return v if v in ("a", "b", "c", "d", "e") else None  # OFF también devuelve "unknown" / "not-applicable"


def parse_off_meta(product: dict) -> dict:
    """Metadatos de producto (todo opcional) -> columnas de Food. Tolerante: lo que falte queda en None / vacío."""
    try:
        nova = int(product.get("nova_group"))
        nova = nova if 1 <= nova <= 4 else None
    except (TypeError, ValueError):
        nova = None
    allergens = []
    for tag in product.get("allergens_tags") or []:
        code = str(tag).split(":", 1)[-1]
        allergens.append(ALLERGENS_ES.get(code, code.replace("-", " ").capitalize()))
    cats = product.get("categories")
    cats = [c.strip() for c in cats.split(",")] if isinstance(cats, str) else [str(c).split(":", 1)[-1] for c in (cats or [])]
    ingredients = product.get("ingredients_text_es") or product.get("ingredients_text")
    generic = product.get("generic_name_es") or product.get("generic_name")
    raw_labels = product.get("labels_tags") or product.get("labels") or []
    if isinstance(raw_labels, str):
        raw_labels = [x.strip() for x in raw_labels.split(",") if x.strip()]
    labels = [
        str(v).split(":", 1)[-1].replace("-", " ").strip().capitalize()
        for v in raw_labels if str(v).strip()
    ][:12]
    extra = {k: v for k, v in {
        "allergens": allergens, "ingredients": (ingredients or "")[:1500] or None, "categories": [c for c in cats if c][:6],
        "generic_name": str(generic).strip()[:200] if generic else None,
        "labels": labels,
        "serving_size": str(product.get("serving_size") or "").strip()[:120] or None,
    }.items() if v}
    qty = product.get("quantity")
    return dict(
        nutriscore_grade=_grade(product.get("nutriscore_grade")), nova_group=nova,
        ecoscore_grade=_grade(product.get("ecoscore_grade") or product.get("environmental_score_grade")),
        image_url=product.get("image_front_small_url") or product.get("image_front_url") or product.get("image_url") or None,
        quantity=str(qty)[:100] if qty else None, extra=extra,
    )


def parse_serving_unit(serving_size: str | None, serving_quantity, product_name: str = "") -> dict | None:
    """Interpreta solo unidades declaradas explícitamente por OFF; nunca inventa gramos por pieza."""
    text = str(serving_size or "").strip().lower()
    if not text:
        return None
    try:
        total = float(str(serving_quantity).replace(",", ".")) if serving_quantity is not None else None
    except (TypeError, ValueError):
        total = None
    if total is None or total <= 0:
        # Puede aparecer tanto "2 pieces (30 g)" como "30 g (2 pieces)".
        weight = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:g|gr|ml)\b", text)
        if weight:
            total = float(weight.group(1).replace(",", "."))
    patterns = (
        r"^\s*(\d+(?:[.,]\d+)?)\s*(?:x\s*)?([^(),\d]+?)\s*(?:\(|$)",
        r"\(\s*(\d+(?:[.,]\d+)?)\s*([^(),\d]+?)\s*\)",
    )
    count, raw_unit = None, None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                candidate_unit = match.group(2).strip().rstrip("s")
                candidate_name = re.sub(r"[^a-záéíóúüñ]", "", candidate_unit)
                # Skip mass/volume tokens and continue looking for an explicit item count.
                if candidate_name in {"g", "gr", "gram", "grams", "ml", "milliliter", "milliliters", "mililitro", "mililitros"}:
                    continue
                count = float(match.group(1).replace(",", "."))
                raw_unit = candidate_unit
                break
            except (TypeError, ValueError):
                continue
    if not count or count <= 0 or not raw_unit or total is None or total <= 0:
        return None
    name = re.sub(r"[^a-záéíóúüñ]", "", raw_unit)
    if "rega" in str(product_name or "").lower():
        singular, plural = "regañá", "regañás"
    else:
        aliases = {
            "piece": ("unidad", "unidades"), "unit": ("unidad", "unidades"),
            "portion": ("ración", "raciones"), "serving": ("ración", "raciones"),
            "slice": ("rebanada", "rebanadas"), "biscuit": ("galleta", "galletas"),
            "cookie": ("galleta", "galletas"), "cracker": ("cracker", "crackers"),
            "tablespoon": ("cucharada", "cucharadas"), "teaspoon": ("cucharadita", "cucharaditas"),
            "bar": ("barrita", "barritas"), "unidad": ("unidad", "unidades"),
            "ración": ("ración", "raciones"), "galleta": ("galleta", "galletas"),
            "rebanada": ("rebanada", "rebanadas"), "loncha": ("loncha", "lonchas"),
            "trozo": ("trozo", "trozos"),
        }
        singular, plural = aliases.get(name, (name, name + ("s" if not name.endswith("s") else "")))
    grams = total / count
    if grams <= 0 or grams > 5000:
        return None
    return {"unit_name": singular[:40], "unit_name_plural": plural[:40], "grams_per_unit": round(grams, 3),
            "description": f"Derivado de serving_size de Open Food Facts: {serving_size}"[:200]}


def _add_off_serving(db: Session, food: Food, serving_size: str | None, serving_quantity, product_name: str = "") -> None:
    unit = parse_serving_unit(serving_size, serving_quantity, product_name or food.name)
    if not unit:
        return
    exists = db.scalar(select(FoodServing.id).where(
        FoodServing.food_id == food.id, FoodServing.unit_name == unit["unit_name"]
    ))
    if not exists:
        db.add(FoodServing(food_id=food.id, **unit))


def enrich_food_from_off(db: Session, food: Food) -> bool:
    """Completa metadatos (foto, Nutri-Score, NOVA, alérgenos...) de un producto ya guardado. Una consulta a la API
    de producto (100/min). Marca off_enriched solo si OFF respondió. Nunca lanza."""
    if food.source != "openfoodfacts" or not food.barcode or (food.extra or {}).get("off_enriched"):
        return False
    try:
        r = httpx.get(OFF_URL.format(code=food.barcode), params={"fields": OFF_FIELDS}, timeout=6,
                      headers={"User-Agent": get_settings().off_user_agent}, follow_redirects=True)
        if not r.is_success or r.json().get("status") != 1:
            return False
        meta = parse_off_meta(r.json()["product"])
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo completar %s desde OFF: %s", food.barcode, e)
        return False
    for col in ("nutriscore_grade", "nova_group", "ecoscore_grade", "image_url", "quantity"):
        if meta[col] is not None:
            setattr(food, col, meta[col])
    product = r.json()["product"]
    if not food.serving_g:
        food.serving_g = _num(product, "serving_quantity")
    food.extra = {**(food.extra or {}), **meta["extra"], "off_enriched": True}  # reasignar: JSONB no detecta mutaciones
    db.add(food)
    db.flush()
    _add_off_serving(db, food, product.get("serving_size"), product.get("serving_quantity"), product.get("product_name_es") or product.get("product_name") or food.name)
    db.commit()
    return True


def find_by_barcode(db: Session, code: str, user_id: int | None) -> Food | None:
    """Alimento visible para el usuario con ese código: el suyo primero y, si no, el compartido (OFF/comunidad).
    Nunca devuelve alimentos privados de otros usuarios."""
    owners = [Food.user_id.is_(None)] + ([Food.user_id == user_id] if user_id is not None else [])
    rows = db.scalars(select(Food).where(Food.barcode == code, or_(*owners))).all()
    return min(rows, key=lambda f: 0 if f.user_id == user_id else 1) if rows else None


def resolve_barcode(db: Session, raw: str, user_id: int | None = None) -> BarcodeResult:
    """BD local (tuyo, comunidad, OFF) -> Open Food Facts -> (el agente completa con web_search si hace falta)."""
    code = normalize_barcode(raw)
    if food := find_by_barcode(db, code, user_id):
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
    raw_name = p.get("product_name_es") or p.get("product_name") or f"Producto {code}"
    brand = (p.get("brands") or "").split(",")[0].strip() or None
    name = clean_name(raw_name, brand, p.get("quantity"))
    nutrients = parse_off_product(p)
    if nutrients is None:
        return BarcodeResult("incomplete", None, name, brand)

    serving = _num(p, "serving_quantity")
    meta = parse_off_meta(p)
    meta["extra"]["off_enriched"] = True  # la consulta por código ya trae todos los campos
    if name != raw_name:
        meta["extra"]["original_name"] = raw_name
    food = Food(name=name, brand=brand, barcode=code, source="openfoodfacts", serving_g=serving, **nutrients, **meta)
    db.add(food)
    db.flush()
    _add_off_serving(db, food, p.get("serving_size"), p.get("serving_quantity"), raw_name)
    db.commit()
    schedule_translation()
    return BarcodeResult("openfoodfacts", food, name, brand)


# ───────────────────────── Búsqueda por texto (search-a-licious) ─────────────────────────
# OFF limita las búsquedas a 10/min/IP, así que: límite propio, caché de consultas recientes y
# persistencia de todo lo encontrado en Postgres (la siguiente búsqueda ya es local).
SEARCH_FIELDS = ("code,product_name,brands,nutriments,serving_quantity,quantity,nutriscore_grade,nova_group,"
                 "ecoscore_grade,environmental_score_grade,image_front_small_url,image_front_url,image_url,"
                 "allergens_tags,ingredients_text_es,ingredients_text,categories,labels,labels_tags,generic_name_es,generic_name,serving_size")
MAX_ENRICH = 10  # si un hit no trae nutrientes, se completa con la API de producto (100/min) como máximo para N hits


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
RECENT_TTL_S = 60


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
    raw_name = str(name).strip()
    clean = clean_name(raw_name, brand, hit.get("quantity"))
    meta = parse_off_meta(hit)
    if clean != raw_name:
        meta["extra"]["original_name"] = raw_name
    return {"code": norm, "name": clean, "brand": brand, "serving_g": _num(hit, "serving_quantity"),
            "serving_unit": parse_serving_unit(hit.get("serving_size"), hit.get("serving_quantity"), raw_name),
            "nutrients": parse_off_product({"nutriments": _nutriments_flat(hit.get("nutriments"))}), "meta": meta}


def _store(db: Session, item: dict) -> bool:
    ins = pg_insert(Food).values(name=item["name"], brand=item["brand"], barcode=item["code"],
                                   source="openfoodfacts", serving_g=item["serving_g"], confidence="medium", license="ODbL",
                                   attribution="Open Food Facts contributors (ODbL)", source_updated_at=func.now(),
                                   **item["nutrients"], **item["meta"])
    # Si el producto ya estaba cacheado sin foto (búsquedas antiguas), completar metadatos sin borrar
    # traducciones ni datos que la ficha local ya tuviera.
    stmt = ins.on_conflict_do_update(
        index_elements=[func.coalesce(Food.user_id, 0), Food.barcode],
        set_={
            "image_url": func.coalesce(ins.excluded.image_url, Food.image_url),
            "nutriscore_grade": func.coalesce(ins.excluded.nutriscore_grade, Food.nutriscore_grade),
            "nova_group": func.coalesce(ins.excluded.nova_group, Food.nova_group),
            "ecoscore_grade": func.coalesce(ins.excluded.ecoscore_grade, Food.ecoscore_grade),
            "quantity": func.coalesce(ins.excluded.quantity, Food.quantity),
            "serving_g": func.coalesce(Food.serving_g, ins.excluded.serving_g),
            "extra": Food.extra.op("||")(ins.excluded.extra),
            "source_updated_at": func.now(),
        },
    ).returning(Food.id, literal_column("(xmax = 0)").label("inserted"))
    food_id, inserted = db.execute(stmt).one()
    unit = item.get("serving_unit")
    if unit:
        exists = db.scalar(select(FoodServing.id).where(
            FoodServing.food_id == food_id, FoodServing.unit_name == unit["unit_name"]
        ))
        if not exists:
            db.add(FoodServing(food_id=food_id, **unit))
    return bool(inserted)


def search_off_and_store(db: Session, query: str, page_size: int = 50) -> int:
    """Busca en OFF y guarda en `foods` los productos con datos nutricionales. Devuelve cuántos son nuevos."""
    s = get_settings()
    r = httpx.get(s.off_search_url, params={"q": query, "page": 1, "page_size": page_size, "langs": "es,en", "fields": SEARCH_FIELDS},
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
    """Consulta online solo si es nueva (60 s) y hay cupo; marca la consulta como hecha."""
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
