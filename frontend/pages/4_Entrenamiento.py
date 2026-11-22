from datetime import date, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import api
import auth
import charts
import ui
from muscles import body_svg, muscle_icon

st.set_page_config(page_title="Entrenamiento", page_icon="🏋️", layout="wide")
ui.inject_css()
auth.require_login()
ui.hero("🏋️ Entrenamiento", "Tu plan, tus series y qué mejorar en la próxima sesión.")

opts = api.options()
CATS, MUSCLES, EQUIP = opts.get("workout_category", {}), opts.get("muscle_group", {}), opts.get("equipment", {})
CARDIO_MUSCLES = opts.get("cardio_muscles", {})
CAT_ICON, TYPES = opts.get("workout_category_icons", {}), opts.get("workout_types", {})
REGIONS, EQUIP_ICON = opts.get("muscle_regions", {}), opts.get("equipment_icons", {})
SPORTS, SPORT_ICON = opts.get("sports", {}), opts.get("sport_icons", {})
if not (CATS and TYPES and REGIONS):
    st.error("No se pudieron cargar las opciones. Reinicia el frontend y comprueba que el backend está actualizado.")
    st.stop()
INTENSITY = {"low": "Intensidad baja", "moderate": "Intensidad moderada", "high": "Intensidad alta"}
today = date.fromisoformat((api.get("/meta/today") or {"date": date.today().isoformat()})["date"])

# Tras guardar una sesión se limpia el formulario (hay que hacerlo ANTES de crear los widgets)
if st.session_state.pop("reset_form", False):
    for k in [k for k in st.session_state if k.startswith(("sel_", "ed_", "df0_", "title_", "notes_", "dist_", "elev_", "steps_", "hr_", "mg_", "eq_", "q_", "w_sport", "plan_day_sel"))]:
        del st.session_state[k]

tab_reg, tab_hist, tab_prog, tab_muscles, tab_plan, tab_3d = st.tabs(
    ["🏋️ Registrar sesión", "📅 Historial", "📈 Progresión", "🫀 Músculos", "📋 Plan y peso", "🎞️ Ejercicios 3D"])


def muscle_chips(ex: dict) -> str:
    return (ui.chip(MUSCLES.get(ex["primary_muscle"], ex["primary_muscle"]), "orange")
            + ui.chips([MUSCLES.get(m, m) for m in ex.get("secondary_muscles", [])])
            + "".join(ui.chip(f"{EQUIP_ICON.get(e, '')} {EQUIP.get(e, e)}", "blue") for e in ex.get("equipment", [])))


def fmt_sets(sets: list[dict]) -> str:
    return ", ".join(f"{s['reps']}×{s['weight_kg']:g} kg" if s.get("weight_kg") else f"{s['reps']} reps" for s in sets)


FB_ICON = {"personal_record": "🏆", "progress": "📈", "maintain": "➡️", "regression": "🔻", "first_time": "🆕", "insufficient_data": "ℹ️"}


def show_feedback(feedback: list[dict]) -> None:
    """Recomendaciones deterministas por ejercicio (calculadas en el backend, sin IA)."""
    if not feedback:
        return
    st.markdown("**💡 Cómo ha ido y qué hacer la próxima vez**")
    for f in feedback:
        extra = f" · Próxima sesión: **{f['suggested_weight_kg']:g} kg**" if f.get("suggested_weight_kg") else ""
        st.markdown(f"{FB_ICON.get(f['status'], '•')} **{f['exercise']}** — {f['message']}{extra}")


# ═════════════════════════ Guías y plan ═════════════════════════
def guide(ex_id: int, key: str) -> None:
    """Ficha «Cómo se hace»: qué trabaja, pasos, errores frecuentes y recurso visual si existe."""
    cache = st.session_state.setdefault("_guide", {})
    with st.expander("ℹ️ Cómo se hace"):
        if ex_id not in cache:
            cache[ex_id] = api.get(f"/exercises/{ex_id}/content") or {}
        c = cache[ex_id]
        if not c:
            return
        if c.get("video_url") and c.get("media_type") == "video":
            st.video(c["video_url"])
        elif c.get("image_url"):
            st.image(c["image_url"], width=320, caption=c.get("media_credit"))
        if c.get("description"):
            st.markdown(c["description"])
        if c.get("start_position"):
            st.markdown(f"**Posición inicial:** {c['start_position']}")
        if c.get("instructions"):
            ui.html(ui.steps_list(c["instructions"]))
        if c.get("common_mistakes"):
            st.markdown("**Errores frecuentes**" if c.get("has_detailed_guide") else "**Consejos generales**")
            st.markdown("\n".join(f"- {m}" for m in c["common_mistakes"]))
        if not c.get("has_detailed_guide"):
            st.caption("Aún no hay una guía detallada de este ejercicio; si tienes dudas de técnica, pide ayuda a un entrenador.")


def plan_state(refresh: bool = False) -> dict:
    if refresh or "_plan" not in st.session_state:
        st.session_state["_plan"] = api.get("/plan") or {"has_plan": False}
    return st.session_state["_plan"]


