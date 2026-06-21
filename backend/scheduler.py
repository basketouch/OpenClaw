import asyncio
import json
import logging
import os
import uuid
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_JOBS_FILE = "/data/scheduler_jobs.json"


def _load_jobs() -> list[dict]:
    try:
        with open(_JOBS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_jobs(jobs: list[dict]):
    os.makedirs(os.path.dirname(_JOBS_FILE), exist_ok=True)
    with open(_JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False, default=str)


def _make_trigger(schedule_type: str, params: dict):
    if schedule_type == "cron":
        return CronTrigger(**params, timezone="Europe/Madrid")
    if schedule_type == "interval":
        return IntervalTrigger(**params)
    raise ValueError(f"Tipo de schedule desconocido: {schedule_type}")


async def _run_job_anthropic(system: str, prompt: str) -> str:
    from tools.registry import execute_tool, get_tool_definitions
    from config import get_ai_client_and_model

    client, model = get_ai_client_and_model()
    messages = [{"role": "user", "content": prompt}]
    final_text = "Tarea ejecutada."

    for _ in range(10):
        resp = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=get_tool_definitions(),
            messages=messages,
        )

        if resp.stop_reason == "end_turn":
            final_text = next(
                (b.text[:140] for b in resp.content if hasattr(b, "text") and b.text),
                "Tarea ejecutada.",
            )
            break

        if resp.stop_reason == "tool_use":
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = await execute_tool(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, ensure_ascii=False, default=str),
                    })
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": results})
        else:
            break

    return final_text


async def _run_job_groq(system: str, prompt: str) -> str:
    from tools.registry import execute_tool, get_tool_definitions
    from config import get_groq_client_and_model
    from groq_compat import to_openai_tools

    client, model = get_groq_client_and_model()
    tools = to_openai_tools(get_tool_definitions())
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    final_text = "Tarea ejecutada."

    for _ in range(10):
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=messages,
            tools=tools,
        )
        choice = resp.choices[0]
        msg = choice.message

        if choice.finish_reason != "tool_calls" or not msg.tool_calls:
            final_text = (msg.content or "Tarea ejecutada.")[:140]
            break

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                out = await execute_tool(tc.function.name, args)
            except Exception as e:
                out = f"Error: {e}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(out, ensure_ascii=False, default=str),
            })

    return final_text


async def _run_job(job_id: str, name: str, prompt: str):
    from config import get_settings

    log.info("Scheduler: ejecutando tarea '%s' (%s)", name, job_id)
    settings = get_settings()

    if settings.model_provider == "groq":
        if not settings.groq_api_key:
            log.error("Scheduler: no hay GROQ_API_KEY configurada")
            return
    elif not settings.anthropic_api_key and not (settings.model_provider == "glm" and settings.glm_api_key):
        log.error("Scheduler: no hay API key configurada")
        return

    from datetime import timezone as _utc
    now = datetime.now(_utc.utc).astimezone(pytz.timezone("Europe/Madrid")).strftime("%A, %d de %B de %Y, %H:%M")
    system = (
        f"Eres Alex, asistente operativo de Jorge. Ahora son las {now} (hora Madrid).\n"
        "Estás ejecutando una tarea programada de forma autónoma. "
        "Completa la tarea directamente con las herramientas disponibles sin pedir confirmación."
    )

    if settings.model_provider == "groq":
        final_text = await _run_job_groq(system, prompt)
    else:
        final_text = await _run_job_anthropic(system, prompt)

    log.info("Scheduler: tarea '%s' completada", name)
    try:
        import push
        await asyncio.to_thread(push.send_notification, f"✓ {name}", final_text)
    except Exception as e:
        log.warning("Push notification failed: %s", e)
    try:
        from tools.telegram_tool import send_telegram
        await send_telegram(f"<b>✓ {name}</b>\n{final_text}")
    except Exception as e:
        log.warning("Telegram notification failed: %s", e)


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
        except Exception as e:
            log.error("Scheduler: error al cargar tarea %s: %s", jd["id"], e)


def start():
    _reload_jobs()
    _scheduler.start()
    log.info("Scheduler iniciado con %d tareas", len(_scheduler.get_jobs()))


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


# ─── API pública para las tools ──────────────────────────────────────────────

def create_job(name: str, prompt: str, schedule_type: str, schedule_params: dict) -> dict:
    _make_trigger(schedule_type, schedule_params)  # valida antes de guardar
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
    for j in jobs:
        j["active"] = f"uj_{j['id']}" in running
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
    for j in jobs:
        if j["id"] == job_id:
            j["enabled"] = enabled
            _save_jobs(jobs)
            _reload_jobs()
            return True
    return False
