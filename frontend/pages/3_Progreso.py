import pandas as pd
import streamlit as st

import api
import auth
import charts
import ui

st.set_page_config(page_title="Progreso", page_icon="📈", layout="wide")
ui.inject_css()
auth.require_login()
ui.hero("📈 Progreso", "Cómo evolucionas: nutrición, entrenamiento y hábitos.")

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

# ═════════════ Análisis automático ═════════════
ui.section("Analiza mi progreso", f"Compara tus últimos {days} días con los {days} anteriores, con datos reales de tu diario.", "🔍")
ai_text = st.toggle("Redactar con IA", value=False, key="ins_ai", help="Los números y logros se calculan siempre por código; la IA solo los redacta.")
if st.button(f"🔍 Analizar mis últimos {days} días", type="primary", key="ins_go"):
    with st.spinner("Analizando tus datos…"):
        st.session_state["_insights"] = api.get("/progress/insights", days=days, ai=str(ai_text).lower())
res = st.session_state.get("_insights")
if res and res["period"]["days"] == days:
    with st.container(border=True):
        st.markdown(res["ai_summary"] or res["summary"])
        if ai_text and not res["ai_summary"] and res["enough_data"]:
            st.caption("La IA no está disponible ahora mismo: te muestro el resumen calculado.")
        if res["achievements"]:
            ui.html("".join(ui.good(a) for a in res["achievements"]))
        if res["pending"]:
            ui.html("".join(ui.todo(a) for a in res["pending"]))
        tr, nu = res["training"], res["nutrition"]
        if res["enough_data"]:
            cmp = st.columns(4)
            cmp[0].metric("Sesiones", tr["sessions"], delta=tr["sessions"] - tr["prev_sessions"], help="Frente al periodo anterior equivalente")
            cmp[1].metric("Volumen (kg)", f"{tr['volume_kg']:,}".replace(",", "."), delta=tr["volume_kg"] - tr["prev_volume_kg"])
            cmp[2].metric("Proteína media", f"{nu['avg_protein_g']} g" if nu["avg_protein_g"] is not None else "—")
            cmp[3].metric("Días con registro", f"{nu['days_logged']} / {days}")
        st.caption(res["note"])

if not has_food and not workouts:
    ui.empty("📈", "Todavía no hay datos en este periodo", "Registra tus comidas y entrenamientos y aquí verás cómo evolucionas.")
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
    with c1:
        ui.html(ui.macro_donut(*mine, "Tu media diaria", goal=goal, grams=(df["protein_g"].mean(), df["carbs_g"].mean(), df["fat_g"].mean())))
    with c2:
        ui.html(ui.macro_donut(*goal, "Tu objetivo", grams=(t["protein_g"], t["carbs_g"], t["fat_g"])))
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

# ═════════════ Hábitos y bienestar ═════════════
water, act, moods = api.get("/water/summary", days=days) or {}, api.get("/activity/summary", days=days) or {}, api.get("/checkins", days=days) or []
if water.get("days_logged"):
    box = section("💧 Agua", f"Objetivo diario: {water['goal_ml']} ml · cumplido {water['days_goal_met']} de {days} días.")
    wdf = pd.DataFrame(water["days"]).assign(date=lambda x: pd.to_datetime(x["date"]))
    box.altair_chart(charts.simple_bars(wdf, "date", "ml", "ml", ui.BLUE, goal=water["goal_ml"]), width="stretch")
if act.get("days_recorded"):
    box = section("👣 Pasos", f"Media {act['avg_steps']:,} pasos · objetivo {act['goal']:,}.".replace(",", "."))
    adf = pd.DataFrame(act["days"]).dropna(subset=["steps"]).assign(date=lambda x: pd.to_datetime(x["date"]))
    box.altair_chart(charts.simple_bars(adf, "date", "steps", "pasos", ui.PURPLE, goal=act["goal"]), width="stretch")
if len(moods) >= 2:
    box = section("🙂 Estado de ánimo y energía", "Se muestran como contexto junto al resto de hábitos; coincidir en el tiempo no implica causa y efecto.")
    mdf = pd.DataFrame(moods).assign(date=lambda x: pd.to_datetime(x["date"])).drop(columns=["notes"])
    long = mdf.melt(id_vars="date", value_vars=["mood", "energy_level"], var_name="Indicador", value_name="v").dropna()
    long["Indicador"] = long["Indicador"].map({"mood": "Ánimo", "energy_level": "Energía"})
    box.altair_chart(charts._finish(charts.alt.Chart(long).mark_line(strokeWidth=2.5, point=True).encode(
        x=charts._x(), y=charts.alt.Y("v:Q", scale=charts.alt.Scale(domain=[1, 5]), title="1 a 5"),
        color=charts.alt.Color("Indicador:N", legend=charts.alt.Legend(orient="bottom", title=None)))), width="stretch")
