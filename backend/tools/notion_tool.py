import contextvars
import json
import os
import re
import secrets
import time
from datetime import date
from typing import Any

import httpx

from config import get_settings

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2026-03-11"
_DESTRUCTIVE_PLANS_PATH = "/data/notion_destructive_plans.json"
_DESTRUCTIVE_PLAN_TTL_SECONDS = 24 * 60 * 60
_active_confirmation_message: contextvars.ContextVar[str] = contextvars.ContextVar(
    "active_notion_confirmation_message", default=""
)


def set_notion_confirmation_message(message: str):
    """Bind destructive-tool confirmation to the current user's actual message."""
    return _active_confirmation_message.set(message or "")


def reset_notion_confirmation_message(token) -> None:
    _active_confirmation_message.reset(token)


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


def _rich_text(value: str, link: str = "") -> list[dict]:
    """Build Notion rich text safely, splitting values at the API text limit."""
    value = str(value or "")
    chunks = [value[index:index + 2000] for index in range(0, len(value), 2000)] or []
    parts = []
    for chunk in chunks:
        text: dict[str, Any] = {"content": chunk}
        if link:
            text["link"] = {"url": link}
        parts.append({"type": "text", "text": text})
    return parts


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


async def read_notion_page(page_id: str, max_blocks: int = 100, start_cursor: str = "") -> dict:
    page = await _request("GET", f"/pages/{page_id}")
    query = f"page_size={max(1, min(100, max_blocks))}"
    if start_cursor.strip():
        query += f"&start_cursor={start_cursor.strip()}"
    blocks = await _request("GET", f"/blocks/{page_id}/children?{query}")
    content = []
    structured_blocks = []
    for block in blocks.get("results", []):
        block_type = block.get("type", "unknown")
        value = block.get(block_type, {})
        text = _plain_text(value.get("rich_text"))
        item: dict[str, Any] = {"id": block.get("id"), "type": block_type}
        if text:
            content.append({"type": block_type, "text": text})
            item["text"] = text
        if block_type == "to_do":
            item["checked"] = bool(value.get("checked", False))
        if block_type == "callout":
            item["color"] = value.get("color", "default")
        if block_type == "table" and block.get("has_children"):
            rows = await _request("GET", f"/blocks/{block['id']}/children?page_size=100")
            item["rows"] = [
                [_plain_text(cell) for cell in row.get("table_row", {}).get("cells", [])]
                for row in rows.get("results", [])
                if row.get("type") == "table_row"
            ]
        elif block.get("has_children"):
            children = await _request("GET", f"/blocks/{block['id']}/children?page_size=50")
            item["children"] = [
                {
                    "id": child.get("id"),
                    "type": child.get("type", "unknown"),
                    "text": _plain_text(child.get(child.get("type", ""), {}).get("rich_text")),
                }
                for child in children.get("results", [])
            ]
        structured_blocks.append(item)
    return {
        "page": _page_summary(page), "content": content, "blocks": structured_blocks,
        "has_more": bool(blocks.get("has_more")), "next_cursor": blocks.get("next_cursor"),
    }


async def create_notion_page(
    parent_page_id: str, title: str, content: str = "", template: str = "",
    sections: dict[str, Any] | None = None, blocks: list[dict[str, Any]] | None = None,
) -> dict:
    """Create a child page with optional rich blocks; never overwrites existing content."""
    title = title.strip()
    if not title:
        return {"ok": False, "error": "title vacío"}
    children = _rich_blocks(content, template, sections, blocks)
    payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": {"title": _rich_text(title)}},
    }
    if children:
        payload["children"] = children[:100]
    page = await _request("POST", "/pages", payload)
    return {"ok": True, "page": _page_summary(page), "blocks_created": len(children)}


async def create_notion_database(
    parent_page_id: str, title: str, properties: list[dict[str, str]], description: str = "",
) -> dict:
    """Create a Notion database under an explicit shared parent page."""
    title = title.strip()
    if not title:
        return {"ok": False, "error": "title vacío"}
    if not isinstance(properties, list) or len(properties) > 20:
        return {"ok": False, "error": "Indica entre 0 y 20 propiedades"}

    schema: dict[str, dict] = {}
    skipped: list[dict[str, str]] = []
    for item in properties:
        name = str((item or {}).get("name", "")).strip()
        kind = str((item or {}).get("type", "")).strip()
        if not name or len(name) > 100:
            skipped.append({"name": name or "(sin nombre)", "reason": "El nombre debe tener entre 1 y 100 caracteres"})
        elif kind not in _CREATE_DATABASE_PROPERTY_TYPES:
            skipped.append({"name": name, "reason": f"Tipo no permitido: {kind}"})
        elif name in schema:
            skipped.append({"name": name, "reason": "La propiedad está repetida"})
        else:
            schema[name] = _CREATE_DATABASE_PROPERTY_TYPES[kind]

    if not any("title" in item for item in schema.values()):
        schema = {"Name": {"title": {}}, **schema}

    payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": _rich_text(title),
        "initial_data_source": {"properties": schema},
    }
    if description.strip():
        payload["description"] = _rich_text(description.strip())
    database = await _request("POST", "/databases", payload)
    return {
        "ok": True,
        "database": {
            "id": database.get("id"),
            "title": _plain_text(database.get("title")) or title,
            "url": database.get("url"),
            "data_sources": database.get("data_sources", []),
        },
        "properties": _data_source_schema((database.get("data_sources") or [{}])[0]) if database.get("data_sources") else schema,
        "skipped": skipped,
    }


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


