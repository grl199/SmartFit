"""Sistema de diseño: CSS adaptable a modo claro/oscuro y componentes HTML pequeños.
Todo texto dinámico (nombres, marcas, ingredientes: datos de terceros) se escapa antes de insertarse."""
import math
from html import escape

import streamlit as st

GREEN, ORANGE, RED, BLUE, PURPLE = "#16a34a", "#f97316", "#dc2626", "#2563eb", "#7c3aed"
NUTRISCORE_COLORS = {"a": "#038141", "b": "#85bb2f", "c": "#fecb02", "d": "#ee8100", "e": "#e63e11"}
NOVA_LABELS = {1: "Sin procesar", 2: "Ingrediente culinario", 3: "Procesado", 4: "Ultraprocesado"}
NOVA_COLORS = {1: "#038141", 2: "#85bb2f", 3: "#ee8100", 4: "#e63e11"}
MEAL_ICONS = {"breakfast": "🍳", "lunch": "🍽️", "snack": "🍎", "dinner": "🌙"}

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1100px;}
h1 {font-weight: 750; letter-spacing: -.02em;}
.sf-card {border: 1px solid rgba(128,128,128,.28); border-radius: 14px; padding: 14px 16px;
          background: rgba(128,128,128,.06); margin-bottom: 10px;}
.sf-card h4 {margin: 0 0 6px 0; font-size: 1rem;}
.sf-muted {opacity: .65; font-size: .85rem;}
.sf-chip {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; margin: 2px 4px 2px 0;
          background: rgba(128,128,128,.16); white-space: nowrap;}
.sf-chip.green {background: rgba(22,163,74,.18);} .sf-chip.orange {background: rgba(249,115,22,.2);}
.sf-chip.red {background: rgba(220,38,38,.18);} .sf-chip.blue {background: rgba(37,99,235,.18);}
.sf-chip.purple {background: rgba(124,58,237,.18);}
.sf-bar {height: 10px; border-radius: 6px; background: rgba(128,128,128,.22); overflow: hidden; margin: 4px 0 10px 0;}
.sf-bar > span {display: block; height: 100%; border-radius: 6px;}
.sf-row {display: flex; justify-content: space-between; font-size: .9rem;}
.sf-ns {display: inline-flex; gap: 2px; align-items: center; vertical-align: middle;}
.sf-ns b {display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center; font-size: .72rem;
          color: #fff; border-radius: 4px; opacity: .35;}
.sf-ns b.on {opacity: 1; width: 26px; height: 26px; line-height: 26px; font-size: .95rem; border-radius: 6px;
             box-shadow: 0 1px 4px rgba(0,0,0,.35);}
.sf-img {width: 84px; height: 84px; object-fit: contain; border-radius: 10px; background: #fff; border: 1px solid rgba(128,128,128,.25);}
.sf-food {display: flex; gap: 14px; align-items: center;}
.sf-big {font-size: 1.35rem; font-weight: 700;}
div[data-testid="stMetricValue"] {font-size: 1.5rem;}
button[kind="secondary"] {border-radius: 999px;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text: str, color: str = "") -> str:
    return f'<span class="sf-chip {color}">{escape(str(text))}</span>'


def chips(items, color: str = "") -> str:
    return "".join(chip(i, color) for i in items)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def card(inner: str) -> None:
    html(f'<div class="sf-card">{inner}</div>')


def ring(value: float, goal: float, unit: str = "kcal", size: int = 190) -> str:
    """Anillo de progreso SVG con el restante (o el exceso) en el centro."""
    pct = min(value / goal, 1.0) if goal else 0.0
    over = bool(goal) and value > goal
    color = RED if over else GREEN
    r, circ = 70, 2 * math.pi * 70
    big = f"+{value - goal:.0f}" if over else f"{max(goal - value, 0):.0f}"
    small = f"{unit} de más" if over else f"{unit} restantes"
    return (f'<svg viewBox="0 0 170 170" width="{size}" height="{size}" role="img" aria-label="{big} {small}">'
            f'<circle cx="85" cy="85" r="{r}" fill="none" stroke="rgba(128,128,128,.25)" stroke-width="14"/>'
            f'<circle cx="85" cy="85" r="{r}" fill="none" stroke="{color}" stroke-width="14" stroke-linecap="round" '
            f'stroke-dasharray="{circ * pct:.1f} {circ:.1f}" transform="rotate(-90 85 85)"/>'
            f'<text x="85" y="86" text-anchor="middle" font-size="32" font-weight="700" fill="currentColor">{big}</text>'
            f'<text x="85" y="108" text-anchor="middle" font-size="12" fill="currentColor" opacity=".7">{small}</text></svg>')


def bar(label: str, value: float, goal: float, unit: str = "g", color: str = GREEN) -> str:
    pct = min(value / goal * 100, 100) if goal else 0
    over = bool(goal) and value > goal
    return (f'<div class="sf-row"><span>{escape(label)}</span><span><b>{value:.0f}</b> / {goal:.0f} {unit}</span></div>'
            f'<div class="sf-bar"><span style="width:{pct:.0f}%; background:{RED if over else color}"></span></div>')


def nutriscore(grade: str | None) -> str:
    if grade not in NUTRISCORE_COLORS:
        return ""
    return ('<span class="sf-ns" title="Nutri-Score">' + "".join(
        f'<b class="{"on" if g == grade else ""}" style="background:{c}">{g.upper()}</b>' for g, c in NUTRISCORE_COLORS.items())
        + "</span>")


def nova(group: int | None) -> str:
    if group not in NOVA_LABELS:
        return ""
    return (f'<span class="sf-chip" style="background:{NOVA_COLORS[group]}33" title="Grupo NOVA">'
            f'NOVA {group} · {NOVA_LABELS[group]}</span>')


def ecoscore(grade: str | None) -> str:
    return chip(f"Eco-Score {grade.upper()}", "green") if grade in NUTRISCORE_COLORS else ""


def safe_image(url: str | None) -> str:
    return f'<img class="sf-img" src="{escape(url, quote=True)}" alt="" loading="lazy"/>' if url and url.startswith("https://") else ""


def food_header(food: dict) -> str:
    """Cabecera de ficha: foto, nombre, marca, código de barras, envase y distintivos."""
    sub = " · ".join(escape(x) for x in (food.get("brand"), food.get("quantity")) if x)
    code = f'<span class="sf-chip">🏷 {escape(food["barcode"])}</span>' if food.get("barcode") else ""
    badges = nutriscore(food.get("nutriscore_grade")) + nova(food.get("nova_group")) + ecoscore(food.get("ecoscore_grade"))
    allergens = chips([f"⚠ {a}" for a in food.get("allergens") or []], "orange")
    return (f'<div class="sf-food">{safe_image(food.get("image_url"))}<div>'
            f'<div class="sf-big">{escape(food["name"])}</div><div class="sf-muted">{sub}</div>'
            f'<div>{code}{chip("🌐 Open Food Facts") if food.get("source") == "openfoodfacts" else ""}</div>'
            f'<div style="margin-top:4px">{badges}</div><div>{allergens}</div></div></div>')
