from duckduckgo_search import DDGS

SEARCH_DEF = {
    "name": "web_search",
    "description": (
        "Busca información actualizada en internet usando DuckDuckGo. "
        "Úsala cuando necesites información reciente, noticias, precios, datos actuales "
        "o cualquier cosa que pueda haber cambiado desde tu fecha de entrenamiento."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Consulta de búsqueda en el idioma más adecuado",
            },
            "max_results": {
                "type": "integer",
                "description": "Número de resultados (por defecto 5, máximo 10)",
            },
        },
        "required": ["query"],
    },
}


def web_search(query: str, max_results: int = 5) -> dict:
    max_results = min(max_results, 10)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return {"resultados": [], "mensaje": "No se encontraron resultados"}
        return {
            "resultados": [
                {
                    "titulo": r.get("title", ""),
                    "url": r.get("href", ""),
                    "resumen": r.get("body", ""),
                }
                for r in results
            ]
        }
    except Exception as e:
        return {"error": str(e)}
