"""Resumen de progreso. Los INDICADORES, LOGROS y PENDIENTES se calculan por código a partir de los datos reales y se comparan con el periodo
anterior equivalente. La IA (opcional) solo redacta a partir de esa estructura: no inventa logros ni métricas, y si falla se usa el texto
determinista. Solo se usan valores numéricos del bienestar: las notas privadas del check-in nunca llegan aquí."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Exercise, Workout, WorkoutSet
from . import habits
from .nutrition import daily_series, get_targets

log = logging.getLogger(__name__)
KCAL_TOLERANCE = 0.10
PROTEIN_OK = 0.90


def _pct(a: float, b: float) -> float:
    return round(a / b * 100) if b else 0


def _nutrition(db: Session, uid: int, start: date, end: date, days: int, t: dict) -> dict:
    rows = daily_series(db, uid, start, end)
    n = len(rows)
    out: dict = {"days_logged": n, "regularity_pct": _pct(n, days), "kcal_target": t.get("kcal"), "protein_target": t.get("protein_g")}
    if not n:
        return {**out, "avg_kcal": None, "avg_protein_g": None, "protein_pct": None, "days_in_kcal_target": None, "macro_split": None}
    avg = lambda k: sum(r[k] for r in rows) / n  # noqa: E731
    kcal_p, kcal_c, kcal_f = avg("protein_g") * 4, avg("carbs_g") * 4, avg("fat_g") * 9
    tot = (kcal_p + kcal_c + kcal_f) or 1
    return {**out, "avg_kcal": round(avg("kcal")), "avg_protein_g": round(avg("protein_g")),
            "protein_pct": _pct(avg("protein_g"), t.get("protein_g") or 0) if t.get("protein_g") else None,
            "days_in_kcal_target": sum(1 for r in rows if t.get("kcal") and abs(r["kcal"] - t["kcal"]) <= t["kcal"] * KCAL_TOLERANCE),
            "macro_split": {"protein": round(kcal_p / tot * 100), "carbs": round(kcal_c / tot * 100), "fat": round(kcal_f / tot * 100)}}


def _best_weights(db: Session, uid: int, start: date | None, end: date) -> dict[int, float]:
    q = (select(WorkoutSet.exercise_id, func.max(WorkoutSet.weight_kg)).join(Workout, Workout.id == WorkoutSet.workout_id)
         .where(Workout.user_id == uid, WorkoutSet.weight_kg > 0, Workout.performed_on <= end).group_by(WorkoutSet.exercise_id))
    if start:
        q = q.where(Workout.performed_on >= start)
    return {e: float(w) for e, w in db.execute(q)}


def _volume(db: Session, uid: int, start: date, end: date) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(WorkoutSet.reps * WorkoutSet.weight_kg), 0)).join(Workout, Workout.id == WorkoutSet.workout_id)
                           .where(Workout.user_id == uid, WorkoutSet.weight_kg > 0, Workout.performed_on.between(start, end))) or 0)


def _training(db: Session, uid: int, start: date, end: date, pstart: date, pend: date, days: int, t: dict) -> dict:
    count = lambda a, b: db.scalar(select(func.count()).select_from(Workout).where(  # noqa: E731
        Workout.user_id == uid, Workout.performed_on.between(a, b))) or 0
    cur, prev_best = _best_weights(db, uid, start, end), _best_weights(db, uid, pstart, pend)
    before = _best_weights(db, uid, None, start - timedelta(days=1))
    names = {e.id: e.name for e in db.scalars(select(Exercise).where(Exercise.id.in_(set(cur) | set(prev_best))))}
    prs = [{"exercise": names[e], "weight_kg": w, "previous_best_kg": before[e]} for e, w in cur.items() if e in before and w > before[e]]
    improved = [{"exercise": names[e], "from_kg": prev_best[e], "to_kg": w} for e, w in cur.items() if e in prev_best and w > prev_best[e]]
    weeks = days / 7
    return {"sessions": count(start, end), "prev_sessions": count(pstart, pend), "target_per_week": t.get("workouts_per_week"),
            "target_sessions": round((t.get("workouts_per_week") or 0) * weeks, 1), "volume_kg": round(_volume(db, uid, start, end)),
            "prev_volume_kg": round(_volume(db, uid, pstart, pend)), "personal_records": sorted(prs, key=lambda x: x["exercise"]),
            "improved": sorted(improved, key=lambda x: x["exercise"])}


def build(db: Session, uid: int, today: date, days: int = 7) -> dict:
    start, pend = today - timedelta(days=days - 1), today - timedelta(days=days)
    pstart = pend - timedelta(days=days - 1)
    t = get_targets(db, uid)
    nutri, nutri_prev = _nutrition(db, uid, start, today, days, t), _nutrition(db, uid, pstart, pend, days, t)
    train = _training(db, uid, start, today, pstart, pend, days, t)
    steps, steps_prev = habits.activity_summary(db, uid, today, days), habits.activity_summary(db, uid, pend, days)
    water = habits.water_summary(db, uid, today, days)
    mood = habits.checkin_stats(db, uid, start, today)

    ach: list[str] = []
    pend_: list[str] = []
    if train["sessions"]:
        if train["sessions"] > train["prev_sessions"]:
            ach.append(f"Has completado {train['sessions']} entrenamientos, frente a {train['prev_sessions']} en el periodo anterior.")
        elif train["target_sessions"] and train["sessions"] >= round(train["target_sessions"]):
            ach.append(f"Has cumplido tu objetivo de entrenamiento: {train['sessions']} sesiones.")
        if train["target_sessions"] and train["sessions"] < round(train["target_sessions"]):
            pend_.append(f"Llevas {train['sessions']} sesiones y tu objetivo para este periodo es de unas {round(train['target_sessions'])}.")
    else:
        pend_.append("No hay entrenamientos registrados en este periodo.")
    for pr in train["personal_records"]:
        ach.append(f"Nuevo récord en {pr['exercise']}: {pr['weight_kg']:g} kg (antes {pr['previous_best_kg']:g} kg).")
    for im in train["improved"]:
        if not any(pr["exercise"] == im["exercise"] for pr in train["personal_records"]):
            ach.append(f"Has subido el peso en {im['exercise']}: de {im['from_kg']:g} a {im['to_kg']:g} kg respecto al periodo anterior.")
    if nutri["days_logged"]:
        if nutri["protein_pct"] is not None:
            (ach if nutri["protein_pct"] >= PROTEIN_OK * 100 else pend_).append(
                f"Tu proteína media ha sido de {nutri['avg_protein_g']} g, el {nutri['protein_pct']} % de tu objetivo ({nutri['protein_target']:.0f} g).")
        if nutri["days_in_kcal_target"] and nutri["days_in_kcal_target"] >= nutri["days_logged"] / 2:
            ach.append(f"Has estado dentro de ±10 % de tu objetivo de calorías {nutri['days_in_kcal_target']} de {nutri['days_logged']} días registrados.")
        if nutri["regularity_pct"] >= 70:
            ach.append(f"Has registrado tus comidas {nutri['days_logged']} de {days} días.")
        elif nutri["regularity_pct"] < 50:
            pend_.append(f"Solo has registrado comidas {nutri['days_logged']} de {days} días: con más registros el análisis será más fiable.")
    else:
        pend_.append("No hay comidas registradas en este periodo.")
    if steps["days_recorded"]:
        if steps["days_goal_met"]:
            ach.append(f"Has alcanzado tu objetivo de {steps['goal']:,} pasos {steps['days_goal_met']} de {steps['days_recorded']} días.".replace(",", "."))
        else:
            pend_.append(f"Tu media de pasos es de {steps['avg_steps']:,} y aún no has llegado a tu objetivo de {steps['goal']:,} ningún día.".replace(",", "."))
    if water["days_logged"]:
        if water["days_goal_met"]:
            ach.append(f"Has cumplido tu objetivo de agua {water['days_goal_met']} días.")
        low = water["days_logged"] - water["days_goal_met"]
        if low:
            pend_.append(f"Hay {low} días con menos agua de la prevista (media {water['avg_ml']} ml; objetivo {water['goal_ml']} ml).")

    sections = {"nutrition": bool(nutri["days_logged"]), "training": bool(train["sessions"]), "activity": bool(steps["days_recorded"]),
                "water": bool(water["days_logged"]), "checkins": bool(mood["days"])}
    enough = nutri["days_logged"] >= 3 or train["sessions"] >= 1
    summary = _summary(days, enough, ach, pend_)
    return {"period": {"days": days, "start": start.isoformat(), "end": today.isoformat(), "prev_start": pstart.isoformat(), "prev_end": pend.isoformat()},
            "enough_data": enough, "sections_with_data": sections,
            "nutrition": nutri, "nutrition_prev": nutri_prev, "training": train,
            "activity": {"avg_steps": steps["avg_steps"], "prev_avg_steps": steps_prev["avg_steps"], "goal": steps["goal"],
                         "days_goal_met": steps["days_goal_met"], "days_recorded": steps["days_recorded"]},
            "wellbeing": {"water_avg_ml": water["avg_ml"], "water_goal_ml": water["goal_ml"], "water_days_goal_met": water["days_goal_met"],
                          "water_days_logged": water["days_logged"], **{f"checkin_{k}": v for k, v in mood.items()}},
            "achievements": ach, "pending": pend_, "summary": summary, "ai_summary": None,
            "note": "Los datos de bienestar se muestran junto a los de entrenamiento y hábitos como contexto; no implican causa y efecto."}


def _summary(days: int, enough: bool, ach: list[str], pend: list[str]) -> str:
    if not enough:
        return (f"Todavía no hay datos suficientes en los últimos {days} días para valorar tu progreso. "
                "Registra tus comidas y entrenamientos unos días más y aquí verás cómo evolucionas.")
    parts = [f"Resumen de tus últimos {days} días:"]
    if ach:
        parts.append(" ".join(ach[:5]))
    if pend:
        parts.append("Aspectos a mejorar: " + " ".join(pend[:3]))
    return "\n\n".join(parts)


SYSTEM = """\
Eres un entrenador y nutricionista cercano. Recibirás un JSON con indicadores YA CALCULADOS del progreso de una persona. Redacta un \
resumen breve (máximo 120 palabras) en español, en segunda persona, motivador y concreto.

Reglas estrictas:
- Usa SOLO los datos del JSON. No inventes logros, cifras, mejoras ni hábitos que no aparezcan.
- Menciona los logros de `achievements` y, con tacto, 1 o 2 cosas de `pending`. Termina con un único siguiente paso práctico.
- No sugieras relaciones causa-efecto entre ánimo/energía y entrenamiento o hábitos: solo menciónalos como contexto.
- No des consejos médicos. Si `enough_data` es false, dilo claramente.
- Responde solo con el texto del resumen.
"""


def ai_rewrite(data: dict, chat: Callable) -> str | None:
    """Devuelve el texto redactado por la IA o None si no está disponible (el llamador conserva el resumen determinista)."""
    payload = {k: data[k] for k in ("period", "enough_data", "nutrition", "training", "activity", "wellbeing", "achievements", "pending")}
    try:
        text = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}])
        text = (text or "").strip()
        return text or None
    except Exception as e:  # noqa: BLE001
        log.warning("Resumen con IA no disponible: %s", str(e)[:150])
        return None
