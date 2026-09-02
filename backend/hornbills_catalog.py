"""Canonical Hornbills destinations. IDs are resolved privately inside Notion."""

HORNIBLLS_DESTINATIONS = {
    "analysis": {"name": "Analysis Library", "when": "Video review, report, clips or team/player analysis.", "rule": "One record per review; separate findings, hypotheses and coaching implications."},
    "practice": {"name": "Practice Sessions", "when": "A planned, reviewed or completed training session.", "rule": "Use only for a concrete session."},
    "scouting": {"name": "Games & Scouting", "when": "Opponent, game plan, game preparation or post-game review.", "rule": "One record per game/opponent; update it as the stage advances."},
    "decisions": {"name": "Decisions & Meetings", "when": "Jorge's meeting preparation, follow-up, technical proposal or confirmed decision.", "rule": "This is Jorge's private working record. Do not prepare or share material with staff unless Jorge explicitly asks."},
    "private_note": {"name": "Private Coach Notes", "when": "Unconfirmed observation, reflection, idea, learning or question to consider later.", "rule": "Default for early-stage observations; preserve uncertainty."},
    "players": {"name": "Players", "when": "Stable player profile, role, strength or development focus.", "rule": "Read first and update only after Jorge confirms the information is stable; use Private Coach Notes for an initial evaluation."},
    "calendar": {"name": "Technical Calendar", "when": "A dated meeting, trip, deadline or independent event.", "rule": "Never duplicate a practice or game here: those dates live only in Practice Sessions or Games & Scouting."},
    "document": {"name": "Document Library", "when": "Game plan, practice document, PDF, presentation, template or resource.", "rule": "Store or link the document; do not duplicate analysis/scouting text."},
}


def get_hornbills_destinations() -> dict:
    return {"destinations": HORNIBLLS_DESTINATIONS}


DESTINATIONS_DEF = {
    "name": "get_hornbills_destinations",
    "description": "Devuelve el mapa canónico de destinos Notion para Hornbills. Úsalo antes de guardar o actualizar conocimiento técnico.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
