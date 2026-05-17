import httpx

SEND_TELEGRAM_DEF = {
    "name": "send_telegram",
    "description": (
        "Envía un mensaje a Jorge por Telegram. "
        "Úsalo para avisos, resúmenes, alertas o cualquier comunicación proactiva. "
        "Soporta formato HTML básico: <b>negrita</b>, <i>cursiva</i>, <code>código</code>."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Texto del mensaje. Puede incluir HTML básico.",
            },
        },
        "required": ["message"],
    },
}


async def send_telegram(message: str) -> dict:
    from config import get_settings
    settings = get_settings()
    if not settings.telegram_bot_token:
        return {"error": "TELEGRAM_BOT_TOKEN no configurado"}
    if not settings.telegram_chat_id:
        return {"error": "TELEGRAM_CHAT_ID no configurado"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": message, "parse_mode": "HTML"},
            )
        data = r.json()
        if data.get("ok"):
            return {"ok": True, "message_id": data["result"]["message_id"]}
        return {"error": data.get("description", "Error desconocido")}
    except Exception as e:
        return {"error": str(e)}
