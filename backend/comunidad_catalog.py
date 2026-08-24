"""Safe, name-based Notion destination map for Comunidad de Entrenadores."""

COMUNIDAD_DESTINATIONS = {
    "backlog": {"name": "Backlog — Comunidad", "when": "Product, Skool, marketing, content, metrics or documentation work that is not yet ready to publish.", "rule": "Check for duplicates before creating or updating. Capture Área, Prioridad, Estado and concise Notas."},
    "project_status": {"name": "Estado del Proyecto", "when": "Verified current state, completed work or a confirmed strategic decision.", "rule": "Read it as the source of truth. Do not append routine notes or unverified claims."},
    "product": {"name": "Producto actual", "when": "A confirmed change to the offer, tiers, audience or included value.", "rule": "Read before explaining the current offer; update only after the commercial decision is confirmed."},
    "pending_publish": {"name": "Pendiente de publicar", "when": "A content piece is already prepared or nearly finished, with channel, format and next publishing action defined.", "rule": "Ideas and drafts do not belong here. Never mark content as published without Jorge's confirmation."},
    "marketing": {"name": "Marketing Comunidad", "when": "Editorial strategy, funnel, channel, campaign, content concept, copy or measurement discussion.", "rule": "Keep ideas as proposals. Do not state performance metrics as current unless verified from the relevant source."},
    "pricing": {"name": "Precios", "when": "A verified pricing or packaging decision.", "rule": "Read before citing prices. Do not change pricing based on a conversational suggestion."},
}


def get_comunidad_destinations() -> dict:
    return {"destinations": COMUNIDAD_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_comunidad_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para Comunidad de Entrenadores. Úsalo antes de organizar información del proyecto.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
