from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st

import api
import auth
import ui
from muscles import body_svg

st.set_page_config(page_title="Entrenamiento", page_icon="🏋️", layout="wide")
ui.inject_css()
auth.require_login()
st.title("🏋️ Entrenamiento")

opts = api.options()
CATS, MUSCLES, EQUIP = opts.get("workout_category", {}), opts.get("muscle_group", {}), opts.get("equipment", {})
if not CATS:
    st.error("No se pudieron cargar las opciones. Reinicia el frontend y comprueba que el backend está actualizado.")
    st.stop()
INTENSITY = {"low": "Intensidad baja", "moderate": "Intensidad moderada", "high": "Intensidad alta"}
today = date.fromisoformat((api.get("/meta/today") or {"date": date.today().isoformat()})["date"])

# Tras guardar una sesión se limpia el formulario (hay que hacerlo ANTES de crear los widgets)
if st.session_state.pop("reset_form", False):
    for k in [k for k in st.session_state if k.startswith(("sel_", "ed_", "df0_", "title_", "notes_"))]:
        del st.session_state[k]

tab_reg, tab_hist, tab_prog, tab_muscles, tab_plan = st.tabs(
    ["🏋️ Registrar sesión", "📅 Historial", "📈 Progresión", "🫀 Músculos", "📋 Plan y peso"])


def muscle_chips(ex: dict) -> str:
    return (ui.chip(MUSCLES.get(ex["primary_muscle"], ex["primary_muscle"]), "orange")
            + ui.chips([MUSCLES.get(m, m) for m in ex.get("secondary_muscles", [])])
            + ui.chip(EQUIP.get(ex.get("equipment"), ""), "blue"))


def fmt_sets(sets: list[dict]) -> str:
    return ", ".join(f"{s['reps']}×{s['weight_kg']:g} kg" if s.get("weight_kg") else f"{s['reps']} reps" for s in sets)


# ═════════════════════════ Registrar sesión ═════════════════════════
def last_sets(ex_id: int) -> list[dict]:
    cache = st.session_state.setdefault("_hist", {})
    if ex_id not in cache:
        cache[ex_id] = api.get(f"/exercises/{ex_id}/history", limit=1) or []
    return cache[ex_id]


def exercise_block(ex: dict) -> pd.DataFrame:
    """Tabla editable de series de un ejercicio, precargada con la última vez que lo hiciste."""
    hist = last_sets(ex["id"])
    with st.container(border=True):
        ui.html(f"<b>{escape(ex['name'])}</b><br>{muscle_chips(ex)}")
        if hist:
            st.caption(f"Última vez ({hist[0]['date']}): {fmt_sets(hist[0]['sets'])}")
        key0 = f"df0_{ex['id']}"
        if key0 not in st.session_state:
            rows = ([{"Reps": s["reps"], "Peso (kg)": s["weight_kg"], "RPE": s["rpe"]} for s in hist[0]["sets"]]
                    if hist else [{"Reps": 10, "Peso (kg)": None, "RPE": None} for _ in range(3)])
            st.session_state[key0] = pd.DataFrame(rows)
        return st.data_editor(
            st.session_state[key0], num_rows="dynamic", hide_index=True, key=f"ed_{ex['id']}", width="stretch",
            column_config={
                "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=200, step=1, format="%d"),
                "Peso (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, max_value=1000.0, step=0.5,
                                                           help="Vacío = peso corporal"),
                "RPE": st.column_config.NumberColumn("RPE", min_value=1.0, max_value=10.0, step=0.5,
                                                     help="Esfuerzo percibido 1-10 (opcional)")})


