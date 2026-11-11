"""Acceso a secretos. La API key de OpenAI vive en HashiCorp Vault (KV v2)."""
import logging
from functools import lru_cache

from .config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def get_openai_api_key() -> str:
    """Lee la key una vez por proceso. Para rotación: reinicia, o añade un TTL aquí."""
    s = get_settings()
    if s.vault_addr:
        import hvac

        client = hvac.Client(url=s.vault_addr, token=s.vault_token)
        # En producción: AppRole / Kubernetes auth en vez de un token estático.
        if not client.is_authenticated():
            raise RuntimeError("Vault: autenticación fallida")
        resp = client.secrets.kv.v2.read_secret_version(
            path=s.vault_path, mount_point=s.vault_mount, raise_on_deleted_version=True
        )
        return resp["data"]["data"][s.vault_key]
    if s.openai_api_key:
        log.warning("Usando OPENAI_API_KEY de entorno (solo desarrollo)")
        return s.openai_api_key
    raise RuntimeError("No hay API key: configura Vault o OPENAI_API_KEY")
