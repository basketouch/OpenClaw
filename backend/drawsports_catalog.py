"""Safe, name-based Notion destination map for DrawSports."""

DRAWSPORTS_DESTINATIONS = {
    "backlog": {"name": "Backlog — DrawSports", "when": "Bug, feature, technical task, App Store issue, web/panel work or documentation task.", "rule": "Check for duplicates before creating or updating. Capture Area, Prioridad, Estado and concise Notas."},
    "project_status": {"name": "Estado del Proyecto", "when": "Verified current product state, completed block of work or a confirmed decision that changes the project narrative.", "rule": "Read it as the source of truth. Do not append routine chat notes or unverified claims."},
    "release": {"name": "Pendiente de publicar", "when": "A change is ready in the repository but not yet published in App Store or web.", "rule": "Accumulate a proposed release item. Never mark a release as published without Jorge's explicit confirmation."},
    "marketing": {"name": "Marketing DrawSports", "when": "Campaign, positioning, content, channel, copy, launch or metric discussion.", "rule": "Keep ideas and copy as proposals until a concrete decision is approved. Do not claim metrics without verification."},
    "version": {"name": "Versión actual en App Store y web", "when": "A verified publication changes what is live.", "rule": "Read before stating what is in production; update only after the publication is confirmed."},
}


def get_drawsports_destinations() -> dict:
    return {"destinations": DRAWSPORTS_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_drawsports_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para DrawSports. Úsalo antes de organizar información del proyecto.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
