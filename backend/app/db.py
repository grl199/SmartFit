from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.schema import SetColumnComment, SetTableComment

from .config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def init_db() -> None:
    """MVP: create_all. Cuando el esquema se estabilice, pasa a Alembic."""
    from . import models  # noqa: F401  (registra las tablas)
    from .migrations import run_migrations

    with engine.begin() as conn:
        for ext in ("vector", "unaccent", "pg_trgm"):
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        # unaccent es STABLE; este envoltorio IMMUTABLE permite usarlo en columnas generadas e índices.
        conn.execute(text("CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
                          "AS $$ SELECT public.unaccent('public.unaccent', $1) $$"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        run_migrations(conn)
        apply_comments(conn)


def apply_comments(conn) -> None:
    """Aplica los `comment=` de los modelos como COMMENT ON TABLE/COLUMN (idempotente).
    Necesario porque create_all no actualiza comentarios de tablas que ya existen."""
    for table in Base.metadata.sorted_tables:
        if table.comment:
            conn.execute(SetTableComment(table))
        for column in table.columns:
            if column.comment:
                conn.execute(SetColumnComment(column))
