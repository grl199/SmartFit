"""Modelo de datos. Cada tabla y columna lleva `comment=`: se aplica como COMMENT ON en Postgres
(db.apply_comments, en cada arranque), así el esquema queda autodocumentado en psql/DBeaver/pgAdmin."""
from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .barcodes import is_restricted_barcode
from .config import get_settings
from .db import Base

# Nutrientes que se rastrean. `foods` los guarda POR 100 g; `food_logs` los guarda ABSOLUTOS
# (snapshot de lo consumido, de modo que editar un alimento no reescribe el histórico).
NUTRIENTS = ("kcal", "protein_g", "carbs_g", "sugars_g", "fat_g", "sat_fat_g", "fiber_g", "sodium_mg")


def _nutr(label: str, unit: str, per_100g: bool):
    scope = ("por cada 100 g de alimento" if per_100g
             else "aportados por esta ingesta (ya escalados a los gramos consumidos)")
    return mapped_column(Float, default=0, comment=f"{label} en {unit}, {scope}.")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_name_lower", text("lower(name)"), unique=True),
        {"comment": "Cuentas de usuario. Raíz de todos los datos personales: el resto de tablas cuelgan de users.id."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador interno del usuario (autoincremental).")
    name: Mapped[str] = mapped_column(
        String(100), comment="Nombre con el que se inicia sesión. Único sin distinguir mayúsculas (índice uq_users_name_lower).")
    password_hash: Mapped[str | None] = mapped_column(
        String(255), comment="Hash argon2id de la contraseña. NULL = cuenta sin credenciales (no puede iniciar sesión).")
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"),
        comment="TRUE cuando el usuario completó el perfil inicial y la IA generó sus objetivos. "
                "Mientras sea FALSE la API bloquea el resto de funciones.")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Fecha de alta de la cuenta.")


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = {"comment": "Perfil del usuario (relación 1:1 con users). Se inyecta en el system prompt del asistente "
                                 "y alimenta el cálculo de objetivos. Los valores válidos están en app/enums.py."}
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True, comment="Usuario al que pertenece el perfil (PK y FK a users.id).")
    sex: Mapped[str | None] = mapped_column(
        String(20), comment="Sexo biológico, usado en la fórmula del metabolismo basal. Valores: 'male' | 'female'.")
    birth_date: Mapped[date | None] = mapped_column(Date, comment="Fecha de nacimiento (de aquí se deriva la edad; solo adultos).")
    height_cm: Mapped[float | None] = mapped_column(Float, comment="Altura en centímetros.")
    activity_level: Mapped[str | None] = mapped_column(
        String(50), comment="Nivel de actividad habitual. Valores: 'sedentary' | 'light' | 'moderate' | 'high' | 'very_high'.")
    goal: Mapped[str | None] = mapped_column(
        String(100), comment="Objetivo principal. Valores: 'gain_muscle' | 'lose_fat' | 'definition' | 'recomposition' | 'maintain'.")
    experience_level: Mapped[str | None] = mapped_column(
        String(20), comment="Experiencia entrenando. Valores: 'beginner' | 'intermediate' | 'advanced'.")
    available_training_days: Mapped[int | None] = mapped_column(
        Integer, comment="Días por semana que el usuario puede entrenar (1-7). Tope para workouts_per_week.")
    dietary_restrictions: Mapped[str | None] = mapped_column(
        Text, comment="Texto libre: alergias, intolerancias, dieta (vegetariana, sin gluten...).")
    context_notes: Mapped[str | None] = mapped_column(
        Text, comment="Texto libre: lesiones, horarios, preferencias... El asistente también añade aquí contexto útil.")


