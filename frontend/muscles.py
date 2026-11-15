"""Mapa muscular (vista frontal y posterior) como SVG, coloreado por series semanales ponderadas."""
from html import escape

LABELS = {
    "chest": "Pecho", "lats": "Dorsales", "upper_back": "Espalda alta / trapecio", "lower_back": "Lumbares",
    "shoulders": "Hombros", "biceps": "Bíceps", "triceps": "Tríceps", "forearms": "Antebrazos", "abs": "Abdominales",
    "obliques": "Oblicuos", "glutes": "Glúteos", "quadriceps": "Cuádriceps", "hamstrings": "Isquiotibiales",
    "adductors": "Aductores", "abductors": "Abductores", "calves": "Gemelos",
}
BASE, EMPTY, STROKE = "#cbd5e1", "#e8edf3", "#94a3b8"
STOPS = [(0.0, (253, 224, 71)), (0.5, (249, 115, 22)), (1.0, (153, 27, 27))]  # amarillo -> naranja -> rojo oscuro


def heat_color(sets: float, max_sets: float = 16) -> str:
    """0 series = gris; >0 = escala amarillo→naranja→rojo hasta `max_sets` series ponderadas."""
    if sets <= 0:
        return EMPTY
    t = min(sets / max_sets, 1.0)
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return "#%02x%02x%02x" % tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
    return "#%02x%02x%02x" % STOPS[-1][1]


def _ell(cx, cy, rx, ry, rot=0, **kw):
    t = f' transform="rotate({rot} {cx} {cy})"' if rot else ""
    return f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx}" ry="{ry}"{t}'


def body_svg(sets: dict[str, float], max_sets: float = 16) -> str:
    """`sets`: músculo -> series ponderadas. Devuelve un SVG autocontenido (sin dependencias externas)."""
    out: list[str] = []

    def muscle(m: str, shape: str):
        v = sets.get(m, 0)
        title = f"{LABELS[m]}: {v:g} series" if v else f"{LABELS[m]}: sin trabajar"
        out.append(f'{shape} fill="{heat_color(v, max_sets)}" stroke="{STROKE}" stroke-width="0.8"><title>{escape(title)}</title>'
                   f'{"</ellipse>" if shape.startswith("<ellipse") else "</rect>" if shape.startswith("<rect") else "</path>"}')

    def base(shape: str):
        out.append(f'{shape} fill="{BASE}" opacity="0.75"/>')

    def silhouette(cx: float):
        base(f'<circle cx="{cx}" cy="28" r="20"')
        base(f'<rect x="{cx - 9}" y="44" width="18" height="22" rx="6"')
        base(f'<path d="M {cx-52} 74 Q {cx-54} 62 {cx-38} 62 L {cx+38} 62 Q {cx+54} 62 {cx+52} 74 L {cx+43} 150 L {cx+37} 196 '
             f'L {cx+46} 236 L {cx-46} 236 L {cx-37} 196 L {cx-43} 150 Z"')
        for s in (-1, 1):
            base(_ell(cx + s * 62, 118, 13, 44, s * 6))        # brazo
            base(_ell(cx + s * 72, 190, 10, 38, s * 5))        # antebrazo
            base(_ell(cx + s * 25, 292, 23, 62))               # muslo
            base(_ell(cx + s * 24, 388, 14, 52))               # pierna
            base(_ell(cx + s * 24, 446, 11, 6))                # pie

    # ───────── Vista frontal (centro x=115) ─────────
    f = 115
    silhouette(f)
    for s in (-1, 1):
        muscle("shoulders", _ell(f + s * 52, 83, 15, 17, s * 10))
        muscle("chest", _ell(f + s * 21, 98, 24, 17, s * -6))
        muscle("biceps", _ell(f + s * 63, 118, 10, 28, s * 6))
        muscle("forearms", _ell(f + s * 72, 190, 9, 33, s * 5))
        muscle("obliques", _ell(f + s * 28, 156, 8, 28, s * -6))
        muscle("abductors", _ell(f + s * 41, 226, 8, 14))
        muscle("quadriceps", _ell(f + s * 29, 270, 16, 50, s * -2))
        muscle("adductors", _ell(f + s * 11, 282, 7, 38, s * 2))
        muscle("calves", _ell(f + s * 24, 388, 11, 40))
        for row in range(3):                                     # abdominales: 3 filas x 2
            muscle("abs", f'<rect x="{f + (-13 if s < 0 else 1):.1f}" y="{124 + row * 23}" width="12" height="20" rx="4"')

    # ───────── Vista posterior (centro x=345) ─────────
    b = 345
    silhouette(b)
    muscle("upper_back", f'<path d="M {b} 64 L {b-30} 78 L {b-22} 122 L {b} 138 L {b+22} 122 L {b+30} 78 Z"')
    for s in (-1, 1):
        muscle("shoulders", _ell(b + s * 52, 83, 15, 17, s * 10))
        muscle("lats", _ell(b + s * 27, 143, 14, 33, s * -8))
        muscle("triceps", _ell(b + s * 63, 118, 10, 28, s * 6))
        muscle("forearms", _ell(b + s * 72, 190, 9, 33, s * 5))
        muscle("abductors", _ell(b + s * 41, 224, 8, 13))
        muscle("glutes", _ell(b + s * 19, 244, 20, 21))
        muscle("hamstrings", _ell(b + s * 26, 304, 17, 44))
        muscle("calves", _ell(b + s * 24, 390, 13, 38))
    muscle("lower_back", f'<rect x="{b-16}" y="170" width="32" height="34" rx="9"')

    # ───────── Títulos y leyenda ─────────
    lg0, lg1 = 70, 390
    out.append(f'<text x="{f}" y="470" text-anchor="middle" font-size="12" fill="#64748b" font-family="sans-serif">Frontal</text>')
    out.append(f'<text x="{b}" y="470" text-anchor="middle" font-size="12" fill="#64748b" font-family="sans-serif">Posterior</text>')
    out.append('<defs><linearGradient id="hg" x1="0" x2="1">' + "".join(
        f'<stop offset="{o}" stop-color="{heat_color(max_sets * o if o else 0.01, max_sets)}"/>' for o in (0, 0.25, 0.5, 0.75, 1)) +
        '</linearGradient></defs>')
    out.append(f'<rect x="{lg0}" y="490" width="{lg1 - lg0}" height="10" rx="5" fill="url(#hg)" stroke="{STROKE}" stroke-width="0.5"/>')
    for x, t in ((lg0, "0"), ((lg0 + lg1) / 2, f"{max_sets / 2:g}"), (lg1, f"{max_sets:g}+")):
        out.append(f'<text x="{x}" y="516" text-anchor="middle" font-size="11" fill="#64748b" font-family="sans-serif">{t}</text>')
    out.append(f'<text x="{(lg0 + lg1) / 2}" y="532" text-anchor="middle" font-size="11" fill="#64748b" font-family="sans-serif">series ponderadas</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 545" width="460" height="545">' + "".join(out) + "</svg>"