def sets_from(ex_id: int, df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        if pd.notna(r["Reps"]) and r["Reps"] >= 1:
            out.append({"exercise_id": ex_id, "reps": int(r["Reps"]),
                        "weight_kg": float(r["Peso (kg)"]) if pd.notna(r["Peso (kg)"]) and r["Peso (kg)"] > 0 else None,
                        "rpe": float(r["RPE"]) if pd.notna(r["RPE"]) else None})
    return out


with tab_reg:
    if saved := st.session_state.pop("saved_workout", None):
        worked = sorted({MUSCLES.get(e["primary_muscle"], e["primary_muscle"]) for e in saved["exercises"]})
        body = f"<h4>✅ Sesión guardada: {escape(saved['kind'])}</h4>"
        if saved.get("kcal_burned") is not None:
            origin = "estimadas por la IA" if saved.get("kcal_source") == "llm" else "introducidas por ti"
            body += f"<div class='sf-big'>🔥 {saved['kcal_burned']:.0f} kcal <span class='sf-muted'>{origin}</span></div>"
            if saved.get("intensity"):
                body += ui.chip(INTENSITY.get(saved["intensity"], saved["intensity"]), "orange") + ui.chip(f"MET {saved['met']:g}")
        if saved.get("kcal_note"):
            body += f"<div class='sf-muted'>{escape(saved['kcal_note'])}</div>"
        if worked:
            body += f"<div style='margin-top:6px'>Músculos trabajados: {ui.chips(worked, 'green')}</div>"
        ui.card(body)

    c1, c2, c3 = st.columns(3)
    d = c1.date_input("Fecha", value=today, max_value=today, key="w_date")
    cat = c2.selectbox("Tipo de sesión", list(CATS), format_func=lambda c: CATS[c], key="w_cat")
    dur = c3.number_input("Duración total (min)", 5, 600, 60, step=5, key="w_dur")
    title = st.text_input("Título", value=CATS[cat].split(" (")[0], key=f"title_{cat}")

    selected: list[int] = []
    edited: dict[int, pd.DataFrame] = {}
    if cat == "cardio":
        st.info("Para cardio basta con el título (por ejemplo «Correr 5 km») y la duración; la IA estimará las calorías.")
    else:
        exercises = api.get("/exercises", category=cat) or []
        by_id = {e["id"]: e for e in exercises}
        selected = st.multiselect(
            "Ejercicios de la sesión", list(by_id), key=f"sel_{cat}", placeholder="Elige uno o varios ejercicios",
            format_func=lambda i: f"{by_id[i]['name']} · {MUSCLES.get(by_id[i]['primary_muscle'], '')}")
        for ex_id in selected:
            edited[ex_id] = exercise_block(by_id[ex_id])

        with st.expander("➕ Crear un ejercicio que no está en la lista"):
            with st.form("new_exercise", clear_on_submit=True):
                n1, n2 = st.columns(2)
                name = n1.text_input("Nombre")
                primary = n2.selectbox("Músculo principal", list(MUSCLES), format_func=lambda m: MUSCLES[m])
                secondary = st.multiselect("Músculos secundarios", list(MUSCLES), format_func=lambda m: MUSCLES[m])
                equip = st.selectbox("Material", list(EQUIP), index=len(EQUIP) - 1, format_func=lambda e: EQUIP[e])
                if st.form_submit_button("Crear ejercicio") and name.strip():
                    if api.post("/exercises", json={"name": name, "primary_muscle": primary,
                                                    "secondary_muscles": secondary, "equipment": equip}):
                        st.success("Creado. Aparecerá en la lista si su músculo principal corresponde a este tipo de sesión.")

    notes = st.text_area("Notas (opcional)", key=f"notes_{cat}", height=70)
    mode = st.radio("Calorías quemadas", ["ia", "manual", "none"], horizontal=True,
                    format_func={"ia": "🤖 Estimar con IA", "manual": "✍️ Introducir a mano", "none": "No registrar"}.get,
                    help="La IA estima la intensidad por el tipo de sesión, la duración y las series; las kcal se calculan "
                         "con tu peso corporal (MET × kg × horas).")
    manual_kcal = st.number_input("Calorías (kcal)", 0, 10000, 300, step=10) if mode == "manual" else None

    if st.button("💾 Guardar sesión", type="primary"):
        sets = [s for ex_id in selected for s in sets_from(ex_id, edited[ex_id])]
        payload = {"performed_on": d.isoformat(), "kind": title.strip() or CATS[cat], "category": cat,
                   "duration_min": int(dur), "notes": notes.strip() or None, "sets": sets, "estimate_calories": mode == "ia"}
        if mode == "manual":
            payload["kcal_burned"] = manual_kcal
        with st.spinner("Guardando" + (" y estimando calorías con IA…" if mode == "ia" else "…")):
            res = api.post("/workouts", json=payload, timeout=api.LONG_TIMEOUT)
        if res:
            st.session_state.update(saved_workout=res, reset_form=True)
            st.session_state.pop("_hist", None)
            st.rerun()

# ═════════════════════════ Historial ═════════════════════════
with tab_hist:
    workouts = api.get("/workouts", days=90) or []
    if not workouts:
        st.info("Aún no hay sesiones registradas en los últimos 90 días.")
    for w in workouts:
        kcal = f" · 🔥 {w['kcal_burned']:.0f} kcal" if w["kcal_burned"] else ""
        with st.expander(f"{w['performed_on']} · {w['kind']} · {w['duration_min']} min{kcal}"):
            tags = ui.chip(CATS.get(w["category"], "Sesión"), "blue")
            if w["intensity"]:
                tags += ui.chip(INTENSITY.get(w["intensity"], w["intensity"]), "orange")
            if w["kcal_source"]:
                tags += ui.chip("kcal por IA" if w["kcal_source"] == "llm" else "kcal manuales", "green")
            if w["met"]:
                tags += ui.chip(f"MET {w['met']:g}")
            ui.html(tags)
            if w["kcal_note"]:
                st.caption(w["kcal_note"])
            if w["notes"]:
                st.write(w["notes"])
            for ex in w["exercises"]:
                st.markdown(f"**{ex['exercise']}** · {MUSCLES.get(ex['primary_muscle'], '')}")
                df = pd.DataFrame(ex["sets"]).rename(columns={"set_number": "Serie", "reps": "Reps", "weight_kg": "Peso (kg)", "rpe": "RPE"})
                st.dataframe(df, hide_index=True, width="stretch")
            b1, b2, _ = st.columns([2, 1, 4])
            if b1.button("🔄 Recalcular calorías (IA)", key=f"re_{w['id']}"):
                with st.spinner("Estimando…"):
                    ok = api.post(f"/workouts/{w['id']}/estimate-calories", timeout=api.LONG_TIMEOUT)
                if ok:
                    st.rerun()
            if b2.button("🗑 Borrar", key=f"dw_{w['id']}"):
                api.delete(f"/workouts/{w['id']}")
                st.rerun()

# ═════════════════════════ Progresión ═════════════════════════
with tab_prog:
    used = api.get("/exercises", used="true") or []
    if not used:
        st.info("Registra series en algún ejercicio para ver su progresión.")
    else:
        by_used = {e["id"]: e for e in used}
        ex_id = st.selectbox("Ejercicio", list(by_used), format_func=lambda i: by_used[i]["name"])
        prog = api.get(f"/exercises/{ex_id}/progress") or []
        if prog:
            df = pd.DataFrame(prog).assign(date=lambda x: pd.to_datetime(x["date"])).set_index("date")
            m = st.columns(3)
            best = df["est_1rm_kg"].max()
            m[0].metric("Mejor 1RM estimado", f"{best:.1f} kg" if pd.notna(best) else "—",
                        help="Fórmula de Epley, solo con series de 1 a 12 repeticiones con peso.")
            m[1].metric("Peso máximo", f"{df['best_weight_kg'].max():.1f} kg" if df["best_weight_kg"].notna().any() else "—")
            m[2].metric("Sesiones", len(df))
            if df["best_weight_kg"].notna().any():
                st.caption("Peso máximo y 1RM estimado por sesión (kg)")
                st.line_chart(df[["best_weight_kg", "est_1rm_kg"]].rename(columns={"best_weight_kg": "Peso máx.", "est_1rm_kg": "1RM estimado"}))
            st.caption("Volumen total por sesión (kg × reps)")
            st.bar_chart(df[["volume_kg"]].rename(columns={"volume_kg": "Volumen"}))

# ═════════════════════════ Músculos ═════════════════════════
with tab_muscles:
    days = st.radio("Periodo", [7, 14, 30], horizontal=True, format_func=lambda d: f"Últimos {d} días")
    data = api.get("/training/muscles", days=days)
    if data:
        weekly = {m: v["sets"] * 7 / days for m, v in data["muscles"].items()}   # media semanal comparable entre periodos
        left, right = st.columns([3, 2])
        with left:
            st.image(body_svg(weekly), width="stretch")
        with right:
            st.caption(f"{data['sessions']} sesiones con series registradas. Color = series ponderadas **por semana** "
                       "(músculo principal = 1, secundarios = 0,5). Referencia habitual para hipertrofia: 10-20 series/semana (orientativo).")
            rows = sorted(((MUSCLES[m], w, data["muscles"][m]["volume_kg"]) for m, w in weekly.items() if w > 0), key=lambda r: -r[1])
            if rows:
                df = pd.DataFrame(rows, columns=["Músculo", "Series/semana", "Volumen (kg)"]).round(1)
                st.bar_chart(df.set_index("Músculo")[["Series/semana"]], horizontal=True)
            idle = [MUSCLES[m] for m, w in weekly.items() if w == 0]
            if idle:
                st.markdown("**Sin trabajar en este periodo**")
                ui.html(ui.chips(idle))
        if rows:
            with st.expander("Detalle por músculo"):
                st.dataframe(df, hide_index=True, width="stretch")

# ═════════════════════════ Plan y peso ═════════════════════════
with tab_plan:
    targets = api.get("/targets") or {"workouts_per_week": 3}
    recent = api.get("/workouts", days=14) or []
    monday = today - timedelta(days=today.weekday())
    this_week = [w for w in recent if date.fromisoformat(w["performed_on"]) >= monday]
    goal = max(targets["workouts_per_week"], 1)
    st.metric("Sesiones esta semana", f"{len(this_week)} / {targets['workouts_per_week']}")
    st.progress(min(len(this_week) / goal, 1.0))
    if targets.get("training_plan"):
        with st.container(border=True):
            st.markdown("**Plan recomendado" + (" por la IA" if targets.get("source") == "llm" else "") + "**")
            st.markdown(targets["training_plan"])
    st.subheader("Peso corporal")
    st.caption("Se usa para estimar las calorías quemadas y tus objetivos.")
    with st.form("weight", clear_on_submit=True):
        w1, w2 = st.columns(2)
        wd = w1.date_input("Fecha", value=today, max_value=today, key="wt_date")
        kg = w2.number_input("Peso (kg)", 30.0, 300.0, 75.0, step=0.1)
        if st.form_submit_button("Guardar peso") and api.post("/metrics/weight", json={"measured_on": wd.isoformat(), "weight_kg": kg}):
            st.rerun()
    weights = api.get("/metrics/weight", days=180) or []
    if weights:
        wdf = pd.DataFrame(weights).assign(measured_on=lambda x: pd.to_datetime(x["measured_on"])).set_index("measured_on")
        st.line_chart(wdf[["weight_kg"]].rename(columns={"weight_kg": "Peso (kg)"}))
