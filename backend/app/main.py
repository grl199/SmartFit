import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import func, select

from . import enums
from .config import get_settings
from .db import SessionLocal, init_db
from .deps import require_onboarded
from .models import User
from .routers import auth, chat, dashboard, foods, logs, profile, training
from .security import hash_password
from .services.exercise_catalog import seed_catalog
from .services.nutrition import today_local

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _bootstrap_existing_user() -> None:
    """Pone credenciales al usuario 1 (el de antes de existir el login) usando BOOTSTRAP_USERNAME/PASSWORD.
    Solo actúa si ese usuario existe y aún no tiene contraseña; nunca pisa una contraseña existente."""
    s = get_settings()
    if not (s.bootstrap_username and s.bootstrap_password):
        return
    with SessionLocal() as db:
        user = db.get(User, 1)
        if user is None or user.password_hash is not None:
            return
        taken = db.scalar(select(User).where(func.lower(User.name) == s.bootstrap_username.strip().lower()))
        if taken:
            log.warning("BOOTSTRAP_USERNAME %r ya lo usa otro usuario; el usuario 1 sigue sin credenciales", s.bootstrap_username)
            return
        user.name, user.password_hash = s.bootstrap_username.strip(), hash_password(s.bootstrap_password)
        db.commit()
        log.info("Credenciales establecidas para el usuario 1 (%s)", user.name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_catalog(db)
    _bootstrap_existing_user()
    yield


app = FastAPI(title="SmartFit API", version="0.2.0", lifespan=lifespan)

# Públicas / solo autenticadas: auth (login, registro) y perfil (incluye el onboarding).
app.include_router(auth.router)
app.include_router(profile.router)
# Resto: requieren sesión Y onboarding completado.
for r in (foods.router, logs.router, dashboard.router, training.router, chat.router):
    app.include_router(r, dependencies=[Depends(require_onboarded)])


@app.get("/meta/today")
def meta_today():
    return {"date": today_local().isoformat()}


@app.get("/meta/options")
def meta_options():
    """Listas cerradas (código -> etiqueta) para los formularios del frontend."""
    return enums.OPTIONS


@app.get("/health")
def health():
    return {"ok": True}
