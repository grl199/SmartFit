from datetime import date, timedelta

import streamlit as st

import api
import auth
import ui
from components import MEALS, quick_add_bar
from habits_ui import mood_card, steps_card, water_card

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


# ───────── Cabecera: saludo + navegación por días ─────────
day = st.session_state.day
data = api.get("/dashboard/day", date=day.isoformat())
if not data:
    st.stop()
t, g = data["totals"], data["targets"]
burned = sum(w["kcal_burned"] or 0 for w in data["workouts"])
left_kcal = g["kcal"] - t["kcal"] + burned
name = (me.get("name") or "").split()[0] if me.get("name") else ""
if day == today:
    sub = (f"Te quedan unas {left_kcal:.0f} kcal para llegar a tu objetivo." if left_kcal > 0 else "Ya has alcanzado tu objetivo de calorías de hoy.") \
        if data["entries"] else "Empieza registrando tu primera comida del día."
    ui.hero(f"Hola, {name} 👋" if name else "Hola 👋", sub)
else:
    ui.hero(f"Diario · {day.strftime('%d/%m/%Y')}", "Estás viendo un día anterior. Puedes revisar y corregir lo que registraste.")
h = st.columns([5, 1, 2.2, 1])
h[0].empty()
h[1].button("◀", on_click=_shift, args=(-1,), width="stretch", help="Día anterior")
h[2].date_input("Día", key="day", max_value=today, label_visibility="collapsed")
h[3].button("▶", on_click=_shift, args=(1,), width="stretch", disabled=st.session_state.day >= today, help="Día siguiente")

# ───────── Resumen: anillo de calorías + macros ─────────
left, right = st.columns([1, 2])
with left:
    ui.card(f'<div style="text-align:center">{ui.ring(t["kcal"], g["kcal"])}'
            f'<div class="sf-muted">{t["kcal"]:.0f} de {g["kcal"]:.0f} kcal'
            + (f' · 🔥 {burned:.0f} entreno' if burned else "") + "</div></div>")
with right:
    ui.card(ui.bar("Proteína", t["protein_g"], g["protein_g"], "g", ui.BLUE) + ui.bar("Hidratos", t["carbs_g"], g["carbs_g"], "g", ui.ORANGE)
            + ui.bar("Grasa", t["fat_g"], g["fat_g"], "g", ui.PURPLE) + ui.bar("Fibra", t["fiber_g"], g["fiber_g"], "g", ui.GREEN))

# ───────── Hábitos del día (solo hoy) ─────────
if day == today:
    hc = st.columns(3)
    with hc[0]:
        water_card("home")
    with hc[1]:
        steps_card("home")
    with hc[2]:
        mood_card(today, "home")
    plan = api.get("/plan") or {}
    if plan.get("has_plan") and not data["workouts"]:
        pday = next((d for d in plan["plan"]["days"] if d["id"] == plan["suggested_day_id"]), None)
        if pday:
            names = [e["exercise"] for e in pday["exercises"]][:5]
            ui.card(f"<h4>🏋️ Te toca hoy: {ui.escape(pday['label'])}</h4>{ui.chips(names, 'orange')}"
                    f"<div class='sf-muted'>{len(pday['exercises'])} ejercicios · tus pesos de la última vez se cargan solos</div>")
            st.page_link("pages/4_Entrenamiento.py", label="Empezar entrenamiento", icon="▶️")
    elif data["workouts"]:
        pass

# ───────── Añadir ─────────
ui.section("Añadir rápido", "Un toque para repetir lo que comes a menudo.", "⚡")
quick_add_bar()
st.page_link("pages/1_Registrar.py", label="Registrar otra comida (buscar, receta, escanear, crear)", icon="➕")

# ───────── Comidas del día ─────────
ui.section("Comidas", "", "🍽️")
if not data["entries"]:
    ui.empty("🥗", "Aún no hay comidas este día", "Pulsa «Registrar otra comida» o usa un habitual de arriba.")
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
    ui.section("Entrenamiento", "", "🏋️")
    cats = (api.options() or {}).get("workout_category", {})
    for w in data["workouts"]:
        kcal = f' · 🔥 ~{w["kcal_burned"]:.0f} kcal' if w["kcal_burned"] else ""
        category = cats.get(w["category"], w["category"] or "Sesión")
        minutes = f'{w["duration_min"]} min'
        ui.card(f'<h4>🏋️ {ui.escape(w["kind"])}</h4>{ui.chip(category, "blue")}{ui.chip(minutes)}{ui.escape(kcal)}'
                f'<div style="margin-top:4px">{ui.cardio_chips(w)}{ui.chips(w["exercises"])}</div>')
