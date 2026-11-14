from fastapi import Depends, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_token

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_MB = 10
_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    """Usuario autenticado por JWT. Se comprueba en BD en cada petición para que borrar una cuenta
    invalide sus tokens al instante."""
    uid = decode_token(creds.credentials) if creds else None
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(401, "Sesión no válida o caducada", headers={"WWW-Authenticate": "Bearer"})
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
