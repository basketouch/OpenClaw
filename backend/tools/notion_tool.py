import re
from datetime import date
from typing import Any

import httpx

from config import get_settings

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2026-03-11"


def _headers() -> dict[str, str]:
    token = get_settings().notion_api_key
    if not token:
        raise RuntimeError("Notion no está configurado: falta NOTION_API_KEY")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(method, f"{_NOTION_API}{path}", headers=_headers(), json=body)
    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f"Notion: HTTP {response.status_code} {detail}")
    return response.json() if response.content else {}


def _plain_text(parts: list[dict] | None) -> str:
    return "".join(part.get("plain_text", "") for part in (parts or []))


def _page_summary(item: dict) -> dict:
    properties = item.get("properties") or {}
    title = "Sin título"
    for prop in properties.values():
        if prop.get("type") == "title":
            title = _plain_text(prop.get("title")) or title
            break
    return {
        "id": item.get("id"),
        "title": title,
        "url": item.get("url"),
        "object": item.get("object"),
        "last_edited_time": item.get("last_edited_time"),
    }


async def search_notion(query: str, limit: int = 10) -> dict:
    """Search only content explicitly shared with the OpenClaw connection."""
    result = await _request("POST", "/search", {
        "query": query.strip(),
        "page_size": max(1, min(20, limit)),
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
    })
    items = []
    for entry in result.get("results", []):
        if entry.get("object") == "page":
            items.append(_page_summary(entry))
        elif entry.get("object") == "data_source":
            items.append({
                "id": entry.get("id"),
                "title": _plain_text(entry.get("title")) or "Base de datos sin título",
                "url": entry.get("url"),
                "object": "data_source",
                "last_edited_time": entry.get("last_edited_time"),
            })
    return {"count": len(items), "items": items}


async def read_notion_page(page_id: str, max_blocks: int = 100) -> dict:
    page = await _request("GET", f"/pages/{page_id}")
    blocks = await _request("GET", f"/blocks/{page_id}/children?page_size={max(1, min(100, max_blocks))}")
    content = []
    for block in blocks.get("results", []):
        block_type = block.get("type", "unknown")
        value = block.get(block_type, {})
        text = _plain_text(value.get("rich_text"))
        if text:
            content.append({"type": block_type, "text": text})
    return {"page": _page_summary(page), "content": content, "has_more": bool(blocks.get("has_more"))}


async def create_notion_page(parent_page_id: str, title: str, content: str = "") -> dict:
    """Create a child page. It never overwrites or deletes existing Notion content."""
    title = title.strip()
    if not title:
        return {"ok": False, "error": "title vacío"}
    children = []
    for paragraph in [part.strip() for part in content.split("\n\n") if part.strip()]:
        children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": paragraph}}]}})
    payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
    }
    if children:
        payload["children"] = children[:100]
    page = await _request("POST", "/pages", payload)
    return {"ok": True, "page": _page_summary(page)}


async def get_hornbills_hub() -> dict:
    """Return the configured Hornbills hub, or locate its shared Notion page."""
    configured_id = get_settings().notion_hornbills_hub_page_id
    if configured_id:
        page = await _request("GET", f"/pages/{configured_id}")
        return {"ok": True, "configured": True, "page": _page_summary(page)}
    result = await search_notion("Technical Area — Bogor Hornbills", limit=10)
    exact = next((item for item in result["items"] if item["title"].lower() == "technical area — bogor hornbills".lower()), None)
    return {"ok": bool(exact), "configured": False, "page": exact, "matches": result["items"]}


async def append_notion_note(page_id: str, content: str) -> dict:
    """Append a dated, non-destructive note to an existing shared Notion page."""
    content = content.strip()
    if not content:
        return {"ok": False, "error": "contenido vacío"}
    paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
    children = [
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": paragraph[:2000]}}]
        }}
        for paragraph in paragraphs[:100]
    ]
    result = await _request("PATCH", f"/blocks/{page_id}/children", {"children": children})
    return {"ok": True, "appended": len(children), "page_id": page_id, "result": result}


