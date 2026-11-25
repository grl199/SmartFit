"""Modelo de datos. Cada tabla y columna lleva `comment=`: se aplica como COMMENT ON en Postgres
(db.apply_comments, en cada arranque), así el esquema queda autodocumentado en psql/DBeaver/pgAdmin."""
from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Computed, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .barcodes import is_restricted_barcode
from .config import get_settings
from .db import Base

# Nutrientes que se rastrean. `foods` los guarda POR 100 g; `food_logs` los guarda ABSOLUTOS
# (snapshot de lo consumido, de modo que editar un alimento no reescribe el histórico).
NUTRIENTS = ("kcal", "protein_g", "carbs_g", "sugars_g", "fat_g", "sat_fat_g", "fiber_g", "sodium_mg")


# Texto normalizado (minúsculas, sin acentos) para buscar por nombre, marca, nombre original y denominación general.
# `f_unaccent` es un envoltorio IMMUTABLE de unaccent (creado en db.init_db) para poder usarlo en columnas generadas.
FOOD_SEARCH_SQL = ("f_unaccent(lower(coalesce(name, '') || ' ' || coalesce(brand, '') || ' ' || "
                   "coalesce(extra ->> 'original_name', '') || ' ' || coalesce(extra ->> 'generic_name', '')))")


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


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = {
        "comment": "Sesiones de autenticación con refresh token rotatorio. Revocar una sesión invalida también sus JWT de acceso.",
    }
    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="Identificador aleatorio de la sesión (sid incluido en el JWT).")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario propietario de la sesión.")
    refresh_token_hash: Mapped[str] = mapped_column(String(64), comment="SHA-256 del refresh token vigente; el secreto en claro nunca se almacena.")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, comment="Caducidad absoluta de la sesión renovable.")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="Fecha de revocación; NULL mientras la sesión está activa.")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación de la sesión.")


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
    water_ml: Mapped[int] = mapped_column(Integer, default=2000, server_default=text("2000"), comment="Objetivo diario de agua, en ml.")
    steps_goal: Mapped[int] = mapped_column(Integer, default=8000, server_default=text("8000"), comment="Objetivo diario de pasos.")
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
    __table_args__ = (
        # Un mismo código puede existir una vez por propietario: el catálogo compartido (user_id NULL) y cada usuario.
        Index("uq_foods_owner_barcode", text("coalesce(user_id, 0)"), text("barcode"), unique=True),
        # Un mismo alimento de una fuente externa solo una vez en el catálogo compartido.
        Index("uq_foods_source_external", "source", "external_id", unique=True,
              postgresql_where=text("external_id IS NOT NULL AND user_id IS NULL")),
        Index("ix_foods_search_trgm", "search_text", postgresql_using="gin", postgresql_ops={"search_text": "gin_trgm_ops"}),
        {"comment": "Catálogo de alimentos con sus valores nutricionales POR 100 g. Incluye productos cacheados de Open Food Facts "
                    "(compartidos), productos confirmados por la comunidad y alimentos creados por usuarios."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del alimento.")
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True,
        comment="Propietario. NULL = alimento compartido (Open Food Facts); no NULL = creado por ese usuario y solo visible para él.")
    name: Mapped[str] = mapped_column(String(300), comment="Nombre del producto o alimento.")
    brand: Mapped[str | None] = mapped_column(String(200), comment="Marca (primera marca si hay varias).")
    barcode: Mapped[str | None] = mapped_column(
        String(32), index=True,
        comment="Código de barras numérico (EAN-8/13, UPC-A, GTIN-14 o código interno de tienda). Único por propietario; NULL si no tiene.")
    source: Mapped[str] = mapped_column(
        String(30), default="manual",
        comment="Origen de los datos: 'manual' | 'openfoodfacts' | 'usda' | 'catalog' (catálogo interno SmartFit) | 'recipe' (receta guardada) | 'web' (encontrado por el asistente) | 'community' (confirmado por varios usuarios).")
    share_status: Mapped[str] = mapped_column(
        String(10), default="private", server_default=text("'private'"),
        comment="Solo en alimentos de usuario: 'private' (solo él) | 'pending' (ofrecido a la comunidad, a la espera de que otro usuario "
                "confirme los mismos datos) | 'verified' (ya forma parte del catálogo compartido).")
    search_text: Mapped[str | None] = mapped_column(
        Text, Computed(FOOD_SEARCH_SQL, persisted=True),
        comment="Columna generada: nombre + marca + nombre original + denominación general, en minúsculas y sin acentos. "
                "Alimenta la búsqueda (índice de trigramas, tolerante a erratas y a variantes entre idiomas).")
    serving_g: Mapped[float | None] = mapped_column(Float, comment="Tamaño de ración habitual en gramos (si se conoce).")
    extra: Mapped[dict] = mapped_column(
        JSONB, default=dict,
        comment="JSON con metadatos extra: allergens (lista en español), ingredients, categories, labels, "
                "generic_name (denominación general), original_name (nombre antes de limpiar/traducir), name_es_done "
                "(el nombre ya pasó por la traducción), confirmed_by (usuarios que confirmaron un alimento de la comunidad), off_enriched (ya se completó desde la API de producto de OFF) y source_url.")
    nutriscore_grade: Mapped[str | None] = mapped_column(String(1), comment="Nutri-Score de Open Food Facts: 'a' (mejor) a 'e' (peor). NULL si no consta.")
    nova_group: Mapped[int | None] = mapped_column(Integer, comment="Grupo NOVA de procesamiento (1 = sin procesar ... 4 = ultraprocesado). NULL si no consta.")
    ecoscore_grade: Mapped[str | None] = mapped_column(String(1), comment="Eco-Score / Green-Score ambiental de OFF: 'a' a 'e'. NULL si no consta.")
    image_url: Mapped[str | None] = mapped_column(Text, comment="URL de la foto frontal del producto (Open Food Facts).")
    quantity: Mapped[str | None] = mapped_column(String(100), comment="Cantidad del envase tal como figura en la etiqueta (p. ej. '800 g').")
    external_id: Mapped[str | None] = mapped_column(
        String(64), comment="Identificador en la fuente original (p. ej. fdcId de USDA). Con `source` evita duplicados en el catálogo compartido.")
    confidence: Mapped[str | None] = mapped_column(
        String(10), comment="Fiabilidad de los datos: 'high' (laboratorio/fuente oficial) | 'medium' (fabricante/comunidad) | 'low' (estimado). NULL = sin valorar.")
    license: Mapped[str | None] = mapped_column(String(40), comment="Licencia de los datos de la fuente (ODbL, CC0...).")
    attribution: Mapped[str | None] = mapped_column(Text, comment="Texto de atribución/cita exigido por la licencia de la fuente.")
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Cuándo se consultó/actualizó este dato en la fuente original.")
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
    def source_url(self) -> str | None:
        """Enlace directo a la ficha de la fuente externa cuando existe."""
        explicit = (self.extra or {}).get("source_url")
        if explicit:
            return str(explicit)
        if self.source == "openfoodfacts" and self.barcode:
            return f"https://world.openfoodfacts.org/product/{self.barcode}"
        return None

    @property
    def confirmed_by(self) -> int | None:
        return (self.extra or {}).get("confirmed_by")

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
    duration_min: Mapped[int] = mapped_column(Integer, comment="Duración total de la sesión en minutos (suma de los tiempos por ejercicio cuando se registran).")
    exercise_durations_min: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"),
        comment="Minutos dedicados a cada ejercicio en esta sesión. Claves = exercise_id como texto; la suma define duration_min cuando existe.")
    category: Mapped[str | None] = mapped_column(
        String(20), comment="Categoría de la sesión (Cardio = walking/running/sport). Valores: 'strength' | 'walking' | 'running' | 'sport' | 'full_body' | 'stretching'.")
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
    kind: Mapped[str] = mapped_column(
        String(12), default="strength", server_default=text("'strength'"),
        comment="Tipo: 'strength' (fuerza) | 'full_body' (cuerpo entero) | 'stretching' (estiramiento).")
    equipment: Mapped[list] = mapped_column(
        JSONB, default=list,
        comment="Lista JSON del equipamiento que usa (claves de enums.EQUIPMENT: none, resistance_band, suspension, barbell, dumbbell, "
                "plate, machine, kettlebell, wheel, medicine_ball, bench, box, other).")
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
    rpe: Mapped[float | None] = mapped_column(
        Float, comment="OBSOLETO: esfuerzo percibido 1-10. Ya no se pide; se conserva el histórico. No equivale a reached_failure.")
    reached_failure: Mapped[bool | None] = mapped_column(
        Boolean, comment="TRUE si la serie llegó al fallo muscular, FALSE si no. NULL = sin indicar (series anteriores o estiramientos).")
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


