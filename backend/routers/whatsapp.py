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
        return Response(content=r.content, media_type="image/png")
    except Exception as e:
        return Response(content=str(e).encode(), media_type="text/plain", status_code=503)
