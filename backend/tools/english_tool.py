import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import get_settings

DATA_DIR = "/data/english"
PHRASES_FILE = os.path.join(DATA_DIR, "phrases.json")

CATEGORIES = {"Basketball", "Coaching", "Meetings", "Daily Life", "Business/Networking", "Useful English"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _safe_category(category: str) -> str:
    return category if category in CATEGORIES else "Useful English"


def _local_load() -> list[dict]:
    try:
        with open(PHRASES_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _local_save(items: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PHRASES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PHRASES_FILE)


def _sb_config() -> tuple[str, str, str] | None:
    s = get_settings()
    if not (s.english_supabase_url and s.english_supabase_service_key and s.english_supabase_user_id):
        return None
    return (
        s.english_supabase_url.rstrip("/"),
        s.english_supabase_service_key,
        s.english_supabase_user_id,
    )


def _sb_headers(key: str, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


async def _sb_request(method: str, table: str, *, params: dict[str, str] | None = None, body: Any = None, prefer: str | None = None):
    config = _sb_config()
    if not config:
        raise RuntimeError("English Supabase no configurado")
    url, key, _ = config
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request(
            method,
            f"{url}/rest/v1/{table}",
            headers=_sb_headers(key, prefer),
            params=params,
            json=body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase {table}: HTTP {response.status_code} {response.text[:300]}")
    if not response.content:
        return []
    return response.json()


def _status_from_level(level: int) -> str:
    if level >= 4:
        return "Automatic"
    if level >= 3:
        return "Familiar"
    if level >= 1:
        return "Learning"
    return "New"


def _concept_to_item(concept: dict, progress: dict | None = None) -> dict:
    progress = progress or {}
    level = int(progress.get("level", 0) or 0)
    return {
        "id": concept.get("id"),
        "phrase": concept.get("en", ""),
        "spanish": concept.get("es", ""),
        "natural_version": concept.get("command") or concept.get("en", ""),
        "category": concept.get("category", "Useful English"),
        "context": concept.get("context") or "",
        "type": "Core Phrase" if (concept.get("note") or "").startswith("CORE") else "Phrase",
        "note": concept.get("note") or "",
        "status": _status_from_level(level),
        "level": level,
        "streak": int(progress.get("streak", 0) or 0),
        "attempts": int(progress.get("attempts", 0) or 0),
        "correct_count": int(progress.get("correct_count", 0) or 0),
        "next_review": progress.get("next_review"),
        "last_review": progress.get("last_seen"),
        "source": "supabase",
    }


async def _fallback_save(
    phrase: str, spanish: str, natural_version: str, category: str, context: str,
    phrase_type: str, importance: int, example: str, my_mistake: str,
) -> dict:
    items = _local_load()
    key = _norm(phrase)
    existing = next((x for x in items if _norm(x.get("phrase", "")) == key), None)
    now = _now().isoformat()
    item = existing or {"id": f"local-{len(items)+1}", "added_at": now, "level": 0, "streak": 0, "attempts": 0, "correct_count": 0, "next_review": now}
    item.update({
        "phrase": phrase.strip(), "spanish": spanish.strip(),
        "natural_version": natural_version.strip(), "category": _safe_category(category),
        "context": context.strip(), "type": phrase_type or "Phrase",
        "importance": max(1, min(5, int(importance))), "example": example.strip(),
        "my_mistake": my_mistake.strip(), "updated_at": now, "source": "local-fallback",
    })
    if not existing:
        items.append(item)
    _local_save(items)
    return {"ok": True, "created": not bool(existing), "item": item, "warning": "Guardado localmente: Supabase no disponible/configurado"}


async def save_english_phrase(
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

    config = _sb_config()
    if not config:
        return await _fallback_save(phrase, spanish, natural_version, category, context, phrase_type, importance, example, my_mistake)

    _, _, user_id = config
    try:
        existing = await _sb_request("GET", "ec_concepts", params={
            "select": "*", "user_id": f"eq.{user_id}", "en": f"eq.{phrase}", "limit": "1",
        })
        note_bits = []
        if phrase_type.lower() == "core phrase":
            note_bits.append("CORE")
        note_bits.append(f"importance:{max(1, min(5, int(importance)))}")
        if example:
            note_bits.append(f"example:{example.strip()}")
        if my_mistake:
            note_bits.append(f"mistake:{my_mistake.strip()}")
        payload = {
            "user_id": user_id,
            "type": "phrase",
            "category": _safe_category(category),
            "en": phrase,
            "es": spanish.strip(),
            "say": "",
            "note": " | ".join(note_bits),
            "status": "approved",
            "context": context.strip() or None,
            "command": natural_version.strip() or phrase,
        }

        if existing:
            concept_id = existing[0]["id"]
            rows = await _sb_request("PATCH", "ec_concepts", params={"id": f"eq.{concept_id}", "select": "*"}, body=payload, prefer="return=representation")
            concept = rows[0] if rows else {**existing[0], **payload}
            created = False
        else:
            rows = await _sb_request("POST", "ec_concepts", params={"select": "*"}, body=payload, prefer="return=representation")
            concept = rows[0]
            concept_id = concept["id"]
            created = True

        progress_rows = await _sb_request("GET", "ec_progress", params={
            "select": "*", "user_id": f"eq.{user_id}", "concept_id": f"eq.{concept_id}", "limit": "1",
        })
        if not progress_rows:
            now = _now().isoformat()
            progress_payload = {
                "user_id": user_id, "concept_id": concept_id,
                "level": 0, "streak": 0, "attempts": 0, "correct_count": 0,
                "next_review": now, "last_seen": now, "updated_at": now,
            }
            progress_rows = await _sb_request("POST", "ec_progress", params={"select": "*"}, body=progress_payload, prefer="return=representation")

        return {"ok": True, "created": created, "item": _concept_to_item(concept, progress_rows[0] if progress_rows else None)}
    except Exception as exc:
        fallback = await _fallback_save(phrase, spanish, natural_version, category, context, phrase_type, importance, example, my_mistake)
        fallback["warning"] = f"Supabase falló; copia local creada: {exc}"
        return fallback


async def search_english_phrases(query: str = "", category: str = "", status: str = "", limit: int = 20) -> dict:
    config = _sb_config()
    if not config:
        items = _local_load()
        q = _norm(query)
        result = [x for x in reversed(items) if (not category or x.get("category") == category) and (not q or q in _norm(" ".join([x.get("phrase", ""), x.get("spanish", ""), x.get("context", "")])))]
        return {"count": len(result[:limit]), "items": result[:limit], "source": "local-fallback"}

    _, _, user_id = config
    params = {
        "select": "*",
        "or": f"(user_id.is.null,user_id.eq.{user_id})",
        "status": "eq.approved",
        "order": "created_at.desc",
        "limit": str(max(1, min(100, limit))),
    }
    if category:
        params["category"] = f"eq.{category}"
    concepts = await _sb_request("GET", "ec_concepts", params=params)

    # The legacy Jorge Lorenzo Coach library groups basketball phrases in
    # Spanish categories (for example, "Defensa") rather than "Basketball".
    # Keep an exact match when it exists, then fall back to the shared library.
    if not concepts and category.strip().lower() in {"basketball", "baloncesto"}:
        params.pop("category")
        concepts = await _sb_request("GET", "ec_concepts", params=params)

    q = _norm(query)
    if q:
        concepts = [
            c for c in concepts
            if q in _norm(" ".join([
                c.get("en") or "",
                c.get("es") or "",
                c.get("context") or "",
                c.get("note") or "",
            ]))
        ]

    ids = [c["id"] for c in concepts]
    progress_by_id: dict[str, dict] = {}
    if ids:
        progress = await _sb_request("GET", "ec_progress", params={
            "select": "*", "user_id": f"eq.{user_id}", "concept_id": f"in.({','.join(ids)})",
        })
        progress_by_id = {p["concept_id"]: p for p in progress}

    items = [_concept_to_item(c, progress_by_id.get(c["id"])) for c in concepts]
    if status:
        items = [x for x in items if x["status"] == status]
    return {"count": len(items), "items": items, "source": "supabase"}


async def get_english_review(limit: int = 5) -> dict:
    config = _sb_config()
    if not config:
        items = _local_load()
        now = _now()
        due = []
        for item in items:
            try:
                due_at = datetime.fromisoformat(item.get("next_review")) if item.get("next_review") else now
            except ValueError:
                due_at = now
            if due_at <= now:
                due.append(item)
        return {"due_count": len(due), "items": due[:limit], "source": "local-fallback"}

    _, _, user_id = config
    now = _now().isoformat()
    progress = await _sb_request("GET", "ec_progress", params={
        "select": "*", "user_id": f"eq.{user_id}", "next_review": f"lte.{now}",
        "order": "level.asc,next_review.asc", "limit": str(max(1, min(20, limit))),
    })
    if not progress:
        return {"due_count": 0, "items": [], "source": "supabase"}
    ids = [p["concept_id"] for p in progress]
    concepts = await _sb_request("GET", "ec_concepts", params={"select": "*", "id": f"in.({','.join(ids)})"})
    by_id = {c["id"]: c for c in concepts}
    items = [_concept_to_item(by_id[p["concept_id"]], p) for p in progress if p["concept_id"] in by_id]
    return {"due_count": len(items), "items": items, "source": "supabase"}


async def record_english_result(phrase_id: str, correct: bool) -> dict:
    config = _sb_config()
    if not config or phrase_id.startswith("local-"):
        items = _local_load()
        item = next((x for x in items if x.get("id") == phrase_id), None)
        if not item:
            return {"ok": False, "error": "phrase_id no encontrado"}
        level = int(item.get("level", 0) or 0)
        streak = int(item.get("streak", 0) or 0)
        attempts = int(item.get("attempts", 0) or 0) + 1
        correct_count = int(item.get("correct_count", 0) or 0) + (1 if correct else 0)
        if correct:
            level = min(level + 1, 4)
            streak += 1
            days = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}[level]
            next_review = _now() + timedelta(days=days)
        else:
            level = max(level - 1, 0)
            streak = 0
            next_review = _now() + timedelta(minutes=5)
        item.update({"level": level, "streak": streak, "attempts": attempts, "correct_count": correct_count, "next_review": next_review.isoformat(), "last_review": _now().isoformat()})
        _local_save(items)
        return {"ok": True, "item": item, "source": "local-fallback"}

    _, _, user_id = config
    rows = await _sb_request("GET", "ec_progress", params={
        "select": "*", "user_id": f"eq.{user_id}", "concept_id": f"eq.{phrase_id}", "limit": "1",
    })
    if not rows:
        return {"ok": False, "error": "phrase_id no encontrado en progreso"}
    current = rows[0]
    level = int(current.get("level", 0) or 0)
    streak = int(current.get("streak", 0) or 0)
    attempts = int(current.get("attempts", 0) or 0) + 1
    correct_count = int(current.get("correct_count", 0) or 0) + (1 if correct else 0)
    if correct:
        level = min(level + 1, 4)
        streak += 1
        days = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}[level]
        next_review = _now() + timedelta(days=days)
    else:
        level = max(level - 1, 0)
        streak = 0
        next_review = _now() + timedelta(minutes=5)
    now = _now().isoformat()
    payload = {
        "level": level, "streak": streak, "attempts": attempts, "correct_count": correct_count,
        "next_review": next_review.isoformat(), "last_seen": now, "updated_at": now,
    }
    updated = await _sb_request("PATCH", "ec_progress", params={
        "user_id": f"eq.{user_id}", "concept_id": f"eq.{phrase_id}", "select": "*",
    }, body=payload, prefer="return=representation")
    concept = await _sb_request("GET", "ec_concepts", params={"select": "*", "id": f"eq.{phrase_id}", "limit": "1"})
    return {"ok": True, "item": _concept_to_item(concept[0], updated[0]) if concept and updated else payload, "source": "supabase"}


async def get_english_progress() -> dict:
    config = _sb_config()
    if not config:
        items = _local_load()
        return {"total": len(items), "source": "local-fallback"}
    _, _, user_id = config
    progress = await _sb_request("GET", "ec_progress", params={"select": "level,streak,attempts,correct_count,next_review", "user_id": f"eq.{user_id}"})
    now = _now()
    by_status = {"New": 0, "Learning": 0, "Familiar": 0, "Automatic": 0}
    due = 0
    attempts = correct_count = 0
    for p in progress:
        by_status[_status_from_level(int(p.get("level", 0) or 0))] += 1
        attempts += int(p.get("attempts", 0) or 0)
        correct_count += int(p.get("correct_count", 0) or 0)
        try:
            if datetime.fromisoformat((p.get("next_review") or now.isoformat()).replace("Z", "+00:00")) <= now:
                due += 1
        except ValueError:
            due += 1
    return {
        "total": len(progress), "by_status": by_status, "due_now": due,
        "attempts": attempts, "correct": correct_count,
        "accuracy_percent": round((correct_count / attempts) * 100) if attempts else 0,
        "source": "supabase",
    }


SAVE_DEF = {
    "name": "save_english_phrase",
    "description": "Guarda o actualiza una frase útil en el English Coach compartido (Supabase). Úsala cuando Jorge pida guardar algo o cuando una frase sea claramente recurrente/importante.",
    "input_schema": {
        "type": "object",
        "properties": {
            "phrase": {"type": "string"}, "spanish": {"type": "string"},
            "natural_version": {"type": "string"},
            "category": {"type": "string", "enum": sorted(CATEGORIES)},
            "context": {"type": "string"},
            "phrase_type": {"type": "string", "description": "Phrase o Core Phrase"},
            "importance": {"type": "integer", "minimum": 1, "maximum": 5},
            "example": {"type": "string"}, "my_mistake": {"type": "string"},
        },
        "required": ["phrase", "spanish"],
    },
}

SEARCH_DEF = {
    "name": "search_english_phrases",
    "description": "Busca la biblioteca compartida y las frases personales guardadas en English Coach. El resultado incluye count e items; si count es mayor que 0, muestra esos items al usuario.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": []},
}

REVIEW_DEF = {
    "name": "get_english_review",
    "description": "Obtiene conceptos que toca repasar según el mismo sistema de progreso de la app English Coach.",
    "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": []},
}

RESULT_DEF = {
    "name": "record_english_result",
    "description": "Registra un acierto/fallo y actualiza nivel, racha y próxima revisión en Supabase.",
    "input_schema": {"type": "object", "properties": {"phrase_id": {"type": "string"}, "correct": {"type": "boolean"}}, "required": ["phrase_id", "correct"]},
}

PROGRESS_DEF = {
    "name": "get_english_progress",
    "description": "Resume progreso, precisión y repasos pendientes del English Coach.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
