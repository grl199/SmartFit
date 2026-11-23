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

