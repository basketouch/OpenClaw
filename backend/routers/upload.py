import base64
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from auth import verify_token
from config import get_openai_client, get_settings

UPLOADS_DIR = "/data/uploads"
MAX_SIZE = 20 * 1024 * 1024  # 20MB

ALLOWED = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf",
    "text/plain", "text/markdown", "text/csv",
}
MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20MB

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload(file: UploadFile = File(...), _: str = Depends(verify_token)):
    if file.content_type not in ALLOWED:
        raise HTTPException(400, f"Tipo no soportado: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "Archivo demasiado grande (máximo 20MB)")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    fid = str(uuid.uuid4())[:8]
    safe_name = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._-")
    path = os.path.join(UPLOADS_DIR, f"{fid}_{safe_name}")
    with open(path, "wb") as f:
        f.write(data)
    return {"file_id": fid, "filename": file.filename, "mime_type": file.content_type, "size": len(data)}


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...), _: str = Depends(verify_token)):
    """Turn a short voice note into editable text without storing the audio."""
    content_type = file.content_type or ""
    if not content_type.startswith("audio/") and content_type not in {"video/webm", "video/mp4"}:
        raise HTTPException(400, "Envía un archivo de audio válido")

    data = await file.read()
    if not data:
        raise HTTPException(400, "El audio está vacío")
    if len(data) > MAX_AUDIO_SIZE:
        raise HTTPException(400, "Audio demasiado grande (máximo 20MB)")

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(503, "La transcripción no está configurada")

    filename = file.filename or "nota-de-voz.webm"
    try:
        result = await get_openai_client().audio.transcriptions.create(
            model=settings.transcription_model,
            file=(filename, data, content_type),
        )
    except Exception as exc:
        raise HTTPException(502, "No se pudo transcribir el audio") from exc

    text = (getattr(result, "text", "") or "").strip()
    if not text:
        raise HTTPException(422, "No se ha podido detectar voz en el audio")
    return {"text": text}


class SpeechBody(BaseModel):
    text: str


@router.post("/speech")
async def create_speech(body: SpeechBody, _: str = Depends(verify_token)):
    """Return generated speech for a response without retaining an audio file."""
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "No hay texto para leer")
    if len(text) > 8_000:
        raise HTTPException(400, "La respuesta es demasiado larga para leerla de una vez")

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(503, "La voz no está configurada")
    try:
        result = await get_openai_client().audio.speech.create(
            model=settings.tts_model,
            voice=settings.tts_voice,
            input=text,
            response_format="mp3",
            instructions="Habla de forma natural, calmada y clara. Respeta el idioma del texto.",
        )
        # The OpenAI SDK returns the binary payload directly here.
        audio = result.read()
    except Exception as exc:
        raise HTTPException(502, "No se pudo generar la respuesta de voz") from exc
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