def add_planned(items: list[dict]) -> None:
    """Callback: añade ejercicios del plan a la sesión (se conservan aunque cambies los filtros)."""
    cache = st.session_state.setdefault("_ex_cache", {})
    for it in items:
        cache.setdefault(it["exercise_id"], {"id": it["exercise_id"], "name": it["exercise"], "primary_muscle": it["primary_muscle"],
                                             "secondary_muscles": [], "equipment": it.get("equipment", []), "kind": "strength"})
    cur = st.session_state.get("sel_strength", [])
    st.session_state["sel_strength"] = list(dict.fromkeys(cur + [it["exercise_id"] for it in items]))
    targets = st.session_state.setdefault("_plan_targets", {})
    for it in items:
        targets[it["exercise_id"]] = (it["sets"], it["reps_min"], it["reps_max"])


def replace_planned(old_id: int, new: dict, item: dict) -> None:
    """Callback: sustituye un ejercicio recomendado por otro solo para esta sesión."""
    cache = st.session_state.setdefault("_ex_cache", {})
    cache[new["id"]] = new
    cur = [i for i in st.session_state.get("sel_strength", []) if i != old_id]
    st.session_state["sel_strength"] = list(dict.fromkeys(cur + [new["id"]]))
    st.session_state.setdefault("_plan_targets", {})[new["id"]] = (item["sets"], item["reps_min"], item["reps_max"])


def alternatives(item: dict) -> list[dict]:
    cache = st.session_state.setdefault("_alts", {})
    m = item["primary_muscle"]
    if m not in cache:
        cache[m] = api.get("/exercises", kind="strength", muscles=m) or []
    return [e for e in cache[m] if e["id"] != item["exercise_id"]]


def recommended_section() -> None:
    """«Ejercicios recomendados para hoy»: día del plan, añadir todos o uno a uno, sustituir y ver cómo se hace."""
    plan = plan_state()
    if not plan.get("has_plan"):
        with st.container(border=True):
            st.markdown("**📋 Aún no tienes un plan estructurado**")
            st.caption("Lo crearemos con ejercicios reales de la lista, según tus días disponibles, tu objetivo y tu experiencia.")
            if st.button("✨ Crear mi plan", type="primary", key="plan_create_reg"):
                with st.spinner("Preparando tu plan…"):
                    if api.post("/plan/generate", timeout=api.LONG_TIMEOUT):
                        plan_state(refresh=True)
                        st.rerun()
        return
    days_ = plan["plan"]["days"]
    ids = [d["id"] for d in days_]
    with st.container(border=True):
        top = st.columns([3, 2])
        top[0].markdown("**⭐ Ejercicios recomendados para hoy**")
        day_id = top[1].selectbox("Día del plan", ids, index=ids.index(plan["suggested_day_id"]) if plan.get("suggested_day_id") in ids else 0,
                                  format_func=lambda i: next(d["label"] for d in days_ if d["id"] == i), label_visibility="collapsed", key="plan_day_sel")
        day_ = next(d for d in days_ if d["id"] == day_id)
        st.button("➕ Añadir todos", key="plan_add_all", on_click=add_planned, args=(day_["exercises"],), type="primary")
        sel = set(st.session_state.get("sel_strength", []))
        for it in day_["exercises"]:
            added = it["exercise_id"] in sel
            c = st.columns([5, 1.2, 1])
            c[0].markdown(f"{'✅ ' if added else ''}**{it['exercise']}**  \n<span class='sf-muted'>{it['sets']} series × {it['reps_min']}-{it['reps_max']} reps"
                          + (f" · descanso {it['rest_s']} s" if it.get("rest_s") else "") + "</span>", unsafe_allow_html=True)
            c[1].button("Añadir" if not added else "Añadido", key=f"plan_add_{it['id']}", on_click=add_planned, args=([it],), disabled=added, width="stretch")
            with c[2].popover("🔁", help="Sustituir por otro ejercicio del mismo músculo"):
                alts = alternatives(it)
                pick = st.selectbox("Sustituir por", [a["id"] for a in alts], format_func=lambda i, alts=alts: next(a["name"] for a in alts if a["id"] == i), key=f"alt_{it['id']}")
                st.button("Usar este", key=f"alt_ok_{it['id']}", on_click=replace_planned, args=(it["exercise_id"], next(a for a in alts if a["id"] == pick), it))
            if it.get("notes"):
                st.caption(it["notes"])
        st.caption("Puedes añadir más ejercicios de la lista o registrar una sesión distinta: el plan es una guía, no una obligación.")


# ═════════════════════════ Registrar sesión ═════════════════════════
def last_sets(ex_id: int) -> list[dict]:
    cache = st.session_state.setdefault("_hist", {})
    if ex_id not in cache:
        cache[ex_id] = api.get(f"/exercises/{ex_id}/history", limit=1) or []
    return cache[ex_id]


def last_card(ex_id: int) -> dict:
    cache = st.session_state.setdefault("_last", {})
    if ex_id not in cache:
        cache[ex_id] = api.get(f"/exercises/{ex_id}/last-session") or {"has_history": False}
    return cache[ex_id]


