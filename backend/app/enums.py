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
