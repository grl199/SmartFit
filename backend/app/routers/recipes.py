from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import Food, Recipe, RecipeIngredient
from ..schemas import LogOut, Meal
from ..services import recipes as svc
from ..services.nutrition import create_log
from ..services.rag import index_day_task
from ..services.food_estimation import estimate_meal

router = APIRouter(prefix="/recipes", tags=["recipes"])


class IngredientIn(BaseModel):
    food_id: int
    quantity_g: float = Field(gt=0, le=5000)
    unit_name: str = Field("g", min_length=1, max_length=40)
    quantity: float | None = Field(None, gt=0, le=5000)
    grams_per_unit: float | None = Field(None, gt=0, le=5000)

    @model_validator(mode="after")
    def normalize_quantity(self):
        if self.quantity is not None:
            if self.unit_name == "g":
                self.grams_per_unit = 1.0
            elif self.grams_per_unit is None:
                raise ValueError("Indica cuántos gramos equivale una unidad.")
            self.quantity_g = round(self.quantity * (self.grams_per_unit or 1), 2)
        else:
            self.quantity = self.quantity_g
            self.grams_per_unit = self.grams_per_unit or 1.0
            self.unit_name = "g"
        return self


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    serving_count: float = Field(1, gt=0, le=100)
    steps: list[str] = Field(default_factory=list, max_length=30)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=40)


class PreviewIn(BaseModel):
    serving_count: float = Field(1, gt=0, le=100)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=40)


class RecipeEstimateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=1500)
    steps: list[str] = Field(default_factory=list, max_length=30)


class EstimatedRecipeItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grams: float = Field(gt=0, le=5000)
    kcal_per_100g: float = Field(ge=0, le=950)
    protein_g_per_100g: float = Field(ge=0, le=100)
    carbs_g_per_100g: float = Field(ge=0, le=100)
    sugars_g_per_100g: float = Field(ge=0, le=100)
    fat_g_per_100g: float = Field(ge=0, le=100)
    sat_fat_g_per_100g: float = Field(ge=0, le=100)
    fiber_g_per_100g: float = Field(ge=0, le=100)
    sodium_mg_per_100g: float = Field(ge=0, le=10000)
    confidence: str = "low"
    unit_name: str = "g"
    quantity: float | None = Field(None, gt=0, le=5000)
    grams_per_unit: float | None = Field(None, gt=0, le=5000)

    @model_validator(mode="after")
    def normalize_quantity(self):
        if self.quantity is not None:
            if self.unit_name == "g":
                self.grams_per_unit = 1.0
            elif self.grams_per_unit is None:
                raise ValueError("Indica los gramos por unidad.")
            self.grams = round(self.quantity * (self.grams_per_unit or 1), 2)
        else:
            self.quantity = self.grams
            self.grams_per_unit = self.grams_per_unit or 1.0
            self.unit_name = "g"
        return self


class RecipeFromEstimateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    serving_count: float = Field(1, gt=0, le=100)
    steps: list[str] = Field(default_factory=list, max_length=30)
    items: list[EstimatedRecipeItemIn] = Field(min_length=1, max_length=25)


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
            "ingredients": [{"id": i.id, "food_id": i.food_id, "food": i.food.name, "brand": i.food.brand,
                             "quantity_g": i.quantity_g, "unit_name": i.unit_name or "g",
                             "quantity": i.quantity if i.quantity is not None else i.quantity_g,
                             "grams_per_unit": i.grams_per_unit if i.grams_per_unit is not None else 1.0,
                             "kcal": round(i.food.kcal * i.quantity_g / 100, 1)} for i in r.ingredients],
            "steps": r.steps or []}


def _fill(db: Session, r: Recipe, body: RecipeIn | PreviewIn, uid: int) -> None:
    r.ingredients.clear()
    for ing in body.ingredients:
        _food(db, ing.food_id, uid)
        r.ingredients.append(RecipeIngredient(
            food_id=ing.food_id, quantity_g=ing.quantity_g, unit_name=ing.unit_name,
            quantity=ing.quantity, grams_per_unit=ing.grams_per_unit,
        ))


