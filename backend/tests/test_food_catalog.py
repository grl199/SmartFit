from types import SimpleNamespace


def test_food_catalog_is_broad_and_recipe_ingredients_exist():
    from app.services.food_catalog import FOODS, RECIPES

    assert len(FOODS) >= 90
    assert len(RECIPES) >= 40
    assert "Tostada con hummus" not in FOODS
    assert "Tostada con hummus" in RECIPES
    missing = {
        ingredient
        for _, _, ingredients in RECIPES.values()
        for ingredient, _ in ingredients
        if ingredient not in FOODS
    }
    assert not missing, f"ingredientes de receta sin alimento base: {sorted(missing)}"


def test_unified_search_mix_keeps_generic_and_branded_products_visible():
    from app.services.food_search import _mix

    items = [
        SimpleNamespace(source="catalog", name="Avena"),
        SimpleNamespace(source="catalog", name="Plátano"),
        SimpleNamespace(source="openfoodfacts", name="Yogur de marca"),
        SimpleNamespace(source="catalog", name="Huevo"),
        SimpleNamespace(source="openfoodfacts", name="Pan de molde de marca"),
    ]
    mixed = _mix(items, 5)
    assert [item.name for item in mixed] == [
        "Avena", "Plátano", "Yogur de marca", "Huevo", "Pan de molde de marca"
    ]

def test_every_generic_food_belongs_to_a_catalog_section():
    from app.services.food_catalog import FOOD_CATALOG_SECTIONS, FOOD_SECTION_BY_NAME, FOODS

    assert len(FOODS) >= 120
    assert len(FOOD_CATALOG_SECTIONS) >= 7
    assert set(FOOD_SECTION_BY_NAME) == set(FOODS)
    sectioned = [name for _, _, _, _, names in FOOD_CATALOG_SECTIONS for name in names]
    assert set(sectioned) == set(FOODS)
    assert len(sectioned) == len(set(sectioned))


def test_generic_search_scope_is_distinct_from_branded_products():
    from app.services.nutrition import search_foods

    # La búsqueda "catalog" se limita a alimentos genéricos compartidos,
    # mientras que "openfoodfacts" es la fuente de productos envasados.
    import inspect
    source = inspect.getsource(search_foods)
    assert 'if source == "catalog"' in source
    assert 'Food.source == "catalog"' in source

def test_every_catalog_food_has_an_icon_and_coffee_lives_in_beverages():
    from app.services.food_catalog import (
        FOOD_CATALOG_SECTIONS,
        FOOD_SECTION_BY_NAME,
        FOODS,
        RECIPES,
        food_icon,
    )

    assert len(FOODS) >= 125
    assert all(food_icon(name) for name in FOODS)
    assert FOOD_SECTION_BY_NAME["Café con leche (leche entera)"] == "beverages"
    assert FOOD_SECTION_BY_NAME["Café con leche (leche semidesnatada)"] == "beverages"
    assert not any(name.startswith("Café con leche") for name in RECIPES)
    beverage = next(section for section in FOOD_CATALOG_SECTIONS if section[0] == "beverages")
    assert "Café con leche (leche entera)" in beverage[4]


def test_system_recipes_include_preparation_steps():
    from app.services.food_catalog import RECIPES, recipe_preparation_steps

    assert "Pisto con huevo" in RECIPES
    steps = recipe_preparation_steps("Pisto con huevo")
    assert len(steps) >= 4
    assert any("berenjena" in step.lower() for step in steps)
    assert all(step.strip() for step in steps)

def test_recipe_payload_accepts_preparation_steps():
    from app.routers.recipes import RecipeIn

    recipe = RecipeIn(
        name="Mi pisto",
        description="Pisto casero",
        serving_count=2,
        steps=["Cortar las verduras", "Pochar la cebolla", "Añadir el tomate y cocinar"],
        ingredients=[{"food_id": 1, "quantity_g": 100}],
    )
    assert recipe.steps == ["Cortar las verduras", "Pochar la cebolla", "Añadir el tomate y cocinar"]




def test_recipe_ingredient_unit_is_normalized_to_grams():
    from app.routers.recipes import IngredientIn

    row = IngredientIn(food_id=1, quantity_g=30, unit_name="cucharada", quantity=2, grams_per_unit=15)
    assert row.quantity_g == 30
    assert row.quantity == 2


def test_recipe_ingredient_requires_conversion_for_non_gram_units():
    import pytest
    from pydantic import ValidationError
    from app.routers.recipes import IngredientIn

    with pytest.raises(ValidationError):
        IngredientIn(food_id=1, quantity_g=30, unit_name="trozo", quantity=2)


def test_automatic_meal_assignment_has_five_categories():
    from app.services.nutrition import guess_meal

    assert [guess_meal(hour) for hour in (8, 10, 13, 17, 21)] == [
        "breakfast", "mid_morning", "lunch", "snack", "dinner"
    ]
