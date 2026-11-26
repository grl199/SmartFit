"""Gráficos Altair con el estilo de la app: líneas de objetivo, colores con significado y tooltips en español."""
import altair as alt
import pandas as pd

import ui

OK, UNDER, OVER = ui.GREEN, ui.BLUE, ui.RED
STATUS_COLORS = alt.Scale(domain=["En objetivo", "Por debajo", "Por encima"], range=[OK, UNDER, OVER])
MACRO_COLORS = alt.Scale(domain=["Proteína", "Hidratos", "Grasa"], range=[ui.BLUE, ui.ORANGE, ui.PURPLE])
HEIGHT = 230


def _x(title=None, fmt="%d %b"):
    return alt.X("date:T", title=title, axis=alt.Axis(format=fmt, labelAngle=0, grid=False, tickCount=6))


def _finish(chart: alt.Chart, height: int = HEIGHT) -> alt.Chart:
    return chart.properties(height=height).configure_view(strokeWidth=0).configure_axis(
        labelFontSize=11, titleFontSize=11, gridOpacity=0.15, domain=False, tickSize=0)


def goal_rule(value: float, label: str, color: str = "#94a3b8") -> alt.Chart:
    """Línea de objetivo discontinua (el valor está en el texto de la sección y en el tooltip: una etiqueta pintada
    encima se solapa con las barras)."""
    df = pd.DataFrame({"v": [value], "t": [f"{label}: {value:,.0f}".replace(",", ".")]})
    return alt.Chart(df).mark_rule(strokeDash=[6, 4], color=color, strokeWidth=1.8, tooltip=True).encode(y="v:Q", tooltip="t:N")


