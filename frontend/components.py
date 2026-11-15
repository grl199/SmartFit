import streamlit as st

import api
import ui

MEALS = {"breakfast": "Desayuno", "lunch": "Comida", "snack": "Snack", "dinner": "Cena"}
NUTRIENT_LABELS = {"kcal": "kcal", "protein_g": "Proteína (g)", "carbs_g": "Hidratos (g)", "fat_g": "Grasa (g)",
                   "sugars_g": "Azúcares (g)", "sat_fat_g": "Saturadas (g)", "fiber_g": "Fibra (g)"}


def quick_add_bar(limit: int = 12, per_row: int = 4) -> None:
    """Barra de alimentos habituales: un clic = registrar la cantidad típica."""
    items = api.get("/logs/frequent", limit=limit) or []
    if not items:
        st.caption("Aquí aparecerán tus alimentos más habituales para re-registrarlos con un clic.")
        return
    for i in range(0, len(items), per_row):
        for col, it in zip(st.columns(per_row), items[i:i + per_row]):
            f = it["food"]
            if col.button(f"{f['name'][:22]} · {it['typical_grams']:.0f} g", key=f"qa_{f['id']}",
                          width="stretch", help=f"{it['times']} veces en los últimos 60 días"):
                if api.post("/logs", json={"food_id": f["id"], "grams": it["typical_grams"]}):
                    st.toast(f"Añadido: {f['name']} ({it['typical_grams']:.0f} g)", icon="✅")
                    st.rerun()


def full_food(food: dict) -> dict:
    """Ficha completa: si el alimento viene de Open Food Facts, el backend completa foto, Nutri-Score,
    NOVA, alérgenos e ingredientes la primera vez que se selecciona. Se cachea en la sesión."""
    cache = st.session_state.setdefault("_food_full", {})
    if food["id"] not in cache:
        cache[food["id"]] = api.get(f"/foods/{food['id']}") or food
    return cache[food["id"]]


def food_log_form(food: dict, key: str, log_date: str | None = None, meal: str | None = None) -> None:
    """Ficha del alimento -> gramos -> vista previa de nutrientes consumidos -> registrar."""
    food = full_food(food)
    with st.container(border=True):
        ui.html(ui.food_header(food))
        if food.get("ingredients") or food.get("categories"):
            with st.expander("Ingredientes y categorías"):
                if food.get("categories"):
                    ui.html(ui.chips(food["categories"], "blue"))
                if food.get("ingredients"):
                    st.caption(food["ingredients"])
        st.caption("Valores por 100 g: " + " · ".join(
            f"{lbl} {food[k]:.1f}" for k, lbl in NUTRIENT_LABELS.items() if k in ("kcal", "protein_g", "carbs_g", "fat_g")))
        default = float(food.get("serving_g") or 100)
        grams = st.number_input("Cantidad (g)", min_value=1.0, max_value=5000.0, value=default, step=5.0, key=f"g_{key}")
        cols = st.columns(len(NUTRIENT_LABELS) + 1)
        for col, (k, lbl) in zip(cols, NUTRIENT_LABELS.items()):
            col.metric(lbl, f"{food[k] * grams / 100:.1f}")
        cols[-1].metric("Sal (g)", f"{food['sodium_mg'] * 2.5 * grams / 100000:.2f}")
        if st.button("➕ Añadir al diario", key=f"add_{key}", type="primary"):
            payload = {"food_id": food["id"], "grams": grams, "meal": meal, "log_date": log_date}
            if api.post("/logs", json=payload):
                st.toast("Registrado", icon="✅")
                st.session_state.pop("scanned_food", None)
                st.rerun()
