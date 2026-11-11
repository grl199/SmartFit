from datetime import date

import streamlit as st

import api

st.set_page_config(page_title="Perfil", page_icon="👤", layout="wide")
st.title("👤 Perfil y objetivos")

p = api.get("/profile") or {}
t = api.get("/targets") or {}

st.subheader("Objetivos diarios")
with st.form("targets"):
    cols = st.columns(5)
    new_t = {
        "kcal": cols[0].number_input("kcal", 500.0, 10000.0, float(t.get("kcal", 2000)), step=50.0),
        "protein_g": cols[1].number_input("Proteína (g)", 0.0, 500.0, float(t.get("protein_g", 120)), step=5.0),
        "carbs_g": cols[2].number_input("Hidratos (g)", 0.0, 1000.0, float(t.get("carbs_g", 220)), step=5.0),
        "fat_g": cols[3].number_input("Grasa (g)", 0.0, 500.0, float(t.get("fat_g", 65)), step=5.0),
        "fiber_g": cols[4].number_input("Fibra (g)", 0.0, 200.0, float(t.get("fiber_g", 30)), step=1.0),
        "workouts_per_week": st.number_input("Entrenos por semana", 0, 14, int(t.get("workouts_per_week", 3))),
    }
    if st.form_submit_button("Guardar objetivos") and api.put("/targets", new_t):
        st.success("Guardado")

st.subheader("Perfil (se inyecta en el contexto del asistente)")
SEX = ["", "hombre", "mujer", "otro"]
with st.form("profile"):
    c = st.columns(3)
    sex = c[0].selectbox("Sexo", SEX, index=SEX.index(p["sex"]) if p.get("sex") in SEX else 0)
    bd = c[1].date_input("Fecha de nacimiento", value=date.fromisoformat(p["birth_date"]) if p.get("birth_date") else None,
                         min_value=date(1900, 1, 1), max_value=date.today())
    h = c[2].number_input("Altura (cm)", 0.0, 250.0, float(p.get("height_cm") or 0), step=1.0)
    act = st.text_input("Nivel de actividad", p.get("activity_level") or "", placeholder="sedentario, moderado, muy activo…")
    goal = st.text_input("Objetivo", p.get("goal") or "", placeholder="perder grasa, ganar músculo, mantener…")
    restr = st.text_area("Alergias / restricciones", p.get("dietary_restrictions") or "")
    notes = st.text_area("Notas para el asistente", p.get("context_notes") or "",
                         placeholder="Lesiones, rutina de entrenamiento, horarios, preferencias…")
    if st.form_submit_button("Guardar perfil"):
        body = {"sex": sex or None, "birth_date": bd.isoformat() if bd else None, "height_cm": h or None,
                "activity_level": act or None, "goal": goal or None,
                "dietary_restrictions": restr or None, "context_notes": notes or None}
        if api.put("/profile", body):
            st.success("Guardado")

if st.button("🔄 Reindexar histórico para el RAG"):
    r = api.post("/rag/reindex")
    if r:
        st.success(f"{r['days_indexed']} días indexados")