def day_status_bars(df: pd.DataFrame, value: str, goal: float, tol: float = 0.10, unit: str = "kcal", label: str = "Objetivo") -> alt.Chart:
    """Barras por día coloreadas según estén dentro de ±tol del objetivo, con línea de objetivo."""
    d = df.copy()
    d["Estado"] = d[value].apply(lambda v: "En objetivo" if abs(v - goal) <= goal * tol else "Por debajo" if v < goal else "Por encima")
    bars = alt.Chart(d).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=18).encode(
        x=_x(), y=alt.Y(f"{value}:Q", title=unit, scale=alt.Scale(domainMin=0)),
        color=alt.Color("Estado:N", scale=STATUS_COLORS, legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[alt.Tooltip("date:T", title="Día", format="%a %d %b"), alt.Tooltip(f"{value}:Q", title=unit.capitalize(), format=",.0f"), "Estado:N"])
    return _finish(bars + goal_rule(goal, label))


def line_with_goal(df: pd.DataFrame, value: str, goal: float | None, title: str, color: str, fmt: str = ",.0f", label: str = "Objetivo") -> alt.Chart:
    line = alt.Chart(df).mark_line(color=color, strokeWidth=2.5, interpolate="linear", point=alt.OverlayMarkDef(color=color, size=55, filled=True)).encode(
        x=_x(), y=alt.Y(f"{value}:Q", title=title, scale=alt.Scale(domainMin=0)),
        tooltip=[alt.Tooltip("date:T", title="Día", format="%a %d %b"), alt.Tooltip(f"{value}:Q", title=title, format=fmt)])
    return _finish(line + goal_rule(goal, label) if goal else line)


def weight_chart(df: pd.DataFrame) -> alt.Chart:
    """Peso con media móvil de 7 mediciones. df: date, weight_kg."""
    d = df.sort_values("date").copy()
    d["Tendencia"] = d["weight_kg"].rolling(7, min_periods=2).mean()
    pts = alt.Chart(d).mark_circle(size=60, color=ui.PURPLE, opacity=.65).encode(
        x=_x(), y=alt.Y("weight_kg:Q", title="kg", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T", title="Día", format="%d %b %Y"), alt.Tooltip("weight_kg:Q", title="Peso (kg)", format=".1f")])
    trend = alt.Chart(d.dropna(subset=["Tendencia"])).mark_line(color=ui.PURPLE, strokeWidth=2.5, interpolate="linear").encode(
        x="date:T", y="Tendencia:Q", tooltip=[alt.Tooltip("Tendencia:Q", title="Media móvil (kg)", format=".1f")])
    return _finish(pts + trend)


def macro_donut(protein_kcal: float, carbs_kcal: float, fat_kcal: float, title: str) -> alt.Chart:
    """Reparto de calorías por macro (4/4/9 kcal por gramo)."""
    d = pd.DataFrame({"Macro": ["Proteína", "Hidratos", "Grasa"], "kcal": [protein_kcal, carbs_kcal, fat_kcal]})
    d["Pct"] = d["kcal"] / max(d["kcal"].sum(), 1)
    arc = alt.Chart(d).mark_arc(innerRadius=42, outerRadius=70, cornerRadius=3).encode(
        theta="kcal:Q", color=alt.Color("Macro:N", scale=MACRO_COLORS, legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Macro:N", alt.Tooltip("Pct:Q", title="Reparto", format=".0%"), alt.Tooltip("kcal:Q", title="kcal", format=",.0f")])
    return arc.properties(height=190, title=alt.TitleParams(title, anchor="middle", fontSize=12, fontWeight="normal")) \
        .configure_view(strokeWidth=0)


def simple_bars(df: pd.DataFrame, x: str, y: str, y_title: str, color: str, goal: float | None = None, xfmt: str = "%d %b",
                tooltip_y_fmt: str = ",.0f", size: int = 18) -> alt.Chart:
    bars = alt.Chart(df).mark_bar(color=color, cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=size).encode(
        x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format=xfmt, labelAngle=0, grid=False, tickCount=6)),
        y=alt.Y(f"{y}:Q", title=y_title, scale=alt.Scale(domainMin=0)),
        tooltip=[alt.Tooltip(f"{x}:T", title="Fecha", format="%d %b %Y"), alt.Tooltip(f"{y}:Q", title=y_title, format=tooltip_y_fmt)])
    return _finish(bars + goal_rule(goal, "Objetivo") if goal else bars)


def speed_chart(df: pd.DataFrame) -> alt.Chart:
    """Velocidad media por sesión (km/h), para andar. df: date, speed_kmh, distance_km."""
    line = alt.Chart(df).mark_line(color=ui.GREEN, strokeWidth=2.5, interpolate="linear",
                                   point=alt.OverlayMarkDef(color=ui.GREEN, size=60, filled=True)).encode(
        x=_x(), y=alt.Y("speed_kmh:Q", title="Velocidad (km/h)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T", title="Día", format="%d %b %Y"), alt.Tooltip("speed_kmh:Q", title="km/h", format=".1f"),
                 alt.Tooltip("distance_km:Q", title="Distancia (km)", format=".2f")])
    return _finish(line)


def pace_chart(df: pd.DataFrame) -> alt.Chart:
    """Ritmo por sesión (min/km): el eje va invertido, de modo que mejorar = subir. df: date, pace (min/km decimal), label."""
    line = alt.Chart(df).mark_line(color=ui.GREEN, strokeWidth=2.5, interpolate="linear",
                                   point=alt.OverlayMarkDef(color=ui.GREEN, size=60, filled=True)).encode(
        x=_x(), y=alt.Y("pace:Q", title="Ritmo (min/km)", scale=alt.Scale(zero=False, reverse=True),
                        axis=alt.Axis(labelExpr="floor(round(datum.value * 60) / 60) + ':' + (round(datum.value * 60) % 60 < 10 ? '0' : '') + (round(datum.value * 60) % 60)")),
        tooltip=[alt.Tooltip("date:T", title="Día", format="%d %b %Y"), alt.Tooltip("label:N", title="Ritmo"),
                 alt.Tooltip("distance_km:Q", title="Distancia (km)", format=".2f")])
    return _finish(line)
