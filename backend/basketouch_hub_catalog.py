"""Safe, name-based Notion destination map for the Basketouch operational hub."""

BASKETOUCH_HUB_DESTINATIONS = {
    "actions": {"name": "Acciones", "when": "A concrete, cross-product or operational next action that must be worked on.", "rule": "This is the only active work list. Check duplicates; create in Inbox unless Jorge explicitly prioritises it. Respect the maximum of five actions in Esta semana."},
    "weekly_review": {"name": "Revisión semanal", "when": "Reviewing commitments and deciding what matters this week.", "rule": "Read it for current focus. Do not keep parallel task lists in chat or another page."},
    "hub_status": {"name": "Estado del Hub", "when": "A verified operational state, architecture decision or completed hub milestone.", "rule": "Read before saying infrastructure or a feature is live. Do not append routine chat notes."},
    "modules": {"name": "Módulos por producto", "when": "Implemented-versus-pending state of a dashboard or product module.", "rule": "Use as reference only; do not claim data or a module exists without verification."},
    "roadmap": {"name": "Roadmap — basketouch.com", "when": "A hub-level initiative needing scope or sequencing.", "rule": "Keep it as a proposal until Jorge confirms priority and ownership."},
    "dashboard_spec": {"name": "Dashboards por producto — especificación técnica", "when": "A dashboard, data-source or instrumentation design decision.", "rule": "Never copy mockup figures into production; real dashboard data must come from verified sources."},
}


def get_basketouch_hub_destinations() -> dict:
    return {"destinations": BASKETOUCH_HUB_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_basketouch_hub_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para Basketouch Hub. Úsalo antes de organizar información transversal u operativa.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
