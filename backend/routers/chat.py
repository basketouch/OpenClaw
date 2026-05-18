import base64
import json
import os
from datetime import datetime, timezone

import anthropic
import pytz
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import verify_token
from config import get_settings
from tools.registry import execute_tool, get_tool_definitions

router = APIRouter(prefix="/api", tags=["chat"])

_TZ = pytz.timezone("Europe/Madrid")
_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

_SYSTEM_BASE = """Eres Alex, asistente operativo avanzado de Jorge.

Zona horaria: Europe/Madrid (España). Todas las fechas y horas son en esta zona horaria.

Capacidades:
- Gestión de contenido, publicaciones y newsletters
- Organización de proyectos y tareas de negocio
- Análisis de información y documentos
- Acceso al workspace de archivos del servidor
- Búsqueda de información actualizada en internet
- Administración completa del servidor VPS (paquetes, servicios, configuración del sistema)

NewsFlow (marca personal de Jorge — acceso directo a base de datos):
- articles: noticias y artículos curados (título, URL, resumen, estado)
- social_posts: posts de LinkedIn y X (contenido, plataforma, estado, fecha programada)
- newsletter_status: ediciones del newsletter INSIDE Life
- publish_queue: cola de vídeos para publicar
- Usa query_newsflow, insert_newsflow, update_newsflow para leer y gestionar el contenido
- Cuando Jorge pregunte por artículos, posts, newsletter o vídeos, consulta NewsFlow directamente

Principios:
- Responde en el idioma del usuario (español por defecto)
- Sé directo y práctico — acción sobre explicación
- Usa herramientas sin pedir permiso para acciones simples
- Para administrar el VPS (apt, systemctl, archivos del sistema) usa host_shell
- Para archivos del workspace (/data, /workspace) o Docker usa run_shell
- Confirma con el usuario antes de acciones destructivas o irreversibles en el servidor"""


def _build_system() -> str:
    now = datetime.now(timezone.utc).astimezone(_TZ)
    fecha = f"{_DAYS[now.weekday()]}, {now.strftime('%d/%m/%Y')} — {now.strftime('%H:%M')} (Europe/Madrid)"
    return f"{_SYSTEM_BASE}\n\nFecha y hora actual: {fecha}"


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    file_id: str | None = None
    filename: str | None = None
    mime_type: str | None = None


def _load_file_block(file_id: str, filename: str, mime_type: str) -> dict | None:
    uploads_dir = "/data/uploads"
    for fname in os.listdir(uploads_dir) if os.path.isdir(uploads_dir) else []:
        if fname.startswith(f"{file_id}_"):
            path = os.path.join(uploads_dir, fname)
            with open(path, "rb") as f:
                data = f.read()
            b64 = base64.standard_b64encode(data).decode()

            if mime_type.startswith("image/"):
                return {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}}
            if mime_type == "application/pdf":
                return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
            # text files — include as plain text block
            try:
                text_content = data.decode("utf-8", errors="replace")
                return {"type": "text", "text": f"[Archivo: {filename}]\n\n{text_content}"}
            except Exception:
                return None
    return None


@router.post("/chat")
async def chat(request: ChatRequest, _: str = Depends(verify_token)):
    settings = get_settings()

    async def generate():
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            tools = get_tool_definitions()
            messages = []

            for i, m in enumerate(request.messages):
                # Attach file to last user message
                if (m.role == "user" and i == len(request.messages) - 1
                        and request.file_id and request.mime_type):
                    file_block = _load_file_block(
                        request.file_id, request.filename or "archivo", request.mime_type
                    )
                    if file_block:
                        content = [file_block, {"type": "text", "text": m.content}]
                        messages.append({"role": "user", "content": content})
                        continue
                messages.append({"role": m.role, "content": m.content})

            while True:
                async with client.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=4096,
                    system=_build_system(),
                    messages=messages,
                    tools=tools,
                ) as stream:
                    async for event in stream:
                        etype = getattr(event, "type", None)
                        if etype == "content_block_start":
                            block = getattr(event, "content_block", None)
                            if block and getattr(block, "type", None) == "tool_use":
                                yield f"data: {json.dumps({'type': 'tool_start', 'name': block.name})}\n\n"
                        elif etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta and getattr(delta, "type", None) == "text_delta":
                                yield f"data: {json.dumps({'type': 'text', 'content': delta.text})}\n\n"
                    message = await stream.get_final_message()

                stop_reason = message.stop_reason
                messages.append({
                    "role": "assistant",
                    "content": [_block_to_dict(b) for b in message.content],
                })

                if stop_reason != "tool_use":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break

                tool_results = []
                for block in message.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    try:
                        result = await execute_tool(block.name, block.input)
                        result_str = json.dumps(result) if not isinstance(result, str) else result
                    except Exception as e:
                        result_str = f"Error ejecutando {block.name}: {e}"
                    yield f"data: {json.dumps({'type': 'tool_done', 'name': block.name})}\n\n"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })
                messages.append({"role": "user", "content": tool_results})

        except anthropic.APIStatusError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': e.message})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _block_to_dict(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": block.type}
