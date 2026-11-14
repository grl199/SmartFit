import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import BodyMetric, User, UserProfile, UserTarget
from ..schemas import OnboardingIn, OnboardingOut, ProfileIO, TargetIO, TargetOut
from ..services.nutrition import today_local
from ..services.plan import PlanGenerationError, PlanRejected, generate_targets

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
    db.add(BodyMetric(user_id=user.id, measured_on=today_local(), weight_kg=body.weight_kg))
    db.commit()

    result = _generate_or_http(db, user.id)
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


@router.get("/targets", response_model=TargetOut)
def get_targets_(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.get(UserTarget, user.id)


@router.put("/targets", response_model=TargetOut)
def put_targets(body: TargetIO, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Edición manual: marca los objetivos como 'manual' pero conserva el plan de entrenamiento previo."""
    t = db.get(UserTarget, user.id) or UserTarget(user_id=user.id)
    for k, v in body.model_dump().items():
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