# ═════════════════════════ Entrenamiento: contenido didáctico y plan estructurado ═════════════════════════
class ExerciseContent(Base):
    __tablename__ = "exercise_contents"
    __table_args__ = {"comment": "Contenido didáctico de un ejercicio (1:1 con exercises), separado del catálogo básico."}
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), primary_key=True, comment="Ejercicio (PK y FK a exercises.id).")
    description: Mapped[str | None] = mapped_column(Text, comment="Qué trabaja y para qué sirve.")
    start_position: Mapped[str | None] = mapped_column(Text, comment="Posición inicial.")
    instructions: Mapped[list] = mapped_column(JSONB, default=list, comment="Lista JSON de pasos de ejecución, en orden.")
    common_mistakes: Mapped[list] = mapped_column(JSONB, default=list, comment="Lista JSON de errores frecuentes.")
    image_url: Mapped[str | None] = mapped_column(Text, comment="Imagen/GIF demostrativo (solo contenido propio o con licencia). NULL si no hay.")
    video_url: Mapped[str | None] = mapped_column(Text, comment="Vídeo demostrativo (solo contenido propio o con licencia). NULL si no hay.")
    media_type: Mapped[str | None] = mapped_column(String(10), comment="Tipo del recurso visual: 'image' | 'gif' | 'video'.")
    media_credit: Mapped[str | None] = mapped_column(Text, comment="Autoría/licencia del recurso visual.")


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = {"comment": "Plan de entrenamiento estructurado. Solo uno activo por usuario; los anteriores se conservan como histórico."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del plan.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Propietario.")
    name: Mapped[str] = mapped_column(String(120), comment="Nombre del plan.")
    source: Mapped[str] = mapped_column(String(10), default="auto", comment="Origen: 'llm' (propuesto por la IA) | 'auto' (reglas por código) | 'manual'.")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), comment="TRUE = plan vigente.")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación.")


