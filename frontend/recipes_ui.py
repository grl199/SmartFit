"""Recetas / alimentos compuestos: usar (con cantidades editables y recálculo en vivo) y crear."""
import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

import api
import ui

SHOWN = (("kcal", "kcal"), ("protein_g", "Proteína (g)"), ("carbs_g", "Hidratos (g)"), ("fat_g", "Grasa (g)"))


def _metrics(per_serving: dict, serving_g: float, label: str = "Por ración") -> None:
    st.caption(f"{label} (≈ {serving_g:.0f} g)")
    cols = st.columns(len(SHOWN))
    for col, (k, lbl) in zip(cols, SHOWN):
        col.metric(lbl, f"{per_serving[k]:.0f}" if k == "kcal" else f"{per_serving[k]:.1f}")


def _use(log_date: str | None, meal: str | None) -> None:
    recipes = api.get("/recipes") or []
    if not recipes:
        ui.empty("🍳", "Aún no hay recetas", "Crea tu primera receta en la pestaña «Crear receta».")
        return
    q = st.text_input("🔎 Buscar receta", key="rc_q", placeholder="café con leche, tostada…")
    if q.strip():
        recipes = [r for r in recipes if q.strip().lower() in r["name"].lower()]
    if not recipes:
        st.info("Ninguna receta coincide.")
        return
    by_id = {r["id"]: r for r in recipes}
    rid = st.selectbox("Receta", list(by_id), key="rc_sel", format_func=lambda i: (
        ("⭐ " if by_id[i]["is_system"] else "👤 ") + f"{by_id[i]['name']} · {by_id[i]['per_serving']['kcal']:.0f} kcal/ración"))
    r = api.get(f"/recipes/{rid}")
    if not r:
        return
    with st.container(border=True):
        ui.html(f"<div class='sf-big'>{ui.escape(r['name'])}</div>" + (f"<div class='sf-muted'>{ui.escape(r['description'])}</div>" if r.get("description") else ""))
        st.markdown("**Ingredientes** · cambia las cantidades y los nutrientes se recalculan al momento")
        df0 = pd.DataFrame([{"ID": i["id"], "FoodID": i["food_id"], "Ingrediente": i["food"], "Cantidad (g)": float(i["quantity_g"])} for i in r["ingredients"]])
        df = st.data_editor(df0, hide_index=True, key=f"rc_ed_{rid}", width="stretch", disabled=["Ingrediente"],
                            column_config={"ID": None, "FoodID": None, "Cantidad (g)": st.column_config.NumberColumn(min_value=1.0, max_value=5000.0, step=5.0)})
        df = df[df["Cantidad (g)"].notna()]
        prev = api.post("/recipes/preview", json={"serving_count": r["serving_count"], "ingredients": [
            {"food_id": int(x.FoodID), "quantity_g": float(x._4)} for x in df.itertuples()]}) if len(df) else None
        if prev:
            _metrics(prev["per_serving"], prev["serving_g"], "Por ración" if r["serving_count"] != 1 else "Total")
        c1, c2 = st.columns([1, 3])
        servings = c1.number_input("Raciones", 0.25, 20.0, 1.0, step=0.25, key=f"rc_sv_{rid}")
        changed = {int(x.ID): float(x._4) for x in df.itertuples() if abs(float(x._4) - next(i["quantity_g"] for i in r["ingredients"] if i["id"] == x.ID)) > 1e-9}
        if c2.button("➕ Añadir al diario", type="primary", key=f"rc_add_{rid}", width="stretch"):
            body = {"servings": servings, "meal": meal, "log_date": log_date, "quantities": changed or None}
            if api.post(f"/recipes/{rid}/log", json=body):
                st.toast(f"Registrado: {r['name']}", icon="✅")
                st.rerun()
        b1, b2 = st.columns(2)
        if len(df) and (changed or r["editable"]):
            lbl = "💾 Guardar mis cambios" if r["editable"] else "💾 Guardar como mi receta"
            if b1.button(lbl, key=f"rc_save_{rid}", width="stretch"):
                target = rid if r["editable"] else (api.post(f"/recipes/{rid}/copy") or {}).get("id")
                body = {"name": r["name"] if r["editable"] else f"{r['name']} (mi versión)", "description": r.get("description"),
                        "serving_count": r["serving_count"], "ingredients": [{"food_id": int(x.FoodID), "quantity_g": float(x._4)} for x in df.itertuples()]}
                if target and api.put(f"/recipes/{target}", body):
                    st.toast("Receta guardada", icon="💾")
                    st.rerun()
        if r["editable"] and b2.button("🗑 Borrar receta", key=f"rc_del_{rid}", width="stretch"):
            if api.delete(f"/recipes/{rid}"):
                st.rerun()


