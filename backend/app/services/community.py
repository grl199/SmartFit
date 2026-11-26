"""Catálogo comunitario: los productos que los usuarios crean con código de barras pueden ofrecerse a los demás.

Un producto NO se publica porque lo diga un usuario: hace falta que al menos CONSENSUS_MIN_USERS usuarios distintos
hayan registrado el mismo código con valores nutricionales concordantes. Entonces se crea una entrada compartida
(user_id NULL, source 'community') con la mediana de los valores. Solo se publican código, nombre, marca y nutrientes:
nunca quién los aportó. Los códigos de tienda ambiguos (prefijo 2) no se comparten.

Límite conocido: con registro abierto, alguien podría crear varias cuentas para fabricar un «consenso». Para un despliegue
público haría falta moderación o reputación; para uso personal/familiar, ALLOW_REGISTRATION=false lo evita."""
import logging
import statistics
from collections import Counter

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import NUTRIENTS, Food

log = logging.getLogger(__name__)
CONSENSUS_MIN_USERS = 2
REL_TOL = 0.10   # tolerancia relativa entre valores de distintos usuarios
ABS_TOL_G = 1.5  # o absoluta, en gramos, para valores pequeños


class NotShareable(Exception):
    """El alimento no cumple los requisitos para ofrecerse. Mensaje apto para el usuario."""


def check_shareable(food: Food) -> None:
    if not food.barcode:
        raise NotShareable("Para compartir un producto necesita código de barras.")
    if food.barcode_ambiguous:
        raise NotShareable("Los códigos de tienda (que empiezan por 2) pueden repetirse entre productos distintos: no se comparten.")
    if food.kcal <= 0:
        raise NotShareable("Indica las calorías por 100 g.")
    if food.kcal > 950 or food.protein_g + food.carbs_g + food.fat_g > 105:
        raise NotShareable("Los valores por 100 g no son posibles (comprueba las unidades).")
    energy = 4 * food.protein_g + 4 * food.carbs_g + 9 * food.fat_g
    if abs(energy - food.kcal) > 0.25 * food.kcal + 25:
        raise NotShareable(f"Las calorías ({food.kcal:.0f}) no cuadran con los macros ({energy:.0f} kcal): revisa los valores.")


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL_G, REL_TOL * max(a, b))


def _agree(a: Food, b: Food) -> bool:
    return (abs(a.kcal - b.kcal) <= max(15, REL_TOL * max(a.kcal, b.kcal))
            and all(_close(getattr(a, n), getattr(b, n)) for n in ("protein_g", "carbs_g", "fat_g")))


def run_consensus(db: Session, barcode: str) -> Food | None:
    """Si hay suficientes usuarios distintos con datos concordantes, publica la entrada comunitaria y la devuelve."""
    if db.scalar(select(Food.id).where(Food.barcode == barcode, Food.user_id.is_(None))):
        return None  # ya existe un producto compartido (OFF o comunidad) con ese código
    subs = list(db.scalars(select(Food).where(Food.barcode == barcode, Food.user_id.is_not(None), Food.share_status == "pending")))
    best: list[Food] = []
    for anchor in subs:
        cluster = [s for s in subs if _agree(anchor, s)]
        if len(cluster) > len(best):
            best = cluster
    if len({f.user_id for f in best}) < CONSENSUS_MIN_USERS:
        return None
    name = Counter(f.name.strip() for f in best).most_common(1)[0][0]
    brand = Counter(f.brand for f in best if f.brand).most_common(1)
    shared = Food(user_id=None, name=name, brand=brand[0][0] if brand else None, barcode=barcode, source="community",
                  share_status="verified", extra={"confirmed_by": len({f.user_id for f in best})},
                  **{n: round(statistics.median(getattr(f, n) for f in best), 1) for n in NUTRIENTS})
    db.add(shared)
    try:
        db.flush()
    except IntegrityError:  # otro proceso lo publicó a la vez
        db.rollback()
        return None
    for f in best:
        f.share_status = "verified"
        db.add(f)
    db.commit()
    log.info("Producto comunitario publicado: %s (%s usuarios)", barcode, shared.extra["confirmed_by"])
    return shared


def share_food(db: Session, food: Food) -> dict:
    """Ofrece el alimento a la comunidad (queda 'pending' hasta que otro usuario lo confirme)."""
    check_shareable(food)
    if food.share_status == "private":
        food.share_status = "pending"
        db.add(food)
        db.commit()
    published = run_consensus(db, food.barcode)
    db.refresh(food)
    return {"status": food.share_status, "published": published is not None or food.share_status == "verified"}


def withdraw_food(db: Session, food: Food) -> str:
    if food.share_status == "pending":
        food.share_status = "private"
        db.add(food)
        db.commit()
    return food.share_status  # 'verified' ya no se retira: forma parte del catálogo compartido
