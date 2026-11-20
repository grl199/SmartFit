from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import Food, Recipe, RecipeIngredient
from ..schemas import LogOut, Meal
from ..services import recipes as svc
from ..services.nutrition import create_log
from ..services.rag import index_day_task

router = APIRouter(prefix="/recipes", tags=["recipes"])


class IngredientIn(BaseModel):
    food_id: int
    quantity_g: float = Field(gt=0, le=5000)


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    serving_count: float = Field(1, gt=0, le=100)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=40)


class PreviewIn(BaseModel):
    serving_count: float = Field(1, gt=0, le=100)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=40)


class RecipeLogIn(BaseModel):
    servings: float = Field(1, gt=0, le=50)
    meal: Meal | None = None
    log_date: date | None = None
    quantities: dict[int, float] | None = Field(None, description="id de ingrediente -> gramos de la receta completa (solo para este registro)")


def _food(db: Session, food_id: int, uid: int) -> Food:
    f = db.get(Food, food_id)
    if not f or f.user_id not in (None, uid):
        raise HTTPException(404, f"Alimento {food_id} no encontrado")
    if f.source == "recipe":
        raise HTTPException(422, "Una receta no puede ser ingrediente de otra receta")
    return f


def _own(db: Session, rid: int, uid: int) -> Recipe:
    r = db.get(Recipe, rid)
    if not r or r.user_id not in (None, uid):
        raise HTTPException(404, "Receta no encontrada")
    return r


def _detail(r: Recipe, uid: int) -> dict:
    items = svc.recipe_items(r)
    return {"id": r.id, "name": r.name, "description": r.description, "is_system": r.user_id is None, "editable": r.user_id == uid,
            "food_id": r.food_id, **svc.summarize(items, r.serving_count),
            "ingredients": [{"id": i.id, "food_id": i.food_id, "food": i.food.name, "brand": i.food.brand, "quantity_g": i.quantity_g,
                             "kcal": round(i.food.kcal * i.quantity_g / 100, 1)} for i in r.ingredients]}


def _fill(db: Session, r: Recipe, body: RecipeIn | PreviewIn, uid: int) -> None:
    r.ingredients.clear()
    for ing in body.ingredients:
        _food(db, ing.food_id, uid)
        r.ingredients.append(RecipeIngredient(food_id=ing.food_id, quantity_g=ing.quantity_g))


@router.get("")
def list_recipes(q: str | None = None, limit: int = Query(50, le=100), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    out = []
    for r in svc.visible_recipes(db, uid, q, limit):
        s = svc.summarize(svc.recipe_items(r), r.serving_count)
        out.append({"id": r.id, "name": r.name, "description": r.description, "is_system": r.user_id is None, "food_id": r.food_id,
                    "serving_count": r.serving_count, "serving_g": s["serving_g"], "per_serving": s["per_serving"]})
    return out


@router.post("/preview")
def preview(body: PreviewIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Recalcula en tiempo real los nutrientes mientras el usuario edita ingredientes y cantidades (no guarda nada)."""
    items = [(_food(db, i.food_id, uid), i.quantity_g) for i in body.ingredients]
    return svc.summarize(items, body.serving_count)


@router.post("", status_code=201)
def create_recipe(body: RecipeIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    r = Recipe(user_id=uid, name=body.name.strip(), description=body.description, serving_count=body.serving_count)
    _fill(db, r, body, uid)
    db.add(r)
    db.flush()
    svc.sync_recipe_food(db, r)
    db.commit()
    return _detail(r, uid)


@router.get("/{rid}")
def get_recipe(rid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return _detail(_own(db, rid, uid), uid)


@router.put("/{rid}")
def update_recipe(rid: int, body: RecipeIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    r = _own(db, rid, uid)
    if r.user_id != uid:
        raise HTTPException(403, "Las recetas del sistema no se editan: haz una copia con POST /recipes/{id}/copy")
    r.name, r.description, r.serving_count = body.name.strip(), body.description, body.serving_count
    _fill(db, r, body, uid)
    db.flush()
    svc.sync_recipe_food(db, r)
    db.commit()
    return _detail(r, uid)


@router.post("/{rid}/copy", status_code=201)
def copy_recipe(rid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Copia una receta (p. ej. del sistema) a las tuyas para poder cambiar ingredientes y cantidades."""
    src = _own(db, rid, uid)
    r = Recipe(user_id=uid, name=f"{src.name} (mi versión)" if src.user_id is None else f"{src.name} (copia)",
               description=src.description, serving_count=src.serving_count)
    r.ingredients = [RecipeIngredient(food_id=i.food_id, quantity_g=i.quantity_g) for i in src.ingredients]
    db.add(r)
    db.flush()
    svc.sync_recipe_food(db, r)
    db.commit()
    return _detail(r, uid)


@router.delete("/{rid}", status_code=204)
def delete_recipe(rid: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    r = _own(db, rid, uid)
    if r.user_id != uid:
        raise HTTPException(403, "Las recetas del sistema no se pueden borrar")
    svc.delete_recipe(db, r)
    db.commit()


@router.post("/{rid}/log", response_model=LogOut, status_code=201)
def log_recipe(rid: int, body: RecipeLogIn, bg: BackgroundTasks, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Registra `servings` raciones. Guarda una INSTANTÁNEA de los nutrientes (igual que FoodLog), con las cantidades
    originales o con `quantities` si se modificaron para esta toma."""
    r = _own(db, rid, uid)
    valid = {i.id for i in r.ingredients}
    if body.quantities and (set(body.quantities) - valid or any(v <= 0 or v > 5000 for v in body.quantities.values())):
        raise HTTPException(422, "Cantidades no válidas para esta receta")
    s = svc.summarize(svc.recipe_items(r, body.quantities), r.serving_count)
    k = body.servings / r.serving_count
    nutrients = {n: round(v * k, 2) for n, v in s["totals"].items()}
    grams = round(s["total_g"] * k, 1)
    if grams > 5000:
        raise HTTPException(422, "La cantidad supera los 5000 g")
    food = db.get(Food, r.food_id)
    log = create_log(db, uid, food, grams, body.meal, body.log_date, nutrients=nutrients)
    bg.add_task(index_day_task, uid, log.log_date)
    return log