class UserTarget(Base):
    __tablename__ = "user_targets"
    __table_args__ = {"comment": "Objetivos diarios de nutrición y entrenamiento (1:1 con users). Los genera la IA en el "
                                 "onboarding y el usuario puede editarlos a mano."}
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True, comment="Usuario propietario (PK y FK a users.id).")
    kcal: Mapped[float] = mapped_column(Float, default=2000, comment="Objetivo diario de energía, en kcal.")
    protein_g: Mapped[float] = mapped_column(Float, default=120, comment="Objetivo diario de proteínas, en gramos.")
    carbs_g: Mapped[float] = mapped_column(Float, default=220, comment="Objetivo diario de hidratos de carbono, en gramos.")
    fat_g: Mapped[float] = mapped_column(Float, default=65, comment="Objetivo diario de grasas, en gramos.")
    fiber_g: Mapped[float] = mapped_column(Float, default=30, comment="Objetivo diario de fibra, en gramos.")
    workouts_per_week: Mapped[int] = mapped_column(Integer, default=3, comment="Objetivo de sesiones de entrenamiento por semana.")
    training_plan: Mapped[str | None] = mapped_column(
        Text, comment="Plan de entrenamiento semanal recomendado por la IA (texto markdown breve). NULL si los objetivos son manuales.")
    rationale: Mapped[str | None] = mapped_column(Text, comment="Explicación breve de la IA sobre por qué propone estos objetivos.")
    source: Mapped[str] = mapped_column(
        String(10), default="manual", server_default=text("'manual'"),
        comment="Origen de los objetivos: 'llm' (generados por la IA) | 'manual' (editados por el usuario).")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(), onupdate=func.now(),
        comment="Última modificación de los objetivos.")


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = {"comment": "Catálogo de alimentos con sus valores nutricionales POR 100 g. Incluye productos cacheados de "
                                 "Open Food Facts (compartidos) y alimentos creados por usuarios."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del alimento.")
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True,
        comment="Propietario. NULL = alimento compartido (Open Food Facts); no NULL = creado por ese usuario y solo visible para él.")
    name: Mapped[str] = mapped_column(String(300), comment="Nombre del producto o alimento.")
    brand: Mapped[str | None] = mapped_column(String(200), comment="Marca (primera marca si hay varias).")
    barcode: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True,
        comment="Código de barras numérico (EAN-8/13, UPC-A, GTIN-14 o código interno de tienda). Único; NULL si no tiene.")
    source: Mapped[str] = mapped_column(
        String(30), default="manual", comment="Origen de los datos: 'manual' | 'openfoodfacts' | 'web' (encontrado por el asistente).")
    serving_g: Mapped[float | None] = mapped_column(Float, comment="Tamaño de ración habitual en gramos (si se conoce).")
    extra: Mapped[dict] = mapped_column(
        JSONB, default=dict,
        comment="JSON con metadatos extra: allergens (lista en español), ingredients, categories, labels, "
                "generic_name (denominación general), original_name (nombre antes de limpiar/traducir), name_es_done "
                "(el nombre ya pasó por la traducción), off_enriched (ya se completó desde la API de producto de OFF) y source_url.")
    nutriscore_grade: Mapped[str | None] = mapped_column(String(1), comment="Nutri-Score de Open Food Facts: 'a' (mejor) a 'e' (peor). NULL si no consta.")
    nova_group: Mapped[int | None] = mapped_column(Integer, comment="Grupo NOVA de procesamiento (1 = sin procesar ... 4 = ultraprocesado). NULL si no consta.")
    ecoscore_grade: Mapped[str | None] = mapped_column(String(1), comment="Eco-Score / Green-Score ambiental de OFF: 'a' a 'e'. NULL si no consta.")
    image_url: Mapped[str | None] = mapped_column(Text, comment="URL de la foto frontal del producto (Open Food Facts).")
    quantity: Mapped[str | None] = mapped_column(String(100), comment="Cantidad del envase tal como figura en la etiqueta (p. ej. '800 g').")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Fecha en que se guardó el alimento.")
    kcal: Mapped[float] = _nutr("Energía", "kcal", True)
    protein_g: Mapped[float] = _nutr("Proteínas", "g", True)
    carbs_g: Mapped[float] = _nutr("Hidratos de carbono totales", "g", True)
    sugars_g: Mapped[float] = _nutr("Azúcares (incluidos en hidratos)", "g", True)
    fat_g: Mapped[float] = _nutr("Grasas totales", "g", True)
    sat_fat_g: Mapped[float] = _nutr("Grasas saturadas (incluidas en grasas)", "g", True)
    fiber_g: Mapped[float] = _nutr("Fibra", "g", True)
    sodium_mg: Mapped[float] = _nutr("Sodio", "mg", True)

    @property
    def allergens(self) -> list[str]:
        return list((self.extra or {}).get("allergens") or [])

    @property
    def generic_name(self) -> str | None:
        """Denominación general en español (p. ej. «Queso fresco granulado»)."""
        return (self.extra or {}).get("generic_name")

    @property
    def original_name(self) -> str | None:
        """Nombre tal como venía en Open Food Facts, si se limpió o tradujo."""
        return (self.extra or {}).get("original_name")

    @property
    def barcode_ambiguous(self) -> bool:
        return is_restricted_barcode(self.barcode)

    @property
    def ingredients(self) -> str | None:
        return (self.extra or {}).get("ingredients")

    @property
    def categories(self) -> list[str]:
        return list((self.extra or {}).get("categories") or [])


