"""Agua, check-in emocional y actividad diaria: consultas y agregaciones (sin IA)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DailyActivity, DailyCheckIn, HydrationLog, UserTarget


def water_goal(db: Session, uid: int) -> int:
    t = db.get(UserTarget, uid)
    return t.water_ml if t else 2000


def steps_goal(db: Session, uid: int) -> int:
    t = db.get(UserTarget, uid)
    return t.steps_goal if t else 8000


def water_by_day(db: Session, uid: int, start: date, end: date) -> dict[date, int]:
    rows = db.execute(select(HydrationLog.log_date, func.sum(HydrationLog.quantity_ml))
                      .where(HydrationLog.user_id == uid, HydrationLog.log_date.between(start, end)).group_by(HydrationLog.log_date)).all()
    return {d: int(ml) for d, ml in rows}


def water_summary(db: Session, uid: int, today: date, days: int) -> dict:
    goal = water_goal(db, uid)
    start = today - timedelta(days=days - 1)
    by_day = water_by_day(db, uid, start, today)
    series = [{"date": (start + timedelta(days=i)).isoformat(), "ml": by_day.get(start + timedelta(days=i), 0),
               "pct": round(by_day.get(start + timedelta(days=i), 0) / goal * 100) if goal else 0} for i in range(days)]
    today_ml = by_day.get(today, 0)
    logged = [d["ml"] for d in series if d["ml"] > 0]
    return {"goal_ml": goal, "today_ml": today_ml, "today_pct": round(today_ml / goal * 100) if goal else 0,
            "avg_ml": round(sum(logged) / len(logged)) if logged else None, "days_logged": len(logged),
            "days_goal_met": sum(1 for d in series if d["ml"] >= goal), "days": series}


def effective_steps(db: Session, uid: int, start: date, end: date) -> dict[date, dict]:
    """Un valor por día. Varias fuentes pueden medir los MISMOS pasos (reloj + móvil), así que NO se suman: se toma el máximo
    entre fuentes (política conservadora contra el doble recuento) y se informa de las fuentes disponibles."""
    rows = db.scalars(select(DailyActivity).where(DailyActivity.user_id == uid, DailyActivity.activity_date.between(start, end))).all()
    by: dict[date, list[DailyActivity]] = defaultdict(list)
    for r in rows:
        by[r.activity_date].append(r)
    out = {}
    for d, items in by.items():
        best = max(items, key=lambda r: r.steps)
        out[d] = {"steps": best.steps, "distance_km": best.distance_km, "active_calories": best.active_calories, "source": best.source,
                  "sources": sorted({r.source for r in items})}
    return out


def activity_summary(db: Session, uid: int, today: date, days: int) -> dict:
    goal = steps_goal(db, uid)
    start = today - timedelta(days=days - 1)
    eff = effective_steps(db, uid, start, today)
    series = [{"date": (start + timedelta(days=i)).isoformat(), "steps": eff.get(start + timedelta(days=i), {}).get("steps")} for i in range(days)]
    recorded = [s["steps"] for s in series if s["steps"] is not None]
    t = eff.get(today, {}).get("steps")
    return {"goal": goal, "today_steps": t, "today_pct": round(t / goal * 100) if (t is not None and goal) else None,
            "avg_steps": round(sum(recorded) / len(recorded)) if recorded else None, "days_recorded": len(recorded),
            "days_goal_met": sum(1 for s in recorded if s >= goal), "days": series}


def checkin_stats(db: Session, uid: int, start: date, end: date) -> dict:
    """Solo valores numéricos: las notas privadas nunca salen de aquí."""
    rows = db.scalars(select(DailyCheckIn).where(DailyCheckIn.user_id == uid, DailyCheckIn.checkin_date.between(start, end))).all()

    def avg(attr):
        v = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(sum(v) / len(v), 2) if v else None
    return {"days": len(rows), "mood_avg": avg("mood"), "energy_avg": avg("energy_level"), "stress_avg": avg("stress_level"),
            "sleep_avg": avg("sleep_quality")}
