import httpx

_TABLES = ["articles", "social_posts", "publish_queue", "newsletter_status", "briefings"]

QUERY_DEF = {
    "name": "query_newsflow",
    "description": (
        "Lee datos de la base de datos de NewsFlow (marca personal de Jorge). "
        "Tablas: articles (noticias/artículos), social_posts (posts LinkedIn/X), "
        "publish_queue (cola de vídeos), newsletter_status (ediciones de newsletter), "
        "briefings (resúmenes diarios con date, content, total_articles, articles JSONB). "
        "Úsala para consultar artículos pendientes, posts programados, estado de newsletter, briefings, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "enum": _TABLES,
                "description": "Tabla a consultar",
            },
            "select": {
                "type": "string",
                "description": "Columnas a devolver, ej: '*' o 'id,title,status'. Por defecto: '*'",
            },
            "filters": {
                "type": "object",
                "description": "Filtros {columna: valor}, ej: {\"status\": \"draft\"}",
            },
            "order": {
                "type": "string",
                "description": "Ordenación, ej: 'created_at.desc'",
            },
            "limit": {
                "type": "integer",
                "description": "Máximo de resultados. Por defecto: 20",
            },
        },
        "required": ["table"],
    },
}

INSERT_DEF = {
    "name": "insert_newsflow",
    "description": "Inserta un nuevo registro en NewsFlow (artículo, post social, etc.).",
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {"type": "string", "enum": _TABLES, "description": "Tabla destino"},
            "data": {"type": "object", "description": "Datos a insertar {columna: valor}"},
        },
        "required": ["table", "data"],
    },
}

UPDATE_DEF = {
    "name": "update_newsflow",
    "description": "Actualiza registros en NewsFlow. Úsalo para cambiar status, editar contenido, etc.",
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {"type": "string", "enum": _TABLES, "description": "Tabla a actualizar"},
            "data": {"type": "object", "description": "Datos a actualizar {columna: valor}"},
            "filters": {"type": "object", "description": "Filtros para seleccionar filas {columna: valor}"},
        },
        "required": ["table", "data", "filters"],
    },
}


def _client_args():
    from config import get_settings
    s = get_settings()
    base = s.supabase_url.rstrip("/") + "/rest/v1"
    headers = {
        "apikey": s.supabase_key,
        "Authorization": f"Bearer {s.supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    return base, headers


async def query_newsflow(
    table: str,
    select: str = "*",
    filters: dict = None,
    order: str = None,
    limit: int = 20,
) -> dict:
    try:
        base, headers = _client_args()
        params = {"select": select, "limit": limit}
        if filters:
            for k, v in filters.items():
                params[k] = f"eq.{v}"
        if order:
            params["order"] = order
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{base}/{table}", headers=headers, params=params)
        if r.status_code >= 400:
            return {"error": r.text[:400]}
        data = r.json()
        return {"data": data, "count": len(data)}
    except Exception as e:
        return {"error": str(e)}


async def insert_newsflow(table: str, data: dict) -> dict:
    try:
        base, headers = _client_args()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{base}/{table}", headers=headers, json=data)
        if r.status_code >= 400:
            return {"error": r.text[:400]}
        return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"error": str(e)}


async def update_newsflow(table: str, data: dict, filters: dict) -> dict:
    try:
        base, headers = _client_args()
        params = {k: f"eq.{v}" for k, v in filters.items()}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.patch(f"{base}/{table}", headers=headers, json=data, params=params)
        if r.status_code >= 400:
            return {"error": r.text[:400]}
        return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"error": str(e)}
