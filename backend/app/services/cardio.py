"""Métricas y carga muscular de andar/correr."""
from .. import enums

LEVELS = ["low", "moderate", "high"]


def pace_min_km(distance_km: float | None, duration_min: float) -> float | None:
    return duration_min / distance_km if distance_km else None


def speed_kmh(distance_km: float | None, duration_min: float) -> float | None:
    return distance_km / (duration_min / 60) if distance_km and duration_min else None


def format_pace(pace: float | None) -> str:
    """5.67 -> '5:40' (min:seg por km)."""
    if not pace:
        return "—"
    m, sec = divmod(round(pace * 60), 60)
    return f"{m}:{sec:02d}"


def intensity_level(category: str | None, duration_min: float, distance_km: float | None,
                    elevation_gain_m: float | None, llm_intensity: str | None) -> str:
    """Intensidad por ritmo/velocidad cuando hay distancia (determinista); si no, la estimada por la IA; si no, moderada.
    Mucho desnivel (>50 m por km) sube un nivel."""
    level = None
    if distance_km and duration_min:
        if category == "running":
            p = duration_min / distance_km
            level = "high" if p < 5.0 else "moderate" if p < 6.5 else "low"
        elif category == "walking":
            v = distance_km / (duration_min / 60)
            level = "low" if v < 4.0 else "moderate" if v <= 5.5 else "high"
        if level and elevation_gain_m and elevation_gain_m / distance_km > 50:
            level = LEVELS[min(LEVELS.index(level) + 1, 2)]
    return level or (llm_intensity if llm_intensity in enums.INTENSITY_FACTOR else "moderate")


def muscle_load(category: str | None, duration_min: float, distance_km: float | None = None,
                elevation_gain_m: float | None = None, llm_intensity: str | None = None) -> dict[str, float]:
    """Series equivalentes por músculo para una sesión de andar/correr ({} si la categoría no tiene perfil)."""
    profile = enums.CARDIO_PROFILES.get(category or "")
    if not profile or duration_min <= 0:
        return {}
    level = intensity_level(category, duration_min, distance_km, elevation_gain_m, llm_intensity)
    eq = duration_min / profile["min_per_set"] * enums.INTENSITY_FACTOR[level]
    load = {m: eq for m in profile["primary"]}
    load.update({m: eq * enums.SECONDARY_WEIGHT for m in profile["secondary"] if m not in load})
    return load
