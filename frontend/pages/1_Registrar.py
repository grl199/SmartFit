from datetime import date

import streamlit as st
from streamlit_searchbox import st_searchbox

import api
import auth
import ui
from components import MEALS, food_log_form, quick_add_bar

st.set_page_config(page_title="Registrar", page_icon="➕", layout="wide")
ui.inject_css()
auth.require_login()
ui.mobile_nav()
st.title("➕ Registrar comida")

today = date.fromisoformat((api.get("/meta/today") or {"date": date.today().isoformat()})["date"])
c1, c2 = st.columns(2)
log_date = c1.date_input("Fecha", value=today, max_value=today)
meal = c2.selectbox("Comida", [None, *MEALS], format_func=lambda m: "Automática (según la hora)" if m is None else MEALS[m])
kw = {"log_date": log_date.isoformat(), "meal": meal}

with st.expander("⭐ Habituales", expanded=True):
    quick_add_bar()

tab_search, tab_scan, tab_manual = st.tabs(["🔎 Buscar", "📷 Código de barras", "✍️ Crear manual"])

# ───────── Búsqueda dinámica ─────────
with tab_search:
    online = st.toggle("Incluir Open Food Facts", value=True,
                       help="Si hay pocos resultados locales, busca también en Open Food Facts y guarda lo encontrado "
                            "(la primera búsqueda de un término puede tardar un segundo).")

    def _label(f: dict) -> str:
        """Una línea por resultado: nombre · marca · kcal · Nutri-Score · 🏷 código de barras."""
        parts = [f["name"]] + ([f["brand"]] if f["brand"] else []) + [f"{f['kcal']:.0f} kcal/100 g"]
        if f.get("nutriscore_grade"):
            parts.append(f"Nutri-Score {f['nutriscore_grade'].upper()}")
        if f.get("barcode"):
            parts.append(f"🏷 {f['barcode']}" + (" ⚠" if f.get("barcode_ambiguous") else ""))
        return " · ".join(parts) + {"openfoodfacts": " 🌐", "community": " 👥"}.get(f["source"], "")

    def _search(term: str):
        if not term or len(term.strip()) < 2:
            return []
        foods = api.get("/foods/search", q=term.strip(), limit=10, online=str(online).lower()) or []
        st.session_state.setdefault("_foods", {}).update({f["id"]: f for f in foods})
        return [(_label(f), f["id"]) for f in foods]

    selected = st_searchbox(_search, placeholder="Empieza a escribir: yogur griego, avena, plátano…",
                            key="food_search", debounce=500, clear_on_submit=False)
    if selected is not None and (food := st.session_state.get("_foods", {}).get(selected)):
        food_log_form(food, f"s{food['id']}", **kw)
    st.caption("🌐 = Open Food Facts (se guarda para próximas búsquedas) · 👥 = confirmado por la comunidad · 🏷 = código de barras (⚠ = código de tienda, puede repetirse entre productos). La búsqueda tolera erratas y variantes entre idiomas («pistacho» ≈ «pistacchio»).")

# ───────── Código de barras ─────────
STATUS_HELP = {
    "not_found": "Open Food Facts no conoce este producto.",
    "incomplete": "Open Food Facts conoce el producto pero sin datos nutricionales.",
    "error": "Open Food Facts no responde ahora mismo.",
}
with tab_scan:
    st.caption("Haz una foto al código o súbela; también puedes escribirlo.")
    photo = st.camera_input("Foto del código de barras") or st.file_uploader("…o sube una imagen", type=["jpg", "jpeg", "png", "webp"])
    manual_code = st.text_input("…o escribe el código (8 a 32 dígitos)", max_chars=32)
    if photo and st.session_state.get("scan_id") != photo.file_id:
        res = api.post("/foods/barcode-image", files={"image": (photo.name, photo.getvalue(), photo.type)})
        st.session_state.update(scan_id=photo.file_id, scan_res=res)
    elif manual_code and st.button("Buscar código"):
        st.session_state.update(scan_id=None, scan_res=api.get(f"/foods/barcode/{manual_code.strip()}"))
    res = st.session_state.get("scan_res")
    if res:
        if res["food"]:
            food_log_form(res["food"], f"b{res['food']['id']}", **kw)
        elif res["status"] == "no_barcode":
            st.warning("No se detecta ningún código. Acércate más, con buena luz y el código plano.")
        else:
            code = (res.get("barcodes") or [""])[0]
            st.warning(f"Código {code}: {STATUS_HELP.get(res['status'], res['status'])}")
            if res.get("name"):
                st.caption(f"Producto: {res['name']}" + (f" · {res['brand']}" if res.get("brand") else ""))
            if st.button("✍️ Crear este producto manualmente", key="prefill_btn"):
                st.session_state["prefill_barcode"] = code
                st.info("Código copiado. Ve a la pestaña «Crear manual»: la próxima vez que lo escanees se reconocerá solo.")

# ───────── Crear manual ─────────
with tab_manual:
    prefill = st.session_state.get("prefill_barcode", "")
    if prefill:
        st.info(f"Creando producto para el código {prefill}")
    with st.form("new_food", clear_on_submit=True):
        name = st.text_input("Nombre *")
        brand = st.text_input("Marca")
        st.caption("Valores por 100 g")
        cols = st.columns(4)
        vals = {k: cols[i % 4].number_input(lbl, min_value=0.0, step=0.1) for i, (k, lbl) in enumerate(
            [("kcal", "kcal"), ("protein_g", "Proteína"), ("carbs_g", "Hidratos"), ("fat_g", "Grasa"),
             ("sugars_g", "Azúcares"), ("sat_fat_g", "Saturadas"), ("fiber_g", "Fibra"), ("sodium_mg", "Sodio (mg)")])}
        barcode = st.text_input("Código de barras (opcional, hasta 32 dígitos)", value=prefill, max_chars=32)
        share = st.checkbox("👥 Compartir con la comunidad", help="Ayuda a que otros usuarios encuentren este producto. Se publican solo el código, "
                            "el nombre, la marca y los valores (nunca quién los aportó) y solo cuando otro usuario registra los mismos datos. "
                            "Requiere código de barras y no vale para códigos de tienda (que empiezan por 2).")
        if st.form_submit_button("Crear alimento") and name:
            created = api.post("/foods", json={"name": name, "brand": brand or None, "barcode": barcode or None, "share": share, **vals})
            if created:
                st.session_state.pop("prefill_barcode", None)
                st.session_state["just_created"] = created
    if created := st.session_state.get("just_created"):
        st.success("Creado. Puedes registrarlo ahora:")
        food_log_form(created, f"n{created['id']}", **kw)
