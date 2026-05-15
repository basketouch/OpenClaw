from datetime import datetime

import pytz

DEFINITION = {
    "name": "get_datetime",
    "description": "Obtiene la fecha y hora actual en la zona horaria especificada.",
    "input_schema": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Zona horaria IANA. Ejemplos: Europe/Madrid, America/Mexico_City, America/Bogota. Por defecto: Europe/Madrid",
            }
        },
        "required": [],
    },
}

_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def get_datetime(timezone: str = "Europe/Madrid") -> dict:
    try:
        tz = pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.timezone("Europe/Madrid")

    now = datetime.now(tz)
    return {
        "fecha": now.strftime("%d/%m/%Y"),
        "hora": now.strftime("%H:%M"),
        "dia_semana": _DAYS[now.weekday()],
        "timestamp_iso": now.isoformat(),
        "timezone": str(tz),
    }
