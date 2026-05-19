import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from auth import verify_token
from config import get_settings

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _openwa_headers(settings) -> dict:
    return {"X-API-Key": settings.waha_api_key} if settings.waha_api_key else {}


@router.get("/status")
async def status(_: str = Depends(verify_token)):
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{settings.waha_url}/api/sessions/{settings.waha_session}",
                headers=_openwa_headers(settings),
            )
            return r.json()
    except Exception as e:
        return {"error": str(e), "status": "OFFLINE"}


@router.post("/start")
async def start_session(_: str = Depends(verify_token)):
    """Arranca la sesión de WhatsApp para poder escanear el QR."""
    settings = get_settings()
    headers = _openwa_headers(settings)
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

            # 2. Session missing — create it then start
            r2 = await client.post(
                f"{settings.waha_url}/api/sessions",
                headers=headers,
                json={"name": settings.waha_session},
            )
            log.append(f"CREATE {r2.status_code}: {_text(r2)}")
            if r2.status_code in (200, 201):
                r3 = await client.post(
                    f"{settings.waha_url}/api/sessions/{settings.waha_session}/start",
                    headers=headers,
                )
                log.append(f"START2 {r3.status_code}: {_text(r3)}")
                return {"ok": r3.status_code in (200, 201), "log": log}

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
                f"{settings.waha_url}/api/sessions/{settings.waha_session}/auth/qr",
                headers=_openwa_headers(settings),
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
