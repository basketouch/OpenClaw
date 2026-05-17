import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from auth import verify_token
from config import get_settings

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _waha_headers(settings) -> dict:
    return {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}


@router.get("/status")
async def status(_: str = Depends(verify_token)):
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{settings.waha_url}/api/sessions/{settings.waha_session}",
                headers=_waha_headers(settings),
            )
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "OFFLINE"}


@router.post("/start")
async def start_session(_: str = Depends(verify_token)):
    """Arranca la sesión de WhatsApp para poder escanear el QR."""
    settings = get_settings()
    headers = _waha_headers(settings)
    log = []

    def _text(r) -> str:
        return r.text[:300] if r.text else "(vacío)"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # 1. Try to start existing session
            r1 = await client.post(
                f"{settings.waha_url}/api/sessions/{settings.waha_session}/start",
                headers=headers,
            )
            log.append(f"START {r1.status_code}: {_text(r1)}")
            if r1.status_code in (200, 201):
                return {"ok": True, "log": log}

            # 2. Session missing — create it
            r2 = await client.post(
                f"{settings.waha_url}/api/sessions",
                headers=headers,
                json={"name": settings.waha_session},
            )
            log.append(f"CREATE {r2.status_code}: {_text(r2)}")
            if r2.status_code in (200, 201):
                # List all sessions to see what was actually created
                r3 = await client.get(f"{settings.waha_url}/api/sessions", headers=headers)
                log.append(f"LIST {r3.status_code}: {_text(r3)}")
                return {"ok": True, "log": log}

            return {"ok": False, "log": log}
    except Exception as e:
        log.append(f"EXCEPTION: {e}")
        return {"ok": False, "log": log, "error": str(e)}


@router.get("/qr")
async def qr_code(_: str = Depends(verify_token)):
    """Devuelve el QR como imagen PNG para escanear con el móvil."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{settings.waha_url}/api/{settings.waha_session}/auth/qr",
                params={"format": "image"},
                headers=_waha_headers(settings),
            )
        if r.status_code != 200:
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "text/plain"),
                status_code=r.status_code,
            )
        return Response(content=r.content, media_type="image/png")
    except Exception as e:
        return Response(content=str(e).encode(), media_type="text/plain", status_code=503)
