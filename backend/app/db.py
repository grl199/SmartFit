from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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

    with engine.begin() as conn:
        for ext in ("vector", "unaccent"):
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
    Base.metadata.create_all(engine)