def _create() -> None:
    items: list[dict] = st.session_state.setdefault("_rb", [])
    c1, c2 = st.columns([3, 1])
    name = c1.text_input("Nombre de la receta", key="rb_name", placeholder="Tostada con aguacate")
    servings = c2.number_input("Raciones", 0.25, 50.0, 1.0, step=0.25, key="rb_serv", help="Cuántas raciones salen con las cantidades de abajo")
    st.markdown("**1 · Añade ingredientes**")

    def _search(term: str):
        if not term or len(term.strip()) < 2:
            return []
        foods = [f for f in (api.get("/foods/search", q=term.strip(), limit=8, online="false") or []) if f["source"] != "recipe"]
        st.session_state.setdefault("_rb_foods", {}).update({f["id"]: f for f in foods})
        return [(f"{f['name']}" + (f" · {f['brand']}" if f["brand"] else "") + f" · {f['kcal']:.0f} kcal/100 g", f["id"]) for f in foods]

    picked = st_searchbox(_search, placeholder="Busca un ingrediente…", key="rb_search", clear_on_submit=True)
    if picked and (f := st.session_state.get("_rb_foods", {}).get(picked)) and f["id"] not in [i["food_id"] for i in items]:
        items.append({"food_id": f["id"], "Ingrediente": f["name"], "Cantidad (g)": float(f.get("serving_g") or 100)})
        st.rerun()
    if not items:
        ui.empty("🥣", "Añade el primer ingrediente", "Busca arriba y ajusta la cantidad en gramos.")
        return
    st.markdown("**2 · Ajusta cantidades** (borra una fila para quitar el ingrediente)")
    df = st.data_editor(pd.DataFrame(items), hide_index=True, num_rows="dynamic", key=f"rb_ed_{len(items)}", width="stretch",
                        disabled=["Ingrediente"], column_config={"food_id": None, "Cantidad (g)": st.column_config.NumberColumn(min_value=1.0, max_value=5000.0, step=5.0)})
    df = df[df["Cantidad (g)"].notna() & df["food_id"].notna()]
    ings = [{"food_id": int(x.food_id), "quantity_g": float(x._3)} for x in df.itertuples()]
    if ings:
        prev = api.post("/recipes/preview", json={"serving_count": servings, "ingredients": ings})
        if prev:
            _metrics(prev["per_serving"], prev["serving_g"])
    b1, b2 = st.columns([3, 1])
    if b1.button("💾 Guardar receta", type="primary", disabled=not (name.strip() and ings), width="stretch"):
        if api.post("/recipes", json={"name": name.strip(), "serving_count": servings, "ingredients": ings}):
            st.session_state["_rb"] = []
            st.toast("Receta guardada. Ya puedes usarla desde «Usar una receta».", icon="🍳")
            st.rerun()
    if b2.button("Vaciar", width="stretch"):
        st.session_state["_rb"] = []
        st.rerun()


def recipes_tab(log_date: str | None, meal: str | None) -> None:
    mode = st.segmented_control("Modo", ["Usar una receta", "Crear receta"], default="Usar una receta", key="rc_mode", label_visibility="collapsed")
    if mode == "Crear receta":
        _create()
    else:
        _use(log_date, meal)
