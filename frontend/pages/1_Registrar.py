from datetime import date

import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

import api
import auth
import ui
from components import MEALS, food_log_form, quick_add_bar
from my_foods_ui import create_from_search, food_fields, my_foods_tab
from recipes_ui import recipes_tab

st.set_page_config(page_title="Registrar", page_icon="➕", layout="wide")
ui.inject_css()
auth.require_login()
ui.hero("➕ Registrar comida", "Busca un alimento, escanea un código, usa una receta o crea uno nuevo.")

today = date.fromisoformat((api.get("/meta/today") or {"date": date.today().isoformat()})["date"])
c1, c2 = st.columns(2)
log_date = c1.date_input("Fecha", value=today, max_value=today)
meal = c2.selectbox("Comida", [None, *MEALS], format_func=lambda m: "Automática (según la hora)" if m is None else MEALS[m])
kw = {"log_date": log_date.isoformat(), "meal": meal}

with st.expander("⭐ Habituales", expanded=True):
    quick_add_bar(log_date=kw["log_date"], meal=kw["meal"])

tab_search, tab_recipe, tab_mine, tab_scan, tab_manual, tab_estimate = st.tabs(["🔎 Buscar", "🍳 Recetas", "👤 Mis alimentos", "📷 Código", "✍️ Crear manual", "✨ Estimar con IA"])

with tab_mine:
    my_foods_tab(kw)

with tab_recipe:
    recipes_tab(log_date.isoformat(), meal)

# ───────── Búsqueda dinámica ─────────
with tab_search:
    online = st.toggle("Buscar también en Open Food Facts", value=True,
                       help="Tu catálogo local se busca siempre, al instante. Si hay pocos resultados, se consulta además Open Food Facts (productos con "
                            "código de barras) y se guarda lo encontrado (la primera vez puede tardar un segundo).")

    def _label(f: dict) -> str:
        """Una línea por resultado: nombre · marca · kcal · Nutri-Score · 🏷 código de barras."""
        parts = [f["name"]] + ([f["brand"]] if f["brand"] else []) + [f"{f['kcal']:.0f} kcal/100 g"]
        if f.get("nutriscore_grade"):
            parts.append(f"Nutri-Score {f['nutriscore_grade'].upper()}")
        if f.get("barcode"):
            parts.append(f"🏷 {f['barcode']}" + (" ⚠" if f.get("barcode_ambiguous") else ""))
        badge = " 👤" if f.get("user_id") else {"openfoodfacts": " 🌐", "usda": " 🌾", "catalog": " ⭐", "recipe": " 🍳", "community": " 👥"}.get(f["source"], "")
        return " · ".join(parts) + badge

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
    state = st.session_state.get("food_search")
    create_from_search(state.get("search", "") if isinstance(state, dict) else "", kw)
    st.caption("👤 = tuyo · ⭐ = catálogo SmartFit · 🌾 = USDA (genérico) · 🍳 = receta · 🌐 = Open Food Facts (se guarda para próximas búsquedas) · 👥 = confirmado por la comunidad · 🏷 = código de barras (⚠ = código de tienda, puede repetirse entre productos). La búsqueda tolera erratas y variantes entre idiomas («pistacho» ≈ «pistacchio»).")

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


