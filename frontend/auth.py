"""Puerta de entrada: login / registro -> onboarding obligatorio -> app."""
from datetime import date

import streamlit as st

import api

MIN_AGE = 18


def _select(label, opts: dict, key: str, **kw):
    return st.selectbox(label, list(opts), format_func=lambda c: opts[c], key=key, **kw)


def _auth_forms() -> None:
    st.title("🏋️ SmartFit")
    if notice := st.session_state.pop("login_notice", None):
        st.warning(notice)
    login, register = st.tabs(["Iniciar sesión", "Crear cuenta"])
    with login, st.form("login"):
        name = st.text_input("Usuario")
        pw = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            data, err = api.auth_request("/auth/login", name, pw)
            if err:
                st.error(err)
            else:
                st.session_state.update(token=data["access_token"], me=data["user"])
                st.rerun()
    with register, st.form("register"):
        name = st.text_input("Nombre de usuario (3-40 caracteres)")
        pw = st.text_input("Contraseña (mínimo 8 caracteres)", type="password")
        pw2 = st.text_input("Repite la contraseña", type="password")
        if st.form_submit_button("Crear cuenta", type="primary"):
            if pw != pw2:
                st.error("Las contraseñas no coinciden")
            else:
                data, err = api.auth_request("/auth/register", name, pw)
                if err:
                    st.error(err)
                else:
                    st.session_state.update(token=data["access_token"], me=data["user"])
                    st.rerun()


def _onboarding(me: dict) -> None:
    opts = api.options()
    if not opts:
        st.error("No se pudieron cargar las opciones del formulario. ¿Está el backend en marcha?")
        st.stop()
    st.title(f"👋 Bienvenido, {me['name']}")
    st.write("Cuéntanos sobre ti. Con estos datos la IA calculará tus **objetivos de nutrición** y un **plan de entrenamiento**. "
             "Este paso es obligatorio y podrás editarlo después.")
    with st.form("onboarding"):
        sex = _select("Sexo (para el cálculo metabólico)", opts["sex"], "ob_sex")
        c1, c2, c3 = st.columns(3)
        birth = c1.date_input("Fecha de nacimiento", value=date(1990, 1, 1), min_value=date(1920, 1, 1),
                              max_value=date(date.today().year - MIN_AGE, date.today().month, date.today().day))
        height = c2.number_input("Altura (cm)", 100.0, 250.0, 170.0, step=1.0)
        weight = c3.number_input("Peso (kg)", 30.0, 300.0, 70.0, step=0.5)
        goal = _select("Objetivo principal", opts["goal"], "ob_goal")
        activity = _select("Nivel de actividad diaria", opts["activity_level"], "ob_act", index=1)
        exp = _select("Experiencia entrenando", opts["experience_level"], "ob_exp")
        days = st.slider("Días a la semana que puedes entrenar", 1, 7, 3)
        restr = st.text_input("Alergias / restricciones alimentarias (opcional)", placeholder="p. ej. sin lactosa, vegetariano")
        notes = st.text_area("Algo más que el asistente deba saber (opcional)", placeholder="Lesiones, horarios, preferencias…")
        st.caption("La app está pensada para adultos sanos; no sustituye el consejo de un profesional sanitario.")
        if st.form_submit_button("✨ Generar mis objetivos con IA", type="primary"):
            payload = dict(sex=sex, birth_date=birth.isoformat(), height_cm=height, weight_kg=weight, activity_level=activity,
                           goal=goal, experience_level=exp, available_training_days=days,
                           dietary_restrictions=restr or None, context_notes=notes or None)
            with st.spinner("La IA está calculando tus objetivos… puede tardar hasta un minuto."):
                res = api.post("/onboarding", json=payload, timeout=api.LONG_TIMEOUT)
            if res:
                st.session_state.onboarding_result = res
                st.rerun()


def show_targets(res: dict) -> None:
    t = res["targets"]
    cols = st.columns(5)
    for col, (label, key, unit) in zip(cols, [("Calorías", "kcal", "kcal"), ("Proteína", "protein_g", "g"), ("Hidratos", "carbs_g", "g"),
                                              ("Grasa", "fat_g", "g"), ("Fibra", "fiber_g", "g")]):
        col.metric(label, f"{t[key]:.0f} {unit}")
    st.caption(f"Metabolismo basal estimado: {res['bmr']:.0f} kcal · Gasto total diario: {res['tdee']:.0f} kcal · "
               f"Entrenos recomendados: {t['workouts_per_week']}/semana")
    if t.get("rationale"):
        st.info(t["rationale"])
    if t.get("training_plan"):
        st.markdown("**Plan de entrenamiento**")
        st.markdown(t["training_plan"])


def _result_screen(res: dict) -> None:
    st.title("✅ Tus objetivos están listos")
    show_targets(res)
    if st.button("Entrar a la app", type="primary"):
        st.session_state.pop("onboarding_result", None)
        st.session_state.pop("me", None)  # se vuelve a pedir: ya estará completado
        st.rerun()


def require_login() -> dict:
    """Llamar al principio de CADA página. Detiene la ejecución si no hay sesión o falta el onboarding."""
    if not st.session_state.get("token"):
        _auth_forms()
        st.stop()
    me = st.session_state.get("me") or api.get("/auth/me")
    if not me:
        st.stop()
    st.session_state.me = me
    if st.session_state.get("onboarding_result"):
        _result_screen(st.session_state.onboarding_result)
        st.stop()
    if not me["onboarding_completed"]:
        _onboarding(me)
        st.stop()
    with st.sidebar:
        st.caption(f"👤 {me['name']}")
        if st.button("Cerrar sesión", key="logout"):
            api.logout()
            st.rerun()
    return me
