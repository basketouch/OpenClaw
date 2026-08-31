import scheduler as sched

CREATE_DEF = {
    "name": "create_scheduled_task",
    "description": (
        "Crea una tarea programada que Alex ejecutará automáticamente. "
        "Puede enviar mensajes por Telegram, revisar emails, crear resúmenes, etc. "
        "Para cron usa schedule_type='cron' con params como {hour:9,minute:0}. "
        "Para una sola vez usa schedule_type='date' con {run_date:'2030-01-01T09:00:00+07:00'}. "
        "Para repetir cada N horas/minutos usa schedule_type='interval' con {hours:2}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nombre descriptivo de la tarea"},
            "prompt": {
                "type": "string",
                "description": (
                    "Instrucción completa de lo que Alex hará al ejecutarse. "
                    "Ej: 'Revisa mis emails no leídos y mándame un resumen por Telegram a Jorge'"
                ),
            },
            "schedule_type": {
                "type": "string",
                "enum": ["cron", "date", "interval"],
                "description": "cron: hora fija. date: una sola vez. interval: cada N minutos/horas",
            },
            "schedule_params": {
                "type": "object",
                "description": (
                    "cron: {hour:9, minute:0} o {hour:9, minute:0, day_of_week:'mon-fri'}. "
                    "date: {run_date:'2030-01-01T09:00:00+07:00'}. "
                    "interval: {minutes:30} o {hours:2}"
                ),
            },
        },
        "required": ["name", "prompt", "schedule_type", "schedule_params"],
    },
}


def create_scheduled_task(name: str, prompt: str, schedule_type: str, schedule_params: dict) -> dict:
    try:
        job = sched.create_job(name, prompt, schedule_type, schedule_params)
        return {"success": True, "tarea": job, "mensaje": f"Tarea '{name}' programada correctamente."}
    except Exception as e:
        return {"success": False, "error": str(e)}


LIST_DEF = {
    "name": "list_scheduled_tasks",
    "description": "Lista todas las tareas programadas con su estado y horario.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def list_scheduled_tasks() -> dict:
    jobs = sched.list_jobs()
    if not jobs:
        return {"tareas": [], "mensaje": "No hay tareas programadas todavía."}
    return {"tareas": jobs}


DELETE_DEF = {
    "name": "delete_scheduled_task",
    "description": "Elimina una tarea programada por su ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "ID de la tarea a eliminar"},
        },
        "required": ["job_id"],
    },
}


def delete_scheduled_task(job_id: str) -> dict:
    ok = sched.delete_job(job_id)
    return {"success": ok, "mensaje": "Tarea eliminada." if ok else f"No se encontró la tarea {job_id}."}


TOGGLE_DEF = {
    "name": "toggle_scheduled_task",
    "description": "Activa o desactiva una tarea programada sin eliminarla.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "ID de la tarea"},
            "enabled": {"type": "boolean", "description": "true para activar, false para pausar"},
        },
        "required": ["job_id", "enabled"],
    },
}


def toggle_scheduled_task(job_id: str, enabled: bool) -> dict:
    ok = sched.toggle_job(job_id, enabled)
    estado = "activada" if enabled else "pausada"
    return {"success": ok, "mensaje": f"Tarea {estado}." if ok else f"No se encontró la tarea {job_id}."}