# ───────── Estimación de platos con IA ─────────
with tab_estimate:
    capabilities = api.get("/foods/estimate-capabilities") or {"description": True, "photo": False}
    modes = ["Descripción", "Solo kcal"] + (["Fotografía"] if capabilities.get("photo") else []) + (["Nota de voz"] if capabilities.get("audio") else [])
    if not capabilities.get("audio"):
        st.caption("Para activar la nota de voz, configura GEMINI_API_KEY o una clave de OpenAI directa/en Vault en el backend.")
    mode = st.radio("¿Cómo quieres registrar la comida?", modes, horizontal=True, key="ai_food_mode")
    description = ""
    if mode in ("Descripción", "Fotografía"):
        description = st.text_area(
            "Describe el plato o añade contexto",
            placeholder="Ej.: ensalada con lechuga, tomate, medio aguacate, una lata de atún y una cucharada de aceite...",
            height=100,
            key="ai_food_description",
        )
    if mode == "Nota de voz":
        st.caption("Graba cómo has preparado la receta o dicta los ingredientes y cantidades. La nota se transcribe para que puedas corregirla antes de estimar.")
        voice = st.audio_input("Grabar nota de voz", key="ai_food_voice")
        if st.button("🎙️ Transcribir nota de voz", disabled=voice is None, key="ai_food_transcribe"):
            transcript_result = api.post(
                "/foods/transcribe-audio",
                files={"audio": (voice.name or "receta.wav", voice.getvalue(), voice.type or "audio/wav")},
                timeout=api.LONG_TIMEOUT,
            )
            if transcript_result:
                st.session_state["ai_food_description"] = transcript_result["transcript"]
                st.session_state["_ai_food_voice_transcribed"] = True
                st.rerun()
        if st.session_state.get("_ai_food_voice_transcribed"):
            description = st.text_area(
                "Transcripción (puedes corregirla antes de estimar)",
                key="ai_food_description",
                height=140,
            )
    if mode == "Solo kcal":
        st.caption("Para comidas cuyo valor energético ya conoces. Los macronutrientes son opcionales y la entrada queda marcada como manual.")
        with st.form("manual_meal_calories", clear_on_submit=True):
            manual_name = st.text_input("Nombre de la comida", placeholder="Ensalada casera")
            c1, c2 = st.columns(2)
            manual_kcal = c1.number_input("Calorías totales (kcal)", min_value=0.0, max_value=9500.0, step=5.0)
            manual_grams = c2.number_input("Peso aproximado de la ración (g)", min_value=1.0, max_value=5000.0, value=100.0, step=5.0,
                                           help="Si no conoces el peso, deja 100 g como referencia. Las kcal totales que introduzcas se conservan.")
            with st.expander("Macronutrientes (opcional)"):
                mc = st.columns(3)
                manual_protein = mc[0].number_input("Proteína (g)", min_value=0.0, max_value=500.0, step=1.0)
                manual_carbs = mc[1].number_input("Hidratos (g)", min_value=0.0, max_value=500.0, step=1.0)
                manual_fat = mc[2].number_input("Grasa (g)", min_value=0.0, max_value=500.0, step=1.0)
            if st.form_submit_button("Añadir al diario", type="primary"):
                if not manual_name.strip():
                    st.warning("Escribe un nombre para identificar la comida.")
                else:
                    saved = api.post("/foods/manual-log", json={
                        "name": manual_name.strip(), "grams": manual_grams, "kcal": manual_kcal,
                        "protein_g": manual_protein, "carbs_g": manual_carbs, "fat_g": manual_fat,
                        "meal": kw["meal"], "log_date": kw["log_date"],
                    })
                    if saved:
                        st.toast(f"Registrado: {manual_name} · {manual_kcal:.0f} kcal", icon="✅")
                        st.rerun()
    photo = None
    if mode == "Fotografía":
        st.caption("Haz una foto del plato completo, con buena luz y desde arriba. La estimación visual es aproximada.")
        photo = st.camera_input("Fotografía del plato", key="ai_food_camera")
        uploaded = st.file_uploader("…o sube una fotografía", type=["jpg", "jpeg", "png", "webp"], key="ai_food_upload")
        photo = photo or uploaded
    elif mode == "Descripción" and not capabilities.get("photo"):
        st.caption("La estimación por fotografía está disponible al activar FOOD_VISION_ENABLED y configurar una clave de OpenAI en el backend.")
    estimate_clicked = st.button("✨ Estimar ingredientes y calorías", type="primary", key="ai_food_estimate") if mode != "Solo kcal" else False
    if estimate_clicked:
        if mode == "Fotografía" and photo is None:
            st.warning("Adjunta una fotografía para continuar.")
        elif mode in ("Descripción", "Nota de voz") and not description.strip():
            st.warning("Describe qué has comido o transcribe una nota de voz para poder estimarlo.")
        else:
            st.session_state.pop("_ai_food_estimate_result", None)
            st.session_state.pop("ai_food_editor", None)
            st.session_state.pop("ai_food_name", None)
            files = {"image": (photo.name or "comida.jpg", photo.getvalue(), photo.type or "image/jpeg")} if photo else None
            result = api.post(
                "/foods/estimate",
                data={"description": description.strip(), "method": "audio" if mode == "Nota de voz" else "description"},
                files=files,
                timeout=240,
            )
            if result:
                st.session_state["_ai_food_estimate_result"] = result

    estimate = st.session_state.get("_ai_food_estimate_result")
    if estimate:
        st.markdown(f"**Propuesta de la IA: {estimate['name']}**")
        st.caption("Estimación orientativa. Revisa ingredientes y cantidades: una fotografía no permite conocer pesos exactos.")
        if estimate.get("assumptions"):
            with st.expander("Suposiciones de la estimación"):
                for assumption in estimate["assumptions"]:
                    st.write(f"• {assumption}")
        frame = pd.DataFrame(estimate["items"])
        editable = st.data_editor(
            frame,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            disabled=["confidence"],
            key="ai_food_editor",
            column_config={
                "grams": st.column_config.NumberColumn("Gramos", min_value=0.1, max_value=5000, step=1),
                "kcal_per_100g": st.column_config.NumberColumn("kcal/100 g", min_value=0, max_value=950, step=1),
                "protein_g_per_100g": st.column_config.NumberColumn("Proteína/100 g", min_value=0, max_value=100, step=0.1),
                "carbs_g_per_100g": st.column_config.NumberColumn("Hidratos/100 g", min_value=0, max_value=100, step=0.1),
                "fat_g_per_100g": st.column_config.NumberColumn("Grasa/100 g", min_value=0, max_value=100, step=0.1),
            },
        )
        editable = editable.copy()
        editable["name"] = editable["name"].fillna("").astype(str).str.strip()
        editable["grams"] = pd.to_numeric(editable["grams"], errors="coerce").fillna(0)
        editable = editable[(editable["name"] != "") & (editable["grams"] > 0)]
        total_grams = float(editable["grams"].sum())
        nutrient_map = {
            "kcal": "kcal_per_100g",
            "protein_g": "protein_g_per_100g",
            "carbs_g": "carbs_g_per_100g",
            "sugars_g": "sugars_g_per_100g",
            "fat_g": "fat_g_per_100g",
            "sat_fat_g": "sat_fat_g_per_100g",
            "fiber_g": "fiber_g_per_100g",
            "sodium_mg": "sodium_mg_per_100g",
        }
        totals = {}
        per100 = {}
        for nutrient, column in nutrient_map.items():
            values = pd.to_numeric(editable[column], errors="coerce").fillna(0) if column in editable else pd.Series(dtype=float)
            totals[nutrient] = float((values * editable["grams"] / 100).sum()) if len(editable) else 0.0
            per100[nutrient] = totals[nutrient] * 100 / total_grams if total_grams else 0.0

        if total_grams > 0:
            st.markdown("**Totales de la comida revisada**")
            cals = st.columns(4)
            cals[0].metric("Peso", f"{total_grams:.0f} g")
            cals[1].metric("Calorías", f"{totals['kcal']:.0f} kcal")
            cals[2].metric("Proteína", f"{totals['protein_g']:.1f} g")
            cals[3].metric("Hidratos / grasa", f"{totals['carbs_g']:.1f} / {totals['fat_g']:.1f} g")
            st.text_input("Nombre para el diario", value=estimate["name"], key="ai_food_name")
            st.caption("Al confirmar se guardará un alimento privado con confianza baja («estimado») y el detalle de los ingredientes. El registro conserva una instantánea de nutrientes.")
            if st.button("✅ Confirmar y añadir al diario", type="primary", key="ai_food_confirm"):
                components = []
                for row in editable.to_dict("records"):
                    item = {"name": row["name"], "grams": float(row["grams"])}
                    for col in nutrient_map.values():
                        item[col] = float(row.get(col) or 0)
                    item["confidence"] = str(row.get("confidence") or "low")
                    components.append(item)
                payload = {
                    "name": st.session_state.get("ai_food_name") or estimate["name"],
                    "grams": round(total_grams, 1),
                    "log_date": kw["log_date"],
                    "meal": kw["meal"],
                    "method": estimate.get("method", "description"),
                    "description": description.strip(),
                    **{key: round(value, 3) for key, value in per100.items()},
                    "components": components,
                }
                saved = api.post("/foods/estimate-log", json=payload)
                if saved:
                    st.toast(f"Registrado: {payload['name']} · {totals['kcal']:.0f} kcal", icon="✅")
                    st.session_state.pop("_ai_food_estimate_result", None)
                    st.rerun()
        else:
            st.warning("Añade al menos un ingrediente con una cantidad mayor que cero.")

