"""Recetas (F03), fuentes nutricionales (F04) y unidades (F05)."""
from conftest import onboard_new_user, rnd


def food_id(client, h, name):
    return next(f["id"] for f in client.get("/foods/search", params={"q": name, "online": False}, headers=h).json() if f["name"] == name)


# ───────────── recetas ─────────────
def test_system_recipes_are_seeded_and_sum_ingredients(client, onboarded):
    h = onboarded["headers"]
    recs = {r["name"]: r for r in client.get("/recipes", headers=h).json()}
    assert {"Tostada con hummus", "Café con leche (leche entera)", "Yogur con avena y fruta"} <= set(recs)
    r = client.get(f"/recipes/{recs['Tostada con hummus']['id']}", headers=h).json()
    # pan 60 g (265 kcal/100) + hummus 30 g (166 kcal/100) = 158.9 + 49.8
    assert r["is_system"] and r["editable"] is False and abs(r["totals"]["kcal"] - 208.8) < 0.5 and r["total_g"] == 90


def test_preview_recomputes_in_real_time_without_saving(client, onboarded):
    h = onboarded["headers"]
    leche, cafe = food_id(client, h, "Leche entera"), food_id(client, h, "Café (infusión, sin azúcar)")
    a = client.post("/recipes/preview", json={"ingredients": [{"food_id": leche, "quantity_g": 100}, {"food_id": cafe, "quantity_g": 100}]}, headers=h).json()
    b = client.post("/recipes/preview", json={"ingredients": [{"food_id": leche, "quantity_g": 200}, {"food_id": cafe, "quantity_g": 100}]}, headers=h).json()
    assert abs(b["totals"]["kcal"] - a["totals"]["kcal"] - 61) < 0.1
    half = client.post("/recipes/preview", json={"serving_count": 2, "ingredients": [{"food_id": leche, "quantity_g": 200}]}, headers=h).json()
    assert half["per_serving"]["kcal"] == 61 and half["serving_g"] == 100


def test_create_log_snapshot_and_history_is_not_rewritten(client):
    u = onboard_new_user(client); h = u["headers"]
    pan, hummus = food_id(client, h, "Pan de molde"), food_id(client, h, "Hummus")
    r = client.post("/recipes", json={"name": f"Mi tostada {rnd()}", "serving_count": 2, "ingredients": [
        {"food_id": pan, "quantity_g": 100}, {"food_id": hummus, "quantity_g": 60}]}, headers=h).json()
    assert r["editable"] and r["per_serving"]["kcal"] == round((265 + 166 * 0.6) / 2, 1)
    log = client.post(f"/recipes/{r['id']}/log", json={"servings": 2, "meal": "breakfast"}, headers=h)
    assert log.status_code == 201 and abs(log.json()["kcal"] - (265 + 99.6)) < 0.1 and log.json()["grams"] == 160
    # cambiar la receta después NO cambia lo ya registrado
    client.put(f"/recipes/{r['id']}", json={"name": r["name"], "serving_count": 2, "ingredients": [{"food_id": pan, "quantity_g": 10}]}, headers=h)
    day = client.get("/dashboard/day", headers=h).json()
    assert abs(day["totals"]["kcal"] - 364.6) < 0.2
    # con cantidades modificadas solo para esta toma
    ing = client.get(f"/recipes/{r['id']}", headers=h).json()["ingredients"][0]["id"]
    again = client.post(f"/recipes/{r['id']}/log", json={"servings": 1, "quantities": {ing: 40}}, headers=h).json()
    assert abs(again["kcal"] - 53) < 0.1 and again["grams"] == 20      # 265 kcal/100 g × 40 g × (1 de 2 raciones)
    assert client.post(f"/recipes/{r['id']}/log", json={"quantities": {999999: 5}}, headers=h).status_code == 422


def test_recipe_is_searchable_as_food_and_permissions(client):
    u, other = onboard_new_user(client), onboard_new_user(client)
    pan = food_id(client, u["headers"], "Pan de molde")
    name = f"Bocata {rnd()}"
    r = client.post("/recipes", json={"name": name, "ingredients": [{"food_id": pan, "quantity_g": 80}]}, headers=u["headers"]).json()
    assert any(f["name"] == name and f["source"] == "recipe" for f in client.get("/foods/search", params={"q": name, "online": False}, headers=u["headers"]).json())
    assert not any(f["name"] == name for f in client.get("/foods/search", params={"q": name, "online": False}, headers=other["headers"]).json())
    assert client.get(f"/recipes/{r['id']}", headers=other["headers"]).status_code == 404
    assert client.put(f"/recipes/{r['id']}", json={"name": "x", "ingredients": [{"food_id": pan, "quantity_g": 1}]}, headers=other["headers"]).status_code == 404
    sys_id = next(x["id"] for x in client.get("/recipes", headers=u["headers"]).json() if x["is_system"])
    assert client.delete(f"/recipes/{sys_id}", headers=u["headers"]).status_code == 403
    copy = client.post(f"/recipes/{sys_id}/copy", headers=u["headers"]).json()
    assert copy["editable"] and not copy["is_system"]
    assert client.post("/recipes", json={"name": "ciclo", "ingredients": [{"food_id": r["food_id"], "quantity_g": 10}]}, headers=u["headers"]).status_code == 422
    assert client.delete(f"/recipes/{r['id']}", headers=u["headers"]).status_code == 204


# ───────────── unidades ─────────────
def test_servings_log_in_units_converts_to_grams(client, onboarded):
    h = onboarded["headers"]
    hummus = food_id(client, h, "Hummus")
    sv = {s["unit_name"]: s for s in client.get(f"/foods/{hummus}/servings", headers=h).json()}
    assert sv["cucharada"]["grams_per_unit"] == 15
    r = client.post("/logs", json={"food_id": hummus, "serving_id": sv["cucharada"]["id"], "quantity": 2}, headers=h)
    assert r.status_code == 201 and r.json()["grams"] == 30
    assert client.post("/logs", json={"food_id": hummus, "serving_id": sv["cucharada"]["id"]}, headers=h).status_code == 422
    assert client.post("/logs", json={"food_id": hummus}, headers=h).status_code == 422
    pan = food_id(client, h, "Pan de molde")
    assert client.post("/logs", json={"food_id": pan, "serving_id": sv["cucharada"]["id"], "quantity": 1}, headers=h).status_code == 404  # unidad de otro alimento
    assert client.post("/logs", json={"food_id": hummus, "grams": 20}, headers=h).status_code == 201   # los gramos siguen funcionando


def test_custom_servings_only_on_own_foods(client, onboarded):
    h = onboarded["headers"]
    mine = client.post("/foods", json={"name": f"Queso {rnd()}", "kcal": 400}, headers=h).json()
    ok = client.post(f"/foods/{mine['id']}/servings", json={"unit_name": "loncha", "unit_name_plural": "lonchas", "grams_per_unit": 20}, headers=h)
    assert ok.status_code == 201
    assert client.post(f"/foods/{mine['id']}/servings", json={"unit_name": "loncha", "grams_per_unit": 25}, headers=h).status_code == 409
    shared = food_id(client, h, "Hummus")
    assert client.post(f"/foods/{shared}/servings", json={"unit_name": "x", "grams_per_unit": 1}, headers=h).status_code == 404
    assert client.delete(f"/foods/{mine['id']}/servings/{ok.json()['id']}", headers=h).status_code == 204


