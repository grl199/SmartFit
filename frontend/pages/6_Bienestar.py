from datetime import date, timedelta

import pandas as pd
import streamlit as st

import api
import auth
import charts
import ui
from habits_ui import fmt_ml, steps_card, water_card

st.set_page_config(page_title="Bienestar", page_icon="💚", layout="wide")
ui.inject_css()
auth.require_login()
ui.hero("💚 Bienestar", "Agua, estado de ánimo y actividad: pequeños hábitos que se notan.")
today = date.fromisoformat((api.get("/meta/today") or {"date": date.today().isoformat()})["date"])

tab_water, tab_mood, tab_act = st.tabs(["💧 Agua", "🙂 Estado de ánimo", "👣 Actividad"])

# ═════════════════════════ Agua ═════════════════════════
with tab_water:
    left, right = st.columns([2, 3])
    with left:
        water_card("bw")
        goal = (api.get("/targets") or {}).get("water_ml", 2000)
        with st.popover("🎯 Cambiar objetivo diario", width="stretch"):
            new = st.number_input("Objetivo (ml)", 500, 10000, int(goal), step=250, key="bw_goal")
            if st.button("Guardar objetivo", key="bw_goal_ok", type="primary"):
                t = api.get("/targets")
                if t and api.put("/targets", {k: t[k] for k in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "workouts_per_week")} | {"water_ml": int(new)}):
                    st.rerun()
    with right:
        s = api.get("/water/summary", days=14) or {}
        if s.get("days_logged"):
            df = pd.DataFrame(s["days"]).assign(date=lambda x: pd.to_datetime(x["date"]))
            st.markdown("**Últimos 14 días**")
            st.altair_chart(charts.simple_bars(df, "date", "ml", "ml", ui.BLUE, goal=s["goal_ml"]), width="stretch")
            st.caption(f"Objetivo cumplido {s['days_goal_met']} de 14 días · media de los días con registro: {fmt_ml(s['avg_ml'])}.")
        else:
            ui.empty("💧", "Aún no hay registros de agua", "Usa los botones de la izquierda: un toque por vaso.")
    logs = api.get("/water", date=today.isoformat()) or []
    if logs:
        with st.expander(f"Tomas de hoy ({len(logs)})"):
            for w in logs:
                c = st.columns([5, 1])
                c[0].write(f"{w['logged_at'][11:16]} · {w['quantity_ml']} ml")
                if c[1].button("🗑", key=f"wdel_{w['id']}", help="Borrar"):
                    api.delete(f"/water/{w['id']}")
                    st.rerun()

