import pandas as pd
import streamlit as st

import api
import auth
import charts
import ui

st.set_page_config(page_title="Progreso", page_icon="📈", layout="wide")
ui.inject_css()
auth.require_login()
st.title("📈 Progreso")

days = st.segmented_control("Periodo", [7, 14, 30, 90], default=14, format_func=lambda d: f"{d} días", label_visibility="collapsed") or 14
data = api.get("/dashboard/range", days=days)
if not data:
    st.stop()
t = data["targets"]
cats = (api.options() or {}).get("workout_category", {})


def kpi(col, label: str, value: str, sub: str = "", accent: str = ui.GREEN) -> None:
    with col:
        ui.card(f'<div class="sf-muted">{ui.escape(label)}</div><div class="sf-big" style="color:{accent}">{ui.escape(value)}</div>'
                f'<div class="sf-muted">{ui.escape(sub)}</div>')


def section(title: str, caption: str = ""):
    box = st.container(border=True)
    box.markdown(f"#### {title}")
    if caption:
        box.caption(caption)
    return box


# ═════════════ Datos ═════════════
df = pd.DataFrame(data["days"])
has_food = not df.empty
if has_food:
    df["date"] = pd.to_datetime(df["log_date"])
weights = api.get("/metrics/weight", days=365) or []
wdf = pd.DataFrame(weights)
if not wdf.empty:
    wdf["date"] = pd.to_datetime(wdf["measured_on"])
workouts = api.get("/workouts", days=days) or []

# ═════════════ Resumen ═════════════
k = st.columns(4)
if has_food:
    avg_kcal, avg_p = df["kcal"].mean(), df["protein_g"].mean()
    in_target = int(((df["kcal"] - t["kcal"]).abs() <= t["kcal"] * 0.10).sum())
    d_kcal = (avg_kcal / t["kcal"] - 1) * 100 if t["kcal"] else 0
    kpi(k[0], "Calorías (media diaria)", f"{avg_kcal:,.0f} kcal".replace(",", "."), f"Objetivo {t['kcal']:.0f} · {d_kcal:+.0f} %",
        ui.GREEN if abs(d_kcal) <= 10 else ui.ORANGE)
    kpi(k[1], "Proteína (media diaria)", f"{avg_p:.0f} g", f"Objetivo {t['protein_g']:.0f} g · {avg_p / t['protein_g'] * 100:.0f} %" if t["protein_g"] else "",
        ui.BLUE if avg_p >= t["protein_g"] * 0.9 else ui.ORANGE)
    kpi(k[2], "Días en objetivo", f"{in_target} de {len(df)}", "Dentro de ±10 % de tus kcal", ui.GREEN if in_target >= len(df) / 2 else ui.ORANGE)
else:
    for col, label in zip(k[:3], ("Calorías", "Proteína", "Días en objetivo")):
        kpi(col, label, "—", "Sin comidas registradas", "#94a3b8")
if not wdf.empty:
    last = wdf.sort_values("date").iloc[-1]
    since = wdf[wdf["date"] >= pd.Timestamp.today().normalize() - pd.Timedelta(days=days)].sort_values("date")
    change = f"{last['weight_kg'] - since.iloc[0]['weight_kg']:+.1f} kg en {days} días" if len(since) >= 2 else "Registra más pesadas para ver la tendencia"
    kpi(k[3], "Peso actual", f"{last['weight_kg']:.1f} kg", change, ui.PURPLE)
else:
    kpi(k[3], "Peso actual", "—", "Sin pesadas registradas", "#94a3b8")

if not has_food and not workouts:
    st.info("Todavía no hay datos en este periodo. Registra tus comidas y entrenamientos y aquí verás cómo evolucionas.")
    st.page_link("pages/1_Registrar.py", label="Registrar una comida", icon="➕")
    st.page_link("pages/4_Entrenamiento.py", label="Registrar un entrenamiento", icon="🏋️")
    st.stop()

# ═════════════ Alimentación ═════════════
if has_food:
    box = section("🍽️ Calorías por día", f"{in_target} de {len(df)} días registrados dentro de ±10 % de tu objetivo de {t['kcal']:.0f} kcal. "
                  "Los días sin registro no se muestran.")
    box.altair_chart(charts.day_status_bars(df, "kcal", t["kcal"], label="Objetivo"), width="stretch")

    box = section("🥩 Macros", "Reparto de las calorías entre proteína, hidratos y grasa (4 · 4 · 9 kcal por gramo).")
    c1, c2, c3 = box.columns([1, 1, 2])
    mine = (df["protein_g"].mean() * 4, df["carbs_g"].mean() * 4, df["fat_g"].mean() * 9)
    goal = (t["protein_g"] * 4, t["carbs_g"] * 4, t["fat_g"] * 9)
    c1.altair_chart(charts.macro_donut(*mine, "Tu media"), width="stretch")
    c2.altair_chart(charts.macro_donut(*goal, "Tu objetivo"), width="stretch")
    c3.markdown("**Proteína por día (g)**")
    c3.altair_chart(charts.line_with_goal(df, "protein_g", t["protein_g"], "g", ui.BLUE), width="stretch")
    if "fiber_g" in df and t.get("fiber_g"):
        box.caption(f"Fibra media: {df['fiber_g'].mean():.0f} g de {t['fiber_g']:.0f} g de objetivo.")

# ═════════════ Peso ═════════════
if len(wdf) >= 2:
    box = section("⚖️ Peso", "Puntos = pesadas; línea = media móvil de 7 mediciones (más fiable que un día suelto).")
    box.altair_chart(charts.weight_chart(wdf[["date", "weight_kg"]]), width="stretch")

# ═════════════ Entrenamiento ═════════════
if workouts:
    wk = pd.DataFrame(workouts).assign(date=lambda x: pd.to_datetime(x["performed_on"]))
    box = section("🏋️ Entrenamiento")
    m = box.columns(4)
    kpi(m[0], "Sesiones", str(len(wk)), f"Objetivo {t['workouts_per_week']}/semana", ui.GREEN)
    kpi(m[1], "Tiempo total", f"{wk['duration_min'].sum() / 60:.1f} h", "", ui.BLUE)
    kpi(m[2], "Kcal quemadas (est.)", f"{wk['kcal_burned'].fillna(0).sum():,.0f}".replace(",", "."), "Estimadas por la IA o manuales", ui.ORANGE)
    km = wk["distance_km"].fillna(0).sum()
    kpi(m[3], "Distancia", f"{km:.1f} km" if km else "—", "Andar + correr", ui.PURPLE)
    box.markdown("".join(ui.chip(f"{cats.get(c, c or 'Sesión')}: {n}", "blue") for c, n in wk["category"].fillna("other").value_counts().items()),
                 unsafe_allow_html=True)
    weekly = wk.groupby(pd.Grouper(key="date", freq="W-MON", label="left", closed="left")).size().rename("Sesiones").reset_index()
    left, right = box.columns(2)
    left.markdown("**Sesiones por semana**")
    left.altair_chart(charts.simple_bars(weekly, "date", "Sesiones", "Sesiones", ui.GREEN, goal=t["workouts_per_week"], size=36), width="stretch")
    daily = wk.groupby("date", as_index=False)["kcal_burned"].sum()
    right.markdown("**Kcal quemadas por día**")
    right.altair_chart(charts.simple_bars(daily, "date", "kcal_burned", "kcal", ui.ORANGE), width="stretch")