class TrainingPlanDay(Base):
    __tablename__ = "training_plan_days"
    __table_args__ = {"comment": "Día de entrenamiento de un plan (p. ej. «Día 1 · Pecho y tríceps»)."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador del día.")
    plan_id: Mapped[int] = mapped_column(ForeignKey("training_plans.id"), index=True, comment="Plan al que pertenece.")
    position: Mapped[int] = mapped_column(Integer, comment="Orden dentro del plan (0, 1, 2...).")
    label: Mapped[str] = mapped_column(String(120), comment="Título del día.")
    muscle_focus: Mapped[list] = mapped_column(JSONB, default=list, comment="Lista JSON de grupos musculares que se trabajan ese día.")


class TrainingPlanExercise(Base):
    __tablename__ = "training_plan_exercises"
    __table_args__ = {"comment": "Ejercicio de un día del plan. Referencia SIEMPRE un ejercicio real del catálogo."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    day_id: Mapped[int] = mapped_column(ForeignKey("training_plan_days.id"), index=True, comment="Día al que pertenece.")
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), comment="Ejercicio del catálogo (FK a exercises.id).")
    position: Mapped[int] = mapped_column(Integer, comment="Orden dentro del día.")
    sets: Mapped[int] = mapped_column(Integer, default=3, comment="Número de series objetivo.")
    reps_min: Mapped[int] = mapped_column(Integer, default=8, comment="Repeticiones objetivo (mínimo del rango).")
    reps_max: Mapped[int] = mapped_column(Integer, default=12, comment="Repeticiones objetivo (máximo del rango).")
    rest_s: Mapped[int | None] = mapped_column(Integer, comment="Descanso entre series, en segundos.")
    notes: Mapped[str | None] = mapped_column(Text, comment="Observaciones.")
    exercise: Mapped[Exercise] = relationship(lazy="joined")


