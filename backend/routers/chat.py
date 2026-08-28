import base64
import json
import os
import time
from datetime import datetime, timezone

import pytz
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import verify_token
from config import get_openai_client, get_settings
from context_profiles import instructions_for_context
from tools.registry import execute_tool, get_profile_tools

router = APIRouter(prefix="/api", tags=["chat"])
_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_USAGE_FILE = "/data/ai_usage.jsonl"

_ALEX_BASE = """Eres Alex, el asistente operativo personal de Jorge.

Tu objetivo es resolver tareas con fiabilidad y el mínimo trabajo posible para Jorge.

Principios:
- Responde en español por defecto, salvo que el usuario use otro idioma o pida otro.
- Sé directo, práctico y orientado a la acción.
- No inventes datos que puedas obtener con una herramienta disponible.
- Usa herramientas cuando sean necesarias; no digas que has hecho algo si no has ejecutado la herramienta correspondiente.
- Si una herramienta falla, explica brevemente qué falló y conserva el error real.
- No repitas preguntas cuya respuesta ya esté en el contexto.
- Para acciones simples y reversibles, actúa directamente.
- Antes de acciones destructivas o irreversibles de servidor, confirma.
- No expongas secretos, tokens ni contraseñas.
- Mantén respuestas compactas salvo que Jorge pida detalle.
- Para consultar Notion, usa search_notion y después read_notion_page; busca antes de decir que algo no está allí.
- English Coach es transversal a cualquier contexto: traduce, corrige y practica inglés sin cambiar de conversación. Si Jorge pide guardar una frase inglesa, una traducción o un chunk, usa save_english_phrase en su biblioteca de English Coach; no la guardes en Notion. Para otras notas, “guárdalo” significa Notion: busca primero una página existente y léela. Si el destino inequívoco es una base, lee su esquema y crea o actualiza sus propiedades válidas. Para contenido nuevo usa create_notion_database_record con template y sections; para un registro existente usa append_notion_rich_blocks. Elige template: hornbills_review, product_update, marketing_proposal, action o structured_note. Esto crea bloques reales de Notion (títulos, listas, callouts y checks), no Markdown como texto. Nunca reemplaces contenido existente salvo petición explícita y nunca digas que está guardado sin ejecutar la herramienta.
- Para novedades: verifica primero el contexto en Notion. Clasifica hechos, decisiones, métricas e incidencias en su contexto; usa Acciones solo para trabajo pendiente y deja como Inbox lo que no requiera trabajo inmediato.
- Antes de crear una acción, consulta query_notion_actions para evitar duplicados. Usa upsert_notion_action para crear o actualizar una acción y completa proyecto, estado, prioridad, semana, resultado esperado, próximo paso, bloqueo y contexto cuando se conozcan.
- No crees más de cinco acciones con estado “Esta semana”: la herramienta lo bloqueará. Si falta información relevante, indica el bloqueo o pide confirmación.

NewsFlow:
- articles: noticias y artículos curados.
- social_posts: publicaciones LinkedIn/X.
- newsletter_status: ediciones de INSIDE Life.
- publish_queue: vídeos pendientes.
Cuando la consulta sea de NewsFlow, usa sus herramientas y no supongas el estado actual.
"""

_ENGLISH_BASE = """Eres English Coach, el asistente personal de inglés de Jorge.

Objetivo: mejorar su inglés hablado y profesional usando situaciones reales de baloncesto, staff, reuniones, academia, negocio y vida diaria.

Reglas:
- Jorge es español y prioriza inglés funcional, natural y fácil de producir oralmente.
- Corrige solo lo que importa; no conviertas una frase correcta y simple en inglés innecesariamente sofisticado.
- Prioriza chunks y frases completas sobre listas de vocabulario aislado.
- Cuando propongas una frase, ofrece primero la versión más útil y natural para decirla en voz alta.
- En baloncesto, conserva terminología habitual internacional (spacing, closeout, low man, drop, switch, etc.).
- Si Jorge escribe en español preguntando cómo decir algo, responde primero con la frase inglesa y después una explicación breve.
- Si practica conversación, no interrumpas cada frase: deja que termine y corrige después los errores de mayor impacto.
- Si Jorge dice “guárdalo”, “esto me cuesta”, “lo uso mucho” o equivalente, usa save_english_phrase.
- Antes de guardar, prioriza frases reutilizables y chunks; evita almacenar ruido o palabras triviales.
- Si pide repasar, usa get_english_review y construye ejercicios solo con su material guardado.
- Si responde a un ejercicio, registra el resultado con record_english_result cuando la frase esté identificada.
- Si pregunta por su progreso, usa get_english_progress.
- Si pide buscar, listar o consultar frases guardadas, usa search_english_phrases.
- El resultado de search_english_phrases es la fuente de verdad: si count es mayor que 0, muestra las frases devueltas; di que no hay frases solo si count es 0.
- Puedes consultar material relacionado en Notion con search_notion y read_notion_page cuando Jorge lo pida.
"""


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    mode: str = "auto"  # auto | general | english | admin | newsflow | communications
    file_id: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    workspace_id: str = "general"
    project_id: str | None = None
    scope_source: str = "auto"  # auto sessions persist; manual assignments always win
    assist_context: str | None = None  # temporary specialist help; does not move the chat


