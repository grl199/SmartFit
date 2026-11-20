"""Catálogo interno SmartFit: alimentos genéricos de uso diario, sus raciones habituales y recetas predefinidas.

Los valores son orientativos (referencia: composición genérica tipo USDA FoodData Central, CC0). Se marcan con
confianza «medium» y fuente «catalog»; si necesitas precisión, usa el producto concreto. Todo se siembra de forma idempotente
(clave `external_id` = «smartfit:<slug>»)."""
import logging
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Food, FoodServing, Recipe, RecipeIngredient

log = logging.getLogger(__name__)
ATTRIBUTION = "Valores genéricos orientativos de SmartFit (referencia: USDA FoodData Central, CC0)."

# nombre: (kcal, prot, hidr, azúcares, grasa, saturadas, fibra, sodio_mg, [(unidad, plural, gramos, aclaración)])
FOODS: dict[str, tuple] = {
    "Café (infusión, sin azúcar)": (1, 0.1, 0, 0, 0, 0, 0, 2, [("taza", "tazas", 150, "taza de café largo"), ("ml", "ml", 1.0, "mililitros")]),
    "Leche entera": (61, 3.2, 4.8, 4.8, 3.3, 1.9, 0, 43, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.03, "mililitros")]),
    "Leche semidesnatada": (46, 3.3, 4.8, 4.8, 1.6, 1.0, 0, 44, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.03, "mililitros")]),
    "Leche desnatada": (34, 3.4, 4.9, 4.9, 0.1, 0.1, 0, 44, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.03, "mililitros")]),
    "Pan de molde": (265, 8.0, 49, 4.0, 3.2, 0.8, 2.7, 490, [("rebanada", "rebanadas", 30, "rebanada media")]),
    "Hummus": (166, 7.9, 14.3, 0.3, 9.6, 1.4, 6.0, 379, [("cucharada", "cucharadas", 15, "cucharada sopera colmada")]),
    "Aceite de oliva virgen extra": (884, 0, 0, 0, 100, 13.8, 0, 2, [("cucharada", "cucharadas", 13.5, "cucharada sopera"), ("cucharadita", "cucharaditas", 4.5, None), ("ml", "ml", 0.91, "mililitros")]),
    "Tomate": (18, 0.9, 3.9, 2.6, 0.2, 0, 1.2, 5, [("rodaja", "rodajas", 20, "rodaja de tomate mediano"), ("unidad", "unidades", 120, "tomate mediano")]),
    "Yogur natural": (61, 3.5, 4.7, 4.7, 3.3, 2.1, 0, 46, [("unidad", "unidades", 125, "tarrina de 125 g")]),
    "Copos de avena": (389, 16.9, 66.3, 0, 6.9, 1.2, 10.6, 2, [("cucharada", "cucharadas", 10, "cucharada sopera"), ("puñado", "puñados", 30, None)]),
    "Plátano": (89, 1.1, 22.8, 12.2, 0.3, 0.1, 2.6, 1, [("unidad", "unidades", 120, "plátano mediano sin piel")]),
    "Almendras": (579, 21.2, 21.6, 4.4, 49.9, 3.8, 12.5, 1, [("unidad", "unidades", 1.2, "almendra"), ("puñado", "puñados", 28, None)]),
}
# receta: (descripción, raciones, [(alimento, gramos)])
RECIPES: dict[str, tuple[str, float, list[tuple[str, float]]]] = {
    "Café con leche (leche entera)": ("Café con leche entera.", 1, [("Café (infusión, sin azúcar)", 100), ("Leche entera", 100)]),
    "Café con leche (leche semidesnatada)": ("Café con leche semidesnatada.", 1, [("Café (infusión, sin azúcar)", 100), ("Leche semidesnatada", 100)]),
    "Café con leche (leche desnatada)": ("Café con leche desnatada.", 1, [("Café (infusión, sin azúcar)", 100), ("Leche desnatada", 100)]),
    "Tostada con hummus": ("Dos rebanadas de pan con hummus.", 1, [("Pan de molde", 60), ("Hummus", 30)]),
    "Tostada con aceite y tomate": ("Dos rebanadas de pan con tomate y aceite de oliva.", 1,
                                    [("Pan de molde", 60), ("Tomate", 60), ("Aceite de oliva virgen extra", 10)]),
    "Yogur con avena y fruta": ("Yogur natural con copos de avena y plátano.", 1,
                                [("Yogur natural", 125), ("Copos de avena", 30), ("Plátano", 60)]),
}


def slug(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def seed_food_catalog(db: Session) -> int:
    """Inserta lo que falte (alimentos, raciones y recetas del sistema). Devuelve cuántos alimentos añadió."""
    from .recipes import sync_recipe_food
    existing = {f.external_id: f for f in db.scalars(select(Food).where(Food.user_id.is_(None), Food.source == "catalog"))}
    added = 0
    for name, (kcal, p, c, sug, fat, sat, fib, sod, servings) in FOODS.items():
        key = f"smartfit:{slug(name)}"
        food = existing.get(key)
        if food is None:
            food = Food(user_id=None, name=name, source="catalog", external_id=key, kcal=kcal, protein_g=p, carbs_g=c, sugars_g=sug,
                        fat_g=fat, sat_fat_g=sat, fiber_g=fib, sodium_mg=sod, confidence="medium", license="CC0", attribution=ATTRIBUTION)
            db.add(food)
            db.flush()
            added += 1
        have = {s.unit_name for s in db.scalars(select(FoodServing).where(FoodServing.food_id == food.id))}
        for unit, plural, grams, desc in servings:
            if unit not in have:
                db.add(FoodServing(food_id=food.id, unit_name=unit, unit_name_plural=plural, grams_per_unit=grams, description=desc))
    db.commit()
    by_name = {f.name: f for f in db.scalars(select(Food).where(Food.user_id.is_(None), Food.source == "catalog"))}
    have_recipes = {r.name for r in db.scalars(select(Recipe).where(Recipe.user_id.is_(None)))}
    for name, (desc, servings, ings) in RECIPES.items():
        if name in have_recipes:
            continue
        r = Recipe(user_id=None, name=name, description=desc, serving_count=servings)
        r.ingredients = [RecipeIngredient(food_id=by_name[n].id, quantity_g=g) for n, g in ings]
        db.add(r)
        db.flush()
        sync_recipe_food(db, r)
    db.commit()
    if added:
        log.info("Catálogo de alimentos: %s añadidos", added)
    return added
