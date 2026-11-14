"""Migraciones ligeras e idempotentes para bases de datos creadas con versiones anteriores.

`create_all` crea las tablas que faltan pero NO añade columnas a tablas existentes; eso lo hace este módulo.
Cuando el esquema se estabilice, sustitúyelo por Alembic."""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import enums

log = logging.getLogger(__name__)

_COLUMNS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
    "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS experience_level VARCHAR(20)",
    "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS available_training_days INTEGER",
    "ALTER TABLE user_targets ADD COLUMN IF NOT EXISTS training_plan TEXT",
    "ALTER TABLE user_targets ADD COLUMN IF NOT EXISTS rationale TEXT",
    "ALTER TABLE user_targets ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'manual'",
    "ALTER TABLE user_targets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_name_lower ON users (lower(name))",
]

# Los usuarios que ya existían antes de añadir el onboarding se consideran onboarded (default TRUE
# solo en el momento de crear la columna); los nuevos nacen con FALSE.
_ONBOARDING = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'users' AND column_name = 'onboarding_completed') THEN
    ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE users ALTER COLUMN onboarding_completed SET DEFAULT FALSE;
  END IF;
END $$;
"""


def _quoted(codes) -> str:
    return ", ".join("'" + c.replace("'", "''") + "'" for c in codes)


def _normalize_legacy_values(conn: Connection) -> None:
    """Versiones anteriores permitían texto libre en sexo/objetivo/actividad. Mapea lo reconocible y,
    para el resto, conserva el texto original en context_notes antes de dejar el campo a NULL."""
    conn.execute(text("UPDATE user_profiles SET sex = 'male' WHERE lower(sex) IN ('hombre', 'masculino')"))
    conn.execute(text("UPDATE user_profiles SET sex = 'female' WHERE lower(sex) IN ('mujer', 'femenino')"))
    conn.execute(text(f"UPDATE user_profiles SET sex = NULL WHERE sex IS NOT NULL AND sex NOT IN ({_quoted(enums.SEX)})"))
    for column, label, valid in (("goal", "Objetivo", enums.GOAL), ("activity_level", "Nivel de actividad", enums.ACTIVITY_LEVEL)):
        bad = f"{column} IS NOT NULL AND {column} NOT IN ({_quoted(valid)})"
        conn.execute(text(
            f"UPDATE user_profiles SET context_notes = concat_ws(E'\\n', context_notes, '{label} previo (texto libre): ' || {column}) WHERE {bad}"))
        conn.execute(text(f"UPDATE user_profiles SET {column} = NULL WHERE {column} IS NOT NULL AND {column} NOT IN ({_quoted(valid)})"))


def run_migrations(conn: Connection) -> None:
    for stmt in _COLUMNS:
        conn.execute(text(stmt))
    conn.execute(text(_ONBOARDING))
    _normalize_legacy_values(conn)
