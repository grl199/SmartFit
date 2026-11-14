"""Contraseñas (argon2id), tokens JWT y freno de fuerza bruta en el login."""
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

from .config import get_settings

log = logging.getLogger(__name__)
_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("contraseña-ficticia")  # para igualar tiempos cuando el usuario no existe

_secret = get_settings().secret_key
if not _secret:
    _secret = secrets.token_urlsafe(48)
    log.warning("SECRET_KEY no definida: se usa una clave aleatoria; las sesiones se perderán al reiniciar.")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Tiempo constante aunque la cuenta no exista o no tenga contraseña."""
    try:
        _ph.verify(stored_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return stored_hash is not None


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=get_settings().token_ttl_hours)}
    return jwt.encode(payload, _secret, algorithm="HS256")


def decode_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, _secret, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# --- Freno de fuerza bruta (en memoria, por nombre de usuario) ---
MAX_FAILS, WINDOW_S = 5, 600
_fails: dict[str, list[float]] = {}


def _recent(key: str) -> list[float]:
    cutoff = time.monotonic() - WINDOW_S
    _fails[key] = [t for t in _fails.get(key, []) if t > cutoff]
    return _fails[key]


def check_throttle(key: str) -> None:
    if len(_recent(key)) >= MAX_FAILS:
        raise HTTPException(429, "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.")


def register_failure(key: str) -> None:
    _recent(key).append(time.monotonic())


def clear_failures(key: str) -> None:
    _fails.pop(key, None)
