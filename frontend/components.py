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


def _share_controls(food: dict, key: str) -> None:
    """Solo en alimentos propios con código de barras: ofrecerlos a la comunidad o retirar la oferta."""
    me = st.session_state.get("me") or {}
    if food.get("user_id") is None or food.get("user_id") != me.get("id") or not food.get("barcode") or food.get("barcode_ambiguous"):
        return
    status = food.get("share_status", "private")
    if status == "private":
        if st.button("👥 Compartir con la comunidad", key=f"share_{key}", help="Se publican solo el código, el nombre, la marca y los valores "
                     "nutricionales (nunca quién los aportó) y solo cuando otro usuario registra los mismos datos."):
            res = api.post(f"/foods/{food['id']}/share")
            if res:
                st.session_state.get("_food_full", {}).pop(food["id"], None)
                st.toast("Publicado en la comunidad" if res.get("published") else "Ofrecido: se publicará cuando otro usuario confirme los datos", icon="👥")
                st.rerun()
    elif status == "pending":
        if st.button("Retirar de la comunidad", key=f"unshare_{key}"):
            if api.delete(f"/foods/{food['id']}/share"):
                st.session_state.get("_food_full", {}).pop(food["id"], None)
                st.rerun()


def _servings(food_id: int) -> list[dict]:
    cache = st.session_state.setdefault("_servings", {})
    if food_id not in cache:
        cache[food_id] = api.get(f"/foods/{food_id}/servings") or []
    return cache[food_id]


def food_log_form(food: dict, key: str, log_date: str | None = None, meal: str | None = None) -> None:
    """Ficha del alimento -> cantidad (gramos o unidades habituales) -> vista previa de nutrientes -> registrar."""
    food = full_food(food)
    with st.container(border=True):
        ui.html(ui.food_header(food))
        if food.get("ingredients") or food.get("categories"):
            with st.expander("Ingredientes y categorías"):
                if food.get("categories"):
                    ui.html(ui.chips(food["categories"], "blue"))
                if food.get("ingredients"):
                    st.caption(food["ingredients"])
        _share_controls(food, key)
        if food.get("user_id") is None and food.get("source") != "recipe":
            if st.button("✏️ Crear mi versión", key=f"cp_{key}", help="Copia este alimento a «Mis alimentos» para ajustar sus valores o unidades"):
                mine = api.post(f"/foods/{food['id']}/copy")
                if mine:
                    st.session_state["_mf_focus"] = mine["id"]
                    st.toast("Copia creada: ajústala en «Mis alimentos».", icon="👤")
                    st.rerun()
        if food.get("license") or food.get("confidence"):
            conf = {"high": "fiabilidad alta", "medium": "fiabilidad media", "low": "estimado"}.get(food.get("confidence") or "", "")
            with st.expander("Origen de los datos"):
                st.caption(" · ".join(x for x in (f"Fuente: {food['source']}", conf, f"Licencia {food['license']}" if food.get("license") else "",
                                                    food.get("attribution") or "") if x))
        st.caption("Valores por 100 g: " + " · ".join(
            f"{lbl} {food[k]:.1f}" for k, lbl in NUTRIENT_LABELS.items() if k in ("kcal", "protein_g", "carbs_g", "fat_g")))
        servings = _servings(food["id"])
        units = {None: "Gramos (g)", **{s["id"]: ("Mililitros (ml)" if s["unit_name"] == "ml"
                                                    else f"{s['unit_name_plural'] or s['unit_name']} (≈ {s['grams_per_unit']:g} g)") for s in servings}}
        by_id = {s["id"]: s for s in servings}
        c1, c2 = st.columns([2, 3])
        unit = c1.selectbox("Unidad", list(units), format_func=units.get, key=f"u_{key}") if servings else None
        if unit is None:
            default = float(food.get("serving_g") or 100)
            amount = c2.number_input("Cantidad (g)", min_value=1.0, max_value=5000.0, value=default, step=5.0, key=f"g_{key}")
            grams, payload_qty = amount, {"grams": amount}
        else:
            sv = by_id[unit]
            is_ml = sv["unit_name"] == "ml"
            amount = c2.number_input("Cantidad (ml)" if is_ml else f"Cantidad ({sv['unit_name_plural'] or sv['unit_name']})", min_value=0.5,
                                     max_value=5000.0 if is_ml else 200.0, value=200.0 if is_ml else 1.0, step=10.0 if is_ml else 0.5, key=f"q_{key}_{unit}")
            grams, payload_qty = amount * sv["grams_per_unit"], {"serving_id": unit, "quantity": amount}
            st.caption(f"Equivale a unos **{grams:.0f} g** (equivalencia orientativa).")
        cols = st.columns(len(NUTRIENT_LABELS) + 1)
        for col, (k, lbl) in zip(cols, NUTRIENT_LABELS.items()):
            col.metric(lbl, f"{food[k] * grams / 100:.1f}")
        cols[-1].metric("Sal (g)", f"{food['sodium_mg'] * 2.5 * grams / 100000:.2f}")
        if st.button("➕ Añadir al diario", key=f"add_{key}", type="primary"):
            payload = {"food_id": food["id"], "meal": meal, "log_date": log_date, **payload_qty}
            if api.post("/logs", json=payload):
                st.toast("Registrado", icon="✅")
                st.session_state.pop("scanned_food", None)
                st.rerun()
