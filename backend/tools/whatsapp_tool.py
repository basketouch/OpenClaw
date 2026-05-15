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


def _headers() -> dict:
    key = get_settings().waha_api_key
    return {"X-Api-Key": key} if key else {}


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return f"{digits}@c.us"


def _looks_like_phone(text: str) -> bool:
    return bool(re.fullmatch(r"[\d\s\+\-\(\)]{6,}", text))


async def _search_waha_contact(query: str) -> str | None:
    """Search WAHA contacts by name; returns chatId (xxx@c.us) or None."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{_waha()}/api/contacts/all",
                params={"session": _session()},
                headers=_headers(),
            )
            contacts = r.json()
        if not isinstance(contacts, list):
            return None
        q = query.lower().strip()
        for c in contacts:
            name = (c.get("name") or c.get("pushname") or "").lower()
            if q == name or q in name or name in q:
                return c.get("id")
    except Exception:
        pass
    return None


async def _resolve_contact(name_or_phone: str) -> str:
    # 1. Check configured aliases first
    contacts = get_settings().whatsapp_contacts
    q = name_or_phone.lower().strip()
    for c in contacts:
        if c.name.lower() == q:
            return _normalize_phone(c.phone)

    # 2. If it looks like a name (not a phone number), search WAHA contacts
    if not _looks_like_phone(name_or_phone):
        waha_id = await _search_waha_contact(name_or_phone)
        if waha_id:
            return waha_id

    # 3. Treat as phone number
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
                "description": "Nombre del contacto (busca en la agenda del móvil) o número completo con código de país (ej: 34612345678)",
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
    chat_id = await _resolve_contact(to)
    payload = {"session": _session(), "chatId": chat_id, "text": message}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{_waha()}/api/sendText", json=payload, headers=_headers())
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
                "description": "Nombre del contacto (busca en la agenda del móvil) o número completo con código de país",
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
    chat_id = await _resolve_contact(to)
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
            r = await client.post(f"{_waha()}/api/sendVoice", json=payload, headers=_headers())
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
            r = await client.get(f"{_waha()}/api/sessions/{_session()}", headers=_headers())
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
    "description": "Muestra los contactos configurados como alias. Para buscar en la agenda completa del móvil usa search_whatsapp_contacts.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def list_whatsapp_contacts() -> dict:
    contacts = get_settings().whatsapp_contacts
    if not contacts:
        return {"contactos": [], "mensaje": "No hay alias configurados. Puedes enviar mensajes usando el nombre del contacto tal como aparece en tu agenda de WhatsApp."}
    return {"contactos": [{"nombre": c.name, "telefono": c.phone} for c in contacts]}


SEARCH_WA_CONTACTS_DEF = {
    "name": "search_whatsapp_contacts",
    "description": "Busca contactos por nombre en la agenda real del móvil vinculado a WhatsApp. Útil para encontrar el número de alguien antes de enviarle un mensaje.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Nombre o parte del nombre del contacto a buscar",
            },
        },
        "required": ["query"],
    },
}


async def search_whatsapp_contacts(query: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{_waha()}/api/contacts/all",
                params={"session": _session()},
                headers=_headers(),
            )
            all_contacts = r.json()
        if not isinstance(all_contacts, list):
            return {"error": "Respuesta inesperada de WAHA", "raw": str(all_contacts)[:200]}
        q = query.lower().strip()
        results = []
        for c in all_contacts:
            name = c.get("name") or c.get("pushname") or ""
            if q in name.lower():
                results.append({
                    "nombre": name,
                    "pushname": c.get("pushname"),
                    "id": c.get("id"),
                })
        if not results:
            return {"encontrados": 0, "mensaje": f"No se encontraron contactos con '{query}'"}
        return {"encontrados": len(results), "contactos": results[:10]}
    except Exception as e:
        return {"error": str(e)}
