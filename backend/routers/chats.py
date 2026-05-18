import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_token

CHATS_DIR = "/data/chats"
router = APIRouter(prefix="/api/chats", tags=["chats"])


def _path(cid: str) -> str:
    return os.path.join(CHATS_DIR, f"{cid}.json")


def _load(cid: str) -> dict:
    with open(_path(cid)) as f:
        return json.load(f)


def _save(chat: dict):
    os.makedirs(CHATS_DIR, exist_ok=True)
    with open(_path(chat["id"]), "w") as f:
        json.dump(chat, f, ensure_ascii=False, indent=2)


@router.get("")
async def list_chats(_: str = Depends(verify_token)):
    os.makedirs(CHATS_DIR, exist_ok=True)
    chats = []
    for fname in os.listdir(CHATS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHATS_DIR, fname)) as f:
                c = json.load(f)
            chats.append({
                "id": c["id"],
                "title": c.get("title", "Nueva conversación"),
                "updated": c.get("updated", c.get("created", "")),
                "preview": c.get("preview", ""),
            })
        except Exception:
            pass
    chats.sort(key=lambda x: x["updated"], reverse=True)
    return {"chats": chats}


@router.post("")
async def create_chat(_: str = Depends(verify_token)):
    now = datetime.now(timezone.utc).isoformat()
    chat = {
        "id": str(uuid.uuid4())[:8],
        "title": "Nueva conversación",
        "created": now,
        "updated": now,
        "preview": "",
        "messages": [],
    }
    _save(chat)
    return chat


@router.get("/{cid}")
async def get_chat(cid: str, _: str = Depends(verify_token)):
    try:
        return _load(cid)
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")


class SaveBody(BaseModel):
    messages: list[dict]
    title: str | None = None


@router.put("/{cid}")
async def save_chat(cid: str, body: SaveBody, _: str = Depends(verify_token)):
    try:
        chat = _load(cid)
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")

    chat["messages"] = body.messages[-40:]  # keep last 40 messages max
    chat["updated"] = datetime.now(timezone.utc).isoformat()

    if body.title:
        chat["title"] = body.title
    elif len(body.messages) >= 1 and chat["title"] == "Nueva conversación":
        first = body.messages[0].get("content", "")
        if isinstance(first, str):
            chat["title"] = first[:50] + ("…" if len(first) > 50 else "")

    for msg in reversed(body.messages):
        if msg["role"] == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                chat["preview"] = content[:80]
            break

    _save(chat)
    return {"success": True}


@router.delete("/{cid}")
async def delete_chat(cid: str, _: str = Depends(verify_token)):
    try:
        os.unlink(_path(cid))
        return {"success": True}
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")
