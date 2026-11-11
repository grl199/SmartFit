import pandas as pd
import streamlit as st

import api

st.set_page_config(page_title="Progreso", page_icon="📈", layout="wide")
st.title("📈 Progreso")

days = st.sidebar.radio("Periodo", [7, 14, 30, 90], index=1, format_func=lambda d: f"{d} días")
data = api.get("/dashboard/range", days=days)
if not data:
    st.stop()
if not data["days"]:
    st.info("Todavía no hay datos en este periodo.")
    st.stop()

df = pd.DataFrame(data["days"]).assign(log_date=lambda d: pd.to_datetime(d.log_date)).set_index("log_date")
df = df.reindex(pd.date_range(data["start"], data["end"]))
t = data["targets"]

st.caption(f"Días con registro: {df.kcal.notna().sum()} de {days}. Las medias se calculan solo sobre esos días.")
c = st.columns(4)
c[0].metric("Media kcal", f"{df.kcal.mean():.0f}", f"objetivo {t['kcal']:.0f}", delta_color="off")
c[1].metric("Media proteína", f"{df.protein_g.mean():.0f} g", f"objetivo {t['protein_g']:.0f} g", delta_color="off")
c[2].metric("Media hidratos", f"{df.carbs_g.mean():.0f} g")
c[3].metric("Media grasa", f"{df.fat_g.mean():.0f} g")

st.subheader("Calorías vs objetivo")
st.line_chart(df[["kcal"]].assign(objetivo=t["kcal"]))
st.subheader("Proteína vs objetivo")
st.bar_chart(df[["protein_g"]])
st.caption(f"Objetivo: {t['protein_g']:.0f} g/día")

weights = api.get("/metrics/weight", days=days) or []
if weights:
    st.subheader("Peso")
    wdf = pd.DataFrame(weights).assign(measured_on=lambda d: pd.to_datetime(d.measured_on)).set_index("measured_on")
    st.line_chart(wdf[["weight_kg"]])