class FoodLog(Base):
    __tablename__ = "food_logs"
    __table_args__ = {"comment": "Diario de comidas: cada fila es una ingesta (alimento + gramos). Guarda un snapshot de los "
                                 "nutrientes consumidos para que editar el alimento no reescriba el histórico."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador de la ingesta.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario que consumió el alimento.")
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), comment="Alimento consumido (FK a foods.id).")
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="Instante en que se registró la ingesta.")
    log_date: Mapped[date] = mapped_column(Date, index=True, comment="Día local del usuario al que se imputa la ingesta (zona horaria de la app).")
    grams: Mapped[float] = mapped_column(Float, comment="Cantidad consumida, en gramos.")
    meal: Mapped[str] = mapped_column(String(20), comment="Comida del día: 'breakfast' | 'lunch' | 'snack' | 'dinner'.")
    kcal: Mapped[float] = _nutr("Energía", "kcal", False)
    protein_g: Mapped[float] = _nutr("Proteínas", "g", False)
    carbs_g: Mapped[float] = _nutr("Hidratos de carbono totales", "g", False)
    sugars_g: Mapped[float] = _nutr("Azúcares (incluidos en hidratos)", "g", False)
    fat_g: Mapped[float] = _nutr("Grasas totales", "g", False)
    sat_fat_g: Mapped[float] = _nutr("Grasas saturadas (incluidas en grasas)", "g", False)
    fiber_g: Mapped[float] = _nutr("Fibra", "g", False)
    sodium_mg: Mapped[float] = _nutr("Sodio", "mg", False)
    food: Mapped[Food] = relationship(lazy="joined")


class Workout(Base):
    __tablename__ = "workouts"
    __table_args__ = {"comment": "Sesiones de entrenamiento realizadas por el usuario."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador de la sesión.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario que entrenó.")
    performed_on: Mapped[date] = mapped_column(Date, index=True, comment="Día en que se realizó el entrenamiento.")
    kind: Mapped[str] = mapped_column(String(100), comment="Tipo de entrenamiento en texto libre (fuerza, running, bici...).")
    duration_min: Mapped[int] = mapped_column(Integer, comment="Duración en minutos.")
    category: Mapped[str | None] = mapped_column(
        String(20), comment="Tipo de sesión. Valores: 'legs' | 'push' | 'pull' | 'upper' | 'full_body' | 'core' | 'walking' | 'running' | 'cardio' | 'other'.")
    kcal_burned: Mapped[float | None] = mapped_column(Float, comment="Energía gastada en la sesión, en kcal (estimada por la IA o introducida a mano).")
    kcal_source: Mapped[str | None] = mapped_column(String(10), comment="Origen de kcal_burned: 'llm' (estimada por la IA) | 'manual'. NULL si no hay estimación.")
    met: Mapped[float | None] = mapped_column(Float, comment="MET medio de la sesión estimado por la IA. kcal = MET x peso(kg) x horas, calculado por código.")
    intensity: Mapped[str | None] = mapped_column(String(10), comment="Intensidad media estimada: 'low' | 'moderate' | 'high'.")
    kcal_note: Mapped[str | None] = mapped_column(Text, comment="Justificación breve de la estimación de calorías.")
    distance_km: Mapped[float | None] = mapped_column(Float, comment="Distancia recorrida en km (andar/correr). El ritmo y la velocidad se derivan de ella y de la duración.")
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, comment="Desnivel positivo acumulado en metros (andar/correr).")
    steps: Mapped[int | None] = mapped_column(Integer, comment="Número de pasos (andar).")
    avg_hr_bpm: Mapped[int | None] = mapped_column(Integer, comment="Frecuencia cardiaca media en pulsaciones por minuto (opcional).")
    notes: Mapped[str | None] = mapped_column(Text, comment="Notas libres sobre la sesión.")


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        Index("uq_exercises_owner_name", text("coalesce(user_id, 0)"), text("lower(name)"), unique=True),
        {"comment": "Catálogo de ejercicios de gimnasio con su músculo principal y secundarios. user_id NULL = catálogo "
                    "compartido (sembrado al arrancar); no NULL = ejercicio creado por ese usuario."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del ejercicio.")
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, comment="Propietario. NULL = catálogo compartido; no NULL = ejercicio personalizado.")
    name: Mapped[str] = mapped_column(String(150), comment="Nombre del ejercicio (único por propietario, sin distinguir mayúsculas).")
    primary_muscle: Mapped[str] = mapped_column(
        String(20), comment="Músculo principal (cuenta 1 por serie). Valores en app/enums.py MUSCLE_GROUP.")
    secondary_muscles: Mapped[list] = mapped_column(
        JSONB, default=list, comment="Lista JSON de músculos secundarios (cuentan 0,5 por serie).")
    equipment: Mapped[str] = mapped_column(
        String(20), default="other", comment="Material: 'barbell' | 'dumbbell' | 'machine' | 'cable' | 'bodyweight' | 'other'.")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de alta del ejercicio.")