def _actions_data_source_id() -> str:
    value = get_settings().notion_actions_data_source_id
    if not value:
        raise RuntimeError("Notion Acciones no está configurado: falta NOTION_ACTIONS_DATA_SOURCE_ID")
    return value


def _property_text(property_value: dict | None) -> str:
    property_value = property_value or {}
    prop_type = property_value.get("type")
    if prop_type in {"title", "rich_text"}:
        return _plain_text(property_value.get(prop_type))
    if prop_type == "select":
        return (property_value.get("select") or {}).get("name", "")
    if prop_type == "url":
        return property_value.get("url") or ""
    if prop_type == "date":
        return (property_value.get("date") or {}).get("start", "")
    return ""


def _action_summary(page: dict) -> dict:
    props = page.get("properties") or {}
    return {
        "id": page.get("id"),
        "url": page.get("url"),
        "action": _property_text(props.get("Acción")),
        "project": _property_text(props.get("Proyecto")),
        "status": _property_text(props.get("Estado")),
        "priority": _property_text(props.get("Prioridad")),
        "week": _property_text(props.get("Semana")),
        "expected_result": _property_text(props.get("Resultado esperado")),
        "next_step": _property_text(props.get("Próximo paso")),
        "blocker": _property_text(props.get("Bloqueo")),
        "context": _property_text(props.get("Contexto")),
    }


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


async def _query_actions(page_size: int = 100) -> list[dict]:
    result = await _request("POST", f"/data_sources/{_actions_data_source_id()}/query", {
        "page_size": max(1, min(100, page_size)),
    })
    return result.get("results", [])


async def query_notion_actions(query: str = "", status: str = "", limit: int = 20) -> dict:
    actions = [_action_summary(page) for page in await _query_actions()]
    needle = _norm(query)
    if needle:
        actions = [item for item in actions if needle in _norm(" ".join([
            item["action"], item["project"], item["expected_result"], item["next_step"], item["blocker"],
        ]))]
    if status:
        actions = [item for item in actions if item["status"].lower() == status.lower()]
    return {"count": len(actions[:max(1, min(100, limit))]), "items": actions[:max(1, min(100, limit))]}


def _rich_text(value: str) -> list[dict]:
    return [{"type": "text", "text": {"content": value}}] if value else []


def _action_properties(
    action: str, project: str, status: str, priority: str, week: str,
    expected_result: str, next_step: str, blocker: str, context: str,
) -> dict[str, Any]:
    values: dict[str, Any] = {"Acción": {"title": _rich_text(action)}}
    if project:
        values["Proyecto"] = {"select": {"name": project}}
    if status:
        values["Estado"] = {"select": {"name": status}}
    if priority:
        values["Prioridad"] = {"select": {"name": priority}}
    if week:
        values["Semana"] = {"date": {"start": week}}
    if expected_result:
        values["Resultado esperado"] = {"rich_text": _rich_text(expected_result)}
    if next_step:
        values["Próximo paso"] = {"rich_text": _rich_text(next_step)}
    if blocker:
        values["Bloqueo"] = {"rich_text": _rich_text(blocker)}
    if context:
        values["Contexto"] = {"url": context}
    return values


