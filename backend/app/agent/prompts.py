from sqlalchemy.orm import Session

from ..models import UserProfile
from ..services.nutrition import day_overview, latest_weight, today_local

WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

SYSTEM_TEMPLATE = """\
Eres el asistente de nutrición y entrenamiento de una app de seguimiento de salud. \
Respondes en el idioma del usuario (por defecto español), de forma clara y concisa.

Hoy es {today} ({weekday}).

## Perfil del usuario
{profile}

## Objetivos diarios
{targets}

## Registrado hoy hasta ahora
{totals}

## Cómo trabajar
- Para cualquier dato del usuario (comidas, totales, entrenos, peso) usa las herramientas. Nunca inventes \
ni estimes cifras que deberían estar registradas.
- Cifras exactas de un día o periodo: get_day_summary / get_period_summary. Preguntas cualitativas o de \
hace tiempo ("¿qué cenas me sentaron mal?", "¿cómo fue mi semana de viaje?"): search_history.
- Código de barras: si el mensaje incluye códigos detectados, llama a lookup_barcode con cada uno. Si el \
producto no existe o sus datos están incompletos, usa web_search (mejor la web del fabricante o fuentes \
fiables), y si encuentras valores por 100 g, ofrécete a guardarlos con create_food (incluye el barcode). \
Indica siempre de dónde salen los datos.
- Si la foto no tiene código legible: si es una etiqueta nutricional, extrae los valores de la imagen; si \
no, pide otra foto más cercana y nítida.
- Los valores de los alimentos están SIEMPRE por 100 g. Consumido = valor × gramos / 100.
- Registra comidas (log_food) solo si el usuario lo pide o lo confirma y tienes alimento y gramos claros. \
Si falta algo, pregunta. Tras registrar, resume lo añadido y cómo queda el día.
- Si el usuario cuenta algo duradero y relevante (alergias, intolerancias, lesiones, preferencias), \
guárdalo con remember.
- Eres un apoyo informativo, no un médico. Ante síntomas, patologías, embarazo, trastornos alimentarios o \
dietas muy restrictivas, recomienda consultar a un profesional sanitario.
"""


def _profile_text(db: Session, user_id: int) -> str:
    p = db.get(UserProfile, user_id)
    lines = []
    if p:
        if p.sex: lines.append(f"Sexo: {p.sex}")
        if p.birth_date:
            t = today_local()
            age = t.year - p.birth_date.year - ((t.month, t.day) < (p.birth_date.month, p.birth_date.day))
            lines.append(f"Edad: {age} años")
        if p.height_cm: lines.append(f"Altura: {p.height_cm:.0f} cm")
        if p.activity_level: lines.append(f"Nivel de actividad: {p.activity_level}")
        if p.goal: lines.append(f"Objetivo: {p.goal}")
        if p.dietary_restrictions: lines.append(f"Restricciones/alergias: {p.dietary_restrictions}")
        if p.context_notes: lines.append(f"Notas: {p.context_notes}")
    if w := latest_weight(db, user_id):
        lines.append(f"Peso más reciente: {w.weight_kg:.1f} kg ({w.measured_on.isoformat()})")
    return "\n".join(f"- {l}" for l in lines) or "Sin datos de perfil todavía."


def build_system_prompt(db: Session, user_id: int) -> str:
    today = today_local()
    ov = day_overview(db, user_id, today)
    t, g = ov["totals"], ov["targets"]
    targets = (f"{g['kcal']:.0f} kcal · proteína {g['protein_g']:.0f} g · hidratos {g['carbs_g']:.0f} g · "
               f"grasa {g['fat_g']:.0f} g · fibra {g['fiber_g']:.0f} g · {g['workouts_per_week']} entrenos/semana")
    totals = (f"{t['kcal']:.0f} kcal · proteína {t['protein_g']:.0f} g · hidratos {t['carbs_g']:.0f} g · "
              f"grasa {t['fat_g']:.0f} g · fibra {t['fiber_g']:.0f} g ({len(ov['entries'])} registros)")
    return SYSTEM_TEMPLATE.format(today=today.isoformat(), weekday=WEEKDAYS[today.weekday()],
                                  profile=_profile_text(db, user_id), targets=targets, totals=totals)