def yes_no(v) -> str:
    return "—" if v is None else ("Sí" if v else "No")


def last_session_card(card: dict) -> None:
    """Tarjeta «Última sesión»: fecha, series, peso máximo, fallo y mejor peso histórico."""
    body = f"<b>Última sesión</b> · {card['date']}"
    chips = []
    if card.get("max_weight_kg"):
        chips.append(ui.chip(f"Peso máx. {card['max_weight_kg']:g} kg", "orange"))
    chips.append(ui.chip(f"{card['total_reps']} reps en total"))
    if card.get("any_failure") is not None:
        chips.append(ui.chip("Llegaste al fallo" if card["any_failure"] else "Sin llegar al fallo", "green"))
    if card.get("best_weight_kg"):
        chips.append(ui.chip(f"Mejor peso: {card['best_weight_kg']:g} kg ({card['best_weight_date']})", "blue"))
    ui.html(body + "<br>" + "".join(chips))
    df = pd.DataFrame([{"Serie": s["set_number"], "Reps": s["reps"],
                        "Peso": f"{s['weight_kg']:g} kg" if s.get("weight_kg") else "Peso corporal",
                        "Fallo": yes_no(s.get("reached_failure"))} for s in card["sets"]])
    st.dataframe(df, hide_index=True, width="stretch")


def exercise_block(ex: dict) -> pd.DataFrame:
    """Tabla editable de series de un ejercicio, precargada con la última vez que lo hiciste (el fallo NO se precarga)."""
    hist = last_sets(ex["id"])
    card = last_card(ex["id"])
    with st.container(border=True):
        ui.html(f"<b>{escape(ex['name'])}</b><br>{muscle_chips(ex)}")
        target = st.session_state.get("_plan_targets", {}).get(ex["id"])
        if target:
            st.caption(f"🎯 Objetivo del plan: {target[0]} series × {target[1]}-{target[2]} repeticiones")
        guide(ex["id"], "blk")
        if card.get("has_history"):
            last_session_card(card)
        key0 = f"df0_{ex['id']}"
        if key0 not in st.session_state:
            rows = ([{"Reps": s["reps"], "Peso (kg)": s["weight_kg"], "Fallo": False} for s in hist[0]["sets"]]
                    if hist else [{"Reps": target[2] if target else 10, "Peso (kg)": None, "Fallo": False} for _ in range(target[0] if target else 3)])
            st.session_state[key0] = pd.DataFrame(rows)
        df = st.data_editor(
            st.session_state[key0], num_rows="dynamic", hide_index=True, key=f"ed_{ex['id']}", width="stretch",
            column_config={
                "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=200, step=1, format="%d"),
                "Peso (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, max_value=1000.0, step=0.5,
                                                           help="Vacío = peso corporal"),
                "Fallo": st.column_config.CheckboxColumn("¿Fallo?", default=False,
                                                         help="Marca si has llegado al fallo muscular en esta serie")})
        # Comparación con la última serie de la última sesión (solo informativa: tú decides qué registrar)
        done = df[df["Reps"].notna()] if len(df) else df
        if card.get("has_history") and len(done) and card["sets"][-1].get("weight_kg") and pd.notna(done.iloc[-1]["Peso (kg)"]):
            before, now = card["sets"][-1]["weight_kg"], float(done.iloc[-1]["Peso (kg)"])
            if now != before:
                st.caption(f"La última vez usaste {before:g} kg en tu última serie. Hoy estás registrando {now:g} kg.")
        return df


def cardio_inputs(cat: str, dur: int) -> dict:
    """Métricas de andar/correr. Devuelve los campos opcionales del payload."""
    running = cat == "running"
    c = st.columns(4 if not running else 3)
    dist = c[0].number_input("Distancia (km)", 0.0, 500.0, 0.0, step=0.1, format="%.2f", key=f"dist_{cat}")
    elev = c[1].number_input("Desnivel positivo (m)", 0, 10000, 0, step=10, key=f"elev_{cat}")
    steps = 0 if running else c[2].number_input("Pasos", 0, 200000, 0, step=100, key=f"steps_{cat}")
    hr = c[-1].number_input("FC media (ppm)", 0, 230, 0, key=f"hr_{cat}", help="Opcional")
    if dist > 0:
        ui.html(ui.cardio_chips({"distance_km": dist, "duration_min": dur, "elevation_gain_m": elev or None,
                                 "steps": steps or None, "avg_hr_bpm": hr if hr >= 30 else None}))
    prof = CARDIO_MUSCLES.get(cat)
    if prof:
        st.caption("Músculos implicados: " + ", ".join(MUSCLES[m] for m in prof["primary"]) + " (principales) y "
                   + ", ".join(MUSCLES[m] for m in prof["secondary"]) + " (secundarios). Se encienden en el mapa muscular según el "
                   "tiempo y el ritmo. La IA estima las calorías con la distancia, el ritmo y el desnivel.")
    return {"distance_km": dist or None, "elevation_gain_m": float(elev) or None, "steps": int(steps) or None,
            "avg_hr_bpm": int(hr) if hr >= 30 else None}


