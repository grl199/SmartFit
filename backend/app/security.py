"""Password hashing, short-lived JWTs, refresh sessions and login throttling."""
import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuthSession

log = logging.getLogger(__name__)
_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("contraseña-ficticia")

_secret = get_settings().secret_key
if not _secret:
    _secret = secrets.token_urlsafe(48)
    log.warning("SECRET_KEY no definida: se usa una clave aleatoria; las sesiones se perderán en cada reinicio.")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        _ph.verify(stored_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return stored_hash is not None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(user_id: int, session_id: str | None = None) -> str:
    now = _utcnow()
    lifetime = (timedelta(minutes=get_settings().access_token_ttl_minutes) if session_id
                else timedelta(hours=get_settings().token_ttl_hours))
    payload = {"sub": str(user_id), "iat": now, "exp": now + lifetime}
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, _secret, algorithm="HS256")


def create_session(db: Session, user_id: int) -> tuple[str, str]:
    """Create a refreshable session; returns (access JWT, opaque refresh secret)."""
    session_id = secrets.token_hex(16)
    refresh_token = secrets.token_urlsafe(48)
    db.add(AuthSession(
        id=session_id,
        user_id=user_id,
        refresh_token_hash=_refresh_hash(refresh_token),
        expires_at=_utcnow() + timedelta(days=get_settings().refresh_token_ttl_days),
    ))
    db.flush()
    return create_token(user_id, session_id), refresh_token


def rotate_session(db: Session, refresh_token: str) -> tuple[str, str, int] | None:
    """Rotate refresh secret atomically; replayed or expired tokens are rejected."""
    row = db.scalar(select(AuthSession).where(
        AuthSession.refresh_token_hash == _refresh_hash(refresh_token),
        AuthSession.revoked_at.is_(None),
    ).with_for_update())
    now = _utcnow()
    if row is None or row.expires_at <= now:
        if row is not None:
            row.revoked_at = now
            db.flush()
        return None
    next_refresh = secrets.token_urlsafe(48)
    row.refresh_token_hash = _refresh_hash(next_refresh)
    return create_token(row.user_id, row.id), next_refresh, row.user_id


def revoke_session(db: Session, refresh_token: str | None = None, session_id: str | None = None) -> None:
    if not refresh_token and not session_id:
        return
    query = select(AuthSession).where(AuthSession.revoked_at.is_(None))
    query = query.where(
        AuthSession.refresh_token_hash == _refresh_hash(refresh_token)
        if refresh_token else AuthSession.id == session_id
    )
    row = db.scalar(query)
    if row is not None:
        row.revoked_at = _utcnow()


def decode_token(token: str) -> tuple[int, str | None] | None:
    try:
        payload = jwt.decode(token, _secret, algorithms=["HS256"])
        return int(payload["sub"]), payload.get("sid")
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# --- Brute-force throttle (in memory, per username) ---
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