# ═════════════════════════ Nutrición: raciones y recetas ═════════════════════════
class FoodServing(Base):
    __tablename__ = "food_servings"
    __table_args__ = (
        UniqueConstraint("food_id", "unit_name", name="uq_food_serving_unit"),
        {"comment": "Equivalencias orientativas entre unidades habituales y gramos, ESPECÍFICAS de cada alimento. "
                    "Internamente todo sigue calculándose en gramos."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), index=True, comment="Alimento al que aplica.")
    unit_name: Mapped[str] = mapped_column(String(40), comment="Unidad en singular (cucharada, rebanada...). 'ml' = mililitros (grams_per_unit = densidad).")
    unit_name_plural: Mapped[str | None] = mapped_column(String(40), comment="Plural (cucharadas, rebanadas...).")
    grams_per_unit: Mapped[float] = mapped_column(Float, comment="Gramos que equivale una unidad.")
    description: Mapped[str | None] = mapped_column(String(200), comment="Aclaración (p. ej. «rasa», «de unos 30 g»).")


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = {"comment": "Alimento compuesto: ingredientes + cantidades. user_id NULL = receta predefinida del sistema. "
                                 "Cada receta tiene un alimento «sombra» (foods.source='recipe') para poder buscarla y registrarla."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador de la receta.")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, comment="Propietario. NULL = receta del sistema.")
    name: Mapped[str] = mapped_column(String(200), comment="Nombre de la receta.")
    description: Mapped[str | None] = mapped_column(Text, comment="Descripción o notas.")
    steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, comment="Pasos ordenados para preparar la receta.")
    serving_count: Mapped[float] = mapped_column(Float, default=1, comment="Raciones que salen de la cantidad total de ingredientes.")
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), comment="Alimento sombra (por 100 g de plato terminado).")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Fecha de creación.")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        lazy="selectin", order_by="RecipeIngredient.id", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = {"comment": "Ingrediente de una receta: alimento + gramos (para la receta completa)."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True, comment="Receta.")
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), comment="Alimento ingrediente.")
    quantity_g: Mapped[float] = mapped_column(Float, comment="Gramos del ingrediente en la receta completa.")
    food: Mapped[Food] = relationship(lazy="joined")


# ═════════════════════════ Hábitos y bienestar ═════════════════════════
class HydrationLog(Base):
    __tablename__ = "hydration_logs"
    __table_args__ = {"comment": "Registro de agua: cada fila es una toma."}
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario.")
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="Instante del registro.")
    log_date: Mapped[date] = mapped_column(Date, index=True, comment="Día local al que se imputa.")
    quantity_ml: Mapped[int] = mapped_column(Integer, comment="Cantidad en ml.")
    source: Mapped[str] = mapped_column(String(10), default="manual", comment="'manual' | 'quick' (botón rápido) | 'import'.")


class DailyCheckIn(Base):
    __tablename__ = "daily_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "checkin_date", name="uq_checkin_user_date"),
        {"comment": "Check-in diario de bienestar (un registro por usuario y día, editable). PRIVADO: las notas nunca se envían a la IA."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario.")
    checkin_date: Mapped[date] = mapped_column(Date, comment="Día del check-in.")
    mood: Mapped[int] = mapped_column(Integer, comment="Estado emocional 1 (muy mal) a 5 (muy bien).")
    energy_level: Mapped[int | None] = mapped_column(Integer, comment="Energía 1-5 (opcional).")
    stress_level: Mapped[int | None] = mapped_column(Integer, comment="Estrés 1-5 (opcional; 5 = mucho estrés).")
    sleep_quality: Mapped[int | None] = mapped_column(Integer, comment="Calidad del descanso 1-5 (opcional).")
    notes: Mapped[str | None] = mapped_column(Text, comment="Nota personal privada.")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now(), onupdate=func.now(),
                                                 comment="Última edición.")


class DailyActivity(Base):
    __tablename__ = "daily_activity"
    __table_args__ = (
        UniqueConstraint("user_id", "activity_date", "source", name="uq_activity_user_date_source"),
        {"comment": "Actividad diaria normalizada (pasos, distancia, calorías activas) por fuente. La sincronización es idempotente: "
                    "reenviar el mismo día y fuente actualiza la fila."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario.")
    activity_date: Mapped[date] = mapped_column(Date, index=True, comment="Día local.")
    steps: Mapped[int] = mapped_column(Integer, default=0, comment="Pasos del día según esta fuente.")
    distance_km: Mapped[float | None] = mapped_column(Float, comment="Distancia (km).")
    active_calories: Mapped[float | None] = mapped_column(Float, comment="Calorías activas (kcal).")
    source: Mapped[str] = mapped_column(String(20), comment="'manual' | 'google_health' | 'health_connect' | 'samsung_health'.")
    external_id: Mapped[str | None] = mapped_column(String(120), comment="Id del registro en el proveedor (para trazabilidad).")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now(), comment="Última sincronización.")


class ActivityConnection(Base):
    __tablename__ = "activity_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_activity_conn_user_provider"),
        {"comment": "Consentimiento explícito del usuario para recibir datos de un proveedor de actividad. Revocable en cualquier momento."},
    )
    id: Mapped[int] = mapped_column(primary_key=True, comment="Identificador.")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, comment="Usuario.")
    provider: Mapped[str] = mapped_column(String(20), comment="'google_health' | 'health_connect' | 'samsung_health'.")
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="Cuándo dio su consentimiento.")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="Cuándo lo revocó (NULL = activo).")