def _data_source_schema(data_source: dict) -> dict[str, str]:
    return {
        name: value.get("type", "unknown")
        for name, value in (data_source.get("properties") or {}).items()
    }


async def read_notion_data_source(data_source_id: str) -> dict:
    """Read a shared Notion data source schema before creating a record."""
    data_source = await _request("GET", f"/data_sources/{data_source_id}")
    return {
        "id": data_source.get("id"),
        "title": _plain_text(data_source.get("title")) or "Base de datos sin título",
        "properties": _data_source_schema(data_source),
    }


_NEW_PROPERTY_TYPES = {
    "rich_text": {"rich_text": {}},
    "date": {"date": {}},
    "select": {"select": {}},
    "multi_select": {"multi_select": {}},
    "number": {"number": {"format": "number"}},
    "checkbox": {"checkbox": {}},
    "url": {"url": {}},
}

_CREATE_DATABASE_PROPERTY_TYPES = {
    "title": {"title": {}},
    **_NEW_PROPERTY_TYPES,
}


async def add_notion_data_source_properties(data_source_id: str, properties: list[dict[str, str]]) -> dict:
    """Add new Notion data-source properties without modifying existing ones."""
    if not isinstance(properties, list) or not properties:
        return {"ok": False, "error": "Debes indicar al menos una columna nueva"}
    if len(properties) > 10:
        return {"ok": False, "error": "Puedes añadir un máximo de 10 columnas por operación"}

    data_source = await _request("GET", f"/data_sources/{data_source_id}")
    existing = _data_source_schema(data_source)
    payload: dict[str, dict] = {}
    added: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for item in properties:
        name = str((item or {}).get("name", "")).strip()
        kind = str((item or {}).get("type", "")).strip()
        if not name or len(name) > 100:
            skipped.append({"name": name or "(sin nombre)", "reason": "El nombre debe tener entre 1 y 100 caracteres"})
        elif kind not in _NEW_PROPERTY_TYPES:
            skipped.append({"name": name, "reason": f"Tipo no permitido: {kind}"})
        elif name in existing or name in payload:
            skipped.append({"name": name, "reason": "La columna ya existe"})
        else:
            payload[name] = _NEW_PROPERTY_TYPES[kind]
            added.append({"name": name, "type": kind})

    if not payload:
        return {"ok": True, "data_source_id": data_source_id, "added": [], "skipped": skipped, "properties": existing}

    updated = await _request("PATCH", f"/data_sources/{data_source_id}", {"properties": payload})
    return {
        "ok": True,
        "data_source_id": data_source_id,
        "added": added,
        "skipped": skipped,
        "properties": _data_source_schema(updated),
    }


def _database_properties(schema: dict[str, str], title: str | None, fields: dict[str, Any]) -> dict:
    result: dict[str, Any] = {}
    title_name = next((name for name, kind in schema.items() if kind == "title"), None)
    if title is not None and not title_name:
        raise RuntimeError("La base de datos no tiene una propiedad de título")
    if title is not None:
        result[title_name] = {"title": _rich_text(title)}
    for name, value in fields.items():
        kind = schema.get(name)
        if not kind or value in (None, "") or kind == "title":
            continue
        if kind == "rich_text":
            result[name] = {"rich_text": _rich_text(str(value))}
        elif kind in {"select", "status"}:
            result[name] = {kind: {"name": str(value)}}
        elif kind == "multi_select":
            result[name] = {"multi_select": [{"name": item.strip()} for item in str(value).split(",") if item.strip()]}
        elif kind == "date":
            result[name] = {"date": {"start": str(value)}}
        elif kind == "url":
            result[name] = {"url": str(value)}
        elif kind == "checkbox":
            result[name] = {"checkbox": str(value).lower() in {"true", "1", "sí", "si", "yes"}}
        elif kind == "number":
            result[name] = {"number": float(value)}
        elif kind == "relation" and isinstance(value, list):
            result[name] = {"relation": [{"id": str(item)} for item in value]}
    return result


