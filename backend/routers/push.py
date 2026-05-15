import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_token
import push

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-key")
async def vapid_key(_: str = Depends(verify_token)):
    pub, _ = push.get_or_create_vapid()
    return {"public_key": pub}


class SubBody(BaseModel):
    endpoint: str
    keys: dict[str, str]
    expirationTime: Any = None


@router.post("/subscribe")
async def subscribe(body: SubBody, _: str = Depends(verify_token)):
    push.save_subscription({"endpoint": body.endpoint, "keys": body.keys})
    return {"ok": True}


@router.post("/test")
async def test_push(_: str = Depends(verify_token)):
    await asyncio.to_thread(push.send_notification, "Alex", "Las notificaciones push funcionan ✓")
    return {"ok": True}
