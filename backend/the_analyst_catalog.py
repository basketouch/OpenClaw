"""Safe, name-based Notion destination map for The Analyst."""

THE_ANALYST_DESTINATIONS = {
    "backlog": {"name": "Backlog — Incoherencias y Limpieza", "when": "Bug, inconsistency, regression, cleanup or concrete technical/product task.", "rule": "Check for duplicates before creating or updating. Keep verified evidence and the expected result concise."},
    "roadmap": {"name": "Roadmap — Próximos Pasos", "when": "A product initiative or next-step proposal that needs prioritisation rather than immediate execution.", "rule": "Keep it as a proposal until Jorge confirms the decision and priority."},
    "project_status": {"name": "Estado del Proyecto", "when": "Verified production state, completed work or a confirmed product decision.", "rule": "Read before stating what is live or complete. Do not append routine chat notes or unverified claims."},
    "prospects": {"name": "Entrenadores — Clientes Potenciales", "when": "A real coach or prospect with useful contact context.", "rule": "Create or update only after Jorge explicitly confirms it is a prospect or uses the CRM shortcut."},
    "ambassadors": {"name": "Entrenadores Embajadores", "when": "A potential ambassador or approved collaboration.", "rule": "Do not create from a casual name mention; confirm fit, value and outreach intent first."},
    "social_calendar": {"name": "Calendario RRSS", "when": "An approved social/email/web content piece with channel, language and publication intent.", "rule": "Draft copy freely, but only schedule or create the record after Jorge confirms the piece."},
    "testimonials": {"name": "Casos de éxito / Testimonios", "when": "A client story or testimonial with explicit permission to use it.", "rule": "Never mark a testimonial as authorised without clear consent."},
    "marketing": {"name": "Marketing The Analyst", "when": "Positioning, campaign, launch, copy, target segment or measurement discussion.", "rule": "Treat ideas as proposals and do not claim campaign results or production metrics without verification."},
}


def get_the_analyst_destinations() -> dict:
    return {"destinations": THE_ANALYST_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_the_analyst_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para The Analyst. Úsalo antes de organizar información del proyecto.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