_RICH_BLOCK_TYPES = {
    "paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item",
    "numbered_list_item", "to_do", "quote", "callout", "divider", "table",
}
_NOTION_COLORS = {
    "default", "gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red",
    "gray_background", "brown_background", "orange_background", "yellow_background",
    "green_background", "blue_background", "purple_background", "pink_background", "red_background",
}
_TEMPLATE_SECTIONS = {
    "hornbills_review": [
        ("Resumen", "summary", "callout"),
        ("Hallazgos", "findings", "bulleted_list_item"),
        ("Hipótesis por validar", "hypotheses", "bulleted_list_item"),
        ("Preguntas técnicas", "questions", "bulleted_list_item"),
        ("Implicaciones para coaching", "implications", "bulleted_list_item"),
        ("Próximo paso", "next_step", "to_do"),
    ],
    "product_update": [
        ("Contexto", "context", "paragraph"),
        ("Decisión", "decision", "callout"),
        ("Estado", "status", "paragraph"),
        ("Trabajo pendiente", "pending_work", "to_do"),
    ],
    "marketing_proposal": [
        ("Objetivo", "objective", "paragraph"),
        ("Audiencia", "audience", "paragraph"),
        ("Mensaje", "message", "paragraph"),
        ("Canal", "channel", "bulleted_list_item"),
        ("Métricas", "metrics", "bulleted_list_item"),
        ("Siguiente decisión", "next_decision", "to_do"),
    ],
    "action": [
        ("Resultado esperado", "expected_result", "paragraph"),
        ("Próximo paso", "next_step", "to_do"),
        ("Bloqueo", "blocker", "callout"),
    ],
    "structured_note": [
        ("Resumen", "summary", "callout"),
        ("Contexto", "context", "paragraph"),
        ("Decisiones", "decisions", "bulleted_list_item"),
        ("Siguientes pasos", "next_steps", "to_do"),
    ],
}


