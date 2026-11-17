import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import (
    BodyMetric, ChatMessage, Conversation, Exercise, Food, FoodLog, MemoryChunk, User, UserProfile, UserTarget, Workout, WorkoutSet,
)
from ..schemas import Credentials, DeleteAccountIn, TokenOut, UserOut
from ..security import (
    check_throttle, clear_failures, create_token, hash_password, register_failure, verify_password,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _find(db: Session, name: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.name) == name.strip().lower()))


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    """Crea la cuenta e inicia sesión. El usuario debe completar el onboarding antes de usar la app."""
    if not get_settings().allow_registration:
        raise HTTPException(403, "El registro de nuevos usuarios está desactivado")
    if _find(db, body.name):
        raise HTTPException(409, "Ese nombre de usuario ya existe")
    user = User(name=body.name, password_hash=hash_password(body.password), onboarding_completed=False)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # carrera entre dos registros simultáneos
        db.rollback()
        raise HTTPException(409, "Ese nombre de usuario ya existe")
    db.add_all([UserProfile(user_id=user.id), UserTarget(user_id=user.id)])
    db.commit()
    return TokenOut(access_token=create_token(user.id), user=user)


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)):
    key = body.name.strip().lower()
    check_throttle(key)
    user = _find(db, body.name)
    if not verify_password(user.password_hash if user else None, body.password):
        register_failure(key)
        raise HTTPException(401, "Usuario o contraseña incorrectos")  # mismo mensaje exista o no el usuario
    clear_failures(key)
    return TokenOut(access_token=create_token(user.id), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.delete("/me", status_code=204)
def delete_account(body: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Borra la cuenta y TODOS sus datos (irreversible). Exige la contraseña como confirmación."""
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Contraseña incorrecta")
    uid = user.id
    # Orden: primero lo que referencia a otras tablas. Los alimentos compartidos (user_id NULL) no se tocan.
    for model in (MemoryChunk, ChatMessage, Conversation, FoodLog, WorkoutSet, Workout, BodyMetric):
        db.execute(delete(model).where(model.user_id == uid))
    db.execute(delete(Food).where(Food.user_id == uid))
    db.execute(delete(Exercise).where(Exercise.user_id == uid))
    db.execute(delete(UserTarget).where(UserTarget.user_id == uid))
    db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
    db.execute(delete(User).where(User.id == uid))
    db.commit()
    log.info("Cuenta %s eliminada", uid)
