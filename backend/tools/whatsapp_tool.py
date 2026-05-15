import asyncio
import base64
import os
import re
import subprocess
import tempfile

import edge_tts
import httpx

from config import get_settings


# ─── Helpers ────────────────────────────────────────────────────────────────

def _waha() -> str:
    return get_settings().waha_url


def _session() -> str:
    return get_settings().waha_session


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return f"{digits}@c.us"


def _resolve_contact(name_or_phone: str) -> str:
    contacts = get_settings().whatsapp_contacts
    q = name_or_phone.lower().strip()
    for c in contacts:
        if c.name.lower() == q:
            return _normalize_phone(c.phone)
    return _normalize_phone(name_or_phone)


async def _tts_ogg(text: str, voice: str) -> bytes:
    """TTS via edge-tts → MP3 → OGG OPUS (formato nativo de WhatsApp)."""
    communicate = edge_tts.Communicate(text, voice)
    mp3_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data += chunk["data"]

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_data)
        mp3_path = f.name

    ogg_path = mp3_path.replace(".mp3", ".ogg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path,
             "-acodec", "libopus", "-b:a", "64k", "-vn", ogg_path],
            check=True, capture_output=True,
        )
        with open(ogg_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(mp3_path)
        if os.path.exists(ogg_path):
            os.unlink(ogg_path)


# ─── Tool definitions ────────────────────────────────────────────────────────

SEND_MSG_DEF = {
    "name": "send_whatsapp_message",
    "description": "Envía un mensaje de texto por WhatsApp a un contacto o número.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Nombre del contacto (de la lista configurada) o número completo con código de país (ej: 34612345678)",
            },
            "message": {
                "type": "string",
                "description": "Texto del mensaje a enviar",
            },
        },
        "required": ["to", "message"],
    },
}


async def send_whatsapp_message(to: str, message: str) -> dict:
    chat_id = _resolve_contact(to)
    payload = {"session": _session(), "chatId": chat_id, "text": message}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{_waha()}/api/sendText", json=payload)
            r.raise_for_status()
        return {"success": True, "para": to, "chat_id": chat_id}
    except Exception as e:
        return {"error": str(e), "success": False}


SEND_VOICE_DEF = {
    "name": "send_whatsapp_voice",
    "description": "Genera una nota de voz con TTS y la envía por WhatsApp. Úsala cuando el usuario pida enviar una nota de voz o audio.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Nombre del contacto o número completo con código de país",
            },
            "text": {
                "type": "string",
                "description": "Texto que se convertirá en nota de voz",
            },
            "voice": {
                "type": "string",
                "description": "Voz TTS. Opciones: es-ES-AlvaroNeural (hombre), es-ES-ElviraNeural (mujer), es-MX-JorgeNeural (hombre México). Por defecto usa la configurada en el sistema.",
            },
        },
        "required": ["to", "text"],
    },
}


async def send_whatsapp_voice(to: str, text: str, voice: str | None = None) -> dict:
    voice = voice or get_settings().tts_voice
    chat_id = _resolve_contact(to)
    try:
        ogg_data = await _tts_ogg(text, voice)
        b64 = base64.b64encode(ogg_data).decode()
        payload = {
            "session": _session(),
            "chatId": chat_id,
            "file": {
                "mimetype": "audio/ogg; codecs=opus",
                "filename": "voice.ogg",
                "data": b64,
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{_waha()}/api/sendVoice", json=payload)
            r.raise_for_status()
        return {"success": True, "para": to, "voice": voice, "characters": len(text)}
    except Exception as e:
        return {"error": str(e), "success": False}


WA_STATUS_DEF = {
    "name": "whatsapp_status",
    "description": "Comprueba si WhatsApp está conectado y listo para enviar mensajes.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


async def whatsapp_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_waha()}/api/sessions/{_session()}")
            data = r.json()
        status = data.get("status", "UNKNOWN")
        return {
            "conectado": status == "WORKING",
            "estado": status,
            "sesion": _session(),
        }
    except Exception as e:
        return {"conectado": False, "error": str(e)}


LIST_WA_CONTACTS_DEF = {
    "name": "list_whatsapp_contacts",
    "description": "Muestra los contactos de WhatsApp configurados.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def list_whatsapp_contacts() -> dict:
    contacts = get_settings().whatsapp_contacts
    if not contacts:
        return {"contactos": [], "mensaje": "No hay contactos WhatsApp configurados en .env"}
    return {"contactos": [{"nombre": c.name, "telefono": c.phone} for c in contacts]}
