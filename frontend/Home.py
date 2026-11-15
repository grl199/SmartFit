from datetime import date, timedelta

import streamlit as st

import api
import auth
import ui
from components import MEALS, quick_add_bar

st.set_page_config(page_title="SmartFit · Hoy", page_icon="🥗", layout="wide")
ui.inject_css()
me = auth.require_login()

today_resp = api.get("/meta/today")
if not today_resp:
    st.stop()
today = date.fromisoformat(today_resp["date"])
st.session_state.setdefault("day", today)


def _shift(n: int) -> None:
    st.session_state.day = min(st.session_state.day + timedelta(days=n), today)


# ───────── Cabecera: navegación por días ─────────
h = st.columns([5, 1, 2.2, 1])
h[0].title("Hoy" if st.session_state.day == today else "Diario")
h[1].button("◀", on_click=_shift, args=(-1,), width="stretch", help="Día anterior")
h[2].date_input("Día", key="day", max_value=today, label_visibility="collapsed")
h[3].button("▶", on_click=_shift, args=(1,), width="stretch", disabled=st.session_state.day >= today, help="Día siguiente")

day = st.session_state.day
data = api.get("/dashboard/day", date=day.isoformat())
if not data:
    st.stop()
t, g = data["totals"], data["targets"]
burned = sum(w["kcal_burned"] or 0 for w in data["workouts"])

# ───────── Resumen: anillo de calorías + macros ─────────
left, right = st.columns([1, 2])
with left:
    ui.card(f'<div style="text-align:center">{ui.ring(t["kcal"], g["kcal"])}'
            f'<div class="sf-muted">{t["kcal"]:.0f} de {g["kcal"]:.0f} kcal'
            + (f' · 🔥 {burned:.0f} entreno' if burned else "") + "</div></div>")
with right:
    ui.card(ui.bar("Proteína", t["protein_g"], g["protein_g"], "g", ui.BLUE) + ui.bar("Hidratos", t["carbs_g"], g["carbs_g"], "g", ui.ORANGE)
            + ui.bar("Grasa", t["fat_g"], g["fat_g"], "g", ui.PURPLE) + ui.bar("Fibra", t["fiber_g"], g["fiber_g"], "g", ui.GREEN))

# ───────── Añadir ─────────
st.subheader("Añadir rápido")
quick_add_bar()
st.page_link("pages/1_Registrar.py", label="Registrar otra comida (buscar, escanear, crear)", icon="➕")

# ───────── Comidas del día ─────────
st.subheader("Comidas")
if not data["entries"]:
    st.info("Aún no hay comidas registradas este día.")
for meal_key, meal_label in MEALS.items():
    rows = [e for e in data["entries"] if e["meal"] == meal_key]
    if not rows:
        continue
    with st.container(border=True):
        ui.html(f'<div class="sf-row"><b>{ui.MEAL_ICONS[meal_key]} {meal_label}</b>'
                f'<span>{sum(r["kcal"] for r in rows):.0f} kcal</span></div>')
        for e in rows:
            c = st.columns([5, 4, 0.7])
            name = ui.escape(e["food"]) + (f' <span class="sf-muted">· {ui.escape(e["brand"])}</span>' if e["brand"] else "")
            c[0].markdown(f'{name}<br><span class="sf-muted">{e["grams"]:.0f} g · {e["time"]}</span>', unsafe_allow_html=True)
            c[1].markdown(ui.chip(f'{e["kcal"]:.0f} kcal', "green") + ui.chip(f'P {e["protein_g"]:.0f}', "blue")
                          + ui.chip(f'H {e["carbs_g"]:.0f}', "orange") + ui.chip(f'G {e["fat_g"]:.0f}', "purple"), unsafe_allow_html=True)
            if c[2].button("🗑", key=f"del_{e['id']}", help="Borrar"):
                api.delete(f"/logs/{e['id']}")
                st.rerun()

# ───────── Entrenamiento del día ─────────
if data["workouts"]:
    st.subheader("Entrenamiento")
    cats = (api.options() or {}).get("workout_category", {})
    for w in data["workouts"]:
        kcal = f' · 🔥 ~{w["kcal_burned"]:.0f} kcal' if w["kcal_burned"] else ""
        category = cats.get(w["category"], w["category"] or "Sesión")
        minutes = f'{w["duration_min"]} min'
        ui.card(f'<h4>🏋️ {ui.escape(w["kind"])}</h4>{ui.chip(category, "blue")}{ui.chip(minutes)}{ui.escape(kcal)}'
                f'<div style="margin-top:4px">{ui.chips(w["exercises"])}</div>')
