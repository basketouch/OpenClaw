"""Canonical Hornbills destinations. IDs are resolved privately inside Notion."""

HORNIBLLS_DESTINATIONS = {
    "analysis": {"name": "Analysis Library", "when": "Video review, report, clips or team/player analysis.", "rule": "One record per review; separate findings, hypotheses and coaching implications."},
    "practice": {"name": "Practice Sessions", "when": "A planned, reviewed or completed training session.", "rule": "Use only for a concrete session."},
    "scouting": {"name": "Games & Scouting", "when": "Opponent, game plan, game preparation or post-game review.", "rule": "One record per game/opponent; update it as the stage advances."},
    "staff": {"name": "Staff Notes & Decisions", "when": "Staff proposal, meeting note or confirmed technical decision.", "rule": "Use questions only when ready to discuss with staff."},
    "private_note": {"name": "Private Coach Notes", "when": "Unconfirmed observation, question for head coach, sensitive reflection, idea or learning.", "rule": "Default for early-stage observations; preserve uncertainty."},
    "calendar": {"name": "Technical Calendar", "when": "A dated practice, game, meeting, trip or deadline.", "rule": "Only create with a concrete date."},
    "document": {"name": "Document Library", "when": "Game plan, practice document, PDF, presentation, template or resource.", "rule": "Store or link the document; do not duplicate analysis/scouting text."},
}


def get_hornbills_destinations() -> dict:
    return {"destinations": HORNIBLLS_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_hornbills_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para Hornbills. Úsalo antes de guardar o actualizar conocimiento técnico.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
