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
