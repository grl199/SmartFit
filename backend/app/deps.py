from datetime import datetime, timezone

from fastapi import Depends, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthSession, User
from .security import decode_token

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_MB = 10
_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Accept mobile bearer tokens and web JWTs bound to a revocable session."""
    decoded = decode_token(creds.credentials) if creds else None
    uid, session_id = decoded if decoded else (None, None)
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(401, "Sesión no válida o caducada", headers={"WWW-Authenticate": "Bearer"})
    if session_id:
        session = db.get(AuthSession, session_id)
        if session is None or session.user_id != user.id or session.revoked_at is not None or session.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(401, "Sesión revocada o caducada", headers={"WWW-Authenticate": "Bearer"})
    return user


def current_user_id(user: User = Depends(current_user)) -> int:
    return user.id


def require_onboarded(user: User = Depends(current_user)) -> None:
    """Bloquea las funciones de la app hasta completar el perfil inicial."""
    if not user.onboarding_completed:
        raise HTTPException(403, "onboarding_required")


def read_image(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_IMAGES:
        raise HTTPException(415, "Formato no soportado (usa JPEG, PNG o WebP)")
    data = upload.file.read(MAX_IMAGE_MB * 1024 * 1024 + 1)
    if len(data) > MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, f"Imagen demasiado grande (máx. {MAX_IMAGE_MB} MB)")
    return data
