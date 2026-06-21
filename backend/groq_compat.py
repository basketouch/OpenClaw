"""Utilidades para usar Groq (API compatible con OpenAI) con las mismas tool
definitions que usamos para Claude/GLM (formato de la API de Messages de Anthropic)."""


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]
