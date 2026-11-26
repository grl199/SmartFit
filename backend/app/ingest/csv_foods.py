"""Importador genérico de CSV (BEDCA u otra base cuya licencia permita reutilizarla, o una tabla propia).

Columnas reconocidas (por 100 g): name*, kcal*, protein_g*, carbs_g*, fat_g*, sugars_g, sat_fat_g, fiber_g, sodium_mg, external_id, brand, serving_g, category.
(* obligatorias). Si tu CSV usa otros nombres de columna, mapea con `--map "Alimento=name" --map "Energía (kcal)=kcal"`.
Sin `external_id` se usa `<fuente>:<slug del nombre>`: así volver a cargar el mismo fichero actualiza en lugar de duplicar."""
from __future__ import annotations

import csv
from pathlib import Path

from ..services.food_catalog import slug
from ..services.food_sources import NUTRIENT_COLS, NormalizedFood, is_sane

REQUIRED = ("name", "kcal", "protein_g", "carbs_g", "fat_g")
KNOWN = {"name", "external_id", "brand", "serving_g", "category", *NUTRIENT_COLS}


def _num(value: str | None, decimal_comma: bool) -> float | None:
    v = (value or "").strip()
    if not v or v.lower() in ("na", "n/a", "tr", "-", "nd"):
        return None
    if decimal_comma:
        v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def read_csv(path: str | Path, *, source: str, license: str | None, attribution: str | None, confidence: str = "medium",
             delimiter: str = ",", decimal_comma: bool = False, mapping: dict[str, str] | None = None) -> tuple[list[NormalizedFood], dict[str, int]]:
    if not source or not source.replace("_", "").replace("-", "").isalnum() or source in ("manual", "openfoodfacts", "usda", "catalog", "recipe", "community", "web"):
        raise ValueError(f"Nombre de fuente no válido o reservado: {source!r}")
    if confidence not in ("high", "medium", "low"):
        raise ValueError("confidence debe ser high, medium o low")
    mapping = mapping or {}
    stats = {"rows": 0, "kept": 0, "skipped_invalid": 0}
    out: list[NormalizedFood] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        cols = {h: mapping.get(h, h) for h in reader.fieldnames or []}
        missing = [c for c in REQUIRED if c not in cols.values()]
        if missing:
            raise ValueError(f"Faltan columnas obligatorias {missing}. Columnas del fichero: {list(cols)}. Usa --map «original=destino».")
        for raw in reader:
            stats["rows"] += 1
            row = {cols[h]: v for h, v in raw.items() if h in cols and cols[h] in KNOWN}
            name = (row.get("name") or "").strip()
            nums = {k: _num(row.get(k), decimal_comma) for k in NUTRIENT_COLS}
            if not name or any(nums[k] is None for k in ("kcal", "protein_g", "carbs_g", "fat_g")):
                stats["skipped_invalid"] += 1
                continue
            serving = _num(row.get("serving_g"), decimal_comma)
            nf = NormalizedFood(source=source, external_id=(row.get("external_id") or "").strip() or f"{source}:{slug(name)}", name=name,
                                nutrients={k: (v if v is not None else 0.0) for k, v in nums.items()}, confidence=confidence, license=license,
                                attribution=attribution, brand=(row.get("brand") or "").strip() or None, serving_g=serving if serving and serving > 0 else None,
                                extra={"category": (row.get("category") or "").strip() or None})
            if not is_sane(nf):
                stats["skipped_invalid"] += 1
                continue
            out.append(nf)
    stats["kept"] = len(out)
    return out, stats
