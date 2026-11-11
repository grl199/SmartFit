from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://health:health@localhost:5432/health"
    timezone: str = "Europe/Madrid"
    api_token: str | None = None
    default_user_id: int = 1  # MVP monousuario; ver deps.current_user_id

    # OpenAI
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
