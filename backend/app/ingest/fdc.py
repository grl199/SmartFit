"""Lector de las descargas CSV oficiales de USDA FoodData Central (https://fdc.nal.usda.gov/download-datasets.html).

Se usan los conjuntos «Foundation Foods» y «SR Legacy» (alimentos genéricos, CC0, valores por 100 g). Acepta una carpeta con los CSV o el .zip
tal cual se descarga. Ficheros que lee: food.csv, food_nutrient.csv, nutrient.csv y (opcional) food_category.csv.
Los nutrientes se identifican por su NÚMERO (nutrient_nbr: 208 energía kcal, 203 proteína…), que es estable entre versiones, y no por el id interno.

NO consulta ninguna API: lee ficheros locales."""
from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..services.food_sources import NormalizedFood, is_sane

NBR_TO_COL = {"208": "kcal", "203": "protein_g", "205": "carbs_g", "269": "sugars_g", "204": "fat_g", "606": "sat_fat_g", "291": "fiber_g",
              "307": "sodium_mg"}
ENERGY_FALLBACK = ("957", "958")    # energía Atwater: los «Foundation» a veces no traen el 208
DATA_TYPES = {"foundation_food": "Foundation", "sr_legacy_food": "SR Legacy"}
ATTRIBUTION = "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central (dominio público, CC0)."
REQUIRED = {"food.csv": {"fdc_id", "data_type", "description"}, "food_nutrient.csv": {"fdc_id", "nutrient_id", "amount"},
            "nutrient.csv": {"id", "nutrient_nbr"}}


class FdcFormatError(ValueError):
    pass


@contextmanager
def _open(src: Path, name: str, required: bool = True):
    """Abre `name` dentro de una carpeta o de un .zip (aunque esté en una subcarpeta). Devuelve un lector de texto o None si es opcional."""
    if not src.exists():
        raise FdcFormatError(f"No encuentro {src}")
    if src.is_file() and not zipfile.is_zipfile(src):
        raise FdcFormatError(f"{src.name} no es una carpeta ni un .zip de FoodData Central")
    if src.is_dir():
        found = next(iter(sorted(src.rglob(name))), None)
        if found is None:
            if required:
                raise FdcFormatError(f"No encuentro {name} en {src}")
            yield None
            return
        with open(found, newline="", encoding="utf-8-sig") as f:
            yield f
        return
    with zipfile.ZipFile(src) as z:
        member = next((n for n in z.namelist() if n == name or n.endswith("/" + name)), None)
        if member is None:
            if required:
                raise FdcFormatError(f"No encuentro {name} dentro de {src.name}")
            yield None
            return
        with z.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as f:
            yield f


def _rows(f, name: str) -> Iterator[dict]:
    reader = csv.DictReader(f)
    missing = REQUIRED.get(name, set()) - set(reader.fieldnames or [])
    if missing:
        raise FdcFormatError(f"{name}: faltan columnas {sorted(missing)} (¿es una descarga CSV de FoodData Central?)")
    yield from reader


def _nbr(value: str) -> str:
    v = (value or "").strip()
    return v[:-2] if v.endswith(".0") else v


def _title(description: str) -> str:
    d = " ".join((description or "").split())
    return d.capitalize() if d.isupper() else d


def read_fdc(src: str | Path) -> tuple[list[NormalizedFood], dict[str, int]]:
    """Devuelve (alimentos normalizados, estadísticas). No toca la base de datos."""
    src = Path(src)
    stats = {"foods_in_file": 0, "kept": 0, "skipped_other_types": 0, "skipped_no_energy": 0, "skipped_incomplete": 0, "skipped_insane": 0}
    with _open(src, "nutrient.csv") as f:
        id_to_nbr = {r["id"]: _nbr(r["nutrient_nbr"]) for r in _rows(f, "nutrient.csv")}
    wanted_ids = {i: n for i, n in id_to_nbr.items() if n in NBR_TO_COL or n in ENERGY_FALLBACK}
    categories: dict[str, str] = {}
    with _open(src, "food_category.csv", required=False) as f:
        if f:
            categories = {r["id"]: r.get("description", "") for r in csv.DictReader(f)}
    foods: dict[str, dict] = {}
    with _open(src, "food.csv") as f:
        for r in _rows(f, "food.csv"):
            stats["foods_in_file"] += 1
            if r["data_type"] not in DATA_TYPES:
                stats["skipped_other_types"] += 1     # sub_sample_food, branded_food…: no son alimentos genéricos
                continue
            foods[r["fdc_id"]] = {"name": _title(r["description"]), "type": DATA_TYPES[r["data_type"]],
                                  "category": categories.get(r.get("food_category_id", ""), ""), "values": {}}
    with _open(src, "food_nutrient.csv") as f:
        for r in _rows(f, "food_nutrient.csv"):
            food = foods.get(r["fdc_id"])
            nbr_id = wanted_ids.get(r["nutrient_id"])
            if food is None or nbr_id is None or r["amount"] in ("", None):
                continue
            try:
                food["values"][nbr_id] = float(r["amount"])
            except ValueError:
                continue
    out: list[NormalizedFood] = []
    for fdc_id, food in foods.items():
        v = food["values"]
        values = {col: v[nbr] for nbr, col in NBR_TO_COL.items() if nbr in v}
        if "kcal" not in values:
            fb = next((v[n] for n in ENERGY_FALLBACK if n in v), None)
            if fb is None:
                stats["skipped_no_energy"] += 1
                continue
            values["kcal"] = fb
        if not all(k in values for k in ("protein_g", "carbs_g", "fat_g")):
            stats["skipped_incomplete"] += 1
            continue
        nf = NormalizedFood(source="usda", external_id=fdc_id, name=food["name"], confidence="high", license="CC0", attribution=ATTRIBUTION,
                            nutrients={k: max(values.get(k, 0.0), 0.0) for k in ("kcal", "protein_g", "carbs_g", "sugars_g", "fat_g", "sat_fat_g", "fiber_g", "sodium_mg")},
                            extra={"usda_data_type": food["type"], "usda_category": food["category"] or None})
        if not is_sane(nf):
            stats["skipped_insane"] += 1
            continue
        out.append(nf)
    stats["kept"] = len(out)
    return out, stats
