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


def is_dark() -> bool:
    """¿Está la app en modo oscuro? (st.context.theme existe desde Streamlit 1.46; si falla, se asume claro)."""
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001
        return False


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def fmt_pace(pace_min_km: float | None) -> str:
    """5.49 -> '5:29' (min:seg por km)."""
    if not pace_min_km:
        return "—"
    m, sec = divmod(round(pace_min_km * 60), 60)
    return f"{m}:{sec:02d}"


def cardio_chips(w: dict) -> str:
    """Distancia, ritmo, velocidad, desnivel, pasos y FC de una sesión de andar/correr (vacío si no hay datos)."""
    out = []
    dist, dur = w.get("distance_km"), w.get("duration_min")
    if dist:
        out.append(chip(f"📏 {dist:g} km", "blue"))
        if dur:
            out.append(chip(f"⏱ {fmt_pace(dur / dist)} /km", "green"))
            out.append(chip(f"{dist / (dur / 60):.1f} km/h"))
    if w.get("elevation_gain_m"):
        out.append(chip(f"⛰ +{w['elevation_gain_m']:g} m"))
    if w.get("steps"):
        out.append(chip(f"👣 {w['steps']:,} pasos".replace(",", ".")))
    if w.get("avg_hr_bpm"):
        out.append(chip(f"❤ {w['avg_hr_bpm']} ppm", "red"))
    return "".join(out)


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


def macro_donut(protein_kcal: float, carbs_kcal: float, fat_kcal: float, title: str, goal: tuple[float, float, float] | None = None,
                grams: tuple[float, float, float] | None = None, size: int = 150) -> str:
    """Anillo con el reparto de calorías por macro. SVG autocontenido (no depende de Vega) + leyenda HTML debajo, de modo
    que NUNCA se solapan. `goal` (kcal) añade el % objetivo junto al real; `grams` muestra los gramos."""
    vals = [max(protein_kcal, 0), max(carbs_kcal, 0), max(fat_kcal, 0)]
    total = sum(vals) or 1
    gtotal = sum(goal) or 1 if goal else None
    names, colors = ("Proteína", "Hidratos", "Grasa"), (BLUE, ORANGE, PURPLE)
    r, circ, gap = 52, 2 * math.pi * 52, 3
    arcs, offset = [], 0.0
    for v, c in zip(vals, colors):
        seg = v / total * circ
        if seg > 0:
            arcs.append(f'<circle cx="65" cy="65" r="{r}" fill="none" stroke="{c}" stroke-width="16" '
                        f'stroke-dasharray="{max(seg - gap, 0.5):.1f} {circ:.1f}" stroke-dashoffset="{-offset:.1f}" transform="rotate(-90 65 65)"/>')
        offset += seg
    legend = ""
    for i, (n, c) in enumerate(zip(names, colors)):
        pct = vals[i] / total * 100
        goal_txt = f' <span class="sf-muted">(obj. {goal[i] / gtotal * 100:.0f} %)</span>' if goal else ""
        g_txt = f' · {grams[i]:.0f} g' if grams else ""
        legend += (f'<div class="sf-row" style="justify-content:flex-start; gap:8px"><span style="display:inline-block;width:10px;height:10px;'
                   f'border-radius:50%;background:{c};margin-top:5px"></span><span>{n} <b>{pct:.0f} %</b>{g_txt}{goal_txt}</span></div>')
    return (f'<div style="text-align:center"><div class="sf-muted" style="margin-bottom:2px">{escape(title)}</div>'
            f'<svg viewBox="0 0 130 130" width="{size}" height="{size}" role="img" aria-label="{escape(title)}">'
            f'<circle cx="65" cy="65" r="{r}" fill="none" stroke="rgba(128,128,128,.22)" stroke-width="16"/>{"".join(arcs)}'
            f'<text x="65" y="63" text-anchor="middle" font-size="19" font-weight="700" fill="currentColor">{total:.0f}</text>'
            f'<text x="65" y="79" text-anchor="middle" font-size="10" fill="currentColor" opacity=".65">kcal</text></svg>'
            f'<div style="display:inline-block; text-align:left; margin-top:4px">{legend}</div></div>')


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


AMBIGUOUS_HELP = ("Código de uso restringido de una tienda o empresa: distintos productos y tiendas pueden usar el mismo número. "
                  "Comprueba que los datos corresponden al producto que tienes delante.")


def ambiguous_chip() -> str:
    return f'<span class="sf-chip orange" title="{escape(AMBIGUOUS_HELP, quote=True)}">⚠ Código de tienda (ambiguo)</span>'


def food_header(food: dict) -> str:
    """Cabecera de ficha: foto, nombre, marca, código de barras, envase y distintivos."""
    sub = " · ".join(escape(x) for x in (food.get("brand"), food.get("quantity")) if x)
    code = f'<span class="sf-chip">🏷 {escape(food["barcode"])}</span>' if food.get("barcode") else ""
    code += ambiguous_chip() if food.get("barcode_ambiguous") else ""
    if food.get("source") == "community":
        code += chip(f"👥 Comunidad · confirmado por {food.get('confirmed_by') or 2} usuarios", "green")
    elif food.get("share_status") == "pending":
        code += chip("⏳ Ofrecido a la comunidad (falta otra confirmación)", "orange")
    generic = f'<div class="sf-muted">{escape(food["generic_name"])}</div>' if food.get("generic_name") else ""
    original = (f'<div class="sf-muted">Nombre original: {escape(food["original_name"])}</div>'
                if food.get("original_name") and food["original_name"] != food["name"] else "")
    badges = nutriscore(food.get("nutriscore_grade")) + nova(food.get("nova_group")) + ecoscore(food.get("ecoscore_grade"))
    allergens = chips([f"⚠ {a}" for a in food.get("allergens") or []], "orange")
    return (f'<div class="sf-food">{safe_image(food.get("image_url"))}<div>'
            f'<div class="sf-big">{escape(food["name"])}</div><div class="sf-muted">{sub}</div>{generic}'
            f'<div>{code}{chip("🌐 Open Food Facts") if food.get("source") == "openfoodfacts" else ""}</div>'
            f'<div style="margin-top:4px">{badges}</div><div>{allergens}</div>{original}</div></div>')
