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
