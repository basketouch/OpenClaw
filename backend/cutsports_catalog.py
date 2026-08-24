"""Safe, name-based Notion destination map for CutSports."""

CUTSPORTS_DESTINATIONS = {
    "backlog": {"name": "Backlog — CutSports", "when": "Bug, feature, technical task, release blocker or documentation task.", "rule": "Create or update only after checking for a duplicate. Capture Area, Prioridad and concise Notas."},
    "crm": {"name": "CRM — CutSports", "when": "A real lead, club, coach or partner with clear contact/prospect information.", "rule": "Never create a contact from a casual mention; require Jorge's explicit confirmation or a CRM shortcut."},
    "project_status": {"name": "Estado del Proyecto", "when": "Verified current state, completed work or a decision that changes the project narrative.", "rule": "Read as source of truth. Do not append routine chat notes automatically."},
    "release": {"name": "Pendiente de publicar", "when": "A completed change that must join the next web or Mac publication batch.", "rule": "Propose the release note; only update after Jorge confirms the release content."},
    "marketing": {"name": "Marketing CutSports", "when": "Campaign, BETA, positioning, copy or launch material.", "rule": "Keep ideas as a proposal until a concrete campaign decision exists."},
    "analytics": {"name": "Analytics & Telemetría — Plan maestro", "when": "Telemetry, privacy, activation, funnel or product usage metrics.", "rule": "Do not state production metrics unless they were verified from the relevant source."},
}


def get_cutsports_destinations() -> dict:
    return {"destinations": CUTSPORTS_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_cutsports_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para CutSports. Úsalo antes de organizar información del proyecto.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
