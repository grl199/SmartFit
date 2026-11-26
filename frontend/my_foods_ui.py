"""Alimentos propios: crear (también desde una búsqueda sin resultados), editar, borrar, unidades habituales y copias personales.
Son PRIVADOS de cada usuario (salvo que decida compartirlos) y salen los primeros en sus búsquedas."""
import streamlit as st

import api
import ui
from components import food_log_form

FIELDS = (("kcal", "kcal"), ("protein_g", "Proteína (g)"), ("carbs_g", "Hidratos (g)"), ("fat_g", "Grasa (g)"),
          ("sugars_g", "Azúcares (g)"), ("sat_fat_g", "Saturadas (g)"), ("fiber_g", "Fibra (g)"), ("sodium_mg", "Sodio (mg)"))


def food_fields(key: str, init: dict | None = None) -> dict:
    """Campos de un alimento (dentro de un st.form). Valores por 100 g."""
    init = init or {}
    name = st.text_input("Nombre *", value=init.get("name", ""), key=f"{key}_n")
    brand = st.text_input("Marca (opcional)", value=init.get("brand") or "", key=f"{key}_b")
    st.caption("Valores por 100 g (los principales bastan; el resto puedes dejarlo en 0)")
    cols = st.columns(4)
    vals = {k: cols[i % 4].number_input(lbl, min_value=0.0, step=0.1, value=float(init.get(k) or 0.0), key=f"{key}_{k}") for i, (k, lbl) in enumerate(FIELDS)}
    serving = st.number_input("Ración habitual en gramos (opcional)", min_value=0.0, max_value=5000.0, step=5.0, value=float(init.get("serving_g") or 0.0), key=f"{key}_sv")
    return {"name": name.strip(), "brand": brand.strip() or None, "serving_g": serving or None, **vals}


def create_from_search(term: str, kw: dict) -> None:
    """«¿No lo encuentras?»: alimento propio con el texto buscado como nombre y, si quieres, una unidad habitual (p. ej. 1 loncha = 20 g)."""
    with st.expander("➕ ¿No lo encuentras? Créalo como alimento tuyo"):
        with st.form(f"cs_form_{term}", clear_on_submit=True):
            data = food_fields(f"cs_{term}", {"name": term})
            c = st.columns(2)
            unit = c[0].text_input("Unidad habitual (opcional)", placeholder="loncha, cucharada, bote…", key=f"cs_{term}_u")
            grams = c[1].number_input("Gramos por unidad", min_value=0.0, max_value=5000.0, step=1.0, key=f"cs_{term}_ug")
            if st.form_submit_button("Crear y registrar", type="primary") and data["name"]:
                created = api.post("/foods", json=data)
                if created:
                    if unit.strip() and grams > 0:
                        api.post(f"/foods/{created['id']}/servings", json={"unit_name": unit.strip(), "grams_per_unit": grams})
                    st.session_state["just_created"] = created
                    st.session_state.pop("_servings", None)
                    st.toast("Alimento creado. Está en «Mis alimentos».", icon="✅")
                    st.rerun()
        st.caption("Solo tú lo ves (a menos que lo compartas) y saldrá el primero cuando lo busques.")


def my_foods_tab(kw: dict) -> None:
    focus = st.session_state.pop("_mf_focus", None)
    if focus:
        st.session_state["mf_sel"] = focus
    q = st.text_input("🔎 Buscar en mis alimentos", key="mf_q", placeholder="Escribe para filtrar…")
    foods = api.get("/foods/mine", q=q.strip() or None) or []
    if not foods:
        ui.empty("👤", "Aún no tienes alimentos propios" if not q else "Ningún alimento tuyo coincide",
                 "Créalos desde «Crear manual», desde una búsqueda sin resultados o con «Crear mi versión» en cualquier alimento.")
        return
    by_id = {f["id"]: f for f in foods}
    if st.session_state.get("mf_sel") not in by_id:
        st.session_state.pop("mf_sel", None)
    fid = st.selectbox("Alimento", list(by_id), key="mf_sel", format_func=lambda i, by_id=by_id: (
        f"{by_id[i]['name']} · {by_id[i]['kcal']:.0f} kcal/100 g" + (f" · usado {by_id[i]['times_used']}×" if by_id[i]["times_used"] else "")))
    food = by_id[fid]
    act = st.segmented_control("Acción", ["Registrar", "Editar", "Unidades"], default="Registrar", key=f"mf_act_{fid}", label_visibility="collapsed")
    if act == "Editar":
        shared = food.get("share_status", "private") != "private"
        if shared:
            st.warning("Este alimento está compartido con la comunidad: retira primero el compartido para poder editarlo.")
        with st.form(f"mf_edit_{fid}"):
            data = food_fields(f"mfe_{fid}", food)
            if st.form_submit_button("💾 Guardar cambios", type="primary", disabled=shared) and data["name"]:
                if api.put(f"/foods/{fid}", {**data, "barcode": food.get("barcode")}):
                    st.toast("Cambios guardados. Tus registros anteriores no cambian.", icon="💾")
                    st.rerun()
        with st.popover("🗑 Borrar alimento"):
            st.caption("Si ya lo has registrado o lo usa una receta, no se podrá borrar (para no romper tu historial).")
            if st.button("Confirmar borrado", key=f"mf_del_{fid}"):
                if api.delete(f"/foods/{fid}") is not None:
                    st.session_state.pop("mf_sel", None)
                    st.rerun()
    elif act == "Unidades":
        st.caption("Equivalencias orientativas: «1 loncha = 20 g». Al registrar podrás elegir la unidad en vez de los gramos.")
        for s in api.get(f"/foods/{fid}/servings") or []:
            c = st.columns([5, 1])
            c[0].write(f"1 {s['unit_name']} = {s['grams_per_unit']:g} g" + (f" · {s['description']}" if s.get("description") else ""))
            if c[1].button("🗑", key=f"sv_del_{s['id']}", help="Borrar unidad"):
                api.delete(f"/foods/{fid}/servings/{s['id']}")
                st.session_state.pop("_servings", None)
                st.rerun()
        with st.form(f"sv_new_{fid}", clear_on_submit=True):
            c = st.columns(3)
            unit = c[0].text_input("Unidad", placeholder="loncha")
            plural = c[1].text_input("Plural (opcional)", placeholder="lonchas")
            grams = c[2].number_input("Gramos", min_value=0.0, max_value=5000.0, step=1.0)
            if st.form_submit_button("Añadir unidad") and unit.strip() and grams > 0:
                if api.post(f"/foods/{fid}/servings", json={"unit_name": unit.strip(), "unit_name_plural": plural.strip() or None, "grams_per_unit": grams}):
                    st.session_state.pop("_servings", None)
                    st.rerun()
    else:
        food_log_form(food, f"mf{fid}", **kw)
