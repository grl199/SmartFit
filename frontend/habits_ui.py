"""Tarjetas rápidas de hábitos (agua, pasos, ánimo) reutilizadas en Inicio y en Bienestar."""
from datetime import date

import streamlit as st

import api
import ui

WATER_QUICK = (150, 250, 330, 500)


def fmt_ml(ml: int) -> str:
    return f"{ml / 1000:.2f}".rstrip("0").rstrip(".") + " L" if ml >= 1000 else f"{ml} ml"


def water_card(key: str = "h", compact: bool = False) -> None:
    """Agua de hoy con barra de progreso y botones de un clic."""
    s = api.get("/water/summary", days=7)
    if not s:
        return
    pct = s["today_pct"]
    ui.html(ui.meter("💧", "Agua", f"{fmt_ml(s['today_ml'])} de {fmt_ml(s['goal_ml'])}", pct, ui.BLUE if pct < 100 else ui.GREEN,
                     "¡Objetivo cumplido! 🎉" if pct >= 100 else f"{pct} %"))
    cols = st.columns(len(WATER_QUICK) if not compact else 2)
    for col, ml in zip(cols, WATER_QUICK if not compact else WATER_QUICK[1::2]):
        if col.button(f"+{ml}", key=f"{key}_w{ml}", width="stretch", help=f"Añadir {ml} ml"):
            if api.post("/water", json={"quantity_ml": ml, "source": "quick"}):
                st.rerun()
    with st.popover("Otra cantidad", width="stretch"):
        ml = st.number_input("ml", 10, 5000, 200, step=10, key=f"{key}_wc")
        if st.button("Añadir", key=f"{key}_wca", type="primary"):
            if api.post("/water", json={"quantity_ml": int(ml), "source": "manual"}):
                st.rerun()


def steps_card(key: str = "h") -> None:
    s = api.get("/activity/summary", days=7)
    if not s:
        return
    steps = s["today_steps"]
    if steps is None:
        ui.html(ui.meter("👣", "Pasos", "Sin datos hoy", None, ui.PURPLE, f"Objetivo {s['goal']:,}".replace(",", ".")))
    else:
        pct = s["today_pct"] or 0
        ui.html(ui.meter("👣", "Pasos", f"{steps:,}".replace(",", "."), pct, ui.PURPLE if pct < 100 else ui.GREEN,
                         "¡Objetivo cumplido! 🎉" if pct >= 100 else f"{pct} % de {s['goal']:,}".replace(",", ".")))
    with st.popover("Registrar pasos de hoy", width="stretch"):
        v = st.number_input("Pasos", 0, 200000, int(steps or 0), step=500, key=f"{key}_st")
        if st.button("Guardar", key=f"{key}_sts", type="primary") and api.put("/activity", {"steps": int(v)}):
            st.rerun()


def mood_card(today: date, key: str = "h") -> None:
    """Check-in de un toque: elige tu estado de ánimo; los detalles (energía, estrés, notas) están en Bienestar."""
    rows = api.get("/checkins", days=1) or []
    mine = next((r for r in rows if r["date"] == today.isoformat()), None)
    if mine:
        emoji, label = ui.MOODS[mine["mood"]]
        extra = " · ".join(x for x in (f"Energía {mine['energy_level']}/5" if mine.get("energy_level") else "",
                                        f"Estrés {mine['stress_level']}/5" if mine.get("stress_level") else "") if x)
        ui.html(f'<div class="sf-meter"><div class="h"><span>🙂 Cómo estás hoy</span><span class="sf-muted">{ui.escape(extra)}</span></div>'
                f'<div class="v">{emoji} {label}</div></div>')
        st.page_link("pages/6_Bienestar.py", label="Añadir energía, estrés o una nota", icon="✏️")
        return
    ui.html(ui.meter("🙂", "¿Cómo te encuentras hoy?", "Elige uno", None))
    cols = st.columns(5)
    for col, (n, (emoji, label)) in zip(cols, ui.MOODS.items()):
        if col.button(emoji, key=f"{key}_m{n}", width="stretch", help=label):
            if api.put(f"/checkins/{today.isoformat()}", {"mood": n}):
                st.rerun()
