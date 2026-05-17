import httpx
from fastapi import APIRouter, Depends
from auth import verify_token
from config import get_settings

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status")
async def status(_: str = Depends(verify_token)):
    settings = get_settings()
    return {
        "token_set": bool(settings.telegram_bot_token),
        "chat_id": settings.telegram_chat_id or None,
    }


@router.get("/detect-chat")
async def detect_chat(_: str = Depends(verify_token)):
    """Lee los últimos mensajes recibidos por el bot y devuelve el chat_id."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return {"error": "TELEGRAM_BOT_TOKEN no configurado en .env"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
                params={"limit": 5},
            )
        data = r.json()
        if not data.get("ok"):
            return {"error": data.get("description", "Error de Telegram")}
        updates = data.get("result", [])
        if not updates:
            return {"error": "No hay mensajes. Envía cualquier mensaje a tu bot primero."}
        for upd in reversed(updates):
            chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat", {})
            if chat.get("id"):
                return {"chat_id": str(chat["id"]), "name": chat.get("first_name") or chat.get("title", "")}
        return {"error": "No se pudo detectar el chat_id"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/test")
async def test_message(_: str = Depends(verify_token)):
    from tools.telegram_tool import send_telegram
    result = await send_telegram("✅ Alex conectado — las notificaciones de Telegram funcionan.")
    return result
