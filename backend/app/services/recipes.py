"""Alimentos compuestos: nutrientes = suma de (nutriente por 100 g × gramos del ingrediente / 100).

Cada receta tiene un alimento «sombra» (foods.source='recipe', por 100 g de plato terminado) para que aparezca en la búsqueda y
en los habituales como cualquier alimento. Al REGISTRAR una receta se guarda una instantánea de los nutrientes (FoodLog), de modo
que cambiar la receta después no altera el histórico."""
from __future__ import annotations

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from ..models import NUTRIENTS, Food, FoodLog, FoodServing, Recipe, RecipeIngredient


def sum_nutrients(items: list[tuple[Food, float]]) -> dict[str, float]:
    """items: [(alimento, gramos)] -> nutrientes totales."""
    total = {n: 0.0 for n in NUTRIENTS}
    for food, grams in items:
        for n in NUTRIENTS:
            total[n] += (getattr(food, n) or 0) * grams / 100
    return {n: round(v, 2) for n, v in total.items()}


def summarize(items: list[tuple[Food, float]], serving_count: float) -> dict:
    total_g = round(sum(g for _, g in items), 2)
    total = sum_nutrients(items)
    k = 1 / serving_count if serving_count else 1
    return {"total_g": total_g, "serving_count": serving_count, "serving_g": round(total_g * k, 1),
            "totals": total, "per_serving": {n: round(v * k, 1) for n, v in total.items()}}


def recipe_items(r: Recipe, quantities: dict[int, float] | None = None) -> list[tuple[Food, float]]:
    """Ingredientes con sus gramos; `quantities` (id de ingrediente -> gramos) sustituye cantidades solo para este cálculo."""
    q = quantities or {}
    return [(i.food, q.get(i.id, i.quantity_g)) for i in r.ingredients]


def sync_recipe_food(db: Session, r: Recipe) -> Food:
    """Crea/actualiza el alimento sombra de la receta (por 100 g de plato terminado)."""
    items = recipe_items(r)
    total_g = sum(g for _, g in items) or 1.0
    per100 = {n: round(v * 100 / total_g, 2) for n, v in sum_nutrients(items).items()}
    food = db.get(Food, r.food_id) if r.food_id else None
    if food is None:
        food = Food(user_id=r.user_id, source="recipe", name=r.name, **per100)
        db.add(food)
        db.flush()
        r.food_id = food.id
    else:
        food.name = r.name
        for n, v in per100.items():
            setattr(food, n, v)
    food.serving_g = round(total_g / (r.serving_count or 1), 1)
    food.confidence, food.license, food.attribution = "medium", None, "Receta calculada a partir de sus ingredientes."
    db.add(food)
    return food


def visible_recipes(db: Session, uid: int, q: str | None = None, limit: int = 50) -> list[Recipe]:
    # Las variantes de café con leche son bebidas genéricas del catálogo, no recetas.
    legacy_drink_recipes = ("Café con leche (leche entera)", "Café con leche (leche semidesnatada)", "Café con leche (leche desnatada)")
    stmt = select(Recipe).where(
        or_(Recipe.user_id.is_(None), Recipe.user_id == uid),
        not_(and_(Recipe.user_id.is_(None), Recipe.name.in_(legacy_drink_recipes))),
    )
    if q and q.strip():
        stmt = stmt.where(func.unaccent(func.lower(Recipe.name)).ilike(f"%{q.strip().lower()}%"))
    return list(db.scalars(stmt.order_by(Recipe.user_id.is_(None), Recipe.name).limit(limit)))


def delete_recipe(db: Session, r: Recipe) -> None:
    food_id = r.food_id
    r.food_id = None
    db.delete(r)
    db.flush()
    if food_id:
        used = db.scalar(select(func.count()).select_from(FoodLog).where(FoodLog.food_id == food_id))
        if not used:  # sin historial: se borra del todo; con historial se conserva el alimento para no romper los registros
            from sqlalchemy import delete
            db.execute(delete(FoodServing).where(FoodServing.food_id == food_id))
            db.execute(delete(Food).where(Food.id == food_id))
