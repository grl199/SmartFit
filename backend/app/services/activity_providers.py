"""Proveedores de actividad física. Todos acaban en la misma estructura normalizada (`DailyActivityIn`).

Estado honesto de cada integración:
  - Health Connect y Samsung Health Data SDK son SDK de Android: no se pueden llamar desde Streamlit/FastAPI. El camino es una pequeña app
    Android complementaria que lee los datos (con el permiso del usuario) y los envía a `POST /activity/sync` con su token. El backend
    ya lo soporta (consentimiento, idempotencia y deduplicación); la app Android NO está incluida en este repositorio.
  - Google Health API (OAuth desde el backend): requiere registrar la app en Google y obtener credenciales; no están configuradas, por
    lo que `GoogleHealthProvider.fetch_daily` lanza `ProviderNotConfigured`. Los tokens OAuth, cuando existan, deben guardarse cifrados
    (nunca en texto plano).
  - Google Fit: no se usa (sus APIs se retiran a finales de 2026)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from pydantic import BaseModel, Field

PROVIDERS = {
    "google_health": {"label": "Google Health", "mode": "pull", "configured": False,
                      "note": "Integración OAuth desde el servidor pendiente de credenciales de Google."},
    "health_connect": {"label": "Health Connect (Android)", "mode": "push", "configured": True,
                       "note": "Requiere la app Android complementaria, que envía los datos a /activity/sync."},
    "samsung_health": {"label": "Samsung Health", "mode": "push", "configured": True,
                       "note": "Requiere la app Android complementaria (Samsung Health Data SDK)."},
}
SOURCES = ("manual", *PROVIDERS)


class ProviderNotConfigured(RuntimeError):
    pass


class DailyActivityIn(BaseModel):
    """Formato normalizado que devuelven todos los proveedores (y que acepta /activity/sync)."""
    activity_date: date
    steps: int = Field(ge=0, le=200_000)
    distance_km: float | None = Field(None, ge=0, le=500)
    active_calories: float | None = Field(None, ge=0, le=20_000)
    external_id: str | None = Field(None, max_length=120)


class ActivityProvider(ABC):
    name: str

    @abstractmethod
    def fetch_daily(self, start: date, end: date) -> list[DailyActivityIn]: ...


class GoogleHealthProvider(ActivityProvider):
    name = "google_health"

    def fetch_daily(self, start: date, end: date) -> list[DailyActivityIn]:
        raise ProviderNotConfigured("Google Health API no está configurada (faltan credenciales OAuth).")


class PushProvider(ActivityProvider):
    """Health Connect / Samsung Health: los datos llegan desde la app móvil por /activity/sync; no hay nada que consultar."""
    def __init__(self, name: str):
        self.name = name

    def fetch_daily(self, start: date, end: date) -> list[DailyActivityIn]:
        return []


def get_provider(name: str) -> ActivityProvider:
    if name == "google_health":
        return GoogleHealthProvider()
    if name in PROVIDERS:
        return PushProvider(name)
    raise KeyError(name)
