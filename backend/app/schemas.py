import datetime as dt
import math
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from .clock import age_on

Meal = Literal["breakfast", "lunch", "snack", "dinner"]


class FoodBase(BaseModel):
    """Valores nutricionales POR 100 g."""
    name: str = Field(min_length=1, max_length=300)
    brand: str | None = None
    barcode: str | None = None
    serving_g: float | None = None
    kcal: float = Field(0, ge=0)
    protein_g: float = Field(0, ge=0)
    carbs_g: float = Field(0, ge=0)
    sugars_g: float = Field(0, ge=0)
    fat_g: float = Field(0, ge=0)
    sat_fat_g: float = Field(0, ge=0)
    fiber_g: float = Field(0, ge=0)
    sodium_mg: float = Field(0, ge=0)


class FoodCreate(FoodBase):
    share: bool = Field(False, description="Ofrecerlo a la comunidad (requiere código de barras no ambiguo y datos coherentes)")


class FoodOut(FoodBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    source_url: str | None = None
    # Metadatos de Open Food Facts (None / vacío si no constan)
    image_url: str | None = None
    nutriscore_grade: str | None = None
    nova_group: int | None = None
    ecoscore_grade: str | None = None
    quantity: str | None = None
    allergens: list[str] = []
    ingredients: str | None = None
    categories: list[str] = []
    generic_name: str | None = None      # «Denominación general» en español
    original_name: str | None = None     # nombre original de OFF si se limpió o tradujo
    barcode_ambiguous: bool = False      # código de uso restringido de tienda (puede repetirse entre productos)
    user_id: int | None = None           # None = catálogo compartido (OFF / comunidad); si no, es tuyo
    share_status: str = "private"        # private | pending | verified (solo alimentos propios)
    confirmed_by: int | None = None      # usuarios que confirmaron un producto de la comunidad
    # Procedencia del dato (fuente, fiabilidad y licencia)
    external_id: str | None = None
    confidence: str | None = None        # high | medium | low
    license: str | None = None
    attribution: str | None = None


class BarcodeOut(BaseModel):
    status: str
    barcodes: list[str] = []
    food: FoodOut | None = None
    name: str | None = None
    brand: str | None = None


class FoodMineOut(FoodOut):
    times_used: int = 0                  # veces que lo has registrado en el diario


class FoodCopyIn(BaseModel):
    """Copia personal de cualquier alimento visible. Lo que no indiques se hereda del original."""
    name: str | None = Field(None, min_length=1, max_length=300)
    brand: str | None = None
    serving_g: float | None = Field(None, gt=0, le=5000)
    kcal: float | None = Field(None, ge=0, le=950)
    protein_g: float | None = Field(None, ge=0, le=100)
    carbs_g: float | None = Field(None, ge=0, le=100)
    sugars_g: float | None = Field(None, ge=0, le=100)
    fat_g: float | None = Field(None, ge=0, le=100)
    sat_fat_g: float | None = Field(None, ge=0, le=100)
    fiber_g: float | None = Field(None, ge=0, le=100)
    sodium_mg: float | None = Field(None, ge=0)


class LogCreate(BaseModel):
    """Cantidad en gramos, o en unidades de una ración del alimento (`serving_id` + `quantity`): 2 cucharadas, 3 lonchas...
    Internamente todo se guarda y calcula en gramos."""
    food_id: int
    grams: float | None = Field(None, gt=0, le=5000)
    serving_id: int | None = None
    quantity: float | None = Field(None, gt=0, le=1000)
    meal: Meal | None = None
    log_date: date | None = None

    @model_validator(mode="after")
    def _one_way(self):
        if self.serving_id is not None:
            if self.quantity is None:
                raise ValueError("Indica la cantidad de unidades")
        elif self.grams is None:
            raise ValueError("Indica los gramos o una unidad (serving_id y quantity)")
        return self


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    food: FoodOut
    logged_at: datetime
    log_date: date
    grams: float
    meal: str
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


class FrequentFood(BaseModel):
    food: FoodOut
    times: int
    typical_grams: float
    last_logged: datetime


SexCode = Literal["male", "female"]
ActivityCode = Literal["sedentary", "light", "moderate", "high", "very_high"]
GoalCode = Literal["gain_muscle", "lose_fat", "definition", "recomposition", "maintain"]
ExperienceCode = Literal["beginner", "intermediate", "advanced"]
MIN_AGE = 18


class ProfileIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sex: SexCode | None = None
    birth_date: date | None = None
    height_cm: float | None = Field(None, ge=100, le=250)
    activity_level: ActivityCode | None = None
    goal: GoalCode | None = None
    experience_level: ExperienceCode | None = None
    available_training_days: int | None = Field(None, ge=1, le=7)
    dietary_restrictions: str | None = Field(None, max_length=500)
    context_notes: str | None = Field(None, max_length=2000)

    @field_validator("birth_date")
    @classmethod
    def _adult(cls, v: date | None):
        if v is not None and not (MIN_AGE <= age_on(v) <= 100):
            raise ValueError(f"La app está pensada para personas de {MIN_AGE} a 100 años")
        return v


class OnboardingIn(ProfileIO):
    """Perfil inicial: todos los datos necesarios para calcular objetivos son obligatorios."""
    sex: SexCode
    birth_date: date
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(gt=30, lt=300)
    activity_level: ActivityCode
    goal: GoalCode
    experience_level: ExperienceCode
    available_training_days: int = Field(ge=1, le=7)


class TargetIO(BaseModel):
    """Objetivos editables a mano."""
    model_config = ConfigDict(from_attributes=True)
    kcal: float = Field(ge=800, le=8000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)
    fiber_g: float = Field(ge=0, le=200)
    workouts_per_week: int = Field(ge=0, le=14)
    water_ml: int | None = Field(None, ge=500, le=10000, description="Objetivo diario de agua (ml). Omitido = no cambia")
    steps_goal: int | None = Field(None, ge=1000, le=50000, description="Objetivo diario de pasos. Omitido = no cambia")


class TargetOut(TargetIO):
    training_plan: str | None = None
    rationale: str | None = None
    source: str = "manual"


class OnboardingOut(BaseModel):
    profile: ProfileIO
    targets: TargetOut
    bmr: float
    tdee: float


class Credentials(BaseModel):
    name: str = Field(min_length=3, max_length=40, description="Nombre de usuario")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("El nombre debe tener al menos 3 caracteres")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    onboarding_completed: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshSessionIn(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class WebSessionOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class DeleteAccountIn(BaseModel):
    password: str


WorkoutCategory = Literal["strength", "walking", "running", "sport", "full_body", "stretching"]
MuscleCode = Literal["abs", "forearms", "biceps", "neck", "lats", "lower_back", "upper_back", "shoulders", "chest", "traps",
                     "triceps", "abductors", "adductors", "quadriceps", "glutes", "hamstrings", "calves"]
EquipmentCode = Literal["none", "resistance_band", "suspension", "barbell", "dumbbell", "plate", "machine", "kettlebell",
                        "wheel", "medicine_ball", "bench", "box", "other"]
ExerciseKind = Literal["strength", "full_body", "stretching"]


class ExerciseIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    kind: ExerciseKind = "strength"
    primary_muscle: MuscleCode
    secondary_muscles: list[MuscleCode] = []
    equipment: list[EquipmentCode] = Field(default_factory=lambda: ["none"], min_length=1, max_length=6)

    @field_validator("equipment", mode="before")
    @classmethod
    def _equipment_list(cls, v):
        """Acepta un texto suelto (compatibilidad) o una lista; sin duplicados."""
        v = [v] if isinstance(v, str) else v
        return list(dict.fromkeys(v)) if isinstance(v, list) else v


class ExerciseOut(ExerciseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None = None


class SetIn(BaseModel):
    exercise_id: int
    reps: int = Field(ge=1, le=200)
    weight_kg: float | None = Field(None, ge=0, le=1000)
    reached_failure: bool | None = Field(None, description="¿Llegó al fallo muscular? None = sin indicar")
    rpe: float | None = Field(None, ge=1, le=10, description="OBSOLETO: se acepta por compatibilidad, la interfaz ya no lo usa")


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exercise_id: int
    set_number: int
    reps: int
    weight_kg: float | None = None
    reached_failure: bool | None = None
    rpe: float | None = None


class RoutePointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    altitude_m: float | None = Field(None, ge=-1000, le=10000)
    accuracy_m: float | None = Field(None, ge=0, le=10000)
    recorded_at: datetime


class WorkoutIn(BaseModel):
    performed_on: date | None = None
    kind: str = Field(min_length=1, max_length=100, description="Título de la sesión")
    category: WorkoutCategory | None = None
    duration_min: int = Field(gt=0, le=600)
    exercise_durations_min: dict[int, int] = Field(default_factory=dict, description="Minutos totales dedicados a cada ejercicio; la suma sustituye duration_min.")
    route_points: list[RoutePointIn] = Field(default_factory=list, max_length=10000)
    kcal_burned: float | None = Field(None, ge=0, le=10000, description="Si se indica, no se estima con IA")
    distance_km: float | None = Field(None, gt=0, le=500)
    elevation_gain_m: float | None = Field(None, ge=0, le=10000)
    steps: int | None = Field(None, ge=0, le=200000)
    avg_hr_bpm: int | None = Field(None, ge=30, le=230)
    notes: str | None = Field(None, max_length=1000)
    sets: list[SetIn] = Field(default=[], max_length=300)
    estimate_calories: bool = True

    @model_validator(mode="after")
    def total_duration_from_exercises(self):
        if self.route_points and self.category not in {"walking", "running"}:
            raise ValueError("La ruta GPS solo se puede guardar en sesiones de andar o correr.")
        if len(self.route_points) > 1:
            route_distance = 0.0
            for previous, current in zip(self.route_points, self.route_points[1:]):
                lat1, lat2 = math.radians(previous.lat), math.radians(current.lat)
                dlat = lat2 - lat1
                dlng = math.radians(current.lng - previous.lng)
                a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
                route_distance += 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
            if route_distance > 0:
                self.distance_km = round(route_distance, 3)
            elevation_gain = sum(
                max(0.0, current.altitude_m - previous.altitude_m)
                for previous, current in zip(self.route_points, self.route_points[1:])
                if previous.altitude_m is not None and current.altitude_m is not None
            )
            if elevation_gain > 0:
                self.elevation_gain_m = round(elevation_gain)
        if not self.exercise_durations_min:
            return self
        exercise_ids = {item.exercise_id for item in self.sets}
        duration_ids = set(self.exercise_durations_min)
        if duration_ids != exercise_ids:
            raise ValueError("Indica el tiempo de todos los ejercicios de la sesión.")
        if any(minutes < 1 or minutes > 600 for minutes in self.exercise_durations_min.values()):
            raise ValueError("Cada ejercicio debe tener entre 1 y 600 minutos.")
        total = sum(self.exercise_durations_min.values())
        if total > 600:
            raise ValueError("La duración total del entrenamiento no puede superar 600 minutos.")
        self.duration_min = total
        return self


class WorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    performed_on: date
    kind: str
    category: str | None = None
    duration_min: int
    exercise_durations_min: dict[int, int] = Field(default_factory=dict)
    route_points: list[dict] = Field(default_factory=list)
    kcal_burned: float | None = None
    kcal_source: str | None = None
    met: float | None = None
    intensity: str | None = None
    kcal_note: str | None = None
    distance_km: float | None = None
    elevation_gain_m: float | None = None
    steps: int | None = None
    avg_hr_bpm: int | None = None
    notes: str | None = None

    @computed_field
    @property
    def pace_min_km(self) -> float | None:
        """Ritmo medio en min/km (solo con distancia)."""
        return round(self.duration_min / self.distance_km, 2) if self.distance_km else None

    @computed_field
    @property
    def speed_kmh(self) -> float | None:
        return round(self.distance_km / (self.duration_min / 60), 2) if self.distance_km else None


class WorkoutExerciseOut(BaseModel):
    exercise_id: int
    exercise: str
    primary_muscle: str
    sets: list[dict]
    duration_min: int | None = None


class ExerciseFeedbackOut(BaseModel):
    exercise_id: int
    exercise: str
    status: Literal["personal_record", "progress", "maintain", "regression", "first_time", "insufficient_data"]
    message: str
    suggested_weight_kg: float | None = None
    personal_record: bool = False
    compared_with: date | None = None      # fecha de la sesión anterior usada como referencia


class WorkoutDetail(WorkoutOut):
    exercises: list[WorkoutExerciseOut] = []
    feedback: list[ExerciseFeedbackOut] = []


class LastSessionOut(BaseModel):
    """Resumen de la última vez que se hizo un ejercicio y su mejor marca histórica."""
    exercise_id: int
    has_history: bool
    date: dt.date | None = None            # (dt.date: el campo se llama «date» y sombrearía el tipo)
    sets: list[dict] = []
    max_weight_kg: float | None = None
    total_reps: int = 0
    any_failure: bool | None = None        # None si ninguna serie tiene el dato
    best_weight_kg: float | None = None    # mejor peso histórico
    best_weight_date: dt.date | None = None


class EnergyOut(BaseModel):
    """Gasto energético calculado por código (sin IA)."""
    age: int | None = None
    weight_kg: float | None = None
    bmr: float | None = None
    tdee: float | None = None
    missing: list[str] = []


class WeightIn(BaseModel):
    measured_on: date | None = None
    weight_kg: float = Field(gt=20, lt=400)
    body_fat_pct: float | None = Field(None, ge=1, le=70)


class WeightOut(WeightIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    measured_on: date


class ChatOut(BaseModel):
    conversation_id: int
    conversation_title: str
    reply: str
    sources: list[dict] = []
    tools_used: list[str] = []
    barcodes: list[str] = []
    transcription: str | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)