class WorkoutSet(Base):
    __tablename__ = "workout_sets"
    __table_args__ = {"comment": "Series realizadas dentro de una sesión de entrenamiento: una fila por serie "
                                 "(ejercicio, repeticiones, peso y esfuerzo). Base del volumen por músculo y de la progresión."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador de la serie.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario que hizo la serie.")
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id"), index=True, comment="Sesión a la que pertenece (FK a workouts.id).")
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True, comment="Ejercicio realizado (FK a exercises.id).")
    set_number: Mapped[int] = mapped_column(Integer, comment="Número de serie dentro de ese ejercicio en la sesión (1, 2, 3...).")
    reps: Mapped[int] = mapped_column(Integer, comment="Repeticiones realizadas.")
    weight_kg: Mapped[float | None] = mapped_column(Float, comment="Peso usado en kilogramos. NULL o 0 = peso corporal.")
    rpe: Mapped[float | None] = mapped_column(Float, comment="Esfuerzo percibido de 1 a 10 (opcional).")
    exercise: Mapped[Exercise] = relationship(lazy="joined")


class BodyMetric(Base):
    __tablename__ = "body_metrics"
    __table_args__ = {"comment": "Mediciones corporales a lo largo del tiempo (peso y % graso). La más reciente es el peso actual."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador de la medición.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario medido.")
    measured_on: Mapped[date] = mapped_column(Date, index=True, comment="Día de la medición.")
    weight_kg: Mapped[float] = mapped_column(Float, comment="Peso corporal en kilogramos.")
    body_fat_pct: Mapped[float | None] = mapped_column(Float, comment="Porcentaje de grasa corporal (opcional).")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"comment": "Conversaciones con el asistente. Cada usuario puede tener varias y saltar de una a otra; "
                                 "cada una conserva su propio historial de mensajes."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador de la conversación.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario dueño de la conversación.")
    title: Mapped[str] = mapped_column(String(120), default="Nueva conversación", comment="Título (se rellena con el primer mensaje; editable).")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación.")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(), onupdate=func.now(),
        comment="Último mensaje o cambio; ordena la lista de conversaciones.")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {"comment": "Mensajes de las conversaciones con el asistente. Los últimos de cada conversación se reenvían al modelo como contexto."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del mensaje (el orden = orden de la conversación).")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario dueño del mensaje.")
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id"), index=True, comment="Conversación a la que pertenece el mensaje (FK a conversations.id).")
    role: Mapped[str] = mapped_column(String(20), comment="Autor del mensaje: 'user' | 'assistant'.")
    content: Mapped[str] = mapped_column(Text, comment="Texto del mensaje (las imágenes no se guardan; se marca con 📷).")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha y hora del mensaje.")


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "ref_date", name="uq_memory_user_kind_date"),
        Index("ix_memory_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        {"comment": "Memoria a largo plazo del asistente para RAG (pgvector): resúmenes diarios y notas, con su embedding."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del fragmento de memoria.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario dueño de la memoria.")
    kind: Mapped[str] = mapped_column(String(30), comment="Tipo de memoria: 'daily_summary' (resumen de un día) | 'note' (hecho guardado por el asistente).")
    ref_date: Mapped[date | None] = mapped_column(
        Date, comment="Día al que se refiere un daily_summary (único por usuario+tipo). NULL en las notas, que pueden ser varias.")
    content: Mapped[str] = mapped_column(Text, comment="Texto que se vectorizó y que se devuelve como contexto al asistente.")
    embedding = mapped_column(
        Vector(get_settings().embedding_dim),
        comment=f"Embedding del contenido ({get_settings().embedding_dim} dimensiones, distancia coseno, índice HNSW).")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación del fragmento.")
