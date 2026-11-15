from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    pass


class FoodOut(FoodBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    # Metadatos de Open Food Facts (None / vacío si no constan)
    image_url: str | None = None
    nutriscore_grade: str | None = None
    nova_group: int | None = None
    ecoscore_grade: str | None = None
    quantity: str | None = None
    allergens: list[str] = []
    ingredients: str | None = None
    categories: list[str] = []


class BarcodeOut(BaseModel):
    status: str
    barcodes: list[str] = []
    food: FoodOut | None = None
    name: str | None = None
    brand: str | None = None


class LogCreate(BaseModel):
    food_id: int
    grams: float = Field(gt=0, le=5000)
    meal: Meal | None = None
    log_date: date | None = None


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


def _age(birth: date) -> int:
    t = date.today()
    return t.year - birth.year - ((t.month, t.day) < (birth.month, birth.day))


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
        if v is not None and not (MIN_AGE <= _age(v) <= 100):
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


class DeleteAccountIn(BaseModel):
    password: str


WorkoutCategory = Literal["legs", "push", "pull", "upper", "full_body", "core", "cardio", "other"]
MuscleCode = Literal["chest", "lats", "upper_back", "lower_back", "shoulders", "biceps", "triceps", "forearms", "abs",
                     "obliques", "glutes", "quadriceps", "hamstrings", "adductors", "abductors", "calves"]
EquipmentCode = Literal["barbell", "dumbbell", "machine", "cable", "bodyweight", "other"]


class ExerciseIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    primary_muscle: MuscleCode
    secondary_muscles: list[MuscleCode] = []
    equipment: EquipmentCode = "other"


class ExerciseOut(ExerciseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None = None


class SetIn(BaseModel):
    exercise_id: int
    reps: int = Field(ge=1, le=200)
    weight_kg: float | None = Field(None, ge=0, le=1000)
    rpe: float | None = Field(None, ge=1, le=10)


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exercise_id: int
    set_number: int
    reps: int
    weight_kg: float | None = None
    rpe: float | None = None


class WorkoutIn(BaseModel):
    performed_on: date | None = None
    kind: str = Field(min_length=1, max_length=100, description="Título de la sesión")
    category: WorkoutCategory | None = None
    duration_min: int = Field(gt=0, le=600)
    kcal_burned: float | None = Field(None, ge=0, le=10000, description="Si se indica, no se estima con IA")
    notes: str | None = Field(None, max_length=1000)
    sets: list[SetIn] = Field(default=[], max_length=300)
    estimate_calories: bool = True


class WorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    performed_on: date
    kind: str
    category: str | None = None
    duration_min: int
    kcal_burned: float | None = None
    kcal_source: str | None = None
    met: float | None = None
    intensity: str | None = None
    kcal_note: str | None = None
    notes: str | None = None


class WorkoutExerciseOut(BaseModel):
    exercise_id: int
    exercise: str
    primary_muscle: str
    sets: list[dict]


class WorkoutDetail(WorkoutOut):
    exercises: list[WorkoutExerciseOut] = []


class WeightIn(BaseModel):
    measured_on: date | None = None
    weight_kg: float = Field(gt=20, lt=400)
    body_fat_pct: float | None = Field(None, ge=1, le=70)


class WeightOut(WeightIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    measured_on: date


class ChatOut(BaseModel):
    reply: str
    sources: list[dict] = []
    tools_used: list[str] = []
    barcodes: list[str] = []


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role: str
    content: str
    created_at: datetime
