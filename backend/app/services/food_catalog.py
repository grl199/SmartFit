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

    "Pan integral": (247, 13.0, 41.0, 5.0, 4.2, 0.8, 7.0, 400, [("rebanada", "rebanadas", 35, "rebanada mediana")]),
    "Pan de barra": (270, 9.0, 52.0, 2.5, 1.8, 0.4, 2.7, 550, [("rebanada", "rebanadas", 30, "rebanada fina"), ("trozo", "trozos", 50, "trozo pequeño")]),
    "Huevo entero": (143, 12.6, 0.7, 0.4, 9.5, 3.1, 0.0, 142, [("unidad", "unidades", 60, "huevo mediano sin cáscara")]),
    "Atún al natural escurrido": (116, 25.5, 0.0, 0.0, 0.8, 0.2, 0.0, 300, [("lata", "latas", 60, "peso escurrido orientativo")]),
    "Pechuga de pollo cocinada": (165, 31.0, 0.0, 0.0, 3.6, 1.0, 0.0, 74, [("filete", "filetes", 120, "filete mediano")]),
    "Pavo cocinado": (135, 29.0, 0.0, 0.0, 1.6, 0.4, 0.0, 50, [("filete", "filetes", 100, "filete mediano")]),
    "Pavo fiambre": (105, 18.0, 2.0, 1.5, 2.0, 0.5, 0.0, 900, [("loncha", "lonchas", 20, "loncha fina")]),
    "Jamón cocido": (116, 20.9, 1.5, 1.0, 3.4, 1.2, 0.0, 900, [("loncha", "lonchas", 20, "loncha fina")]),
    "Aguacate": (160, 2.0, 8.5, 0.7, 14.7, 2.1, 6.7, 7, [("medio", "medios", 75, "medio aguacate sin piel ni hueso")]),
    "Lechuga": (15, 1.4, 2.9, 0.8, 0.2, 0.0, 1.3, 28, [("hoja", "hojas", 10, "hoja grande")]),
    "Pepino": (15, 0.7, 3.6, 1.7, 0.1, 0.0, 0.5, 2, [("unidad", "unidades", 250, "pepino mediano")]),
    "Cebolla": (40, 1.1, 9.3, 4.2, 0.1, 0.0, 1.7, 4, [("unidad", "unidades", 110, "cebolla mediana")]),
    "Zanahoria": (41, 0.9, 9.6, 4.7, 0.2, 0.0, 2.8, 69, [("unidad", "unidades", 60, "zanahoria mediana")]),
    "Arroz blanco cocido": (130, 2.7, 28.2, 0.1, 0.3, 0.1, 0.4, 1, [("vaso", "vasos", 160, "vaso de arroz cocido")]),
    "Pasta cocida": (158, 5.8, 30.9, 0.6, 0.9, 0.2, 1.8, 1, [("plato", "platos", 180, "ración cocida")]),
    "Patata cocida": (87, 1.9, 20.1, 0.9, 0.1, 0.0, 1.8, 4, [("unidad", "unidades", 150, "patata mediana")]),
    "Garbanzos cocidos": (164, 8.9, 27.4, 4.8, 2.6, 0.3, 7.6, 7, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Lentejas cocidas": (116, 9.0, 20.1, 1.8, 0.4, 0.1, 7.9, 2, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Quinoa cocida": (120, 4.4, 21.3, 0.9, 1.9, 0.2, 2.8, 7, [("vaso", "vasos", 150, "vaso de quinoa cocida")]),
    "Queso fresco batido 0%": (46, 8.5, 3.5, 3.5, 0.2, 0.1, 0.0, 40, [("tarrina", "tarrinas", 200, "tarrina individual")]),
    "Queso fresco": (174, 11.0, 3.4, 2.7, 12.7, 8.3, 0.0, 450, [("porción", "porciones", 50, "porción individual")]),
    "Manzana": (52, 0.3, 13.8, 10.4, 0.2, 0.0, 2.4, 1, [("unidad", "unidades", 170, "manzana mediana")]),
    "Naranja": (47, 0.9, 11.8, 9.4, 0.1, 0.0, 2.4, 0, [("unidad", "unidades", 150, "naranja mediana sin piel")]),
    "Fresas": (32, 0.7, 7.7, 4.9, 0.3, 0.0, 2.0, 1, [("puñado", "puñados", 80, None)]),
    "Yogur griego natural": (97, 9.0, 3.9, 3.2, 5.0, 3.3, 0.0, 35, [("unidad", "unidades", 150, "tarrina individual")]),
    "Espinacas": (23, 2.9, 3.6, 0.4, 0.4, 0.1, 2.2, 79, [("puñado", "puñados", 30, None)]),
    "Champiñones": (22, 3.1, 3.3, 2.0, 0.3, 0.0, 1.0, 5, [("unidad", "unidades", 18, "champiñón mediano")]),
    "Salsa de tomate casera": (50, 1.5, 7.0, 5.0, 1.8, 0.3, 1.5, 250, [("cucharada", "cucharadas", 20, "cucharada sopera")]),

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

    "Tostada integral con aguacate": ("Tostada de pan integral con aguacate y un toque de aceite.", 1,
                                      [("Pan integral", 50), ("Aguacate", 40), ("Aceite de oliva virgen extra", 5)]),
    "Tostada integral con tomate y aceite": ("Tostada integral con tomate natural y aceite de oliva.", 1,
                                             [("Pan integral", 50), ("Tomate", 60), ("Aceite de oliva virgen extra", 8)]),
    "Tostada integral con pavo": ("Tostada integral con pavo y tomate.", 1,
                                  [("Pan integral", 50), ("Pavo fiambre", 40), ("Tomate", 30)]),
    "Bocadillo de pavo y tomate": ("Bocadillo pequeño de pavo con tomate.", 1,
                                  [("Pan de barra", 100), ("Pavo fiambre", 60), ("Tomate", 30)]),
    "Ensalada mixta con atún": ("Ensalada de lechuga, tomate, pepino, atún, huevo y aceite.", 1,
                               [("Lechuga", 60), ("Tomate", 100), ("Pepino", 50), ("Atún al natural escurrido", 80),
                                ("Huevo entero", 60), ("Aceite de oliva virgen extra", 8)]),
    "Ensalada de garbanzos y atún": ("Ensalada de garbanzos con atún, tomate y cebolla.", 1,
                                    [("Garbanzos cocidos", 150), ("Atún al natural escurrido", 80), ("Tomate", 60),
                                     ("Cebolla", 20), ("Aceite de oliva virgen extra", 8)]),
    "Ensalada de quinoa": ("Ensalada fría de quinoa, tomate, pepino y aguacate.", 1,
                           [("Quinoa cocida", 120), ("Tomate", 60), ("Pepino", 50), ("Aguacate", 40),
                            ("Aceite de oliva virgen extra", 5)]),
    "Ensalada de lentejas": ("Ensalada de lentejas con tomate, cebolla y zanahoria.", 1,
                             [("Lentejas cocidas", 150), ("Tomate", 60), ("Cebolla", 20), ("Zanahoria", 40),
                              ("Aceite de oliva virgen extra", 8)]),
    "Tortilla francesa": ("Tortilla francesa de dos huevos con aceite.", 1,
                          [("Huevo entero", 120), ("Aceite de oliva virgen extra", 5)]),
    "Huevos revueltos con queso fresco": ("Huevos revueltos con queso fresco.", 1,
                                         [("Huevo entero", 120), ("Queso fresco", 40)]),
    "Pollo con arroz": ("Pechuga de pollo a la plancha con arroz blanco cocido.", 1,
                        [("Pechuga de pollo cocinada", 120), ("Arroz blanco cocido", 150)]),
    "Pasta con tomate y atún": ("Pasta cocida con salsa de tomate y atún.", 1,
                                [("Pasta cocida", 180), ("Salsa de tomate casera", 60),
                                 ("Atún al natural escurrido", 70), ("Aceite de oliva virgen extra", 5)]),
    "Lentejas estofadas caseras": ("Lentejas con zanahoria, cebolla y patata.", 1,
                                   [("Lentejas cocidas", 180), ("Zanahoria", 40), ("Cebolla", 30),
                                    ("Patata cocida", 60), ("Aceite de oliva virgen extra", 5)]),
    "Arroz con pollo y verduras": ("Arroz con pollo, zanahoria y cebolla.", 1,
                                   [("Arroz blanco cocido", 150), ("Pechuga de pollo cocinada", 100),
                                    ("Zanahoria", 40), ("Cebolla", 30), ("Aceite de oliva virgen extra", 5)]),
    "Patata cocida con huevo y atún": ("Patata cocida con huevo, atún y aceite de oliva.", 1,
                                       [("Patata cocida", 150), ("Huevo entero", 60), ("Atún al natural escurrido", 60),
                                        ("Aceite de oliva virgen extra", 5)]),
    "Garbanzos con espinacas": ("Garbanzos guisados con espinacas y tomate.", 1,
                                [("Garbanzos cocidos", 150), ("Espinacas", 80), ("Tomate", 40),
                                 ("Cebolla", 20), ("Aceite de oliva virgen extra", 5)]),
    "Porridge de avena con leche y plátano": ("Gachas de avena con leche entera y plátano.", 1,
                                              [("Copos de avena", 40), ("Leche entera", 150), ("Plátano", 60)]),
    "Yogur griego con fresas y avena": ("Yogur griego natural con fresas y avena.", 1,
                                       [("Yogur griego natural", 150), ("Fresas", 80), ("Copos de avena", 20)]),
    "Batido de plátano y leche": ("Batido casero de plátano con leche entera.", 1,
                                  [("Plátano", 100), ("Leche entera", 200)]),
    "Crema de verduras casera": ("Crema de zanahoria, patata, cebolla y espinacas.", 1,
                                 [("Zanahoria", 80), ("Patata cocida", 100), ("Cebolla", 30),
                                  ("Espinacas", 30), ("Aceite de oliva virgen extra", 5)]),

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