@st.cache_data(show_spinner=False)
def _icon(muscle: str, dark: bool) -> str:
    return muscle_icon(muscle, dark)


def muscle_picker(cat: str) -> list[str]:
    """Selector de grupos musculares por región (tren superior / inferior), con un pictograma por músculo."""
    selected: list[str] = []
    dark = ui.is_dark()

    def clear() -> None:
        for k in [k for k in st.session_state if k.startswith(f"mg_{cat}_")]:
            st.session_state[k] = False

    with st.expander("🎯 Grupos musculares", expanded=True):
        for region in REGIONS.values():
            st.markdown(f"**{region['icon']} {region['label']}**")
            muscles = region["muscles"]
            for i in range(0, len(muscles), 6):
                for col, m in zip(st.columns(6), muscles[i:i + 6]):
                    with col:
                        st.image(_icon(m, dark), width=64)
                        if st.checkbox(MUSCLES[m], key=f"mg_{cat}_{m}"):
                            selected.append(m)
        st.button("Quitar selección", key=f"mg_clear_{cat}", on_click=clear, disabled=not selected)
    return selected


def equipment_picker(cat: str) -> list[str]:
    return st.pills("🧰 Equipamiento (ejercicios que usan alguno de estos)", list(EQUIP), selection_mode="multi", key=f"eq_{cat}",
                    format_func=lambda e: f"{EQUIP_ICON.get(e, '')} {EQUIP[e]}") or []


def equipment_icons(ex: dict) -> str:
    return " ".join(EQUIP_ICON.get(e, "") for e in ex.get("equipment", []))


