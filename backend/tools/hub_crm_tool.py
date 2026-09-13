"""Private read-only bridge to the operational Basketouch Hub CRM."""

from typing import Any

import httpx

from config import get_settings


def _settings() -> tuple[str, str]:
    settings = get_settings()
    url = (settings.hub_crm_url or "").rstrip("/")
    secret = settings.hub_crm_api_secret or ""
    if not url or not secret:
        raise RuntimeError("CRM del Hub no configurado: faltan HUB_CRM_URL o HUB_CRM_API_SECRET")
    return url, secret


async def _request(params: dict[str, Any]) -> dict[str, Any]:
    url, secret = _settings()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params=params, headers={"Authorization": f"Bearer {secret}"})
    if response.status_code >= 400:
        raise RuntimeError(f"CRM del Hub: HTTP {response.status_code} {response.text[:300]}")
    return response.json()


async def get_hub_crm_summary() -> dict:
    """Return live CRM metrics from Basketouch Hub, not a Notion summary."""
    return await _request({"mode": "summary"})


async def search_hub_crm_contacts(query: str = "", limit: int = 20) -> dict:
    """Search all Hub CRM contacts, including newsletter-only contacts."""
    return await _request({"mode": "search", "q": query.strip(), "limit": max(1, min(50, int(limit)))})


async def read_hub_crm_contact(contact_id: str = "", email: str = "") -> dict:
    """Read a single Hub CRM contact by its CRM id or email."""
    if not contact_id.strip() and not email.strip():
        return {"ok": False, "error": "Indica contact_id o email"}
    payload: dict[str, str] = {"mode": "contact"}
    if contact_id.strip():
        payload["id"] = contact_id.strip()
    if email.strip():
        payload["email"] = email.strip()
    return await _request(payload)


SUMMARY_DEF = {
    "name": "get_hub_crm_summary",
    "description": "Consulta las métricas actuales del CRM operativo de Basketouch Hub: contactos, newsletter, BETA, contactos sin próxima acción y contactos en varios proyectos. Úsala para cifras CRM; no uses Notion como fuente de esas métricas.",
    "input_schema": {"type": "object", "properties": {}},
}

SEARCH_DEF = {
    "name": "search_hub_crm_contacts",
    "description": "Busca en todo el CRM operativo de Basketouch Hub, incluidos contactos de producto y contactos que solo pertenecen a la newsletter. Es solo lectura.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Nombre, email, organización, producto, estado o próxima acción."},
            "limit": {"type": "integer", "description": "Máximo de resultados (1-50).", "default": 20},
        },
    },
}

READ_DEF = {
    "name": "read_hub_crm_contact",
    "description": "Lee la ficha completa disponible de un contacto del CRM operativo de Basketouch Hub. Es solo lectura.",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string", "description": "ID del CRM devuelto por la búsqueda."},
            "email": {"type": "string", "description": "Email del contacto si no se conoce el ID."},
        },
    },
}