async def upsert_notion_action(
    action: str,
    project: str = "",
    status: str = "Inbox",
    priority: str = "Media",
    week: str = "",
    expected_result: str = "",
    next_step: str = "",
    blocker: str = "",
    context: str = "",
) -> dict:
    """Create an action or update an exact duplicate; never creates a sixth weekly action."""
    action = action.strip()
    if not action:
        return {"ok": False, "error": "action vacía"}
    if status not in {"Inbox", "Esta semana", "En curso", "Bloqueado", "Hecho", "Descartado"}:
        return {"ok": False, "error": "estado no válido"}
    if priority and priority not in {"Alta", "Media", "Baja"}:
        return {"ok": False, "error": "prioridad no válida"}
    if project and project not in {"DrawSports", "CutSports", "The Analyst", "Basketouch Hub"}:
        return {"ok": False, "error": "proyecto no válido"}
    if week:
        try:
            date.fromisoformat(week)
        except ValueError:
            return {"ok": False, "error": "week debe tener formato AAAA-MM-DD"}

    pages = await _query_actions()
    items = [_action_summary(page) for page in pages]
    exact = next((item for item in items if _norm(item["action"]) == _norm(action)), None)
    properties = _action_properties(action, project, status, priority, week, expected_result, next_step, blocker, context)
    if exact:
        page = await _request("PATCH", f"/pages/{exact['id']}", {"properties": properties})
        return {"ok": True, "created": False, "item": _action_summary(page)}

    if status == "Esta semana":
        weekly = [item for item in items if item["status"] == "Esta semana"]
        if len(weekly) >= 5:
            return {"ok": False, "error": "límite semanal alcanzado: ya hay 5 acciones en Esta semana", "weekly_actions": weekly}

    page = await _request("POST", "/pages", {
        "parent": {"type": "data_source_id", "data_source_id": _actions_data_source_id()},
        "properties": properties,
    })
    return {"ok": True, "created": True, "item": _action_summary(page)}


SEARCH_DEF = {
    "name": "search_notion",
    "description": "Busca páginas y bases de datos en el Notion compartido con Alex. Úsala antes de afirmar que un dato no existe en Notion.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"]},
}

READ_DEF = {
    "name": "read_notion_page",
    "description": "Lee una página de Notion por su id después de localizarla con search_notion.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "max_blocks": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["page_id"]},
}

CREATE_PAGE_DEF = {
    "name": "create_notion_page",
    "description": "Crea una página hija en Notion. Confirma con Jorge antes de crearla salvo que él haya pedido claramente crear esa página concreta.",
    "input_schema": {"type": "object", "properties": {"parent_page_id": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}}, "required": ["parent_page_id", "title"]},
}

HORNBILLS_HUB_DEF = {
    "name": "get_hornbills_hub",
    "description": "Localiza el hub compartido de Notion 'Technical Area — Bogor Hornbills'. Usa primero este resultado para leer o clasificar una sesión técnica.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

APPEND_NOTE_DEF = {
    "name": "append_notion_note",
    "description": "Añade una nota nueva a una página existente de Notion sin sobrescribir nada. Úsala solo al cerrar una sesión o cuando Jorge pida guardar/resumir; lee la página antes para evitar duplicados.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "content": {"type": "string", "description": "Nota concisa, estructurada y sin datos inventados."}}, "required": ["page_id", "content"]},
}

QUERY_ACTIONS_DEF = {
    "name": "query_notion_actions",
    "description": "Consulta la base central Acciones de Notion para localizar trabajo existente y evitar duplicados.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": []},
}

UPSERT_ACTION_DEF = {
    "name": "upsert_notion_action",
    "description": "Crea una acción en la base central Acciones o actualiza una existente con el mismo título. Aplica automáticamente el límite de cinco acciones en Esta semana y nunca borra acciones.",
    "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "project": {"type": "string", "enum": ["DrawSports", "CutSports", "The Analyst", "Basketouch Hub"]}, "status": {"type": "string", "enum": ["Inbox", "Esta semana", "En curso", "Bloqueado", "Hecho", "Descartado"]}, "priority": {"type": "string", "enum": ["Alta", "Media", "Baja"]}, "week": {"type": "string", "description": "Fecha de inicio de semana AAAA-MM-DD"}, "expected_result": {"type": "string"}, "next_step": {"type": "string"}, "blocker": {"type": "string"}, "context": {"type": "string", "description": "URL de Notion relacionada"}}, "required": ["action"]},
}
