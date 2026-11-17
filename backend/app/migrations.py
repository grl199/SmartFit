"""Migraciones ligeras e idempotentes para bases de datos creadas con versiones anteriores.

`create_all` crea las tablas que faltan pero NO añade columnas a tablas existentes; eso lo hace este módulo.
Cuando el esquema se estabilice, sustitúyelo por Alembic."""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import enums
from .models import FOOD_SEARCH_SQL

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
    # Open Food Facts: metadatos de producto
    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS nutriscore_grade VARCHAR(1)",
    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS nova_group INTEGER",
    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS ecoscore_grade VARCHAR(1)",
    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS image_url TEXT",
    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS quantity VARCHAR(100)",
    # Entrenamiento: categoría y calorías estimadas
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS category VARCHAR(20)",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS kcal_source VARCHAR(10)",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS met DOUBLE PRECISION",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS intensity VARCHAR(10)",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS kcal_note TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_exercises_owner_name ON exercises (coalesce(user_id, 0), lower(name))",
    # Andar/correr: métricas
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS distance_km DOUBLE PRECISION",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS elevation_gain_m DOUBLE PRECISION",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS steps INTEGER",
    "ALTER TABLE workouts ADD COLUMN IF NOT EXISTS avg_hr_bpm INTEGER",
    # Varias conversaciones
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS conversation_id INTEGER REFERENCES conversations(id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_messages_conversation_id ON chat_messages (conversation_id)",
    # Ejercicios: tipo
    "ALTER TABLE exercises ADD COLUMN IF NOT EXISTS kind VARCHAR(12) NOT NULL DEFAULT 'strength'",
    # Alimentos: código único por propietario, compartir con la comunidad, búsqueda tolerante
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_foods_owner_barcode ON foods (coalesce(user_id, 0), barcode)",
    "ALTER TABLE foods ADD COLUMN IF NOT EXISTS share_status VARCHAR(10) NOT NULL DEFAULT 'private'",
    f"ALTER TABLE foods ADD COLUMN IF NOT EXISTS search_text TEXT GENERATED ALWAYS AS ({FOOD_SEARCH_SQL}) STORED",
    "CREATE INDEX IF NOT EXISTS ix_foods_search_trgm ON foods USING gin (search_text gin_trgm_ops)",
    # Taxonomía nueva: sin «oblicuos» (se funden con abdominales) y sesiones reagrupadas
    "UPDATE exercises SET primary_muscle = 'abs' WHERE primary_muscle = 'obliques'",
    """UPDATE exercises SET secondary_muscles = (
           SELECT COALESCE(jsonb_agg(DISTINCT CASE WHEN v = 'obliques' THEN 'abs' ELSE v END), '[]'::jsonb)
           FROM jsonb_array_elements_text(secondary_muscles) AS v) WHERE secondary_muscles ? 'obliques'""",
    "UPDATE workouts SET category = 'strength' WHERE category IN ('legs', 'push', 'pull', 'upper', 'core', 'other')",
    "UPDATE workouts SET category = 'sport' WHERE category = 'cardio'",
]

# El equipamiento pasa de un texto a una lista JSON y se adapta a la nueva lista (cable -> máquina, peso corporal -> ninguno).
_EQUIPMENT_LIST = """
DO $$ BEGIN
  IF (SELECT data_type FROM information_schema.columns WHERE table_name = 'exercises' AND column_name = 'equipment') = 'character varying' THEN
    ALTER TABLE exercises ALTER COLUMN equipment DROP DEFAULT;
    ALTER TABLE exercises ALTER COLUMN equipment TYPE JSONB USING (
      CASE equipment WHEN 'bodyweight' THEN '["none"]'::jsonb WHEN 'cable' THEN '["machine"]'::jsonb
                     ELSE jsonb_build_array(COALESCE(equipment, 'other')) END);
  END IF;
END $$;
"""

# El código de barras era único a nivel global: dos usuarios no podían tener el mismo código (y el de uno podía "verse"
# en consultas de otro). Ahora es único por propietario.
_BARCODE_INDEX = """
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_foods_barcode' AND indexdef LIKE 'CREATE UNIQUE%') THEN
    DROP INDEX ix_foods_barcode;
    CREATE INDEX ix_foods_barcode ON foods (barcode);
  END IF;
END $$;
"""

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


def _legacy_conversations(conn: Connection) -> None:
    """Los mensajes anteriores a las conversaciones se agrupan en «Conversación anterior» (una por usuario)."""
    conn.execute(text("""
        WITH created AS (
            INSERT INTO conversations (user_id, title)
            SELECT DISTINCT user_id, 'Conversación anterior' FROM chat_messages WHERE conversation_id IS NULL
            RETURNING id, user_id)
        UPDATE chat_messages m SET conversation_id = created.id
        FROM created WHERE m.user_id = created.user_id AND m.conversation_id IS NULL"""))


def run_migrations(conn: Connection) -> None:
    conn.execute(text(_EQUIPMENT_LIST))
    conn.execute(text(_BARCODE_INDEX))
    for stmt in _COLUMNS:
        conn.execute(text(stmt))
    conn.execute(text("UPDATE workouts SET kcal_source = 'manual' WHERE kcal_burned IS NOT NULL AND kcal_source IS NULL"))
    conn.execute(text(_ONBOARDING))
    _normalize_legacy_values(conn)
    _legacy_conversations(conn)
