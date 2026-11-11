from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base

# Nutrientes que se rastrean. Food los guarda POR 100 g; FoodLog los guarda ABSOLUTOS
# (snapshot de lo consumido, de modo que editar un alimento no reescribe el histórico).
NUTRIENTS = ("kcal", "protein_g", "carbs_g", "sugars_g", "fat_g", "sat_fat_g", "fiber_g", "sodium_mg")


class NutrientMixin:
    kcal: Mapped[float] = mapped_column(Float, default=0)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    sugars_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    sat_fat_g: Mapped[float] = mapped_column(Float, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, default=0)
    sodium_mg: Mapped[float] = mapped_column(Float, default=0)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserProfile(Base):
    """Datos generales inyectados en el system prompt."""
    __tablename__ = "user_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    sex: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    height_cm: Mapped[float | None] = mapped_column(Float)
    activity_level: Mapped[str | None] = mapped_column(String(50))
    goal: Mapped[str | None] = mapped_column(String(100))
    dietary_restrictions: Mapped[str | None] = mapped_column(Text)
    context_notes: Mapped[str | None] = mapped_column(Text)  # texto libre: lesiones, rutina, preferencias...


class UserTarget(Base):
    __tablename__ = "user_targets"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    kcal: Mapped[float] = mapped_column(Float, default=2000)
    protein_g: Mapped[float] = mapped_column(Float, default=120)
    carbs_g: Mapped[float] = mapped_column(Float, default=220)
    fat_g: Mapped[float] = mapped_column(Float, default=65)
    fiber_g: Mapped[float] = mapped_column(Float, default=30)
    workouts_per_week: Mapped[int] = mapped_column(Integer, default=3)


class Food(NutrientMixin, Base):
    """Catálogo. user_id NULL = compartido (Open Food Facts); no NULL = creado por el usuario."""
    __tablename__ = "foods"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    brand: Mapped[str | None] = mapped_column(String(200))
    barcode: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")  # manual | openfoodfacts | web
    serving_g: Mapped[float | None] = mapped_column(Float)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)  # micronutrientes, URL de origen...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FoodLog(NutrientMixin, Base):
    __tablename__ = "food_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"))
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    log_date: Mapped[date] = mapped_column(Date, index=True)  # fecha local del usuario
    grams: Mapped[float] = mapped_column(Float)
    meal: Mapped[str] = mapped_column(String(20))  # breakfast | lunch | snack | dinner
    food: Mapped[Food] = relationship(lazy="joined")


class Workout(Base):
    __tablename__ = "workouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    performed_on: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(100))
    duration_min: Mapped[int] = mapped_column(Integer)
    kcal_burned: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)


class BodyMetric(Base):
    __tablename__ = "body_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    measured_on: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryChunk(Base):
    """Memoria a largo plazo para RAG: resúmenes diarios y notas (pgvector)."""
    __tablename__ = "memory_chunks"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "ref_date", name="uq_memory_user_kind_date"),
        Index(
            "ix_memory_embedding", "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # daily_summary | note
    ref_date: Mapped[date | None] = mapped_column(Date)  # NULL en notas => permite varias
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(get_settings().embedding_dim))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