def _build_instructions(mode: str, workspace_id: str = "general", project_id: str | None = None) -> str:
    settings = get_settings()
    try:
        tz = pytz.timezone(settings.user_timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(timezone.utc).astimezone(tz)
    fecha = f"{_DAYS[now.weekday()]}, {now.strftime('%d/%m/%Y')} — {now.strftime('%H:%M')} ({tz.zone})"
    base = _ENGLISH_BASE if mode == "english" else _ALEX_BASE
    # Context policy lives outside the visual workspace catalogue. It is the
    # extension point for scoped instructions, memory retrieval and tools.
    scope = f"workspace={workspace_id}" + (f", project={project_id}" if project_id else "")
    context_instructions = instructions_for_context(workspace_id, project_id)
    return f"{base}\n\nContexto de trabajo activo: {scope}\n{context_instructions}\nFecha y hora actual: {fecha}"


def _last_user_text(request: ChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content.strip()
    return ""


def _route_mode(request: ChatRequest) -> str:
    if request.assist_context == "english":
        return "english"
    if request.workspace_id == "english":
        return "english"
    if request.mode != "auto":
        return request.mode
    text = _last_user_text(request).lower()

    english_markers = (
        "english coach", "inglés", "ingles", "cómo digo", "como digo", "translate to english",
        "corrige mi inglés", "corrige mi ingles", "practiquemos inglés", "practice english",
        "guarda esta frase", "repasemos inglés", "repasemos ingles",
    )
    if any(marker in text for marker in english_markers):
        return "english"

    admin_markers = (
        "vps", "docker", "deploy", "desplieg", "servidor", "systemctl", "journalctl",
        "reinicia", "logs del servidor", "contenedor",
    )
    if any(marker in text for marker in admin_markers):
        return "admin"

    newsflow_markers = (
        "newsflow", "newsletter", "inside life", "social_posts", "publish_queue",
        "artículos curados", "articulos curados",
    )
    if any(marker in text for marker in newsflow_markers):
        return "newsflow"

    communication_markers = (
        "email", "correo", "gmail", "telegram", "mensaje a ", "escribe a ",
        "respóndele", "respondele", "contesta a ",
    )
    if any(marker in text for marker in communication_markers):
        return "communications"

    return "general"


def _route_scope(request: ChatRequest) -> tuple[str, str | None]:
    """Fast deterministic context router. Manual assignment is never overridden."""
    if request.scope_source == "manual":
        return request.workspace_id, request.project_id
    # Preserve the auto-selected context for a continuing conversation.
    if request.workspace_id in {"hornbills", "english"} or request.project_id:
        return request.workspace_id, request.project_id

    text = _last_user_text(request).lower()
    project_markers = {
        "cutsports": "cutsports", "cut sports": "cutsports",
        "drawsports": "drawsports", "draw sports": "drawsports",
        "the analyst": "the-analyst", "comunidad": "comunidad",
        "basketouch hub": "basketouch-hub", "basketouch": "basketouch-hub",
    }
    for marker, project_id in project_markers.items():
        if marker in text:
            return "projects", project_id
    hornbills_markers = ("hornbills", "hornbill", "bogor", "césar", "cesar", "video review", "vídeo", "video", "pnr", "pick and roll")
    if any(marker in text for marker in hornbills_markers):
        return "hornbills", None
    english_markers = ("english coach", "inglés", "ingles", "cómo digo", "como digo", "translate to english", "practice english")
    if any(marker in text for marker in english_markers):
        return "english", None
    return "general", None


def _select_model(request: ChatRequest, mode: str) -> tuple[str, str]:
    settings = get_settings()
    if mode == "english":
        return settings.english_model, "low"

    text = _last_user_text(request).lower()
    complex_markers = (
        "debug", "refactor", "arquitectura", "analiza a fondo", "investiga a fondo",
        "revisa el código", "revisa el codigo", "diseña", "diseña una arquitectura",
    )
    is_complex = mode == "admin" or len(text) > 2500 or any(x in text for x in complex_markers)
    if is_complex:
        return settings.alex_complex_model, "medium"
    return settings.alex_model, "low"


def _profile_for_mode(mode: str, workspace_id: str = "general", project_id: str | None = None) -> str:
    # Hornbills uses its own restricted Notion capture profile while retaining
    # the general response style and model.
    if mode == "hornbills":
        return "hornbills"
    if workspace_id == "projects" and project_id == "cutsports":
        return "cutsports"
    if workspace_id == "projects" and project_id == "drawsports":
        return "drawsports"
    if workspace_id == "projects" and project_id == "the-analyst":
        return "the_analyst"
    if workspace_id == "projects" and project_id == "comunidad":
        return "comunidad"
    if workspace_id == "projects" and project_id == "basketouch-hub":
        return "basketouch_hub"
    if mode in {"admin", "newsflow", "communications", "english"}:
        return mode
    return "general"


def _find_upload(file_id: str) -> str | None:
    uploads_dir = "/data/uploads"
    if not os.path.isdir(uploads_dir):
        return None
    for fname in os.listdir(uploads_dir):
        if fname.startswith(f"{file_id}_"):
            return os.path.join(uploads_dir, fname)
    return None


def _build_file_content(file_id: str, filename: str, mime_type: str) -> dict | None:
    path = _find_upload(file_id)
    if not path:
        return None
    with open(path, "rb") as f:
        data = f.read()

    if mime_type.startswith("image/"):
        b64 = base64.b64encode(data).decode()
        return {"type": "input_image", "image_url": f"data:{mime_type};base64,{b64}"}

    if mime_type == "application/pdf":
        b64 = base64.b64encode(data).decode()
        return {
            "type": "input_file",
            "filename": filename,
            "file_data": f"data:application/pdf;base64,{b64}",
        }

    try:
        text = data.decode("utf-8", errors="replace")
        return {"type": "input_text", "text": f"[Archivo: {filename}]\n\n{text}"}
    except Exception:
        return None


def _build_input(request: ChatRequest) -> list[dict]:
    messages = request.messages[-16:]
    result: list[dict] = []
    for i, message in enumerate(messages):
        role = message.role if message.role in {"user", "assistant"} else "user"
        is_last = i == len(messages) - 1
        if role == "user" and is_last and request.file_id and request.mime_type:
            file_content = _build_file_content(
                request.file_id,
                request.filename or "archivo",
                request.mime_type,
            )
            content = []
            if file_content:
                content.append(file_content)
            content.append({"type": "input_text", "text": message.content or "Analiza el archivo adjunto."})
            result.append({"role": "user", "content": content})
        else:
            result.append({"role": role, "content": message.content})
    return result


def _serialize_output_items(response) -> list[dict]:
    items = []
    for item in response.output:
        if hasattr(item, "model_dump"):
            items.append(item.model_dump(exclude_none=True))
    return items


def _usage_dict(response) -> dict:
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump(exclude_none=True)
    return {}


def _write_usage(model: str, mode: str, profile: str, elapsed: float, response) -> None:
    try:
        os.makedirs(os.path.dirname(_USAGE_FILE), exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "mode": mode,
            "tool_profile": profile,
            "elapsed_ms": round(elapsed * 1000),
            "usage": _usage_dict(response),
        }
        with open(_USAGE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


async def _run_openai(request: ChatRequest):
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurada")

    workspace_id, project_id = _route_scope(request)
    request.workspace_id, request.project_id = workspace_id, project_id
    mode = _route_mode(request)
    if workspace_id == "hornbills" and mode == "general":
        mode = "hornbills"
    profile = _profile_for_mode(mode, workspace_id, project_id)
    model, reasoning_effort = _select_model(request, mode)
    tools = get_profile_tools(profile)
    input_items = _build_input(request)
    client = get_openai_client()
    started = time.monotonic()
    final_response = None

    for _ in range(8):
        response = await client.responses.create(
            model=model,
            instructions=_build_instructions(mode, workspace_id, project_id),
            input=input_items,
            tools=tools,
            tool_choice="auto" if tools else "none",
            reasoning={"effort": reasoning_effort},
            max_output_tokens=4096,
            store=False,
        )
        final_response = response

        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            text = response.output_text or ""
            if text:
                yield f"data: {json.dumps({'type': 'text', 'content': text}, ensure_ascii=False)}\n\n"
            break

        input_items.extend(_serialize_output_items(response))

        for call in calls:
            name = call.name
            yield f"data: {json.dumps({'type': 'tool_start', 'name': name}, ensure_ascii=False)}\n\n"
            try:
                args = json.loads(call.arguments or "{}")
                result = await execute_tool(name, args)
                result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            except Exception as exc:
                result_str = f"Error ejecutando {name}: {exc}"
            yield f"data: {json.dumps({'type': 'tool_done', 'name': name}, ensure_ascii=False)}\n\n"
            input_items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": result_str,
            })
    else:
        raise RuntimeError("Se alcanzó el máximo de iteraciones de herramientas")

    if final_response is not None:
        _write_usage(model, mode, profile, time.monotonic() - started, final_response)
    yield f"data: {json.dumps({'type': 'done', 'mode': mode, 'model': model, 'workspace_id': workspace_id, 'project_id': project_id})}\n\n"


@router.post("/chat")
async def chat(request: ChatRequest, _: str = Depends(verify_token)):
    async def generate():
        try:
            async for chunk in _run_openai(request):
                yield chunk
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
