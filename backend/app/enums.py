"""Listas cerradas de valores permitidos (código -> etiqueta en español).

Fuente única de verdad: el backend valida con estos códigos y el frontend los pide a /meta/options.
Si cambias una lista, actualiza también los `Literal` de schemas.py (un test comprueba que coinciden).
"""

SEX = {
    "male": "Hombre",
    "female": "Mujer",
}

ACTIVITY_LEVEL = {
    "sedentary": "Sedentario (poco o ningún ejercicio)",
    "light": "Ligero (1-3 días de ejercicio/semana)",
    "moderate": "Moderado (3-5 días/semana)",
    "high": "Alto (6-7 días/semana)",
    "very_high": "Muy alto (entreno intenso y/o trabajo físico)",
}

# Factor de actividad (PAL) sobre el metabolismo basal para estimar el gasto diario total.
ACTIVITY_FACTOR = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725, "very_high": 1.9}

GOAL = {
    "gain_muscle": "Ganar músculo (volumen)",
    "lose_fat": "Perder grasa",
    "definition": "Definición (perder grasa conservando músculo)",
    "recomposition": "Recomposición corporal",
    "maintain": "Mantener peso y físico",
}

EXPERIENCE_LEVEL = {
    "beginner": "Principiante (menos de 1 año entrenando)",
    "intermediate": "Intermedio (1-3 años)",
    "advanced": "Avanzado (más de 3 años)",
}

# Objetivos que implican déficit calórico (no se generan si el IMC es bajo).
DEFICIT_GOALS = {"lose_fat", "definition"}

OPTIONS = {
    "sex": SEX,
    "activity_level": ACTIVITY_LEVEL,
    "goal": GOAL,
    "experience_level": EXPERIENCE_LEVEL,
}


# ───────────── Entrenamiento ─────────────
# Jerarquía: TIPO de sesión (Fuerza / Cardio / Cuerpo entero / Estiramientos) -> categoría. Cardio se divide en
# Andar, Correr y Otros deportes. En Fuerza y Estiramientos se eligen grupos musculares y equipamiento.
WORKOUT_CATEGORY = {
    "strength": "Fuerza",
    "walking": "Andar",
    "running": "Correr",
    "sport": "Otros deportes",
    "full_body": "Cuerpo entero",
    "stretching": "Estiramientos",
}
WORKOUT_CATEGORY_ICONS = {"strength": "🏋️", "walking": "🚶", "running": "🏃", "sport": "⚽", "full_body": "🤸", "stretching": "🧘"}
WORKOUT_TYPES = {  # nivel 1 de la jerarquía, en el orden en que se muestra
    "strength": {"label": "Fuerza", "icon": "🏋️", "categories": ["strength"]},
    "cardio": {"label": "Cardio", "icon": "🏃", "categories": ["walking", "running", "sport"]},
    "full_body": {"label": "Cuerpo entero", "icon": "🤸", "categories": ["full_body"]},
    "stretching": {"label": "Estiramientos", "icon": "🧘", "categories": ["stretching"]},
}
SPORTS = {  # para «Otros deportes» (el título de la sesión toma el nombre)
    "football": "Fútbol", "tennis": "Tenis", "padel": "Pádel", "basketball": "Baloncesto", "swimming": "Natación",
    "cycling": "Ciclismo", "rowing": "Remo", "climbing": "Escalada", "boxing": "Boxeo", "other": "Otro",
}
SPORT_ICONS = {"football": "⚽", "tennis": "🎾", "padel": "🏓", "basketball": "🏀", "swimming": "🏊", "cycling": "🚴",
               "rowing": "🚣", "climbing": "🧗", "boxing": "🥊", "other": "➕"}

# Grupos musculares, agrupados por región (el orden es el de la interfaz).
MUSCLE_REGIONS = {
    "upper": {"label": "Tren superior", "icon": "💪",
              "muscles": ["abs", "forearms", "biceps", "neck", "lats", "lower_back", "upper_back", "shoulders", "chest", "traps", "triceps"]},
    "lower": {"label": "Tren inferior", "icon": "🦵",
              "muscles": ["abductors", "adductors", "quadriceps", "glutes", "hamstrings", "calves"]},
}
MUSCLE_GROUP = {
    "abs": "Abdominales", "forearms": "Antebrazo", "biceps": "Bíceps", "neck": "Cuello", "lats": "Dorsales",
    "lower_back": "Espalda baja", "upper_back": "Espalda superior", "shoulders": "Hombros", "chest": "Pecho",
    "traps": "Trapecio", "triceps": "Tríceps",
    "abductors": "Abductores", "adductors": "Aductores", "quadriceps": "Cuádriceps", "glutes": "Glúteos",
    "hamstrings": "Isquiotibiales", "calves": "Pantorrillas",
}

EQUIPMENT = {
    "none": "Ninguno (peso corporal)", "resistance_band": "Banda de resistencia", "suspension": "Banda de suspensión (TRX)",
    "barbell": "Barra", "dumbbell": "Mancuerna", "plate": "Disco", "machine": "Máquina", "kettlebell": "Pesa rusa",
    "wheel": "Rueda", "medicine_ball": "Balón medicinal", "bench": "Banco(s)", "box": "Cajones", "other": "Otros",
}
EQUIPMENT_ICONS = {
    "none": "🧍", "resistance_band": "🪢", "suspension": "⛓️", "barbell": "🏋️", "dumbbell": "💪", "plate": "⚪",
    "machine": "⚙️", "kettlebell": "🔔", "wheel": "🛞", "medicine_ball": "🏐", "bench": "🛋️", "box": "📦", "other": "➕",
}

EXERCISE_KIND = {"strength": "Fuerza", "full_body": "Cuerpo entero", "stretching": "Estiramientos"}

# Andar/correr no tienen series: su carga muscular se estima con tiempo e intensidad (series equivalentes).
#   series_eq = minutos / min_per_set x factor_de_intensidad ; principales cuentan 1, secundarios SECONDARY_WEIGHT.
# Es una estimación orientativa para el mapa muscular, no una medida fisiológica.
CARDIO_PROFILES = {
    "running": {"primary": ["quadriceps", "hamstrings", "glutes", "calves"],
                "secondary": ["abs", "lower_back", "adductors", "abductors"], "min_per_set": 6},
    "walking": {"primary": ["calves", "quadriceps", "glutes", "hamstrings"],
                "secondary": ["abductors", "adductors", "lower_back"], "min_per_set": 10},
}
INTENSITY_FACTOR = {"low": 0.7, "moderate": 1.0, "high": 1.4}
SECONDARY_WEIGHT = 0.5  # una serie cuenta 1 para el músculo principal y 0,5 para cada secundario

OPTIONS.update({
    "workout_category": WORKOUT_CATEGORY,
    "workout_category_icons": WORKOUT_CATEGORY_ICONS,
    "workout_types": WORKOUT_TYPES,
    "sports": SPORTS,
    "sport_icons": SPORT_ICONS,
    "muscle_group": MUSCLE_GROUP,
    "muscle_regions": MUSCLE_REGIONS,
    "equipment": EQUIPMENT,
    "equipment_icons": EQUIPMENT_ICONS,
    "exercise_kind": EXERCISE_KIND,
    "cardio_muscles": {k: {"primary": v["primary"], "secondary": v["secondary"]} for k, v in CARDIO_PROFILES.items()},
})
