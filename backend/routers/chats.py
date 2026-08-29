import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_token

CHATS_DIR = "/data/chats"
router = APIRouter(prefix="/api/chats", tags=["chats"])
VALID_MODES = {"auto", "general", "english", "admin", "newsflow", "communications"}

# Navigation taxonomy is deliberately data-only.  The chat router can use the
# optional hooks below, but the sidebar must never depend on memory/tool rules.
WORKSPACES = [
    {"id": "general", "name": "General", "icon": "💬", "instruction_hook": "general"},
    {"id": "hornbills", "name": "Hornbills", "icon": "🏀", "instruction_hook": "hornbills"},
    {"id": "english", "name": "English", "icon": "🇬🇧", "instruction_hook": "english"},
    {"id": "projects", "name": "Projects", "icon": "🚀", "instruction_hook": "projects"},
]
PROJECTS = [
    {"id": "cutsports", "workspace_id": "projects", "name": "CutSports", "instruction_hook": "cutsports"},
    {"id": "drawsports", "workspace_id": "projects", "name": "DrawSports", "instruction_hook": "drawsports"},
    {"id": "the-analyst", "workspace_id": "projects", "name": "The Analyst", "instruction_hook": "the_analyst"},
    {"id": "comunidad", "workspace_id": "projects", "name": "Comunidad", "instruction_hook": "comunidad"},
    {"id": "basketouch-hub", "workspace_id": "projects", "name": "Basketouch Hub", "instruction_hook": "basketouch_hub"},
]
WORKSPACE_IDS = {item["id"] for item in WORKSPACES}
PROJECT_IDS = {item["id"] for item in PROJECTS}


def _path(cid: str) -> str:
    return os.path.join(CHATS_DIR, f"{cid}.json")


def _load(cid: str) -> dict:
    with open(_path(cid)) as f:
        return json.load(f)


def _save(chat: dict):
    os.makedirs(CHATS_DIR, exist_ok=True)
    with open(_path(chat["id"]), "w") as f:
        json.dump(chat, f, ensure_ascii=False, indent=2)


def _normalise_scope(chat: dict) -> bool:
    """Backwards-compatible migration for chats created before workspaces."""
    changed = False
    if chat.get("workspace_id") not in WORKSPACE_IDS:
        chat["workspace_id"] = "general"
        changed = True
    project_id = chat.get("project_id")
    if project_id not in PROJECT_IDS or (
        project_id and chat["workspace_id"] != "projects"
    ):
        if project_id is not None:
            chat.pop("project_id", None)
            changed = True
    chat.setdefault("scope_source", "auto")
    return changed


def _summary(chat: dict) -> dict:
    return {
        "id": chat["id"],
        "title": chat.get("title", "Nueva conversación"),
        "updated": chat.get("updated", chat.get("created", "")),
        "preview": chat.get("preview", ""),
        "mode": chat.get("mode", "auto"),
        "workspace_id": chat["workspace_id"],
        "project_id": chat.get("project_id"),
        "scope_source": chat.get("scope_source", "auto"),
    }


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
            if _normalise_scope(c):
                _save(c)
            chats.append(_summary(c))
        except Exception:
            pass
    chats.sort(key=lambda x: x["updated"], reverse=True)
    return {"chats": chats, "workspaces": WORKSPACES, "projects": PROJECTS}


class CreateBody(BaseModel):
    mode: str = "auto"
    workspace_id: str = "general"
    project_id: str | None = None


@router.post("")
async def create_chat(body: CreateBody | None = None, _: str = Depends(verify_token)):
    now = datetime.now(timezone.utc).isoformat()
    requested_mode = (body.mode if body else "auto")
    mode = requested_mode if requested_mode in VALID_MODES else "auto"
    workspace_id = body.workspace_id if body and body.workspace_id in WORKSPACE_IDS else "general"
    project_id = body.project_id if body and body.project_id in PROJECT_IDS else None
    if workspace_id != "projects":
        project_id = None
    chat = {
        "id": str(uuid.uuid4())[:8],
        "title": "Nueva conversación",
        "created": now,
        "updated": now,
        "preview": "",
        "mode": mode,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "scope_source": "manual" if (workspace_id != "general" or project_id) else "auto",
        "messages": [],
    }
    _save(chat)
    return chat


@router.get("/{cid}")
async def get_chat(cid: str, _: str = Depends(verify_token)):
    try:
        chat = _load(cid)
        chat.setdefault("mode", "auto")
        if _normalise_scope(chat):
            _save(chat)
        return chat
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")


class SaveBody(BaseModel):
    # A scope change from the sidebar must not need to resend (or risk
    # overwriting) the conversation body.
    messages: list[dict] | None = None
    title: str | None = None
    mode: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    scope_source: str | None = None


class RenameBody(BaseModel):
    title: str


@router.put("/{cid}")
async def save_chat(cid: str, body: SaveBody, _: str = Depends(verify_token)):
    try:
        chat = _load(cid)
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")

    if body.messages is not None:
        chat["messages"] = body.messages[-40:]
    chat["updated"] = datetime.now(timezone.utc).isoformat()
    _normalise_scope(chat)

    if body.workspace_id in WORKSPACE_IDS:
        chat["workspace_id"] = body.workspace_id
        chat["project_id"] = body.project_id if (
            body.workspace_id == "projects" and body.project_id in PROJECT_IDS
        ) else None
        chat["scope_source"] = "manual" if body.scope_source != "auto" else "auto"

    if body.mode in VALID_MODES:
        chat["mode"] = body.mode
    else:
        chat.setdefault("mode", "auto")

    if body.title:
        chat["title"] = body.title
    elif body.messages and chat["title"] == "Nueva conversación":
        first = body.messages[0].get("content", "")
        if isinstance(first, str):
            chat["title"] = first[:50] + ("…" if len(first) > 50 else "")

    if body.messages is not None:
        for msg in reversed(body.messages):
            if msg["role"] == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    chat["preview"] = content[:80]
                break

    _save(chat)
    return {"success": True, "mode": chat.get("mode", "auto"), "workspace_id": chat["workspace_id"], "project_id": chat.get("project_id")}


@router.patch("/{cid}/title")
async def rename_chat(cid: str, body: RenameBody, _: str = Depends(verify_token)):
    """Rename a conversation without modifying its messages or scope."""
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "El nombre no puede estar vacío")
    if len(title) > 120:
        raise HTTPException(400, "El nombre no puede tener más de 120 caracteres")
    try:
        chat = _load(cid)
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")

    chat["title"] = title
    chat["updated"] = datetime.now(timezone.utc).isoformat()
    _normalise_scope(chat)
    _save(chat)
    return {"success": True, "title": title}


@router.delete("/{cid}")
async def delete_chat(cid: str, _: str = Depends(verify_token)):
    try:
        os.unlink(_path(cid))
        return {"success": True}
    except FileNotFoundError:
        raise HTTPException(404, "Chat no encontrado")
