from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import enums
from ..models import BodyMetric, User, UserProfile, UserTarget
from ..services.nutrition import day_overview, latest_weight, today_local
from ..clock import age_on as plan_age
from ..services.plan import energy

WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

SYSTEM_TEMPLATE = """\
Eres el asistente de nutrición y entrenamiento de una app de seguimiento de salud. \
Respondes en el idioma del usuario (por defecto español), de forma clara y concisa.

Hoy es {today} ({weekday}).

## Perfil del usuario
{profile}

## Objetivos diarios
{targets}

## Plan de entrenamiento recomendado
{plan}

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


def _weight_line(db: Session, user_id: int) -> str | None:
    last = latest_weight(db, user_id)
    if not last:
        return None
    line = f"Peso actual: {last.weight_kg:.1f} kg ({last.measured_on.isoformat()})"
    if last.body_fat_pct:
        line += f", {last.body_fat_pct:.0f}% de grasa"
    first = db.scalar(select(BodyMetric).where(BodyMetric.user_id == user_id,
                                               BodyMetric.measured_on >= today_local() - timedelta(days=30))
                      .order_by(BodyMetric.measured_on).limit(1))
    if first and first.id != last.id:
        line += f"; variación en 30 días: {last.weight_kg - first.weight_kg:+.1f} kg"
    return line


def _profile_text(db: Session, user_id: int) -> str:
    u, p = db.get(User, user_id), db.get(UserProfile, user_id)
    lines = [f"Nombre de usuario: {u.name}"] if u else []
    last = latest_weight(db, user_id)
    if p:
        if p.sex: lines.append(f"Sexo: {enums.SEX.get(p.sex, p.sex)}")
        if p.birth_date:
            lines.append(f"Edad: {plan_age(p.birth_date)} años")
        if p.height_cm: lines.append(f"Altura: {p.height_cm:.0f} cm")
    if w := _weight_line(db, user_id):
        lines.append(w)
        if p and p.height_cm:
            lines.append(f"IMC: {last.weight_kg / (p.height_cm / 100) ** 2:.1f}")
    if p:
        if p.activity_level: lines.append(f"Nivel de actividad: {enums.ACTIVITY_LEVEL.get(p.activity_level, p.activity_level)}")
        if p.goal: lines.append(f"Objetivo principal: {enums.GOAL.get(p.goal, p.goal)}")
        if p.experience_level: lines.append(f"Experiencia entrenando: {enums.EXPERIENCE_LEVEL.get(p.experience_level, p.experience_level)}")
        if p.available_training_days: lines.append(f"Días disponibles para entrenar: {p.available_training_days}/semana")
        if p.dietary_restrictions: lines.append(f"Alergias/restricciones dietéticas: {p.dietary_restrictions}")
        if p.context_notes: lines.append(f"Notas del usuario: {p.context_notes}")
        if p.sex and p.birth_date and p.height_cm and p.activity_level and last:
            bmr, tdee = energy(p.sex, last.weight_kg, p.height_cm, plan_age(p.birth_date), p.activity_level)
            lines.append(f"Gasto energético estimado: metabolismo basal {bmr} kcal, gasto total diario {tdee} kcal")
    return "\n".join(f"- {l}" for l in lines) or "Sin datos de perfil todavía."


def _plan_text(db: Session, user_id: int) -> str:
    t = db.get(UserTarget, user_id)
    if not t or not t.training_plan:
        return "Sin plan de entrenamiento definido."
    origin = "generado por IA" if t.source == "llm" else "objetivos editados manualmente después"
    return f"({origin})\n{t.training_plan[:1500]}" + (f"\nMotivo: {t.rationale[:500]}" if t.rationale else "")


def build_system_prompt(db: Session, user_id: int) -> str:
    today = today_local()
    ov = day_overview(db, user_id, today)
    t, g = ov["totals"], ov["targets"]
    targets = (f"{g['kcal']:.0f} kcal · proteína {g['protein_g']:.0f} g · hidratos {g['carbs_g']:.0f} g · "
               f"grasa {g['fat_g']:.0f} g · fibra {g['fiber_g']:.0f} g · {g['workouts_per_week']} entrenos/semana")
    totals = (f"{t['kcal']:.0f} kcal · proteína {t['protein_g']:.0f} g · hidratos {t['carbs_g']:.0f} g · "
              f"grasa {t['fat_g']:.0f} g · fibra {t['fiber_g']:.0f} g ({len(ov['entries'])} registros)")
    return SYSTEM_TEMPLATE.format(today=today.isoformat(), weekday=WEEKDAYS[today.weekday()],
                                  profile=_profile_text(db, user_id), targets=targets, plan=_plan_text(db, user_id), totals=totals)