# ═════════════════════════ Estado de ánimo ═════════════════════════
with tab_mood:
    st.caption("🔒 Tus notas son privadas: no se envían a la IA ni se usan en ningún resumen.")
    day = st.date_input("Día", value=today, max_value=today, key="mood_day")
    rows = {r["date"]: r for r in (api.get("/checkins", days=120) or [])}
    cur = rows.get(day.isoformat(), {})
    with st.container(border=True):
        mood = st.segmented_control("¿Cómo te encuentras?", list(ui.MOODS), default=cur.get("mood"), key=f"mood_{day}",
                                    format_func=lambda n: f"{ui.MOODS[n][0]} {ui.MOODS[n][1]}")
        c = st.columns(3)
        energy = c[0].select_slider("Energía", [None, 1, 2, 3, 4, 5], value=cur.get("energy_level"), key=f"en_{day}", format_func=lambda v: "—" if v is None else f"{v}/5")
        stress = c[1].select_slider("Estrés", [None, 1, 2, 3, 4, 5], value=cur.get("stress_level"), key=f"st_{day}", format_func=lambda v: "—" if v is None else f"{v}/5")
        sleep = c[2].select_slider("Descanso", [None, 1, 2, 3, 4, 5], value=cur.get("sleep_quality"), key=f"sl_{day}", format_func=lambda v: "—" if v is None else f"{v}/5")
        notes = st.text_area("Nota personal (opcional)", value=cur.get("notes") or "", key=f"nt_{day}", height=80,
                             placeholder="Me he encontrado con energía y he podido completar el entrenamiento…")
        b = st.columns([2, 1, 3])
        if b[0].button("💾 Guardar" if not cur else "💾 Actualizar", type="primary", disabled=mood is None, key=f"mood_save_{day}"):
            if api.put(f"/checkins/{day.isoformat()}", {"mood": mood, "energy_level": energy, "stress_level": stress, "sleep_quality": sleep, "notes": notes or None}):
                st.toast("Check-in guardado", icon="🙂")
                st.rerun()
        if cur and b[1].button("🗑", key=f"mood_del_{day}", help="Borrar este check-in"):
            api.delete(f"/checkins/{day.isoformat()}")
            st.rerun()
    if len(rows) >= 2:
        df = pd.DataFrame(rows.values()).assign(date=lambda x: pd.to_datetime(x["date"]))
        st.markdown("**Evolución**")
        long = df.melt(id_vars="date", value_vars=["mood", "energy_level", "stress_level", "sleep_quality"], var_name="Indicador", value_name="v").dropna()
        long["Indicador"] = long["Indicador"].map({"mood": "Ánimo", "energy_level": "Energía", "stress_level": "Estrés", "sleep_quality": "Descanso"})
        st.altair_chart(charts._finish(charts.alt.Chart(long).mark_line(strokeWidth=2.5, point=True).encode(
            x=charts._x(), y=charts.alt.Y("v:Q", scale=charts.alt.Scale(domain=[1, 5]), title="1 a 5"),
            color=charts.alt.Color("Indicador:N", legend=charts.alt.Legend(orient="bottom", title=None)),
            tooltip=[charts.alt.Tooltip("date:T", format="%d %b"), "Indicador:N", "v:Q"])), width="stretch")
        st.caption("Se muestran juntos como contexto: que dos cosas coincidan en el tiempo no significa que una cause la otra.")
    else:
        ui.empty("🙂", "Tu evolución aparecerá aquí", "Con un par de check-ins verás el gráfico.")

# ═════════════════════════ Actividad ═════════════════════════
with tab_act:
    left, right = st.columns([2, 3])
    with left:
        steps_card("ba")
    with right:
        s = api.get("/activity/summary", days=14) or {}
        if s.get("days_recorded"):
            df = pd.DataFrame(s["days"]).dropna(subset=["steps"]).assign(date=lambda x: pd.to_datetime(x["date"]))
            st.markdown("**Pasos por día**")
            st.altair_chart(charts.simple_bars(df, "date", "steps", "pasos", ui.PURPLE, goal=s["goal"]), width="stretch")
            st.caption(f"Media: {s['avg_steps']:,} pasos · objetivo alcanzado {s['days_goal_met']} de {s['days_recorded']} días registrados.".replace(",", "."))
        else:
            ui.empty("👣", "Sin pasos registrados", "Regístralos a mano o conecta una fuente de datos.")
    st.subheader("Fuentes de datos")
    st.caption("Tú decides qué se conecta: puedes revocar el permiso cuando quieras y, si lo deseas, borrar lo ya importado. "
               "Si varias fuentes miden el mismo día, **no se suman**: se usa el valor más alto para no contar los pasos dos veces.")
    for c in api.get("/activity/connections") or []:
        with st.container(border=True):
            h = st.columns([4, 2])
            h[0].markdown(f"**{c['label']}** " + ("· 🟢 conectado" if c["connected"] else ""))
            h[0].caption(c["note"])
            if c["connected"]:
                keep = h[1].checkbox("Borrar también lo importado", key=f"cdd_{c['provider']}")
                if h[1].button("Desconectar", key=f"cd_{c['provider']}"):
                    api.call("DELETE", f"/activity/connections/{c['provider']}", params={"delete_data": str(keep).lower()})
                    st.rerun()
            elif c["configured"]:
                if h[1].button("Dar permiso y conectar", key=f"cc_{c['provider']}"):
                    api.post("/activity/connections", json={"provider": c["provider"]})
                    st.rerun()
            else:
                h[1].caption("Aún no disponible")
