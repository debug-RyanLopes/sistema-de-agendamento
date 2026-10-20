import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import CONFIG

FUSO = ZoneInfo(CONFIG.timezone)


def agora_local() -> datetime:
    """Hora de parede no fuso configurado (Manaus por padrão), sem tzinfo, como no banco."""
    return datetime.now(FUSO).replace(tzinfo=None)


def ultimo_dia_do_mes(dia: date) -> date:
    return dia.replace(day=calendar.monthrange(dia.year, dia.month)[1])
