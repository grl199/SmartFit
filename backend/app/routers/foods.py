from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id, read_image
from ..models import Food
from ..schemas import BarcodeOut, FoodCreate, FoodOut
from ..services.images import decode_barcodes
from ..services.nutrition import search_foods
from ..services.openfoodfacts import normalize_barcode, resolve_barcode

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search", response_model=list[FoodOut])
def search(q: str = Query(min_length=1), limit: int = Query(10, le=30),
           db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return search_foods(db, uid, q, limit)


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
