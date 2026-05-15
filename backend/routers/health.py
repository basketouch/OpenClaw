from datetime import datetime

from fastapi import APIRouter, Depends

from auth import verify_token

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_public():
    return {"status": "ok"}


@router.get("/api/health")
async def health_auth(_: str = Depends(verify_token)):
    return {
        "status": "ok",
        "service": "openclaw",
        "timestamp": datetime.utcnow().isoformat(),
    }
