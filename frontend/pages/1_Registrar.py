from datetime import date

import streamlit as st

import api
from components import MEALS, food_log_form, quick_add_bar

st.set_page_config(page_title="Registrar", page_icon="➕", layout="wide")
st.title("➕ Registrar comida")

today = date.fromisoformat((api.get("/meta/today") or {"date": date.today().isoformat()})["date"])
c1, c2 = st.columns(2)
log_date = c1.date_input("Fecha", value=today, max_value=today)
meal = c2.selectbox("Comida", [None, *MEALS], format_func=lambda m: "Automática (según la hora)" if m is None else MEALS[m])
kw = {"log_date": log_date.isoformat(), "meal": meal}

with st.expander("⭐ Habituales", expanded=True):
    quick_add_bar()

tab_search, tab_scan, tab_manual = st.tabs(["🔎 Buscar", "📷 Código de barras", "✍️ Crear manual"])

with tab_search:
    q = st.text_input("Nombre o marca", placeholder="p. ej. yogur griego")
    if q:
        foods = api.get("/foods/search", q=q) or []
        if not foods:
            st.info("Sin resultados. Prueba con el escáner, el chat (busca en la web) o créalo a mano.")
        else:
            food = st.selectbox("Resultados", foods, format_func=lambda f: f"{f['name']}" + (f" · {f['brand']}" if f["brand"] else "") + f" ({f['kcal']:.0f} kcal/100 g)")
            food_log_form(food, f"s{food['id']}", **kw)

with tab_scan:
    st.caption("Haz una foto al código o súbela. Si el producto no está en Open Food Facts, pregúntaselo al chat.")
    photo = st.camera_input("Foto del código de barras") or st.file_uploader("…o sube una imagen", type=["jpg", "jpeg", "png", "webp"])
    manual_code = st.text_input("…o escribe el código", max_chars=14)
    if photo and st.session_state.get("scan_id") != photo.file_id:
        res = api.post("/foods/barcode-image", files={"image": (photo.name, photo.getvalue(), photo.type)})
        st.session_state.update(scan_id=photo.file_id, scan_res=res)
    elif manual_code and st.button("Buscar código"):
        st.session_state.update(scan_id=None, scan_res=api.get(f"/foods/barcode/{manual_code}"))
    res = st.session_state.get("scan_res")
    if res:
        if res["food"]:
            food_log_form(res["food"], f"b{res['food']['id']}", **kw)
        elif res["status"] == "no_barcode":
            st.warning("No se detecta ningún código. Acércate más, con buena luz y el código plano.")
        else:
            st.warning(f"Códigos {res['barcodes']}: producto sin datos nutricionales utilizables ({res['status']}). "
                       "Pídele al chat que lo busque en la web y lo guarde.")

with tab_manual:
    with st.form("new_food", clear_on_submit=True):
        name = st.text_input("Nombre *")
        brand = st.text_input("Marca")
        st.caption("Valores por 100 g")
        cols = st.columns(4)
        vals = {k: cols[i % 4].number_input(lbl, min_value=0.0, step=0.1) for i, (k, lbl) in enumerate(
            [("kcal", "kcal"), ("protein_g", "Proteína"), ("carbs_g", "Hidratos"), ("fat_g", "Grasa"),
             ("sugars_g", "Azúcares"), ("sat_fat_g", "Saturadas"), ("fiber_g", "Fibra"), ("sodium_mg", "Sodio (mg)")])}
        barcode = st.text_input("Código de barras (opcional)")
        if st.form_submit_button("Crear alimento") and name:
            if api.post("/foods", json={"name": name, "brand": brand or None, "barcode": barcode or None, **vals}):
                st.success("Creado. Ya puedes buscarlo en la pestaña «Buscar».")
