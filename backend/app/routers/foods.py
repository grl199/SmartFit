from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id, read_image
from ..models import Food
from ..schemas import BarcodeOut, FoodCreate, FoodOut
from ..services.images import decode_barcodes
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
def by_barcode(code: str, db: Session = Depends(get_db)):
    try:
        res = resolve_barcode(db, code)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return BarcodeOut(status=res.status, barcodes=[code], food=res.food, name=res.name, brand=res.brand)


@router.post("/barcode-image", response_model=BarcodeOut)
def scan_image(image: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        codes = decode_barcodes(read_image(image))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not codes:
        return BarcodeOut(status="no_barcode")
    for c in codes:  # devuelve el primero que se pueda resolver
        res = resolve_barcode(db, c)
        if res.food:
            return BarcodeOut(status=res.status, barcodes=codes, food=res.food)
    return BarcodeOut(status=res.status, barcodes=codes, name=res.name, brand=res.brand)


@router.post("", response_model=FoodOut, status_code=201)
def create_food(body: FoodCreate, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    data = body.model_dump()
    if data["barcode"]:
        try:
            data["barcode"] = normalize_barcode(data["barcode"])
        except ValueError as e:
            raise HTTPException(422, str(e))
    food = Food(user_id=uid, source="manual", **data)
    db.add(food)
    db.commit()
    return food


@router.post("/translate-names")
def translate_names_now(limit: int = Query(20, ge=1, le=40), db: Session = Depends(get_db)):
    """Traduce al español (con IA) los nombres de productos de Open Food Facts que aún no se han procesado."""
    try:
        done = translate_pending_names(db, limit)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(502, f"No se pudo traducir ahora mismo: {str(e)[:150]}")
    return {"translated": done, "pending": pending_count(db)}


@router.get("/{food_id}", response_model=FoodOut)
def get_food(food_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Ficha del alimento. Si viene de Open Food Facts y aún no tiene sus metadatos (foto, Nutri-Score, NOVA,
    alérgenos, ingredientes), se completan ahora con una sola consulta."""
    food = db.get(Food, food_id)
    if not food or food.user_id not in (None, uid):
        raise HTTPException(404, "Alimento no encontrado")
    enrich_food_from_off(db, food)
    return food
