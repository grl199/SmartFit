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
WORKOUT_CATEGORY = {
    "legs": "Pierna",
    "push": "Empuje (pecho, hombro, tríceps)",
    "pull": "Tirón (espalda, bíceps)",
    "upper": "Tren superior",
    "full_body": "Cuerpo completo",
    "core": "Core / abdomen",
    "walking": "Andar",
    "running": "Correr",
    "cardio": "Otro cardio (bici, nadar, elíptica…)",
    "other": "Otro",
}

MUSCLE_GROUP = {
    "chest": "Pecho",
    "lats": "Dorsales",
    "upper_back": "Espalda alta / trapecio",
    "lower_back": "Lumbares",
    "shoulders": "Hombros",
    "biceps": "Bíceps",
    "triceps": "Tríceps",
    "forearms": "Antebrazos",
    "abs": "Abdominales",
    "obliques": "Oblicuos",
    "glutes": "Glúteos",
    "quadriceps": "Cuádriceps",
    "hamstrings": "Isquiotibiales",
    "adductors": "Aductores",
    "abductors": "Abductores",
    "calves": "Gemelos",
}

EQUIPMENT = {
    "barbell": "Barra",
    "dumbbell": "Mancuernas",
    "machine": "Máquina",
    "cable": "Polea",
    "bodyweight": "Peso corporal",
    "other": "Otro",
}

# Músculos que se muestran al elegir cada tipo de sesión (filtra el catálogo de ejercicios).
CATEGORY_MUSCLES = {
    "legs": ["quadriceps", "hamstrings", "glutes", "adductors", "abductors", "calves"],
    "push": ["chest", "shoulders", "triceps"],
    "pull": ["lats", "upper_back", "biceps", "forearms", "lower_back"],
    "upper": ["chest", "shoulders", "triceps", "lats", "upper_back", "biceps", "forearms"],
    "core": ["abs", "obliques", "lower_back"],
    "full_body": list(MUSCLE_GROUP),
    "walking": [],
    "running": [],
    "cardio": [],
    "other": list(MUSCLE_GROUP),
}

# Músculos implicados en andar/correr (no hay series que contar). La carga se convierte en "series equivalentes":
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
    "muscle_group": MUSCLE_GROUP,
    "equipment": EQUIPMENT,
    "cardio_muscles": {k: {"primary": v["primary"], "secondary": v["secondary"]} for k, v in CARDIO_PROFILES.items()},
})
