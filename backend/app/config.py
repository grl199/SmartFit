from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://health:health@localhost:5432/health"
    timezone: str = "Europe/Madrid"

    # --- Autenticación ---
    # Clave para firmar los JWT. Genera una con: python -c "import secrets; print(secrets.token_urlsafe(48))"
    # Si falta, se genera una aleatoria al arrancar (las sesiones se pierden en cada reinicio).
    secret_key: str | None = None
    token_ttl_hours: int = 12
    allow_registration: bool = True
    # Credenciales para el usuario 1 ya existente (solo se aplican si aún no tiene contraseña).
    bootstrap_username: str | None = None
    bootstrap_password: str | None = None

    # Proveedor de chat y embeddings: "openrouter" o "openai".
    ai_provider: str = "openrouter"

    # OpenRouter
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-oss-20b:free"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout: float = 90.0

    # OpenAI directo (alternativa)
    openai_model: str = "gpt-5.5"
    openai_reasoning_effort: str | None = "low"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    openai_api_key: str | None = None  # solo desarrollo; en prod viene de Vault

    # Vault (KV v2)
    vault_addr: str | None = None
    vault_token: str | None = None
    vault_mount: str = "secret"
    vault_path: str = "healthapp/openai"
    vault_key: str = "api_key"

    off_user_agent: str = "HealthApp/0.1 (tu-email@ejemplo.com)"
    # Búsqueda de texto de Open Food Facts (search-a-licious). OFF limita a 10 búsquedas/min/IP.
    off_search_url: str = "https://search.openfoodfacts.org/search"
    off_search_per_minute: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
