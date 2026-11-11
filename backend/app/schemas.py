from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ProfileIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sex: str | None = None
    birth_date: date | None = None
    height_cm: float | None = Field(None, gt=0, lt=300)
    activity_level: str | None = None
    goal: str | None = None
    dietary_restrictions: str | None = None
    context_notes: str | None = None


class TargetIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kcal: float = Field(gt=0)
    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    fiber_g: float = Field(ge=0)
    workouts_per_week: int = Field(ge=0, le=14)


class WorkoutIn(BaseModel):
    performed_on: date | None = None
    kind: str = Field(min_length=1, max_length=100)
    duration_min: int = Field(gt=0, le=600)
    kcal_burned: float | None = Field(None, ge=0)
    notes: str | None = None


class WorkoutOut(WorkoutIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    performed_on: date


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
