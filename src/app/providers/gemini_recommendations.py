"""Gemini contextual recommendations using the user's BYOK API key."""

from __future__ import annotations

import json
import logging
import re

import requests

from app.providers import recommendation_cache
from app.recommendation_sources import SOURCE_AI
from integrations.imports.helpers import decrypt

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"
_TIMEOUT = 20
_MAX_ITEMS = 12

SYSTEM_PROMPT = (
    "You recommend movies and TV shows. Prefer titles that match the seed's "
    "tone, humor, craft, and cultural context. Lean toward titles familiar to "
    "Hungarian audiences when they fit. Return only titles that really exist. "
    "Do not include the seed title itself."
)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "year": {"type": "integer"},
                    "media_type": {
                        "type": "string",
                        "enum": ["movie", "tv"],
                    },
                },
                "required": ["title", "year", "media_type"],
            },
        }
    },
    "required": ["recommendations"],
}


def recommend_titles(user, *, title: str, year, media_type: str, media_id) -> list[dict]:
    """Return [{title, year, media_type}, ...] for the seed, with durable cache."""
    api_key = _user_api_key(user)
    if not api_key:
        return []

    seed_key = str(media_id)
    cached = recommendation_cache.get_cached_payload(
        SOURCE_AI,
        media_type,
        seed_key,
        user_id=user.id,
    )
    if cached is not None:
        return _normalize_items(cached, fallback_type=media_type)

    try:
        items = _call_gemini(
            api_key,
            title=title,
            year=year,
            media_type=media_type,
        )
    except Exception:
        logger.exception("Gemini recommendations failed for %s/%s", media_type, media_id)
        return []

    recommendation_cache.set_cached_payload(
        SOURCE_AI,
        media_type,
        seed_key,
        items,
        user_id=user.id,
    )
    return items


def _user_api_key(user) -> str:
    raw = getattr(user, "gemini_api_key", "") or ""
    if not raw:
        return ""
    try:
        return decrypt(raw)
    except Exception:
        logger.exception("Could not decrypt Gemini API key for user=%s", user.id)
        return ""


def _call_gemini(api_key: str, *, title: str, year, media_type: str) -> list[dict]:
    """Call Gemini generateContent with a structured JSON schema."""
    year_bit = f" ({year})" if year else ""
    kind = "TV show" if media_type == "tv" else "movie"
    user_prompt = (
        f"Recommend up to {_MAX_ITEMS} titles similar in spirit to the {kind} "
        f'"{title}{year_bit}". Reply with JSON only.'
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
    }
    response = requests.post(
        url,
        params={"key": api_key},
        json=body,
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return _normalize_items(_parse_json_text(text), fallback_type=media_type)


def _parse_json_text(text: str):
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Sometimes the model wraps JSON in fences despite schema.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, dict):
        return parsed.get("recommendations") or []
    if isinstance(parsed, list):
        return parsed
    return []


def _normalize_items(raw, *, fallback_type: str) -> list[dict]:
    items = []
    seen = set()
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        try:
            year = int(entry.get("year"))
        except (TypeError, ValueError):
            year = None
        mtype = (entry.get("media_type") or fallback_type or "movie").strip().lower()
        if mtype not in ("movie", "tv"):
            mtype = fallback_type if fallback_type in ("movie", "tv") else "movie"
        key = (title.casefold(), year, mtype)
        if key in seen:
            continue
        seen.add(key)
        items.append({"title": title, "year": year, "media_type": mtype})
        if len(items) >= _MAX_ITEMS:
            break
    return items