def _section_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _normalise_rich_block(spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a constrained, model-friendly block spec into a Notion API block."""
    block_type = str(spec.get("type", "")).strip()
    if block_type not in _RICH_BLOCK_TYPES:
        raise ValueError(f"tipo de bloque no permitido: {block_type}")
    if block_type == "divider":
        return {"object": "block", "type": "divider", "divider": {}}
    if block_type == "table":
        rows = spec.get("rows")
        if not isinstance(rows, list) or not rows or not all(isinstance(row, list) and row for row in rows):
            raise ValueError("una tabla necesita rows con al menos una celda por fila")
        width = len(rows[0])
        if width > 20 or any(len(row) != width for row in rows):
            raise ValueError("las filas de la tabla deben tener el mismo número de celdas (máximo 20)")
        children = [
            {
                "object": "block",
                "type": "table_row",
                "table_row": {"cells": [_rich_text(str(cell)) for cell in row]},
            }
            for row in rows[:100]
        ]
        return {
            "object": "block", "type": "table",
            "table": {
                "table_width": width,
                "has_column_header": bool(spec.get("has_column_header", False)),
                "has_row_header": bool(spec.get("has_row_header", False)),
            },
            "children": children,
        }

    text = str(spec.get("text", "")).strip()
    if not text:
        raise ValueError(f"el bloque {block_type} necesita texto")
    value: dict[str, Any] = {"rich_text": _rich_text(text, str(spec.get("url", "")).strip())}
    if block_type.startswith("heading_"):
        value["is_toggleable"] = False
    elif block_type == "to_do":
        value["checked"] = bool(spec.get("checked", False))
    elif block_type == "callout":
        icon = str(spec.get("icon", "💡"))[:8]
        value["icon"] = {"type": "emoji", "emoji": icon}
        color = str(spec.get("color", "blue_background"))
        if color in _NOTION_COLORS:
            value["color"] = color
    return {"object": "block", "type": block_type, block_type: value}


def _template_blocks(template: str, sections: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if template not in _TEMPLATE_SECTIONS:
        raise ValueError("template no válido")
    sections = sections or {}
    blocks: list[dict[str, Any]] = []
    for title, key, block_type in _TEMPLATE_SECTIONS[template]:
        values = _section_values(sections.get(key))
        if not values:
            continue
        blocks.append(_normalise_rich_block({"type": "heading_2", "text": title}))
        for value in values:
            spec: dict[str, Any] = {"type": block_type, "text": value}
            if block_type == "callout":
                spec["icon"] = "📌"
                spec["color"] = "blue_background"
            blocks.append(_normalise_rich_block(spec))
    return blocks


def _rich_blocks(
    content: str = "", template: str = "", sections: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if template:
        result.extend(_template_blocks(template, sections))
    if content.strip() and not result:
        result.extend(
            _normalise_rich_block({"type": "paragraph", "text": paragraph})
            for paragraph in [part.strip() for part in content.split("\n\n") if part.strip()]
        )
    for block in blocks or []:
        if not isinstance(block, dict):
            raise ValueError("cada bloque debe ser un objeto")
        result.append(_normalise_rich_block(block))
    if len(result) > 100:
        raise ValueError("máximo 100 bloques por operación")
    return result


async def append_notion_rich_blocks(
    page_id: str, template: str = "", sections: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None, content: str = "",
) -> dict:
    """Append structured blocks safely; this never replaces existing page content."""
    rich_blocks = _rich_blocks(content, template, sections, blocks)
    if not rich_blocks:
        return {"ok": False, "error": "contenido enriquecido vacío"}
    result = await _request("PATCH", f"/blocks/{page_id}/children", {"children": rich_blocks})
    return {"ok": True, "appended": len(rich_blocks), "page_id": page_id, "result": result}


async def update_notion_block(block_id: str, block: dict[str, Any]) -> dict:
    """Update one supported Notion block while preserving its block type."""
    current = await _request("GET", f"/blocks/{block_id}")
    current_type = current.get("type", "")
    requested_type = str((block or {}).get("type", "")).strip()
    if current_type not in _RICH_BLOCK_TYPES or current_type in {"divider", "table"}:
        return {"ok": False, "error": f"El bloque {current_type or 'desconocido'} no admite esta edición directa"}
    if requested_type != current_type:
        return {"ok": False, "error": f"El bloque es de tipo {current_type}; no se puede convertir en {requested_type or 'otro tipo'}"}
    normalised = _normalise_rich_block(block)
    updated = await _request("PATCH", f"/blocks/{block_id}", {current_type: normalised[current_type]})
    return {"ok": True, "block": _block_preview(updated)}


async def update_notion_page_markdown(page_id: str, updates: list[dict[str, str]]) -> dict:
    """Make precise formatted text replacements in an existing Notion page."""
    if not isinstance(updates, list) or not updates or len(updates) > 20:
        return {"ok": False, "error": "Indica entre 1 y 20 sustituciones"}
    content_updates = []
    for item in updates:
        old_str = str((item or {}).get("old_str", ""))
        new_str = str((item or {}).get("new_str", ""))
        if not old_str:
            return {"ok": False, "error": "Cada sustitución necesita old_str"}
        content_updates.append({"old_str": old_str, "new_str": new_str})
    result = await _request("PATCH", f"/pages/{page_id}/markdown", {
        "type": "update_content",
        "update_content": {"content_updates": content_updates},
    })
    return {"ok": True, "page_id": page_id, "updated": len(content_updates), "result": result}


async def replace_notion_page_content(page_id: str, markdown: str) -> dict:
    """Replace page content with enhanced Markdown after an explicit user instruction."""
    if not markdown.strip():
        return {"ok": False, "error": "El contenido nuevo no puede estar vacío"}
    result = await _request("PATCH", f"/pages/{page_id}/markdown", {
        "type": "replace_content",
        "replace_content": {"new_str": markdown},
    })
    return {"ok": True, "page_id": page_id, "result": result}


async def move_notion_page(page_id: str, parent_id: str, parent_type: str = "page_id") -> dict:
    """Move a Notion page under another page or into a data source."""
    if parent_type not in {"page_id", "data_source_id"}:
        return {"ok": False, "error": "parent_type debe ser page_id o data_source_id"}
    page = await _request("GET", f"/pages/{page_id}")
    if parent_type == "page_id":
        await _request("GET", f"/pages/{parent_id}")
        parent = {"type": "page_id", "page_id": parent_id}
    else:
        await _request("GET", f"/data_sources/{parent_id}")
        parent = {"type": "data_source_id", "data_source_id": parent_id}
    moved = await _request("POST", f"/pages/{page_id}/move", {"parent": parent})
    return {"ok": True, "page": _page_summary(moved or page), "parent": parent}


async def set_notion_page_trash(page_id: str, in_trash: bool) -> dict:
    """Send a page to Notion trash or restore it."""
    page = await _request("GET", f"/pages/{page_id}")
    updated = await _request("PATCH", f"/pages/{page_id}", {"in_trash": bool(in_trash)})
    return {"ok": True, "page": _page_summary(updated or page), "in_trash": bool(in_trash)}


def _load_destructive_plans() -> dict[str, Any]:
    data: dict[str, Any] = {}
    for path in _destructive_plan_paths():
        try:
            with open(path, encoding="utf-8") as file:
                stored = json.load(file)
            if isinstance(stored, dict):
                for plan_id, plan in stored.items():
                    data.setdefault(plan_id, plan)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    now = time.time()
    plans = {plan_id: plan for plan_id, plan in data.items() if plan.get("expires_at", 0) > now}
    if plans != data:
        _save_destructive_plans(plans)
    return plans


def _destructive_plan_paths() -> list[str]:
    workspace_path = get_settings().workspace_path.rstrip("/")
    backup_path = f"{workspace_path}/notion_destructive_plans.json"
    return list(dict.fromkeys([_DESTRUCTIVE_PLANS_PATH, backup_path]))


def _save_destructive_plans(plans: dict[str, Any]) -> None:
    saved = False
    errors = []
    for path in _destructive_plan_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temporary = f"{path}.{secrets.token_hex(4)}.tmp"
            with open(temporary, "w", encoding="utf-8") as file:
                json.dump(plans, file, ensure_ascii=False)
            os.replace(temporary, path)
            saved = True
        except OSError as exc:
            errors.append(str(exc))
    if not saved:
        raise RuntimeError("No se pudo guardar el plan de confirmación: " + "; ".join(errors))


def _block_preview(block: dict[str, Any]) -> dict[str, Any]:
    block_type = block.get("type", "unknown")
    value = block.get(block_type, {})
    text = _plain_text(value.get("rich_text"))
    return {
        "id": block.get("id"),
        "type": block_type,
        "text": text[:240],
        "has_children": bool(block.get("has_children", False)),
    }


def _direct_child_of_page(block: dict[str, Any], source_page_id: str) -> bool:
    parent = block.get("parent") or {}
    return parent.get("type") == "page_id" and parent.get("page_id") == source_page_id


def _move_spec_from_block(block: dict[str, Any], rows: list[list[str]] | None = None) -> dict[str, Any]:
    """Copy only simple API-supported blocks; complex/nested blocks remain manual moves."""
    block_type = block.get("type", "")
    if block.get("has_children") and block_type != "table":
        raise ValueError("los bloques con contenido anidado no se pueden mover automáticamente")
    if block_type == "divider":
        return {"type": "divider"}
    if block_type == "table":
        if not rows:
            raise ValueError("la tabla no tiene filas que se puedan copiar")
        value = block.get("table", {})
        return {
            "type": "table", "rows": rows,
            "has_column_header": bool(value.get("has_column_header", False)),
            "has_row_header": bool(value.get("has_row_header", False)),
        }
    if block_type not in _RICH_BLOCK_TYPES:
        raise ValueError(f"el tipo {block_type or 'unknown'} no se puede mover automáticamente")
    value = block.get(block_type, {})
    text = _plain_text(value.get("rich_text"))
    if not text:
        raise ValueError("el bloque no contiene texto que se pueda copiar")
    spec: dict[str, Any] = {"type": block_type, "text": text}
    if block_type == "to_do":
        spec["checked"] = bool(value.get("checked", False))
    if block_type == "callout":
        icon = (value.get("icon") or {}).get("emoji")
        if icon:
            spec["icon"] = icon
        spec["color"] = value.get("color", "blue_background")
    return spec


async def _plan_move_specs(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = []
    for block in blocks:
        rows = None
        if block.get("type") == "table":
            response = await _request("GET", f"/blocks/{block['id']}/children?page_size=100")
            rows = [
                [_plain_text(cell) for cell in row.get("table_row", {}).get("cells", [])]
                for row in response.get("results", [])
                if row.get("type") == "table_row"
            ]
        specs.append(_move_spec_from_block(block, rows))
    return specs


async def prepare_notion_destructive_change(
    operation: str, source_page_id: str, block_ids: list[str], target_page_id: str = "",
    reason: str = "",
) -> dict:
    """Prepare—not execute—a deletion or block move that requires two user confirmations."""
    if operation not in {"delete_blocks", "move_blocks"}:
        return {"ok": False, "error": "operación no válida"}
    if not source_page_id or not block_ids or len(block_ids) > 20:
        return {"ok": False, "error": "indica una página origen y entre 1 y 20 bloques"}
    if operation == "move_blocks" and not target_page_id:
        return {"ok": False, "error": "mover bloques requiere una página destino"}
    if operation == "move_blocks" and target_page_id == source_page_id:
        return {"ok": False, "error": "el destino debe ser distinto del origen"}

    source_page = await _request("GET", f"/pages/{source_page_id}")
    if operation == "move_blocks":
        await _request("GET", f"/pages/{target_page_id}")
    source_blocks = [await _request("GET", f"/blocks/{block_id}") for block_id in block_ids]
    if any(not _direct_child_of_page(block, source_page_id) for block in source_blocks):
        return {"ok": False, "error": "solo se pueden gestionar bloques directos de la página origen"}

    move_specs = []
    if operation == "move_blocks":
        try:
            move_specs = await _plan_move_specs(source_blocks)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    plan_id = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10].upper()
    plans = _load_destructive_plans()
    plans[plan_id] = {
        "operation": operation,
        "source_page_id": source_page_id,
        "target_page_id": target_page_id,
        "block_ids": block_ids,
        "move_specs": move_specs,
        "reason": reason.strip(),
        "state": "awaiting_first_confirmation",
        "created_at": time.time(),
        "expires_at": time.time() + _DESTRUCTIVE_PLAN_TTL_SECONDS,
    }
    _save_destructive_plans(plans)
    verb = "mandar a la papelera" if operation == "delete_blocks" else "copiar al destino y mandar los originales a la papelera"
    return {
        "ok": True,
        "prepared": True,
        "plan_id": plan_id,
        "source_page": _page_summary(source_page),
        "operation": operation,
        "effect": verb,
        "reason": reason.strip(),
        "blocks": [_block_preview(block) for block in source_blocks],
        "first_confirmation": f"CONFIRMAR {plan_id} PASO 1",
        "second_confirmation": f"CONFIRMAR {plan_id} PASO 2",
        "expires_in_minutes": _DESTRUCTIVE_PLAN_TTL_SECONDS // 60,
    }


def _has_current_confirmation(plan_id: str, step: int) -> bool:
    expected = f"confirmar {plan_id} paso {step}".casefold()
    actual = " ".join(_active_confirmation_message.get().split()).casefold()
    return actual == expected


async def confirm_notion_destructive_change(plan_id: str) -> dict:
    """Advance or execute a prepared plan only when the exact user confirmation is present."""
    plans = _load_destructive_plans()
    plan = plans.get(plan_id)
    if not plan:
        return {"ok": False, "error": "plan inexistente o caducado; prepara uno nuevo"}
    if plan["state"] == "awaiting_first_confirmation":
        if not _has_current_confirmation(plan_id, 1):
            return {"ok": False, "error": f"falta la primera confirmación exacta: CONFIRMAR {plan_id} PASO 1"}
        plan["state"] = "awaiting_second_confirmation"
        _save_destructive_plans(plans)
        return {
            "ok": True, "first_confirmation_recorded": True,
            "message": "Primera confirmación registrada. Explica de nuevo el efecto y pide la segunda confirmación en un mensaje separado.",
            "second_confirmation": f"CONFIRMAR {plan_id} PASO 2",
        }
    if plan["state"] != "awaiting_second_confirmation":
        return {"ok": False, "error": "el plan no está listo para confirmar"}
    if not _has_current_confirmation(plan_id, 2):
        return {"ok": False, "error": f"falta la segunda confirmación exacta: CONFIRMAR {plan_id} PASO 2"}

    if plan["operation"] == "move_blocks":
        await _request("PATCH", f"/blocks/{plan['target_page_id']}/children", {"children": [_normalise_rich_block(spec) for spec in plan["move_specs"]]})
    results = [await _request("DELETE", f"/blocks/{block_id}") for block_id in plan["block_ids"]]
    plans.pop(plan_id, None)
    _save_destructive_plans(plans)
    return {
        "ok": True, "executed": True, "operation": plan["operation"],
        "trashed_blocks": len(results), "target_page_id": plan.get("target_page_id") or None,
        "message": "Operación terminada. Los bloques originales están en la papelera de Notion y se pueden restaurar.",
    }


async def cancel_notion_destructive_change(plan_id: str) -> dict:
    """Cancel a prepared destructive plan before its second confirmation."""
    plans = _load_destructive_plans()
    if plan_id not in plans:
        return {"ok": False, "error": "plan inexistente o ya finalizado"}
    plans.pop(plan_id, None)
    _save_destructive_plans(plans)
    return {"ok": True, "cancelled": True}


async def create_notion_database_record(
    data_source_id: str, title: str, content: str = "", fields: dict[str, Any] | None = None,
    template: str = "", sections: dict[str, Any] | None = None, blocks: list[dict[str, Any]] | None = None,
) -> dict:
    """Create a record with schema-safe properties and optional rich Notion blocks."""
    title = title.strip()
    if not title:
        return {"ok": False, "error": "title vacío"}
    data_source = await _request("GET", f"/data_sources/{data_source_id}")
    properties = _database_properties(_data_source_schema(data_source), title, fields or {})
    children = _rich_blocks(content, template, sections, blocks)
    page = await _request("POST", "/pages", {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
        "children": children,
    })
    return {"ok": True, "page": _page_summary(page), "blocks_created": len(children)}


async def update_notion_database_record(page_id: str, fields: dict[str, Any]) -> dict:
    """Update known properties of an existing database record; never changes content."""
    page = await _request("GET", f"/pages/{page_id}")
    data_source_id = (page.get("parent") or {}).get("data_source_id")
    if not data_source_id:
        return {"ok": False, "error": "la página no pertenece a una base de datos"}
    data_source = await _request("GET", f"/data_sources/{data_source_id}")
    properties = _database_properties(_data_source_schema(data_source), None, fields)
    updated = await _request("PATCH", f"/pages/{page_id}", {"properties": properties})
    return {"ok": True, "page": _page_summary(updated)}


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
    "description": "Lee una página de Notion por su id después de localizarla con search_notion. Si devuelve has_more=true, vuelve a llamarla con next_cursor para leer la siguiente tanda de bloques.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "max_blocks": {"type": "integer", "minimum": 1, "maximum": 100}, "start_cursor": {"type": "string", "description": "Cursor next_cursor devuelto por una lectura anterior de la misma página."}}, "required": ["page_id"]},
}

CREATE_PAGE_DEF = {
    "name": "create_notion_page",
    "description": "Crea una página hija en Notion con contenido enriquecido opcional. Confirma con Jorge antes de crearla salvo que él haya pedido claramente crear esa página concreta.",
    "input_schema": {"type": "object", "properties": {"parent_page_id": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}, "template": {"type": "string", "enum": ["hornbills_review", "product_update", "marketing_proposal", "action", "structured_note"]}, "sections": {"type": "object", "additionalProperties": {}}, "blocks": {"type": "array", "items": {"type": "object", "additionalProperties": {}}}}, "required": ["parent_page_id", "title"]},
}

CREATE_DATABASE_DEF = {
    "name": "create_notion_database",
    "description": "Crea una base de datos nueva como hija de una página concreta de Notion. Úsala solo cuando Jorge haya pedido explícitamente crear esa base, con nombre y ubicación claros. Nunca la crees en Backlog u otra página por suposición.",
    "input_schema": {
        "type": "object",
        "properties": {
            "parent_page_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "properties": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["title", "rich_text", "date", "select", "multi_select", "number", "checkbox", "url"]},
                    },
                    "required": ["name", "type"],
                },
            },
        },
        "required": ["parent_page_id", "title", "properties"],
    },
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

APPEND_RICH_BLOCKS_DEF = {
    "name": "append_notion_rich_blocks",
    "description": "Añade bloques enriquecidos a una página o registro de Notion sin sustituir contenido existente. Lee primero la página. Usa template para una estructura consistente o blocks para títulos, listas, callouts, checks, tablas y enlaces.",
    "input_schema": {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "template": {"type": "string", "enum": ["hornbills_review", "product_update", "marketing_proposal", "action", "structured_note"]},
            "sections": {"type": "object", "additionalProperties": {}},
            "content": {"type": "string", "description": "Alternativa simple si no se usa template ni blocks."},
            "blocks": {
                "type": "array",
                "description": "Bloques permitidos: paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item, to_do, quote, callout, divider o table. Las tablas usan rows.",
                "items": {"type": "object", "additionalProperties": {}},
            },
        },
        "required": ["page_id"],
    },
}

UPDATE_BLOCK_DEF = {
    "name": "update_notion_block",
    "description": "Edita un bloque existente de Notion conservando su formato y tipo (título, párrafo, lista, check, cita o callout). Lee primero la página, identifica el bloque exacto y úsala para corregir o reescribir ese bloque; no añadas texto plano duplicado.",
    "input_schema": {
        "type": "object",
        "properties": {
            "block_id": {"type": "string"},
            "block": {"type": "object", "description": "Debe conservar el mismo type del bloque actual y usar text, checked, icon, color o url cuando corresponda."},
        },
        "required": ["block_id", "block"],
    },
}

UPDATE_PAGE_MARKDOWN_DEF = {
    "name": "update_notion_page_markdown",
    "description": "Sustituye texto o Markdown de forma precisa dentro de una página de Notion. Lee primero el contenido y usa old_str exacto para no reescribir ni duplicar el resto de la página. Conserva formato enriquecido de Notion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "updates": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "object", "properties": {"old_str": {"type": "string"}, "new_str": {"type": "string"}}, "required": ["old_str", "new_str"]}},
        },
        "required": ["page_id", "updates"],
    },
}

REPLACE_PAGE_CONTENT_DEF = {
    "name": "replace_notion_page_content",
    "description": "Reemplaza todo el contenido de una página por Markdown enriquecido. Úsala ÚNICAMENTE si Jorge ha pedido claramente rehacer o sustituir toda la página; primero lee la página y describe brevemente qué se sustituirá. No permite borrar páginas hijas o bases de datos.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "markdown": {"type": "string"}}, "required": ["page_id", "markdown"]},
}

MOVE_PAGE_DEF = {
    "name": "move_notion_page",
    "description": "Mueve una página de Notion a una página padre concreta o a una base concreta. Úsala solo cuando Jorge haya indicado claramente el destino; verifica origen y destino antes de mover.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "parent_id": {"type": "string"}, "parent_type": {"type": "string", "enum": ["page_id", "data_source_id"]}}, "required": ["page_id", "parent_id"]},
}

SET_PAGE_TRASH_DEF = {
    "name": "set_notion_page_trash",
    "description": "Manda una página de Notion a la papelera o la restaura. Úsala solo tras una instrucción inequívoca de Jorge para borrar o restaurar esa página concreta; confirma el título y el efecto antes de ejecutarla.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "in_trash": {"type": "boolean"}}, "required": ["page_id", "in_trash"]},
}

PREPARE_DESTRUCTIVE_CHANGE_DEF = {
    "name": "prepare_notion_destructive_change",
    "description": "PREPARA, pero nunca ejecuta, el borrado o movimiento de bloques directos de una página de Notion. Úsala solo después de leer la página y de que Jorge haya indicado exactamente qué bloques quiere cambiar. Tras prepararla, explica el efecto y que habrá DOS confirmaciones separadas; muestra la primera frase exacta devuelta. Para mover, los bloques compatibles se copian al destino y los originales se mandan a la papelera solo tras la segunda confirmación.",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["delete_blocks", "move_blocks"]},
            "source_page_id": {"type": "string"},
            "block_ids": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string"}},
            "target_page_id": {"type": "string", "description": "Obligatorio para move_blocks."},
            "reason": {"type": "string", "description": "Motivo breve que se mostrará a Jorge."},
        },
        "required": ["operation", "source_page_id", "block_ids"],
    },
}

CONFIRM_DESTRUCTIVE_CHANGE_DEF = {
    "name": "confirm_notion_destructive_change",
    "description": "Registra la primera confirmación o ejecuta la segunda de un cambio de bloques ya preparado. Llámala SOLO cuando el último mensaje de Jorge sea exactamente la frase de confirmación devuelta por el plan. La primera no cambia Notion: vuelve a explicar el efecto y pide la segunda frase en un mensaje separado. La segunda realiza el cambio.",
    "input_schema": {
        "type": "object",
        "properties": {"plan_id": {"type": "string"}},
        "required": ["plan_id"],
    },
}

CANCEL_DESTRUCTIVE_CHANGE_DEF = {
    "name": "cancel_notion_destructive_change",
    "description": "Cancela un borrado o movimiento de bloques que estaba preparado y todavía no se ha ejecutado. Úsala si Jorge cancela o cambia de idea.",
    "input_schema": {
        "type": "object",
        "properties": {"plan_id": {"type": "string"}},
        "required": ["plan_id"],
    },
}

READ_DATA_SOURCE_DEF = {
    "name": "read_notion_data_source",
    "description": "Lee el esquema real de una base de datos de Notion antes de crear un registro. Úsala después de localizar la base con search_notion.",
    "input_schema": {"type": "object", "properties": {"data_source_id": {"type": "string"}}, "required": ["data_source_id"]},
}

ADD_DATA_SOURCE_PROPERTIES_DEF = {
    "name": "add_notion_data_source_properties",
    "description": "Añade columnas NUEVAS a una base de Notion. Úsala solo si Jorge ha pedido explícitamente añadir campos y después de leer el esquema. Nunca borra, renombra ni cambia el tipo de columnas existentes; las columnas ya presentes se omiten.",
    "input_schema": {
        "type": "object",
        "properties": {
            "data_source_id": {"type": "string"},
            "properties": {
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["rich_text", "date", "select", "multi_select", "number", "checkbox", "url"]},
                    },
                    "required": ["name", "type"],
                },
            },
        },
        "required": ["data_source_id", "properties"],
    },
}

CREATE_DATABASE_RECORD_DEF = {
    "name": "create_notion_database_record",
    "description": "Crea un registro nuevo dentro de una base de datos compartida de Notion. Lee antes el esquema, guarda solo propiedades válidas y puede crear contenido enriquecido con template o blocks. Nunca modifica ni borra registros existentes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "data_source_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "fields": {"type": "object", "additionalProperties": {}},
            "template": {"type": "string", "enum": ["hornbills_review", "product_update", "marketing_proposal", "action", "structured_note"]},
            "sections": {"type": "object", "additionalProperties": {}},
            "blocks": {"type": "array", "items": {"type": "object", "additionalProperties": {}}},
        },
        "required": ["data_source_id", "title"],
    },
}

UPDATE_DATABASE_RECORD_DEF = {
    "name": "update_notion_database_record",
    "description": "Actualiza propiedades conocidas de un registro existente de una base de datos de Notion. Úsala solo después de leer o localizar el registro; nunca sustituye el contenido de la página.",
    "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}, "fields": {"type": "object", "additionalProperties": {}}}, "required": ["page_id", "fields"]},
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
