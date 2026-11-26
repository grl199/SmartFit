"""Fecha local de la app y cálculo de edad en un único sitio.

Antes la edad se calculaba en tres lugares con `date.today()` (zona horaria del servidor); ahora todo usa la
zona horaria configurada (`settings.timezone`), de modo que el cumpleaños cambia a medianoche HORA LOCAL."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import get_settings


def now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def today_local() -> date:
    return now_local().date()


def age_on(birth: date, today: date | None = None) -> int:
    """Edad cumplida en `today` (por defecto, hoy en la zona horaria local)."""
    t = today or today_local()
    return t.year - birth.year - ((t.month, t.day) < (birth.month, birth.day))