# ───────── Crear manual ─────────
with tab_manual:
    prefill = st.session_state.get("prefill_barcode", "")
    if prefill:
        st.info(f"Creando producto para el código {prefill}")
    with st.form("new_food", clear_on_submit=True):
        data = food_fields("nf")
        c = st.columns(2)
        unit = c[0].text_input("Unidad habitual (opcional)", placeholder="loncha, cucharada, bote…", key="nf_u")
        ugrams = c[1].number_input("Gramos por unidad", min_value=0.0, max_value=5000.0, step=1.0, key="nf_ug")
        barcode = st.text_input("Código de barras (opcional, hasta 32 dígitos)", value=prefill, max_chars=32)
        share = st.checkbox("👥 Compartir con la comunidad", help="Ayuda a que otros usuarios encuentren este producto. Se publican solo el código, "
                            "el nombre, la marca y los valores (nunca quién los aportó) y solo cuando otro usuario registra los mismos datos. "
                            "Requiere código de barras y no vale para códigos de tienda (que empiezan por 2).")
        if st.form_submit_button("Crear alimento", type="primary") and data["name"]:
            created = api.post("/foods", json={**data, "barcode": barcode or None, "share": share})
            if created:
                if unit.strip() and ugrams > 0:
                    api.post(f"/foods/{created['id']}/servings", json={"unit_name": unit.strip(), "grams_per_unit": ugrams})
                    st.session_state.pop("_servings", None)
                st.session_state.pop("prefill_barcode", None)
                st.session_state["just_created"] = created
    if created := st.session_state.get("just_created"):
        st.success("Creado. Puedes registrarlo ahora:")
        food_log_form(created, f"n{created['id']}", **kw)
