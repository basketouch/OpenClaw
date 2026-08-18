import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

DATA_DIR = "/data/english"
PHRASES_FILE = os.path.join(DATA_DIR, "phrases.json")

CATEGORIES = {"Basketball", "Coaching", "Meetings", "Daily Life", "Business/Networking", "Useful English"}
STATUSES = {"New", "Learning", "Familiar", "Automatic"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> list[dict]:
    try:
        with open(PHRASES_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PHRASES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PHRASES_FILE)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _safe_category(category: str) -> str:
    return category if category in CATEGORIES else "Useful English"


def save_english_phrase(
    phrase: str,
    spanish: str,
    natural_version: str = "",
    category: str = "Useful English",
    context: str = "",
    phrase_type: str = "Phrase",
    importance: int = 3,
    example: str = "",
    my_mistake: str = "",
) -> dict:
    phrase = phrase.strip()
    if not phrase:
        return {"ok": False, "error": "phrase vacía"}

    items = _load()
    key = _norm(phrase)
    existing = next((x for x in items if _norm(x.get("phrase", "")) == key), None)
    now = _now()

    if existing:
        existing.update({
            "spanish": spanish.strip() or existing.get("spanish", ""),
            "natural_version": natural_version.strip() or existing.get("natural_version", ""),
            "category": _safe_category(category),
            "context": context.strip() or existing.get("context", ""),
            "type": phrase_type.strip() or existing.get("type", "Phrase"),
            "importance": max(1, min(5, int(importance))),
            "example": example.strip() or existing.get("example", ""),
            "my_mistake": my_mistake.strip() or existing.get("my_mistake", ""),
            "updated_at": now.isoformat(),
        })
        _save(items)
        return {"ok": True, "created": False, "item": existing}

    item = {
        "id": str(uuid.uuid4())[:8],
        "phrase": phrase,
        "spanish": spanish.strip(),
        "natural_version": natural_version.strip(),
        "category": _safe_category(category),
        "context": context.strip(),
        "type": phrase_type.strip() or "Phrase",
        "importance": max(1, min(5, int(importance))),
        "example": example.strip(),
        "my_mistake": my_mistake.strip(),
        "status": "New",
        "added_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "last_review": None,
        "next_review": now.isoformat(),
        "times_reviewed": 0,
        "correct_streak": 0,
    }
    items.append(item)
    _save(items)
    return {"ok": True, "created": True, "item": item}


def search_english_phrases(query: str = "", category: str = "", status: str = "", limit: int = 20) -> dict:
    items = _load()
    q = _norm(query)
    result = []
    for item in reversed(items):
        if category and item.get("category") != category:
            continue
        if status and item.get("status") != status:
            continue
        haystack = " ".join([
            item.get("phrase", ""), item.get("spanish", ""), item.get("context", ""), item.get("example", "")
        ])
        if q and q not in _norm(haystack):
            continue
        result.append(item)
        if len(result) >= max(1, min(100, limit)):
            break
    return {"count": len(result), "items": result}


def get_english_review(limit: int = 5) -> dict:
    now = _now()
    items = _load()
    due = []
    for item in items:
        next_review = item.get("next_review")
        try:
            due_at = datetime.fromisoformat(next_review) if next_review else now
        except ValueError:
            due_at = now
        if due_at <= now:
            due.append(item)

    due.sort(key=lambda x: (
        -int(x.get("importance", 3)),
        int(x.get("times_reviewed", 0)),
        x.get("added_at", ""),
    ))
    selected = due[:max(1, min(20, limit))]
    return {"due_count": len(due), "items": selected}


def record_english_result(phrase_id: str, correct: bool) -> dict:
    items = _load()
    item = next((x for x in items if x.get("id") == phrase_id), None)
    if not item:
        return {"ok": False, "error": "phrase_id no encontrado"}

    now = _now()
    streak = int(item.get("correct_streak", 0))
    reviewed = int(item.get("times_reviewed", 0)) + 1

    if correct:
        streak += 1
        intervals = [1, 3, 7, 15, 30, 60]
        days = intervals[min(streak - 1, len(intervals) - 1)]
        if streak >= 5:
            status = "Automatic"
        elif streak >= 3:
            status = "Familiar"
        else:
            status = "Learning"
    else:
        streak = 0
        days = 1
        status = "Learning"

    item.update({
        "correct_streak": streak,
        "times_reviewed": reviewed,
        "status": status,
        "last_review": now.isoformat(),
        "next_review": (now + timedelta(days=days)).isoformat(),
        "updated_at": now.isoformat(),
    })
    _save(items)
    return {"ok": True, "item": item}


def get_english_progress() -> dict:
    items = _load()
    by_status = {status: 0 for status in STATUSES}
    by_category = {category: 0 for category in CATEGORIES}
    core = 0
    for item in items:
        by_status[item.get("status", "New")] = by_status.get(item.get("status", "New"), 0) + 1
        category = item.get("category", "Useful English")
        by_category[category] = by_category.get(category, 0) + 1
        if item.get("type", "").lower() == "core phrase":
            core += 1
    return {
        "total": len(items),
        "core_phrases": core,
        "by_status": by_status,
        "by_category": by_category,
        "due_now": get_english_review(limit=20)["due_count"],
    }


SAVE_DEF = {
    "name": "save_english_phrase",
    "description": "Guarda o actualiza una frase útil en el English Playbook de Jorge. Úsala cuando Jorge pida guardar algo o cuando quede claro que una frase es recurrente/importante.",
    "input_schema": {
        "type": "object",
        "properties": {
            "phrase": {"type": "string"},
            "spanish": {"type": "string"},
            "natural_version": {"type": "string"},
            "category": {"type": "string", "enum": sorted(CATEGORIES)},
            "context": {"type": "string"},
            "phrase_type": {"type": "string", "description": "Normalmente Phrase o Core Phrase."},
            "importance": {"type": "integer", "minimum": 1, "maximum": 5},
            "example": {"type": "string"},
            "my_mistake": {"type": "string"},
        },
        "required": ["phrase", "spanish"],
    },
}

SEARCH_DEF = {
    "name": "search_english_phrases",
    "description": "Busca frases ya guardadas en el English Playbook.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string"},
            "status": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": [],
    },
}

REVIEW_DEF = {
    "name": "get_english_review",
    "description": "Obtiene frases que toca repasar según spaced repetition.",
    "input_schema": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
        "required": [],
    },
}

RESULT_DEF = {
    "name": "record_english_result",
    "description": "Registra si Jorge acertó o falló una frase durante un repaso y calcula la próxima revisión.",
    "input_schema": {
        "type": "object",
        "properties": {
            "phrase_id": {"type": "string"},
            "correct": {"type": "boolean"},
        },
        "required": ["phrase_id", "correct"],
    },
}

PROGRESS_DEF = {
    "name": "get_english_progress",
    "description": "Resume el progreso del English Playbook: frases, estados, categorías y pendientes de repaso.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
