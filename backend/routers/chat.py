import json

import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import verify_token
from config import get_settings
from tools.registry import execute_tool, get_tool_definitions

router = APIRouter(prefix="/api", tags=["chat"])

SYSTEM_PROMPT = """Eres Alex, asistente operativo avanzado de Jorge.

Capacidades:
- Gestión de contenido, publicaciones y newsletters
- Organización de proyectos y tareas de negocio
- Análisis de información y documentos
- Acceso al workspace de archivos del servidor

Principios:
- Responde en el idioma del usuario (español por defecto)
- Sé directo y práctico — acción sobre explicación
- Usa herramientas sin pedir permiso para acciones simples
- Si necesitas la fecha/hora actual, usa siempre get_datetime"""


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@router.post("/chat")
async def chat(request: ChatRequest, _: str = Depends(verify_token)):
    settings = get_settings()

    async def generate():
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            tools = get_tool_definitions()
            messages = [{"role": m.role, "content": m.content} for m in request.messages]

            # Agentic loop — continues until no more tool calls
            while True:
                async with client.messages.stream(
                    model=settings.anthropic_model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
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

                # Execute all tool calls and collect results
                tool_results = []
                for block in message.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue

                    try:
                        result = await execute_tool(block.name, block.input)
                        result_str = (
                            json.dumps(result) if not isinstance(result, str) else result
                        )
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _block_to_dict(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": block.type}
