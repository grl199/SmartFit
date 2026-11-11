import streamlit as st

import api

MEALS = {"breakfast": "Desayuno", "lunch": "Comida", "snack": "Snack", "dinner": "Cena"}
NUTRIENT_LABELS = {"kcal": "kcal", "protein_g": "Proteína (g)", "carbs_g": "Hidratos (g)", "fat_g": "Grasa (g)",
                   "sugars_g": "Azúcares (g)", "fiber_g": "Fibra (g)", "sodium_mg": "Sodio (mg)"}


def progress_block(totals: dict, targets: dict) -> None:
    items = [("kcal", "Calorías", "kcal"), ("protein_g", "Proteína", "g"), ("carbs_g", "Hidratos", "g"),
             ("fat_g", "Grasa", "g"), ("fiber_g", "Fibra", "g")]
    for col, (key, label, unit) in zip(st.columns(len(items)), items):
        val, goal = totals.get(key, 0), targets.get(key) or 0
        with col:
            st.metric(label, f"{val:.0f} / {goal:.0f} {unit}",
                      delta=f"{val - goal:+.0f}" if goal and val > goal else None, delta_color="inverse")
            st.progress(min(val / goal, 1.0) if goal else 0.0)


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


def food_log_form(food: dict, key: str, log_date: str | None = None, meal: str | None = None) -> None:
    """Gramos -> vista previa de nutrientes consumidos -> registrar."""
    st.markdown(f"**{food['name']}**" + (f" · {food['brand']}" if food.get("brand") else ""))
    st.caption("Valores por 100 g: " + " · ".join(
        f"{lbl} {food[k]:.1f}" for k, lbl in NUTRIENT_LABELS.items() if k in ("kcal", "protein_g", "carbs_g", "fat_g")))
    default = float(food.get("serving_g") or 100)
    grams = st.number_input("Cantidad (g)", min_value=1.0, max_value=5000.0, value=default, step=5.0, key=f"g_{key}")
    cols = st.columns(len(NUTRIENT_LABELS))
    for col, (k, lbl) in zip(cols, NUTRIENT_LABELS.items()):
        col.metric(lbl, f"{food[k] * grams / 100:.1f}")
    if st.button("➕ Añadir al diario", key=f"add_{key}", type="primary"):
        payload = {"food_id": food["id"], "grams": grams, "meal": meal, "log_date": log_date}
        if api.post("/logs", json=payload):
            st.toast("Registrado", icon="✅")
            st.session_state.pop("scanned_food", None)
            st.rerun()
