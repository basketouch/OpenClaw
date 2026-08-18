from datetime import datetime

import pytz

DEFINITION = {
    "name": "get_datetime",
    "description": "Obtiene la fecha y hora actual. Si no se indica zona horaria, usa la configurada para Jorge.",
    "input_schema": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Zona horaria IANA opcional. Ejemplos: Europe/Madrid, Asia/Jakarta, America/Bogota.",
            }
        },
        "required": [],
    },
}

_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def get_datetime(timezone: str | None = None) -> dict:
    from config import get_settings

    fallback = get_settings().user_timezone
    tz_name = timezone or fallback
    try:
        tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        try:
            tz = pytz.timezone(fallback)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.UTC

    now = datetime.now(tz)
    return {
        "fecha": now.strftime("%d/%m/%Y"),
        "hora": now.strftime("%H:%M"),
        "dia_semana": _DAYS[now.weekday()],
        "timestamp_iso": now.isoformat(),
        "timezone": str(tz),
    }
