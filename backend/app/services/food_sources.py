"""Capa de fuentes nutricionales: cada fuente se normaliza a `NormalizedFood` y se vuelca al catálogo compartido de Postgres.

La búsqueda NUNCA llama a APIs de pago o con cupo (USDA, etc.): los datos se cargan UNA VEZ, por lotes, con `python -m app.ingest`
(ver docs/FUENTES_NUTRICIONALES.md). Después todo se busca en local, al instante y sin límites. Open Food Facts sigue siendo la única fuente
en línea (productos con código de barras) y se guarda al consultarla.

Cada alimento conserva fuente, id externo, fecha, fiabilidad y atribución/licencia, y no se duplica: índice único (source, external_id)."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from sqlalchemy import func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Food

NUTRIENT_COLS = ("kcal", "protein_g", "carbs_g", "sugars_g", "fat_g", "sat_fat_g", "fiber_g", "sodium_mg")
MAX_KCAL_PER_100G = 950   # el aceite puro ronda las 900; más que eso es un dato corrupto


@dataclass
class NormalizedFood:
    source: str
    external_id: str
    name: str
    nutrients: dict[str, float]
    confidence: str = "medium"
    license: str | None = None
    attribution: str | None = None
    brand: str | None = None
    serving_g: float | None = None
    extra: dict = field(default_factory=dict)


def is_sane(nf: NormalizedFood) -> bool:
    n = nf.nutrients
    return bool(nf.name.strip()) and 0 <= n.get("kcal", -1) <= MAX_KCAL_PER_100G and all(n.get(k, 0) >= 0 for k in NUTRIENT_COLS) \
        and (n.get("protein_g", 0) + n.get("carbs_g", 0) + n.get("fat_g", 0)) <= 105   # macros por 100 g no pueden pasar de ~100 g


def _chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def bulk_upsert(db: Session, items: Iterable[NormalizedFood], chunk: int = 1000) -> dict[str, int]:
    """Vuelca alimentos al catálogo compartido. IDEMPOTENTE: repetir la carga (p. ej. con una versión nueva de la fuente) actualiza
    nutrientes y procedencia de los ya existentes sin duplicar y SIN tocar el nombre ni `extra` (así se conservan traducciones)."""
    unique: dict[tuple[str, str], NormalizedFood] = {}
    for nf in items:
        unique[(nf.source, nf.external_id)] = nf     # si el lote trae duplicados, gana el último
    inserted = updated = 0
    for batch in _chunks(list(unique.values()), chunk):
        rows = [dict(user_id=None, name=nf.name, brand=nf.brand, serving_g=nf.serving_g, source=nf.source, external_id=nf.external_id,
                     confidence=nf.confidence, license=nf.license, attribution=nf.attribution, source_updated_at=func.now(), extra=nf.extra,
                     **{k: nf.nutrients.get(k, 0.0) for k in NUTRIENT_COLS}) for nf in batch]
        ins = pg_insert(Food).values(rows)
        stmt = ins.on_conflict_do_update(
            index_elements=[Food.source, Food.external_id], index_where=Food.external_id.is_not(None) & Food.user_id.is_(None),
            set_={**{k: ins.excluded[k] for k in NUTRIENT_COLS}, "confidence": ins.excluded.confidence, "license": ins.excluded.license,
                  "attribution": ins.excluded.attribution, "source_updated_at": func.now()},
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        for (was_inserted,) in db.execute(stmt):
            inserted += bool(was_inserted)
            updated += not was_inserted
        db.commit()
    return {"inserted": inserted, "updated": updated}
