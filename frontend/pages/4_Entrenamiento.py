from datetime import date, timedelta

import pandas as pd
import streamlit as st

import api

st.set_page_config(page_title="Entrenamiento", page_icon="🏋️", layout="wide")
st.title("🏋️ Entrenamiento")

workouts = api.get("/workouts", days=60) or []
targets = api.get("/targets") or {"workouts_per_week": 3}
week_start = date.today() - timedelta(days=date.today().weekday())
this_week = [w for w in workouts if date.fromisoformat(w["performed_on"]) >= week_start]
st.metric("Entrenos esta semana", f"{len(this_week)} / {targets['workouts_per_week']}")
st.progress(min(len(this_week) / max(targets["workouts_per_week"], 1), 1.0))

c1, c2 = st.columns(2)
with c1:
    st.subheader("Añadir entreno")
    with st.form("workout", clear_on_submit=True):
        d = st.date_input("Fecha", value=date.today())
        kind = st.text_input("Tipo", placeholder="Fuerza, running, bici…")
        dur = st.number_input("Duración (min)", 5, 600, 60, step=5)
        kcal = st.number_input("Kcal quemadas (opcional)", 0, 5000, 0, step=10)
        notes = st.text_area("Notas")
        if st.form_submit_button("Guardar") and kind:
            if api.post("/workouts", json={"performed_on": d.isoformat(), "kind": kind, "duration_min": dur,
                                           "kcal_burned": kcal or None, "notes": notes or None}):
                st.rerun()
with c2:
    st.subheader("Registrar peso")
    with st.form("weight", clear_on_submit=True):
        wd = st.date_input("Fecha ", value=date.today())
        kg = st.number_input("Peso (kg)", 20.0, 400.0, 75.0, step=0.1)
        if st.form_submit_button("Guardar peso"):
            if api.post("/metrics/weight", json={"measured_on": wd.isoformat(), "weight_kg": kg}):
                st.rerun()

st.subheader("Últimos 60 días")
if workouts:
    st.dataframe(pd.DataFrame(workouts)[["performed_on", "kind", "duration_min", "kcal_burned", "notes"]],
                 hide_index=True, width="stretch")
else:
    st.info("Sin entrenos registrados.")
