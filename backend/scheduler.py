import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_JOBS_FILE = "/data/scheduler_jobs.json"


def _load_jobs() -> list[dict]:
    try:
        with open(_JOBS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_jobs(jobs: list[dict]):
    os.makedirs(os.path.dirname(_JOBS_FILE), exist_ok=True)
    with open(_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False, default=str)


def _timezone_name() -> str:
    from config import get_settings
    name = get_settings().user_timezone
    try:
        pytz.timezone(name)
        return name
    except pytz.exceptions.UnknownTimeZoneError:
        return "Europe/Madrid"


def _make_trigger(schedule_type: str, params: dict):
    if schedule_type == "cron":
        return CronTrigger(**params, timezone=_timezone_name())
    if schedule_type == "interval":
        return IntervalTrigger(**params)
    if schedule_type == "date":
        return DateTrigger(**params, timezone=_timezone_name())
    raise ValueError(f"Tipo de schedule desconocido: {schedule_type}")


def _serialize_output_items(response) -> list[dict]:
    return [
        item.model_dump(exclude_none=True)
        for item in response.output
        if hasattr(item, "model_dump")
    ]


async def _run_job_openai(system: str, prompt: str) -> str:
    from config import get_openai_client, get_settings
    from tools.registry import execute_tool, get_openai_tool_definitions

    settings = get_settings()
    client = get_openai_client()
    tools = get_openai_tool_definitions()
    input_items: list[dict] = [{"role": "user", "content": prompt}]

    for _ in range(8):
        response = await client.responses.create(
            model=settings.alex_model,
            instructions=system,
            input=input_items,
            tools=tools,
            tool_choice="auto",
            reasoning={"effort": "low"},
            max_output_tokens=4096,
            store=False,
        )

        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            return (response.output_text or "Tarea ejecutada.")[:500]

        input_items.extend(_serialize_output_items(response))
        for call in calls:
            try:
                args = json.loads(call.arguments or "{}")
                out = await execute_tool(call.name, args)
                output = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
            except Exception as exc:
                output = f"Error ejecutando {call.name}: {exc}"
            input_items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": output,
            })

    return "La tarea alcanzó el máximo de pasos permitidos."


async def _run_job(job_id: str, name: str, prompt: str):
    from config import get_settings

    log.info("Scheduler: ejecutando tarea '%s' (%s)", name, job_id)
    settings = get_settings()
    if not settings.openai_api_key:
        log.error("Scheduler: OPENAI_API_KEY no está configurada")
        return

    tz_name = _timezone_name()
    now = datetime.now(timezone.utc).astimezone(pytz.timezone(tz_name)).strftime("%A, %d de %B de %Y, %H:%M")
    system = (
        f"Eres Alex, asistente operativo de Jorge. Ahora son las {now} ({tz_name}).\n"
        "Estás ejecutando una tarea programada. Completa la tarea directamente con las herramientas disponibles. "
        "No inventes resultados de herramientas. No ejecutes acciones destructivas de servidor salvo que la tarea "
        "programada las solicite de forma explícita."
    )

    final_text = await _run_job_openai(system, prompt)
    log.info("Scheduler: tarea '%s' completada", name)

    try:
        import push
        await asyncio.to_thread(push.send_notification, f"✓ {name}", final_text)
    except Exception as exc:
        log.warning("Push notification failed: %s", exc)
    try:
        from tools.telegram_tool import send_telegram
        await send_telegram(f"<b>✓ {name}</b>\n{final_text}")
    except Exception as exc:
        log.warning("Telegram notification failed: %s", exc)

    # A one-time reminder should not return after a server restart.
    jobs = _load_jobs()
    if any(job.get("id") == job_id and job.get("schedule_type") == "date" for job in jobs):
        _save_jobs([job for job in jobs if job.get("id") != job_id])


def _reload_jobs():
    for job in _scheduler.get_jobs():
        if job.id.startswith("uj_"):
            job.remove()

    for jd in _load_jobs():
        if not jd.get("enabled", True):
            continue
        try:
            trigger = _make_trigger(jd["schedule_type"], jd["schedule_params"])
            _scheduler.add_job(
                _run_job,
                trigger=trigger,
                id=f"uj_{jd['id']}",
                args=[jd["id"], jd["name"], jd["prompt"]],
                replace_existing=True,
                misfire_grace_time=300,
            )
            log.info("Scheduler: cargada tarea '%s'", jd["name"])
        except Exception as exc:
            log.error("Scheduler: error al cargar tarea %s: %s", jd["id"], exc)


def start():
    _reload_jobs()
    _scheduler.start()
    log.info("Scheduler iniciado con %d tareas", len(_scheduler.get_jobs()))


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def create_job(name: str, prompt: str, schedule_type: str, schedule_params: dict) -> dict:
    name = name.strip()
    prompt = prompt.strip()
    if not name or not prompt:
        raise ValueError("El título y el mensaje son obligatorios")
    _make_trigger(schedule_type, schedule_params)
    job = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "prompt": prompt,
        "schedule_type": schedule_type,
        "schedule_params": schedule_params,
        "enabled": True,
        "created": datetime.now().isoformat(),
    }
    jobs = _load_jobs()
    jobs.append(job)
    _save_jobs(jobs)
    _reload_jobs()
    return job


def list_jobs() -> list[dict]:
    jobs = _load_jobs()
    running = {j.id for j in _scheduler.get_jobs()}
    for job in jobs:
        job["active"] = f"uj_{job['id']}" in running
    return jobs


def delete_job(job_id: str) -> bool:
    jobs = _load_jobs()
    new = [j for j in jobs if j["id"] != job_id]
    if len(new) == len(jobs):
        return False
    _save_jobs(new)
    _reload_jobs()
    return True


def toggle_job(job_id: str, enabled: bool) -> bool:
    jobs = _load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["enabled"] = enabled
            _save_jobs(jobs)
            _reload_jobs()
            return True
    return False


def update_job(job_id: str, name: str, prompt: str, schedule_type: str, schedule_params: dict) -> dict | None:
    name = name.strip()
    prompt = prompt.strip()
    if not name or not prompt:
        raise ValueError("El título y el mensaje son obligatorios")
    _make_trigger(schedule_type, schedule_params)
    jobs = _load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job.update({
                "name": name,
                "prompt": prompt,
                "schedule_type": schedule_type,
                "schedule_params": schedule_params,
            })
            _save_jobs(jobs)
            _reload_jobs()
            return job
    return None
