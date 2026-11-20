from datetime import date

import streamlit as st

import api
import auth
import ui

st.set_page_config(page_title="Perfil", page_icon="👤", layout="wide")
ui.inject_css()
me = auth.require_login()
st.title("👤 Perfil y objetivos")

opts = api.options()
p = api.get("/profile") or {}
t = api.get("/targets") or {}


def pick(label, key, current, **kw):
    """Selectbox sobre una lista cerrada (permite «sin indicar» si el dato está vacío)."""
    codes = list(opts[key])
    if current is None:
        codes = [None, *codes]
    return st.selectbox(label, codes, index=codes.index(current) if current in codes else 0,
                        format_func=lambda c: "— sin indicar —" if c is None else opts[key][c], **kw)


# ───────── Energía (calculada por código, sin IA) ─────────
en = api.get("/profile/energy") or {}
st.subheader("Tu gasto energético")
if en.get("missing"):
    st.info("Completa en el perfil (más abajo) para calcularlo: " + ", ".join(en["missing"]) + ".")
else:
    m = st.columns(4)
    m[0].metric("Edad", f"{en['age']} años")
    m[1].metric("Metabolismo basal", f"{en['bmr']:.0f} kcal/día")
    m[2].metric("Gasto total (TDEE)", f"{en['tdee']:.0f} kcal/día")
    m[3].metric("Peso usado", f"{en['weight_kg']:g} kg")
    st.caption("Se calcula automáticamente con Mifflin-St Jeor a partir de tu perfil y tu último peso, y se actualiza al cambiar "
               "peso, altura, fecha de nacimiento o actividad. Es una estimación. Tus objetivos nutricionales solo cambian si "
               "pulsas «Recalcular objetivos con IA».")

# ───────── Objetivos ─────────
st.subheader("Objetivos diarios")
src = {"llm": "🤖 Generados por la IA", "manual": "✍️ Editados a mano"}.get(t.get("source"), "")
st.caption(src)
if t.get("rationale"):
    st.info(t["rationale"])
if t.get("training_plan"):
    with st.expander("📋 Plan de entrenamiento recomendado"):
        st.markdown(t["training_plan"])

if st.button("🤖 Recalcular objetivos con IA (usa tu perfil y peso actuales)"):
    with st.spinner("La IA está calculando…"):
        res = api.post("/targets/generate", timeout=api.LONG_TIMEOUT)
    if res:
        st.success("Objetivos actualizados")
        auth.show_targets(res)
        st.stop()

with st.form("targets"):
    cols = st.columns(5)
    new_t = {
        "kcal": cols[0].number_input("kcal", 800.0, 8000.0, float(t.get("kcal", 2000)), step=50.0),
        "protein_g": cols[1].number_input("Proteína (g)", 0.0, 500.0, float(t.get("protein_g", 120)), step=5.0),
        "carbs_g": cols[2].number_input("Hidratos (g)", 0.0, 1000.0, float(t.get("carbs_g", 220)), step=5.0),
        "fat_g": cols[3].number_input("Grasa (g)", 0.0, 500.0, float(t.get("fat_g", 65)), step=5.0),
        "fiber_g": cols[4].number_input("Fibra (g)", 0.0, 200.0, float(t.get("fiber_g", 30)), step=1.0),
    }
    g3 = st.columns(3)
    new_t["workouts_per_week"] = g3[0].number_input("Entrenos por semana", 0, 14, int(t.get("workouts_per_week", 3)))
    new_t["water_ml"] = g3[1].number_input("Agua al día (ml)", 500, 10000, int(t.get("water_ml", 2000)), step=250)
    new_t["steps_goal"] = g3[2].number_input("Pasos al día", 1000, 50000, int(t.get("steps_goal", 8000)), step=500)
    if st.form_submit_button("Guardar objetivos manualmente") and api.put("/targets", new_t):
        st.success("Guardado")

# ───────── Perfil ─────────
st.subheader("Perfil (se inyecta en el contexto del asistente)")
with st.form("profile"):
    c = st.columns(3)
    sex = pick("Sexo", "sex", p.get("sex"))
    bd = c[1].date_input("Fecha de nacimiento", value=date.fromisoformat(p["birth_date"]) if p.get("birth_date") else None,
                         min_value=date(1920, 1, 1), max_value=date.today())
    h = c[2].number_input("Altura (cm)", 0.0, 250.0, float(p.get("height_cm") or 0), step=1.0)
    c = st.columns(3)
    goal = pick("Objetivo principal", "goal", p.get("goal"))
    act = pick("Nivel de actividad", "activity_level", p.get("activity_level"))
    exp = pick("Experiencia entrenando", "experience_level", p.get("experience_level"))
    days = st.slider("Días disponibles para entrenar", 1, 7, int(p.get("available_training_days") or 3))
    restr = st.text_area("Alergias / restricciones", p.get("dietary_restrictions") or "")
    notes = st.text_area("Notas para el asistente", p.get("context_notes") or "",
                         placeholder="Lesiones, rutina de entrenamiento, horarios, preferencias…")
    if st.form_submit_button("Guardar perfil"):
        body = {"sex": sex, "birth_date": bd.isoformat() if bd else None, "height_cm": h or None, "activity_level": act,
                "goal": goal, "experience_level": exp, "available_training_days": days,
                "dietary_restrictions": restr or None, "context_notes": notes or None}
        if api.put("/profile", body):
            st.success("Guardado. Pulsa «Recalcular objetivos con IA» si quieres actualizar tus objetivos.")

if st.button("🌐 Traducir al español los nombres de productos pendientes"):
    with st.spinner("Traduciendo…"):
        r = api.post("/foods/translate-names", timeout=api.LONG_TIMEOUT)
    if r:
        st.success(f"{r['translated']} nombres traducidos" + (f"; quedan {r['pending']} (vuelve a pulsar)." if r["pending"] else "."))

if st.button("🔄 Reindexar histórico para el RAG"):
    r = api.post("/rag/reindex")
    if r:
        st.success(f"{r['days_indexed']} días indexados")

# ───────── Zona de peligro ─────────
st.divider()
with st.expander("⚠️ Eliminar mi cuenta"):
    st.warning(f"Se borrarán **todos** los datos de «{me['name']}» (diario, entrenos, peso, chat, memoria, alimentos creados). "
               "No se puede deshacer.")
    pw = st.text_input("Confirma con tu contraseña", type="password", key="del_pw")
    sure = st.checkbox("Entiendo que es irreversible", key="del_sure")
    if st.button("Eliminar cuenta definitivamente", type="primary", disabled=not (pw and sure)):
        if api.call("DELETE", "/auth/me", json={"password": pw}):
            api.logout("Tu cuenta ha sido eliminada.")
            st.rerun()
