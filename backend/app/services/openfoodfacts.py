import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import select
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
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12:  # UPC-A -> EAN-13
        digits = "0" + digits
    if len(digits) not in (8, 13):
        raise ValueError(f"Código de barras no válido: {raw!r}")
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