@router.get("")
def list_recipes(q: str | None = None, limit: int = Query(50, le=100), db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    out = []
    for r in svc.visible_recipes(db, uid, q, limit):
        s = svc.summarize(svc.recipe_items(r), r.serving_count)
        out.append({"id": r.id, "name": r.name, "description": r.description, "is_system": r.user_id is None, "food_id": r.food_id,
                    "serving_count": r.serving_count, "serving_g": s["serving_g"], "per_serving": s["per_serving"], "steps": r.steps or []})
    return out


@router.post("/preview")
def preview(body: PreviewIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Recalcula en tiempo real los nutrientes mientras el usuario edita ingredientes y cantidades (no guarda nada)."""
    items = [(_food(db, i.food_id, uid), i.quantity_g) for i in body.ingredients]
    return svc.summarize(items, body.serving_count)



@router.post("/estimate")
def estimate_recipe(body: RecipeEstimateIn):
    """Propone ingredientes y cantidades de una receta con IA; no guarda nada."""
    prompt = (
        f"Receta: {body.name}.\nDescripción: {body.description}\n"
        f"Pasos: {'; '.join(body.steps)}.\n"
        "Descompón la receta completa en ingredientes, estimando los gramos comestibles y los nutrientes "
        "por 100 g de cada ingrediente. Devuelve los pesos para toda la receta, no por ración."
    )
    try:
        result = estimate_meal(prompt)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, "No se pudo estimar la receta con la IA. Puedes añadir los ingredientes manualmente.") from exc
    return result


@router.post("/from-estimate", status_code=201)
def create_recipe_from_estimate(body: RecipeFromEstimateIn, db: Session = Depends(get_db),
                                uid: int = Depends(current_user_id)):
    """Guarda como alimentos privados los ingredientes estimados y crea una receta revisable."""
    total_grams = sum(item.grams for item in body.items)
    if total_grams <= 0 or total_grams > 5000:
        raise HTTPException(422, "La cantidad total de la receta debe estar entre 0 y 5000 g.")
    r = Recipe(
        user_id=uid, name=body.name.strip(), description=body.description,
        serving_count=body.serving_count, steps=body.steps,
    )
    for item in body.items:
        if item.protein_g_per_100g + item.carbs_g_per_100g + item.fat_g_per_100g > 105:
            raise HTTPException(422, f"Macronutrientes no plausibles en {item.name}.")
        if item.sugars_g_per_100g > item.carbs_g_per_100g + 0.5 or item.sat_fat_g_per_100g > item.fat_g_per_100g + 0.5:
            raise HTTPException(422, f"Valores nutricionales incoherentes en {item.name}.")
        food = Food(
            user_id=uid, source="manual", name=item.name.strip(), serving_g=item.grams,
            kcal=item.kcal_per_100g, protein_g=item.protein_g_per_100g,
            carbs_g=item.carbs_g_per_100g, sugars_g=item.sugars_g_per_100g,
            fat_g=item.fat_g_per_100g, sat_fat_g=item.sat_fat_g_per_100g,
            fiber_g=item.fiber_g_per_100g, sodium_mg=item.sodium_mg_per_100g,
            confidence="low",
            attribution="Estimación orientativa de IA revisada por el usuario; no equivale a análisis de laboratorio.",
            extra={"ai_estimated_recipe_ingredient": True},
        )
        db.add(food)
        db.flush()
        r.ingredients.append(RecipeIngredient(
            food_id=food.id, quantity_g=item.grams, unit_name=item.unit_name,
            quantity=item.quantity, grams_per_unit=item.grams_per_unit,
        ))
    db.add(r)
    db.flush()
    svc.sync_recipe_food(db, r)
    db.commit()
    return _detail(r, uid)

@router.post("", status_code=201)
def create_recipe(body: RecipeIn, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    r = Recipe(user_id=uid, name=body.name.strip(), description=body.description, serving_count=body.serving_count, steps=body.steps)
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
    r.name, r.description, r.serving_count, r.steps = body.name.strip(), body.description, body.serving_count, body.steps
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
               description=src.description, serving_count=src.serving_count, steps=list(src.steps or []))
    r.ingredients = [RecipeIngredient(
        food_id=i.food_id, quantity_g=i.quantity_g, unit_name=i.unit_name or "g",
        quantity=i.quantity, grams_per_unit=i.grams_per_unit,
    ) for i in src.ingredients]
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