def sets_from(ex_id: int, df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        if pd.notna(r["Reps"]) and r["Reps"] >= 1:
            out.append({"exercise_id": ex_id, "reps": int(r["Reps"]),
                        "weight_kg": float(r["Peso (kg)"]) if pd.notna(r["Peso (kg)"]) and r["Peso (kg)"] > 0 else None,
                        "reached_failure": bool(r["Fallo"]) if pd.notna(r["Fallo"]) else None})
    return out


with tab_reg:
    if saved := st.session_state.pop("saved_workout", None):
        worked = sorted({MUSCLES.get(e["primary_muscle"], e["primary_muscle"]) for e in saved["exercises"]})
        if saved.get("category") in CARDIO_MUSCLES:
            worked = [MUSCLES[m] for m in CARDIO_MUSCLES[saved["category"]]["primary"]]
        body = f"<h4>✅ Sesión guardada: {escape(saved['kind'])}</h4>"
        if saved.get("kcal_burned") is not None:
            origin = "estimadas por la IA" if saved.get("kcal_source") == "llm" else "introducidas por ti"
            body += f"<div class='sf-big'>🔥 {saved['kcal_burned']:.0f} kcal <span class='sf-muted'>{origin}</span></div>"
            if saved.get("intensity"):
                body += ui.chip(INTENSITY.get(saved["intensity"], saved["intensity"]), "orange") + ui.chip(f"MET {saved['met']:g}")
        if ui.cardio_chips(saved):
            body += f"<div>{ui.cardio_chips(saved)}</div>"
        if saved.get("kcal_note"):
            body += f"<div class='sf-muted'>{escape(saved['kcal_note'])}</div>"
        if worked:
            body += f"<div style='margin-top:6px'>Músculos trabajados: {ui.chips(worked, 'green')}</div>"
        ui.card(body)
        show_feedback(saved.get("feedback") or [])

    # ── Nivel 1: tipo de sesión ──
    type_key = st.segmented_control("Tipo de sesión", list(TYPES), default="strength", key="w_type",
                                    format_func=lambda t: f"{TYPES[t]['icon']} {TYPES[t]['label']}") or "strength"
    subs = TYPES[type_key]["categories"]
    cat = subs[0]
    if len(subs) > 1:       # Cardio -> Andar / Correr / Otros deportes
        cat = st.segmented_control("Cardio", subs, default=subs[0], key=f"w_sub_{type_key}",
                                   format_func=lambda c: f"{CAT_ICON.get(c, '')} {CATS[c]}") or subs[0]

    c1, c2 = st.columns(2)
    d = c1.date_input("Fecha", value=today, max_value=today, key="w_date")
    dur = c2.number_input("Duración total (min)", 5, 600, 60, step=5, key="w_dur")

    # ── Nivel 2: depende del tipo ──
    selected: list[int] = []
    edited: dict[int, pd.DataFrame] = {}
    metrics: dict = {}
    default_title = CATS[cat]
    if cat in ("walking", "running"):
        metrics = cardio_inputs(cat, int(dur))
    elif cat == "sport":
        sport = st.selectbox("Deporte", list(SPORTS), format_func=lambda k: f"{SPORT_ICON.get(k, '')} {SPORTS[k]}", key="w_sport")
        default_title = (st.text_input("¿Qué deporte?", key="w_sport_other") or "Deporte").strip() if sport == "other" else SPORTS[sport]
        hr = st.number_input("FC media (ppm, opcional)", 0, 230, 0, key="hr_sport")
        metrics = {"avg_hr_bpm": int(hr) if hr >= 30 else None}
        st.caption("La IA estima las calorías con el deporte y la duración. (No se enciende el mapa muscular: no hay un perfil muscular fiable para cada deporte.)")
    else:   # fuerza / cuerpo entero / estiramientos
        if cat == "strength":
            recommended_section()
        chosen_muscles = muscle_picker(cat) if cat in ("strength", "stretching") else []
        chosen_equip = equipment_picker(cat) if cat in ("strength", "full_body") else []
        text = st.text_input("🔎 Buscar ejercicio", key=f"q_{cat}", placeholder="p. ej. sentadilla, curl, estiramiento…")
        params = {"kind": cat}
        if chosen_muscles:
            params["muscles"] = ",".join(chosen_muscles)
        if chosen_equip:
            params["equipment"] = ",".join(chosen_equip)
        if text.strip():
            params["q"] = text.strip()
        cache = st.session_state.setdefault("_ex_cache", {})
        found = api.get("/exercises", **params) or []
        cache.update({e["id"]: e for e in found})
        keep = [i for i in st.session_state.get(f"sel_{cat}", []) if i in cache]     # lo ya elegido no se pierde al cambiar filtros
        options = list(dict.fromkeys([e["id"] for e in found] + keep))
        st.caption(f"{len(found)} ejercicios" + (" con estos filtros" if chosen_muscles or chosen_equip or text.strip() else " disponibles"))
        selected = st.multiselect(
            "Ejercicios de la sesión", options, key=f"sel_{cat}", placeholder="Elige uno o varios ejercicios",
            format_func=lambda i: f"{cache[i]['name']} · {MUSCLES.get(cache[i]['primary_muscle'], '')} {equipment_icons(cache[i])}")
        if cat == "stretching":
            if selected:
                ui.html("".join(ui.chip(cache[i]["name"].replace("Estiramiento de ", ""), "green") for i in selected))
        else:
            for ex_id in selected:
                edited[ex_id] = exercise_block(cache[ex_id])
        if selected:   # título sugerido a partir de los músculos trabajados
            worked = list(dict.fromkeys(MUSCLES.get(cache[i]["primary_muscle"], "") for i in selected))[:3]
            default_title = f"{CATS[cat]}: {', '.join(worked)}"

        with st.expander("➕ Crear un ejercicio que no está en la lista"):
            with st.form("new_exercise", clear_on_submit=True):
                n1, n2 = st.columns(2)
                name = n1.text_input("Nombre")
                primary = n2.selectbox("Músculo principal", list(MUSCLES), format_func=lambda m: MUSCLES[m])
                secondary = st.multiselect("Músculos secundarios", list(MUSCLES), format_func=lambda m: MUSCLES[m])
                n3, n4 = st.columns(2)
                kind_new = n3.selectbox("Tipo", list(opts.get("exercise_kind", {"strength": "Fuerza"})), index=0, format_func=lambda k: opts.get("exercise_kind", {}).get(k, k))
                equip = n4.multiselect("Equipamiento", list(EQUIP), default=["none"], format_func=lambda e: f"{EQUIP_ICON.get(e, '')} {EQUIP[e]}")
                if st.form_submit_button("Crear ejercicio") and name.strip():
                    if api.post("/exercises", json={"name": name, "kind": kind_new, "primary_muscle": primary,
                                                    "secondary_muscles": secondary, "equipment": equip or ["none"]}):
                        st.success("Creado. Ya aparece en la lista con los filtros que coincidan.")

    title = st.text_input("Título de la sesión", value=default_title, key=f"title_{cat}_{abs(hash(default_title)) % 10**6}")
    notes = st.text_area("Notas (opcional)", key=f"notes_{cat}", height=70)
    mode = st.radio("Calorías quemadas", ["ia", "manual", "none"], horizontal=True,
                    format_func={"ia": "🤖 Estimar con IA", "manual": "✍️ Introducir a mano", "none": "No registrar"}.get,
                    help="La IA estima la intensidad por el tipo de sesión, la duración y las series; las kcal se calculan "
                         "con tu peso corporal (MET × kg × horas).")
    manual_kcal = st.number_input("Calorías (kcal)", 0, 10000, 300, step=10) if mode == "manual" else None

    if st.button("💾 Guardar sesión", type="primary"):
        if cat == "stretching":
            sets = [{"exercise_id": i, "reps": 1} for i in selected]          # un estiramiento realizado = 1 serie
        else:
            sets = [s_ for ex_id in selected for s_ in sets_from(ex_id, edited[ex_id])]
        payload = {"performed_on": d.isoformat(), "kind": title.strip() or CATS[cat], "category": cat,
                   "duration_min": int(dur), "notes": notes.strip() or None, "sets": sets, "estimate_calories": mode == "ia"}
        payload.update(metrics)
        if mode == "manual":
            payload["kcal_burned"] = manual_kcal
        with st.spinner("Guardando" + (" y estimando calorías con IA…" if mode == "ia" else "…")):
            res = api.post("/workouts", json=payload, timeout=api.LONG_TIMEOUT)
        if res:
            st.session_state.update(saved_workout=res, reset_form=True)
            st.session_state.pop("_hist", None)
            st.session_state.pop("_last", None)
            st.session_state.pop("_plan_targets", None)
            plan_state(refresh=True)        # la sesión guardada hace avanzar el día sugerido
            st.rerun()

# ═════════════════════════ Historial ═════════════════════════
with tab_hist:
    workouts = api.get("/workouts", days=90) or []
    if not workouts:
        st.info("Aún no hay sesiones registradas en los últimos 90 días.")
    else:
        present = [c for c in CATS if any(w["category"] == c for w in workouts)]
        flt = st.pills("Filtrar por tipo", present, format_func=lambda c: f"{CAT_ICON.get(c, '')} {CATS[c]}", selection_mode="multi", key="hist_filter")
        workouts = [w for w in workouts if not flt or w["category"] in flt]
    for w in workouts:
        kcal = f" · 🔥 {w['kcal_burned']:.0f} kcal" if w["kcal_burned"] else ""
        with st.expander(f"{w['performed_on']} · {w['kind']} · {w['duration_min']} min{kcal}"):
            tags = ui.chip(f"{CAT_ICON.get(w['category'], '')} {CATS.get(w['category'], 'Sesión')}", "blue")
            if w["intensity"]:
                tags += ui.chip(INTENSITY.get(w["intensity"], w["intensity"]), "orange")
            if w["kcal_source"]:
                tags += ui.chip("kcal por IA" if w["kcal_source"] == "llm" else "kcal manuales", "green")
            if w["met"]:
                tags += ui.chip(f"MET {w['met']:g}")
            ui.html(tags)
            if ui.cardio_chips(w):
                ui.html(ui.cardio_chips(w))
            if w["kcal_note"]:
                st.caption(w["kcal_note"])
            if w["notes"]:
                st.write(w["notes"])
            for ex in w["exercises"]:
                st.markdown(f"**{ex['exercise']}** · {MUSCLES.get(ex['primary_muscle'], '')}")
                df = pd.DataFrame(ex["sets"]).rename(columns={"set_number": "Serie", "reps": "Reps", "weight_kg": "Peso (kg)",
                                                              "reached_failure": "Fallo", "rpe": "RPE (antiguo)"})
                df["Fallo"] = df["Fallo"].map(yes_no)
                if df["RPE (antiguo)"].isna().all():      # el RPE solo se muestra en sesiones antiguas que lo tienen
                    df = df.drop(columns="RPE (antiguo)")
                st.dataframe(df, hide_index=True, width="stretch")
            if w["exercises"] and st.toggle("💡 Ver recomendaciones de esta sesión", key=f"fb_{w['id']}"):
                show_feedback((api.get(f"/workouts/{w['id']}") or {}).get("feedback") or [])
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
def strength_progress() -> None:
    used = api.get("/exercises", used="true") or []
    if not used:
        st.info("Registra series en algún ejercicio para ver su progresión.")
        return
    by_used = {e["id"]: e for e in used}
    ex_id = st.selectbox("Ejercicio", list(by_used), format_func=lambda i: by_used[i]["name"])
    prog = api.get(f"/exercises/{ex_id}/progress") or []
    if not prog:
        return
    df = pd.DataFrame(prog).assign(date=lambda x: pd.to_datetime(x["date"]))
    m = st.columns(3)
    best = df["est_1rm_kg"].max()
    m[0].metric("Mejor 1RM estimado", f"{best:.1f} kg" if pd.notna(best) else "—",
                help="Fórmula de Epley, solo con series de 1 a 12 repeticiones con peso.")
    m[1].metric("Peso máximo", f"{df['best_weight_kg'].max():.1f} kg" if df["best_weight_kg"].notna().any() else "—")
    m[2].metric("Sesiones", len(df))
    if df["best_weight_kg"].notna().any():
        st.markdown("**Peso máximo y 1RM estimado por sesión (kg)**")
        long = df.melt(id_vars="date", value_vars=["best_weight_kg", "est_1rm_kg"], var_name="Serie", value_name="kg").dropna()
        long["Serie"] = long["Serie"].map({"best_weight_kg": "Peso máx.", "est_1rm_kg": "1RM estimado"})
        st.altair_chart(charts._finish(charts.alt.Chart(long).mark_line(strokeWidth=2.5, point=charts.alt.OverlayMarkDef(size=55, filled=True)).encode(
            x=charts._x(), y=charts.alt.Y("kg:Q", scale=charts.alt.Scale(zero=False), title="kg"),
            color=charts.alt.Color("Serie:N", scale=charts.alt.Scale(range=[ui.ORANGE, ui.GREEN]), legend=charts.alt.Legend(orient="bottom", title=None)),
            tooltip=[charts.alt.Tooltip("date:T", title="Día", format="%d %b %Y"), "Serie:N", charts.alt.Tooltip("kg:Q", format=".1f")])), width="stretch")
    st.markdown("**Volumen total por sesión (kg × reps)**")
    st.altair_chart(charts.simple_bars(df, "date", "volume_kg", "kg", ui.PURPLE), width="stretch")


def distance_progress(kind: str) -> None:
    running = kind == "running"
    sessions = [w for w in (api.get("/workouts", days=365) or []) if w["category"] == kind and w["distance_km"]]
    if not sessions:
        st.info("Registra sesiones de " + ("correr" if running else "andar") + " con distancia para ver tu evolución.")
        return
    df = pd.DataFrame(sessions).assign(date=lambda x: pd.to_datetime(x["performed_on"])).sort_values("date")
    df["pace"] = df["pace_min_km"]
    df["label"] = df["pace"].apply(ui.fmt_pace) + " /km"
    k = st.columns(4)
    k[0].metric("Sesiones", len(df))
    k[1].metric("Distancia total", f"{df['distance_km'].sum():.1f} km")
    if running:
        k[2].metric("Mejor ritmo", f"{ui.fmt_pace(df['pace'].min())} /km")
        k[3].metric("Sesión más larga", f"{df['distance_km'].max():.1f} km")
    else:
        k[2].metric("Velocidad media", f"{df['speed_kmh'].mean():.1f} km/h")
        k[3].metric("Pasos totales", f"{int(df['steps'].fillna(0).sum()):,}".replace(",", ".") if df["steps"].notna().any() else "—")
    st.markdown("**Ritmo por sesión** (arriba = más rápido)" if running else "**Velocidad media por sesión**")
    st.altair_chart(charts.pace_chart(df) if running else charts.speed_chart(df), width="stretch")
    left, right = st.columns(2)
    weekly = df.groupby(pd.Grouper(key="date", freq="W-MON", label="left", closed="left"))["distance_km"].sum().reset_index()
    left.markdown("**Kilómetros por semana**")
    left.altair_chart(charts.simple_bars(weekly, "date", "distance_km", "km", ui.BLUE, tooltip_y_fmt=".1f", size=30), width="stretch")
    if df["elevation_gain_m"].notna().any():
        right.markdown("**Desnivel positivo por sesión (m)**")
        right.altair_chart(charts.simple_bars(df.dropna(subset=["elevation_gain_m"]), "date", "elevation_gain_m", "m", ui.ORANGE), width="stretch")
    elif not running and df["steps"].notna().any():
        right.markdown("**Pasos por sesión**")
        right.altair_chart(charts.simple_bars(df.dropna(subset=["steps"]), "date", "steps", "pasos", ui.PURPLE), width="stretch")


with tab_prog:
    kind = st.radio("Ver", ["strength", "running", "walking"], horizontal=True, label_visibility="collapsed",
                    format_func={"strength": "🏋️ Fuerza", "running": "🏃 Correr", "walking": "🚶 Andar"}.get)
    if kind == "strength":
        strength_progress()
    else:
        distance_progress(kind)

# ═════════════════════════ Músculos ═════════════════════════
with tab_muscles:
    days = st.radio("Periodo", [7, 14, 30], horizontal=True, format_func=lambda d: f"Últimos {d} días")
    data = api.get("/training/muscles", days=days)
    if data:
        weekly = {m: v["sets"] * 7 / days for m, v in data["muscles"].items()}   # media semanal comparable entre periodos
        left, right = st.columns([3, 2])
        with left:
            st.image(body_svg(weekly, dark=ui.is_dark()), width="stretch")
        with right:
            st.caption(f"{data['sessions']} sesiones con series o carga registrada. Color = series ponderadas **por semana** "
                       "(músculo principal = 1, secundarios = 0,5). Andar y correr suman **series equivalentes** estimadas con el tiempo "
                       "y el ritmo. Referencia habitual para hipertrofia: 10-20 series/semana (orientativo).")
            rows = sorted(((MUSCLES[m], w, data["muscles"][m]["strength_sets"] * 7 / days, data["muscles"][m]["cardio_sets"] * 7 / days,
                            data["muscles"][m]["volume_kg"]) for m, w in weekly.items() if w > 0), key=lambda r: -r[1])
            if rows:
                df = pd.DataFrame(rows, columns=["Músculo", "Series/semana", "Fuerza", "Andar/correr", "Volumen (kg)"]).round(1)
                st.bar_chart(df.set_index("Músculo")[["Fuerza", "Andar/correr"]], horizontal=True, color=[ui.ORANGE, ui.GREEN])
            idle = [MUSCLES[m] for m, w in weekly.items() if w == 0]
            if idle:
                st.markdown("**Sin trabajar en este periodo**")
                ui.html(ui.chips(idle))
        if rows:
            with st.expander("Detalle por músculo"):
                st.dataframe(df, hide_index=True, width="stretch")


def plan_ui(plan: dict, targets: dict) -> None:
    """Plan estructurado: días con ejercicios editables (series, repeticiones, descanso) + plan antiguo en texto."""
    if not plan.get("has_plan"):
        ui.empty("📋", "Todavía no tienes un plan estructurado", "Se crea con ejercicios reales de la lista a partir de tu perfil.")
        if st.button("✨ Crear mi plan", type="primary", key="plan_create_tab"):
            with st.spinner("Preparando tu plan…"):
                if api.post("/plan/generate", timeout=api.LONG_TIMEOUT):
                    st.rerun()
    else:
        p = plan["plan"]
        origin = {"llm": "propuesto por la IA", "auto": "generado por reglas", "manual": "editado por ti"}.get(p["source"], "")
        ui.section(p["name"], f"Plan {origin}. Edita series, repeticiones y descansos; los ejercicios siempre son de la lista.", "📋")
        for d in p["days"]:
            star = " ⭐ (siguiente)" if d["id"] == plan.get("suggested_day_id") else ""
            with st.expander(f"{d['label']}{star}", expanded=d["id"] == plan.get("suggested_day_id")):
                ui.html(ui.chips([MUSCLES.get(m, m) for m in d["muscle_focus"]], "orange"))
                df0 = pd.DataFrame([{"ID": e["exercise_id"], "Ejercicio": e["exercise"], "Series": e["sets"], "Reps mín": e["reps_min"],
                                     "Reps máx": e["reps_max"], "Descanso (s)": e["rest_s"] or 0} for e in d["exercises"]])
                df = st.data_editor(df0, hide_index=True, num_rows="dynamic", key=f"pe_{d['id']}_{len(d['exercises'])}", width="stretch", disabled=["Ejercicio"],
                                    column_config={"ID": None, "Series": st.column_config.NumberColumn(min_value=1, max_value=8, step=1),
                                                   "Reps mín": st.column_config.NumberColumn(min_value=1, max_value=50, step=1),
                                                   "Reps máx": st.column_config.NumberColumn(min_value=1, max_value=50, step=1),
                                                   "Descanso (s)": st.column_config.NumberColumn(min_value=0, max_value=600, step=15)})
                for e in d["exercises"]:
                    guide(e["exercise_id"], f"pl{d['id']}")
                add = st.text_input("Añadir ejercicio al día", key=f"pa_q_{d['id']}", placeholder="Busca por nombre…")
                found = (api.get("/exercises", kind="strength", q=add.strip()) or [])[:15] if add.strip() else []
                new_id = st.selectbox("Resultado", [None] + [f["id"] for f in found], key=f"pa_s_{d['id']}",
                                      format_func=lambda i, found=found: "—" if i is None else next(f["name"] for f in found if f["id"] == i), disabled=not found)
                b = st.columns([1, 1, 3])
                if b[0].button("💾 Guardar día", key=f"ps_{d['id']}", type="primary"):
                    rows = [r for r in df.itertuples() if pd.notna(r.ID)]
                    exs = [{"exercise_id": int(r.ID), "sets": int(r.Series), "reps_min": int(r._4), "reps_max": int(r._5), "rest_s": int(r._6) or None} for r in rows]
                    if new_id and new_id not in [x["exercise_id"] for x in exs]:
                        exs.append({"exercise_id": new_id, "sets": 3, "reps_min": 8, "reps_max": 12, "rest_s": 90})
                    if api.put(f"/plan/days/{d['id']}", {"exercises": exs}):
                        st.toast("Día guardado", icon="💾")
                        st.rerun()
        if st.button("🔄 Regenerar plan", key="plan_regen", help="Crea un plan nuevo; el anterior se conserva en el histórico"):
            with st.spinner("Preparando tu plan…"):
                if api.post("/plan/generate", timeout=api.LONG_TIMEOUT):
                    st.rerun()
    if plan.get("legacy_markdown") or targets.get("training_plan"):
        with st.expander("📝 Texto del plan original"):
            st.markdown(plan.get("legacy_markdown") or targets.get("training_plan"))


# ═════════════════════════ Plan y peso ═════════════════════════
with tab_plan:
    targets = api.get("/targets") or {"workouts_per_week": 3}
    recent = api.get("/workouts", days=14) or []
    monday = today - timedelta(days=today.weekday())
    this_week = [w for w in recent if date.fromisoformat(w["performed_on"]) >= monday]
    goal = max(targets["workouts_per_week"], 1)
    st.metric("Sesiones esta semana", f"{len(this_week)} / {targets['workouts_per_week']}")
    st.progress(min(len(this_week) / goal, 1.0))
    plan_ui(plan_state(refresh=True), targets)
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


# ════════════════════════ Animaciones 3D ════════════════════════
with tab_3d:
    st.markdown("### 🎞️ Biblioteca de movimientos en 3D")
    st.caption("20 ejercicios animados en bucle. Selecciona el movimiento, pausa la repetición o arrastra la escena para cambiar el ángulo. Son demostraciones visuales orientativas; ajusta la técnica a tu movilidad y carga.")
    animation_file = Path(__file__).resolve().parents[1] / "exercise_animations_3d.html"
    if animation_file.is_file():
        st.components.v1.html(animation_file.read_text(encoding="utf-8"), height=650, scrolling=False)
    else:
        st.error("No se encuentra el visor 3D. Comprueba que frontend/exercise_animations_3d.html está incluido en el despliegue.")
