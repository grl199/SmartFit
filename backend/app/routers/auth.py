import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import (
    ActivityConnection, AuthSession, BodyMetric, ChatMessage, Conversation, DailyActivity, DailyCheckIn, Exercise, ExerciseContent, Food, FoodLog,
    FoodServing, HydrationLog, MemoryChunk, Recipe, RecipeIngredient, TrainingPlan, TrainingPlanDay, TrainingPlanExercise, User,
    UserProfile, UserTarget, Workout, WorkoutSet,
)
from ..schemas import Credentials, DeleteAccountIn, RefreshSessionIn, TokenOut, UserOut
from ..security import (
    check_throttle, clear_failures, create_session, create_token, hash_password, register_failure,
    decode_token, revoke_session, rotate_session, verify_password,
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


@router.post("/session/register", status_code=201)
def register_web_session(body: Credentials, db: Session = Depends(get_db)):
    """Web-only session: refresh secret is returned to the Next.js server, never browser JS."""
    if not get_settings().allow_registration:
        raise HTTPException(403, "El registro de nuevos usuarios está desactivado")
    if _find(db, body.name):
        raise HTTPException(409, "Ese nombre de usuario ya existe")
    user = User(name=body.name, password_hash=hash_password(body.password), onboarding_completed=False)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese nombre de usuario ya existe")
    db.add_all([UserProfile(user_id=user.id), UserTarget(user_id=user.id)])
    db.flush()
    access, refresh = create_session(db, user.id)
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/session/login")
def login_web_session(body: Credentials, db: Session = Depends(get_db)):
    key = body.name.strip().lower()
    check_throttle(key)
    user = _find(db, body.name)
    if not verify_password(user.password_hash if user else None, body.password):
        register_failure(key)
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    clear_failures(key)
    access, refresh = create_session(db, user.id)
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/session/refresh")
def refresh_web_session(body: RefreshSessionIn, db: Session = Depends(get_db)):
    rotated = rotate_session(db, body.refresh_token)
    if rotated is None:
        db.commit()
        raise HTTPException(401, "Sesión no válida o caducada")
    access, refresh, user_id = rotated
    user = db.get(User, user_id)
    if user is None:
        db.rollback()
        raise HTTPException(401, "Sesión no válida o caducada")
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/session/logout", status_code=204)
def logout_web_session(
    body: RefreshSessionIn | None = None,
    creds: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
):
    decoded = decode_token(creds.credentials) if creds else None
    if body and body.refresh_token:
        revoke_session(db, refresh_token=body.refresh_token)
    elif decoded and decoded[1]:
        revoke_session(db, session_id=decoded[1])
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.delete("/me", status_code=204)
def delete_account(body: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Borra la cuenta y TODOS sus datos (irreversible). Exige la contraseña como confirmación."""
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Contraseña incorrecta")
    uid = user.id
    db.execute(delete(AuthSession).where(AuthSession.user_id == uid))
    # Orden: primero lo que referencia a otras tablas. Los alimentos compartidos (user_id NULL) no se tocan.
    for model in (MemoryChunk, ChatMessage, Conversation, FoodLog, WorkoutSet, Workout, BodyMetric,
                  HydrationLog, DailyCheckIn, DailyActivity, ActivityConnection):
        db.execute(delete(model).where(model.user_id == uid))
    # Plan de entrenamiento (ejercicios -> días -> planes) y recetas (ingredientes -> recetas) propios
    plans = select(TrainingPlan.id).where(TrainingPlan.user_id == uid)
    days = select(TrainingPlanDay.id).where(TrainingPlanDay.plan_id.in_(plans))
    db.execute(delete(TrainingPlanExercise).where(TrainingPlanExercise.day_id.in_(days)))
    db.execute(delete(TrainingPlanDay).where(TrainingPlanDay.plan_id.in_(plans)))
    db.execute(delete(TrainingPlan).where(TrainingPlan.user_id == uid))
    # Ingredientes que usan alimentos propios en recetas del sistema no existen (las del sistema solo usan catálogo).
    db.execute(delete(RecipeIngredient).where(RecipeIngredient.recipe_id.in_(select(Recipe.id).where(Recipe.user_id == uid))))
    db.execute(delete(Recipe).where(Recipe.user_id == uid))
    own_foods = select(Food.id).where(Food.user_id == uid)
    db.execute(delete(FoodServing).where(FoodServing.food_id.in_(own_foods)))
    db.execute(delete(ExerciseContent).where(ExerciseContent.exercise_id.in_(select(Exercise.id).where(Exercise.user_id == uid))))
    db.execute(delete(Food).where(Food.user_id == uid))
    db.execute(delete(Exercise).where(Exercise.user_id == uid))
    db.execute(delete(UserTarget).where(UserTarget.user_id == uid))
    db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
    db.execute(delete(User).where(User.id == uid))
    db.commit()
    log.info("Cuenta %s eliminada", uid)
