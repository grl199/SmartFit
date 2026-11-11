from datetime import date

import streamlit as st

import api
from components import MEALS, progress_block, quick_add_bar

st.set_page_config(page_title="Salud · Hoy", page_icon="🥗", layout="wide")
st.title("🥗 Hoy")

today_resp = api.get("/meta/today")
if not today_resp:
    st.stop()
today = date.fromisoformat(today_resp["date"])
day = st.sidebar.date_input("Día", value=today, max_value=today)
data = api.get("/dashboard/day", date=day.isoformat())
if not data:
    st.stop()

progress_block(data["totals"], data["targets"])

t = data["totals"]
done = len(data["workouts"])
st.caption(f"Entrenos hoy: {done}" + (" · " + ", ".join(f"{w['kind']} {w['duration_min']} min" for w in data["workouts"]) if done else ""))

st.subheader("Añadir rápido")
quick_add_bar()

st.subheader("Registro del día")
if not data["entries"]:
    st.info("Aún no hay comidas registradas. Usa «Registrar» o el chat.")
for meal_key, meal_label in MEALS.items():
    rows = [e for e in data["entries"] if e["meal"] == meal_key]
    if not rows:
        continue
    st.markdown(f"**{meal_label}** · {sum(r['kcal'] for r in rows):.0f} kcal")
    for e in rows:
        c = st.columns([5, 1.2, 1.2, 1.2, 1.2, 0.8])
        c[0].write(f"{e['food']}" + (f" _({e['brand']})_" if e["brand"] else "") + f" · {e['grams']:.0f} g")
        c[1].write(f"{e['kcal']:.0f} kcal")
        c[2].write(f"P {e['protein_g']:.0f} g")
        c[3].write(f"H {e['carbs_g']:.0f} g")
        c[4].write(f"G {e['fat_g']:.0f} g")
        if c[5].button("🗑", key=f"del_{e['id']}", help="Borrar"):
            api.delete(f"/logs/{e['id']}")
            st.rerun()
