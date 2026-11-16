"""User-selectable recommendation engines (TMDB / IMDb / AI)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _lazy

# Preference keys → display label. Order is the UI order.
RECOMMENDATION_SOURCE_OPTIONS = (
    ("tmdb", "TMDB"),
    ("imdb", "IMDb"),
    ("ai", _lazy("AI")),
)

RECOMMENDATION_DEFAULT_ON = frozenset({"tmdb", "imdb"})

_USER_FLAG = {
    "tmdb": "rec_tmdb_enabled",
    "imdb": "rec_imdb_enabled",
    "ai": "rec_ai_enabled",
}

SOURCE_TMDB = "tmdb"
SOURCE_IMDB = "imdb"
SOURCE_AI = "ai"
ALL_SOURCES = (SOURCE_TMDB, SOURCE_IMDB, SOURCE_AI)


def user_has_gemini_key(user) -> bool:
    """Return True when the user has a stored Gemini API key."""
    return bool(getattr(user, "gemini_api_key", "") or "")


def user_source_enabled(user, key: str) -> bool:
    """Return whether the user wants this recommendation source on by default."""
    field = _USER_FLAG.get(key)
    if not field:
        return False
    if key == SOURCE_AI and not user_has_gemini_key(user):
        return False
    return bool(getattr(user, field, key in RECOMMENDATION_DEFAULT_ON))


def recommendation_source_rows(user):
    """Rows for Preferences toggles and detail-page pills."""
    has_key = user_has_gemini_key(user)
    rows = []
    for key, label in RECOMMENDATION_SOURCE_OPTIONS:
        available = True if key != SOURCE_AI else has_key
        rows.append(
            {
                "key": key,
                "label": label,
                "enabled": user_source_enabled(user, key) if available else False,
                "available": available,
            }
        )
    return rows


def enabled_source_keys(user) -> list[str]:
    """Ordered list of sources enabled in the user's preferences."""
    return [key for key, _label in RECOMMENDATION_SOURCE_OPTIONS if user_source_enabled(user, key)]


def parse_source_keys(raw: str | None, user, *, allow_empty: bool = False) -> list[str]:
    """Parse a comma-separated sources query into an allowed ordered list."""
    if raw is None:
        return enabled_source_keys(user)
    if raw.strip() == "":
        return [] if allow_empty else enabled_source_keys(user)

    requested = []
    for part in raw.split(","):
        key = part.strip().lower()
        if key in ALL_SOURCES and key not in requested:
            if key == SOURCE_AI and not user_has_gemini_key(user):
                continue
            requested.append(key)
    if requested:
        return requested
    return [] if allow_empty else enabled_source_keys(user)
