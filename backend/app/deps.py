import secrets

from fastapi import Header, HTTPException, UploadFile

from .config import get_settings

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_MB = 10


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    token = get_settings().api_token
    if token and not secrets.compare_digest(x_api_key or "", token):
        raise HTTPException(401, "API key inválida")


def current_user_id() -> int:
    """MVP monousuario. Para multiusuario: valida un JWT/OIDC aquí y devuelve su user id;
    el resto del código ya filtra siempre por user_id."""
    return get_settings().default_user_id


def read_image(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_IMAGES:
        raise HTTPException(415, "Formato no soportado (usa JPEG, PNG o WebP)")
    data = upload.file.read(MAX_IMAGE_MB * 1024 * 1024 + 1)
    if len(data) > MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, f"Imagen demasiado grande (máx. {MAX_IMAGE_MB} MB)")
    return data
