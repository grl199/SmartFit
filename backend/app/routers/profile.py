import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import BodyMetric, User, UserProfile, UserTarget
from ..clock import age_on
from ..schemas import EnergyOut, OnboardingIn, OnboardingOut, ProfileIO, TargetIO, TargetOut
from ..services.nutrition import latest_weight, today_local
from ..services.plan import PlanGenerationError, PlanRejected, energy, generate_fallback_targets, generate_targets

log = logging.getLogger(__name__)
# Este router solo exige estar autenticado (no onboarded): contiene el propio onboarding.
router = APIRouter(tags=["profile"])


def _generate_or_http(db: Session, user_id: int) -> dict:
    try:
        return generate_targets(db, user_id)
    except PlanRejected as e:
        raise HTTPException(422, str(e))
    except PlanGenerationError as e:
        log.error("%s", e)
        raise HTTPException(502, "La IA no pudo generar un plan válido. Inténtalo de nuevo en unos segundos.")
    except Exception:  # red, clave inválida, límite del proveedor...
        log.exception("Fallo llamando al modelo")
        raise HTTPException(502, "No se pudo contactar con el modelo de IA. Revisa la configuración e inténtalo de nuevo.")


@router.post("/onboarding", response_model=OnboardingOut)
def onboarding(body: OnboardingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Paso OBLIGATORIO tras el registro: guarda el perfil y el peso, pide objetivos al LLM y
    marca la cuenta como completada. Si el LLM falla, el perfil queda guardado y se puede reintentar."""
    data = body.model_dump(exclude={"weight_kg"})
    profile = db.get(UserProfile, user.id) or UserProfile(user_id=user.id)
    for k, v in data.items():
        setattr(profile, k, v)
    db.add(profile)
    # Onboarding can be retried safely: update today's weight instead of creating duplicates.
    metric = db.scalar(select(BodyMetric).where(
        BodyMetric.user_id == user.id, BodyMetric.measured_on == today_local(),
    ).order_by(BodyMetric.id.desc()))
    if metric is None:
        metric = BodyMetric(user_id=user.id, measured_on=today_local(), weight_kg=body.weight_kg)
    else:
        metric.weight_kg = body.weight_kg
    db.add(metric)
    db.commit()

    try:
        result = generate_targets(db, user.id)
    except PlanRejected as e:
        raise HTTPException(422, str(e))
    except Exception:
        # A provider outage or unusable model response must not trap the account in onboarding.
        log.exception("La IA no pudo generar el plan inicial; se aplican objetivos provisionales.")
        result = generate_fallback_targets(db, user.id)

    user.onboarding_completed = True
    db.add(user)
    db.commit()
    return OnboardingOut(profile=result["profile"], targets=result["targets"], bmr=result["bmr"], tdee=result["tdee"])


@router.get("/profile", response_model=ProfileIO)
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(UserProfile, user.id) or ProfileIO()


@router.put("/profile", response_model=ProfileIO)
def put_profile(body: ProfileIO, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(UserProfile, user.id) or UserProfile(user_id=user.id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.add(p)
    db.commit()
    return p


@router.get("/profile/energy", response_model=EnergyOut)
def get_energy(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Edad, metabolismo basal (Mifflin-St Jeor) y gasto total, calculados SIEMPRE por código con el perfil y el último
    peso: se actualizan solos al cambiar peso, altura, fecha de nacimiento o actividad. No llama a la IA."""
    p, w = db.get(UserProfile, user.id), latest_weight(db, user.id)
    out = EnergyOut(age=age_on(p.birth_date) if p and p.birth_date else None, weight_kg=w.weight_kg if w else None)
    out.missing = [n for n, v in (("sexo", p and p.sex), ("fecha de nacimiento", p and p.birth_date), ("altura", p and p.height_cm),
                                  ("nivel de actividad", p and p.activity_level), ("peso", w)) if not v]
    if not out.missing:
        out.bmr, out.tdee = energy(p.sex, w.weight_kg, p.height_cm, out.age, p.activity_level)
    return out


@router.get("/targets", response_model=TargetOut)
def get_targets_(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(UserTarget, user.id)


@router.put("/targets", response_model=TargetOut)
def put_targets(body: TargetIO, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Edición manual: marca los objetivos como 'manual' pero conserva el plan de entrenamiento previo."""
    t = db.get(UserTarget, user.id) or UserTarget(user_id=user.id)
    for k, v in body.model_dump().items():
        if v is not None or k not in ("water_ml", "steps_goal"):   # agua y pasos opcionales: omitidos = sin cambios
            setattr(t, k, v)
    t.source = "manual"
    db.add(t)
    db.commit()
    return t


@router.post("/targets/generate", response_model=OnboardingOut)
def regenerate_targets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Recalcula los objetivos con la IA a partir del perfil y el peso actuales."""
    result = _generate_or_http(db, user.id)
    return OnboardingOut(profile=result["profile"], targets=result["targets"], bmr=result["bmr"], tdee=result["tdee"])
