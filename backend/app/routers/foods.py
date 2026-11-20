from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id, read_image
from ..models import Food, FoodLog, FoodServing, RecipeIngredient
from ..schemas import BarcodeOut, FoodBase, FoodCopyIn, FoodCreate, FoodMineOut, FoodOut
from ..services.images import decode_barcodes
from ..services import community
from ..services.food_search import search_hybrid
from ..services.names import pending_count, translate_pending_names
from ..services.openfoodfacts import enrich_food_from_off, normalize_barcode, resolve_barcode

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search", response_model=list[FoodOut])
def search(q: str = Query(min_length=1), limit: int = Query(10, le=30), online: bool = True,
           db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Búsqueda mientras se escribe: BD local; si hay pocos resultados, completa con Open Food Facts
    (limitado y cacheado) y persiste lo encontrado."""
    return search_hybrid(db, uid, q, limit, online)


@router.get("/barcode/{code}", response_model=BarcodeOut)
def by_barcode(code: str, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    try:
        res = resolve_barcode(db, code, uid)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return BarcodeOut(status=res.status, barcodes=[code], food=res.food, name=res.name, brand=res.brand)


@router.post("/barcode-image", response_model=BarcodeOut)
def scan_image(image: UploadFile = File(...), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    try:
        codes = decode_barcodes(read_image(image))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not codes:
        return BarcodeOut(status="no_barcode")
    for c in codes:  # devuelve el primero que se pueda resolver
        res = resolve_barcode(db, c, uid)
        if res.food:
            return BarcodeOut(status=res.status, barcodes=codes, food=res.food)
    return BarcodeOut(status=res.status, barcodes=codes, name=res.name, brand=res.brand)


@router.post("", response_model=FoodOut, status_code=201)
def create_food(body: FoodCreate, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    data = body.model_dump(exclude={"share"})
    if data["barcode"]:
        try:
            data["barcode"] = normalize_barcode(data["barcode"])
        except ValueError as e:
            raise HTTPException(422, str(e))
    food = Food(user_id=uid, source="manual", **data)
    if body.share:  # se valida ANTES de guardar: si no cumple, no se crea nada
        try:
            community.check_shareable(food)
        except community.NotShareable as e:
            raise HTTPException(422, str(e))
    db.add(food)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya tienes un alimento con ese código de barras")
    if body.share:
        community.share_food(db, food)
    return food


@router.post("/{food_id}/share")
def share(food_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Ofrece un alimento tuyo a la comunidad. Se publica cuando otro usuario registra los mismos datos."""
    food = db.get(Food, food_id)
    if not food or food.user_id != uid:
        raise HTTPException(404, "Alimento no encontrado")
    try:
        return community.share_food(db, food)
    except community.NotShareable as e:
        raise HTTPException(422, str(e))


@router.delete("/{food_id}/share")
def unshare(food_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    food = db.get(Food, food_id)
    if not food or food.user_id != uid:
        raise HTTPException(404, "Alimento no encontrado")
    return {"status": community.withdraw_food(db, food)}


@router.post("/translate-names")
def translate_names_now(limit: int = Query(20, ge=1, le=40), db: Session = Depends(get_db)):
    """Traduce al español (con IA) los nombres de productos de Open Food Facts que aún no se han procesado."""
    try:
        done = translate_pending_names(db, limit)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(502, f"No se pudo traducir ahora mismo: {str(e)[:150]}")
    return {"translated": done, "pending": pending_count(db)}


class ServingIn(BaseModel):
    unit_name: str = Field(min_length=1, max_length=40)
    unit_name_plural: str | None = Field(None, max_length=40)
    grams_per_unit: float = Field(gt=0, le=5000)
    description: str | None = Field(None, max_length=200)


class ServingOut(ServingIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    food_id: int


@router.get("/{food_id}/servings", response_model=list[ServingOut])
def list_servings(food_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Unidades habituales del alimento (cucharada, rebanada, loncha...) con su equivalencia en gramos. Son orientativas
    y específicas de cada alimento."""
    food = db.get(Food, food_id)
    if not food or food.user_id not in (None, uid):
        raise HTTPException(404, "Alimento no encontrado")
    return db.scalars(select(FoodServing).where(FoodServing.food_id == food_id).order_by(FoodServing.grams_per_unit.desc())).all()


@router.post("/{food_id}/servings", response_model=ServingOut, status_code=201)
def add_serving(food_id: int, body: ServingIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Solo en alimentos propios: el catálogo compartido no se modifica."""
    food = db.get(Food, food_id)
    if not food or food.user_id != uid:
        raise HTTPException(404, "Alimento no encontrado")
    sv = FoodServing(food_id=food_id, **body.model_dump())
    db.add(sv)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una unidad con ese nombre para este alimento")
    return sv


@router.delete("/{food_id}/servings/{serving_id}", status_code=204)
def delete_serving(food_id: int, serving_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    food = db.get(Food, food_id)
    sv = db.get(FoodServing, serving_id)
    if not food or food.user_id != uid or not sv or sv.food_id != food_id:
        raise HTTPException(404, "Unidad no encontrada")
    db.delete(sv)
    db.commit()


def _own_food(db: Session, food_id: int, uid: int) -> Food:
    food = db.get(Food, food_id)
    if not food or food.user_id != uid:
        raise HTTPException(404, "Alimento no encontrado")
    if food.source == "recipe":
        raise HTTPException(422, "Esto es una receta: edítala desde Recetas")
    return food


@router.get("/mine", response_model=list[FoodMineOut])
def my_foods(q: str | None = None, limit: int = Query(100, le=300), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Tus alimentos personalizados (privados salvo que los compartas), con cuántas veces los has usado."""
    used = select(FoodLog.food_id, func.count().label("n")).where(FoodLog.user_id == uid).group_by(FoodLog.food_id).subquery()
    stmt = (select(Food, func.coalesce(used.c.n, 0)).outerjoin(used, used.c.food_id == Food.id)
            .where(Food.user_id == uid, Food.source != "recipe"))
    if q and q.strip():
        for t in q.lower().split():
            stmt = stmt.where(Food.search_text.ilike(f"%{t}%"))
    out = []
    for food, n in db.execute(stmt.order_by(func.coalesce(used.c.n, 0).desc(), Food.name).limit(limit)):
        item = FoodMineOut.model_validate(food)
        item.times_used = n
        out.append(item)
    return out


@router.put("/{food_id}", response_model=FoodOut)
def update_food(food_id: int, body: FoodBase, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Edita un alimento TUYO. Los registros que ya hiciste con él no cambian (guardan su propia instantánea)."""
    food = _own_food(db, food_id, uid)
    if food.share_status != "private":
        raise HTTPException(409, "Este alimento está compartido con la comunidad: retira primero el compartido para editarlo")
    data = body.model_dump()
    if data["barcode"]:
        try:
            data["barcode"] = normalize_barcode(data["barcode"])
        except ValueError as e:
            raise HTTPException(422, str(e))
    for k, v in data.items():
        setattr(food, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya tienes un alimento con ese código de barras")
    return food


@router.delete("/{food_id}", status_code=204)
def delete_food(food_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Borra un alimento TUYO. Si ya lo has registrado o lo usa una receta, no se borra (para no romper tu historial)."""
    food = _own_food(db, food_id, uid)
    logs = db.scalar(select(func.count()).select_from(FoodLog).where(FoodLog.food_id == food_id)) or 0
    recipes = db.scalar(select(func.count()).select_from(RecipeIngredient).where(RecipeIngredient.food_id == food_id)) or 0
    if logs or recipes:
        raise HTTPException(409, f"No se puede borrar: lo has registrado {logs} veces y lo usan {recipes} recetas. "
                                 "Puedes editarlo o crear otro.")
    if food.share_status != "private":
        raise HTTPException(409, "Este alimento está compartido con la comunidad: retira primero el compartido")
    db.execute(delete(FoodServing).where(FoodServing.food_id == food_id))
    db.delete(food)
    db.commit()


@router.post("/{food_id}/copy", response_model=FoodOut, status_code=201)
def copy_food(food_id: int, body: FoodCopyIn | None = None, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Crea TU versión de cualquier alimento (del catálogo, de Open Food Facts, de la comunidad o tuyo) para ajustarla a lo que comes.
    Hereda nutrientes, ración y unidades; puedes cambiar lo que quieras. El original no se modifica."""
    src = db.get(Food, food_id)
    if not src or src.user_id not in (None, uid) or src.source == "recipe":
        raise HTTPException(404, "Alimento no encontrado")
    over = (body.model_dump(exclude_none=True) if body else {})
    fields = ("name", "brand", "serving_g", "kcal", "protein_g", "carbs_g", "sugars_g", "fat_g", "sat_fat_g", "fiber_g", "sodium_mg")
    data = {k: getattr(src, k) for k in fields} | over
    if "name" not in over:
        data["name"] = f"{src.name} (mío)"[:300]
    food = Food(user_id=uid, source="manual", extra={"copied_from": src.id}, **data)
    db.add(food)
    db.flush()
    for sv in db.scalars(select(FoodServing).where(FoodServing.food_id == src.id)):
        db.add(FoodServing(food_id=food.id, unit_name=sv.unit_name, unit_name_plural=sv.unit_name_plural, grams_per_unit=sv.grams_per_unit,
                           description=sv.description))
    db.commit()
    return food


@router.get("/{food_id}", response_model=FoodOut)
def get_food(food_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Ficha del alimento. Si viene de Open Food Facts y aún no tiene sus metadatos (foto, Nutri-Score, NOVA,
    alérgenos, ingredientes), se completan ahora con una sola consulta."""
    food = db.get(Food, food_id)
    if not food or food.user_id not in (None, uid):
        raise HTTPException(404, "Alimento no encontrado")
    enrich_food_from_off(db, food)
    return food
