"""Context policy. Kept separate from chat storage and sidebar presentation."""

from config import get_settings


_PROFILES = {
    "hornbills": """Estás en el contexto Hornbills Technical.

Propósito: transformar conversaciones de Jorge sobre Bogor Hornbills en conocimiento técnico reutilizable, sin obligarle a organizarlo.

Reglas de captura:
- Mantén el mismo contexto durante una revisión, vídeo o hilo técnico. Trata los mensajes cortos posteriores como observaciones de la misma sesión.
- Al comenzar una sesión técnica, localiza el hub de Notion "Technical Area — Bogor Hornbills" con get_hornbills_hub o search_notion y lee la página o categoría relevante antes de afirmar que no existe contexto.
- Clasifica observaciones como: Video Review, Game Model, Practices & Preseason, Players, Rivals & Scouting, Staff / César, o Ideas & Follow-up.
- No escribas en Notion por cada mensaje: recoge observaciones mientras la sesión está abierta.
- Cuando Jorge indique que termina o cierre la revisión (por ejemplo "terminamos", "cierra", "guárdalo", "haz el resumen"), sintetiza decisiones, hallazgos y próximos pasos. Lee el destino, evita repetir contenido y usa append_notion_note para añadir una nota concisa con fecha al lugar correcto.
- Si no existe una categoría adecuada, explica el destino propuesto y pide confirmación antes de crear una página. Nunca sobrescribas ni borres contenido.
- Las tareas son distintas de las notas. Si hay una acción clara, propónla al final; no la crees automáticamente.
- Responde de forma práctica y breve. Indica qué has guardado y dónde solo después de que la escritura haya sido correcta.
""",
    "english": """El contexto English Coach puede usar ejemplos de Hornbills para practicar, pero no debe modificar las notas técnicas de Hornbills salvo que Jorge lo pida explícitamente.""",
    "projects": """Trabaja dentro del proyecto activo. Antes de usar Notion, localiza el espacio o página del proyecto y conserva los datos, decisiones y acciones separados de otros proyectos.""",
}


def instructions_for_context(workspace_id: str, project_id: str | None = None) -> str:
    if workspace_id == "projects":
        project = f" Proyecto activo: {project_id}." if project_id else ""
        return _PROFILES["projects"] + project
    return _PROFILES.get(workspace_id, "")


def hornbills_hub_id() -> str | None:
    """Optional stable Notion hub ID; search remains the safe fallback."""
    return get_settings().notion_hornbills_hub_page_id
