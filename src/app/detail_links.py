"""External detail-page links and Port.hu resolution via Wikidata P905."""

from __future__ import annotations

import logging
import re

from django.core.cache import cache

from app.models import MediaTypes
from app.providers import services

logger = logging.getLogger(__name__)

# Preference keys → display label. Order is the on-page link order.
DETAIL_LINK_OPTIONS = (
    ("imdb", "IMDb"),
    ("wikidata", "Wikidata"),
    ("letterboxd", "Letterboxd"),
    ("tvdb", "TVDB"),
    ("trakt", "Trakt"),
    ("port_hu", "Port.hu"),
)

DETAIL_LINK_DEFAULT_ON = frozenset({"imdb", "wikidata", "trakt"})

_USER_FLAG = {
    "imdb": "link_imdb_enabled",
    "wikidata": "link_wikidata_enabled",
    "letterboxd": "link_letterboxd_enabled",
    "tvdb": "link_tvdb_enabled",
    "trakt": "link_trakt_enabled",
    "port_hu": "link_port_hu_enabled",
}

_WIKIDATA_QID = re.compile(r"^Q\d+$")
_HIT_SECONDS = 60 * 60 * 24 * 7
_MISS_SECONDS = 60 * 60 * 6
_MISS = "__none__"
_LOOKUP_ERROR = object()
_WIKIDATA_UA = {
    "User-Agent": "MediaTrail/1.0 (https://github.com/aicon/MediaTrail; detail-links)",
}


def user_link_enabled(user, key: str) -> bool:
    """Return whether the user wants this detail-link provider shown."""
    field = _USER_FLAG.get(key)
    if not field:
        return False
    return bool(getattr(user, field, key in DETAIL_LINK_DEFAULT_ON))


def build_external_links(external_ids, *, media_type, tmdb_id=None):
    """Build provider→URL map from TMDB external ids. No Port.hu here."""
    links = {}
    ids = external_ids or {}
    imdb_id = ids.get("imdb_id") or ""
    wikidata_id = ids.get("wikidata_id") or ""
    tvdb_id = ids.get("tvdb_id")
    is_movie = media_type == MediaTypes.MOVIE.value

    if imdb_id:
        links["imdb"] = f"https://www.imdb.com/title/{imdb_id}/"

    if wikidata_id:
        links["wikidata"] = f"https://www.wikidata.org/wiki/{wikidata_id}"

    # Letterboxd documents TMDB movie ids; TV is rarely supported.
    if tmdb_id and is_movie:
        links["letterboxd"] = f"https://www.letterboxd.com/tmdb/{tmdb_id}"

    if tvdb_id and media_type in (
        MediaTypes.TV.value,
        MediaTypes.SEASON.value,
    ):
        links["tvdb"] = (
            f"https://www.thetvdb.com/dereferrer/series/{tvdb_id}"
        )

    if imdb_id:
        if is_movie:
            links["trakt"] = f"https://trakt.tv/movies/{imdb_id}"
        elif media_type in (MediaTypes.TV.value, MediaTypes.SEASON.value):
            links["trakt"] = f"https://trakt.tv/shows/{imdb_id}"

    return links


def resolve_port_hu_url(wikidata_id: str | None) -> str | None:
    """Resolve Port.hu jump URL from Wikidata Q-id → P905, with cache."""
    port_id = _wikidata_claim(wikidata_id, "P905")
    if not port_id:
        return None
    return f"https://port.hu/jump/movie-{port_id}"


def _wikidata_claim(wikidata_id: str | None, prop: str) -> str | None:
    """Read one Wikidata claim value (cached per Q-id + property)."""
    if not wikidata_id or not _WIKIDATA_QID.match(wikidata_id):
        return None

    cache_key = f"wikidata_{prop}_{wikidata_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return None if cached == _MISS else cached

    value = _fetch_wikidata_claim(wikidata_id, prop)
    if value is _LOOKUP_ERROR:
        # Do not cache transport/API failures as permanent misses.
        return None
    if not value:
        cache.set(cache_key, _MISS, _MISS_SECONDS)
        return None
    cache.set(cache_key, value, _HIT_SECONDS)
    return value


def _fetch_wikidata_claim(wikidata_id: str, prop: str):
    """Read a single property via the Wikidata API. No HTML scraping."""
    try:
        response = services.api_request(
            "WIKIDATA",
            "GET",
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetclaims",
                "entity": wikidata_id,
                "property": prop,
                "format": "json",
            },
            headers=_WIKIDATA_UA,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Wikidata %s lookup failed for %s",
            prop,
            wikidata_id,
        )
        return _LOOKUP_ERROR

    claims = (response or {}).get("claims", {}).get(prop) or []
    for claim in claims:
        mainsnak = claim.get("mainsnak") or {}
        if mainsnak.get("snaktype") != "value":
            continue
        value = (mainsnak.get("datavalue") or {}).get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_link_map(external_links: dict) -> dict:
    """Accept provider keys or legacy display labels from older TMDB cache."""
    legacy = {label: key for key, label in DETAIL_LINK_OPTIONS}
    # Drop retired detail-link providers (kept only for cache cleanup).
    legacy["Simkl"] = "simkl"
    normalized = {}
    for key, url in (external_links or {}).items():
        code = key if key in _USER_FLAG or key == "simkl" else legacy.get(key)
        if code == "simkl":
            continue
        if code and url:
            normalized[code] = url
    return normalized


def visible_detail_links(user, external_links: dict, *, wikidata_id=None) -> dict:
    """Filter links by user prefs; add Port.hu when enabled and resolvable.

    Returns an ordered display-name → URL mapping for the template.
    """
    links = _normalize_link_map(external_links)
    if user_link_enabled(user, "port_hu"):
        port_url = resolve_port_hu_url(wikidata_id)
        if port_url:
            links["port_hu"] = port_url

    ordered = {}
    for key, label in DETAIL_LINK_OPTIONS:
        if not user_link_enabled(user, key):
            continue
        url = links.get(key)
        if url:
            ordered[label] = url
    return ordered


def apply_user_detail_links(media: dict, user, media_type: str) -> None:
    """Replace media['external_links'] with the user-filtered display map."""
    ids = dict(media.get("external_ids") or {})
    legacy = _normalize_link_map(media.get("external_links") or {})

    # Recover ids from older cached link maps so Trakt still works.
    if not ids.get("imdb_id"):
        imdb_url = legacy.get("imdb") or ""
        match = re.search(r"(tt\d+)", imdb_url)
        if match:
            ids["imdb_id"] = match.group(1)
    if not ids.get("wikidata_id"):
        wiki_url = legacy.get("wikidata") or ""
        match = re.search(r"(Q\d+)", wiki_url)
        if match:
            ids["wikidata_id"] = match.group(1)
    if not ids.get("tvdb_id"):
        tvdb_url = legacy.get("tvdb") or ""
        match = re.search(r"/series/(\d+)", tvdb_url)
        if match:
            ids["tvdb_id"] = match.group(1)

    tmdb_id = media.get("media_id")
    if ids:
        raw = build_external_links(
            ids,
            media_type=media_type,
            tmdb_id=tmdb_id if media_type == MediaTypes.MOVIE.value else None,
        )
    else:
        raw = legacy

    media["external_links"] = visible_detail_links(
        user,
        raw,
        wikidata_id=ids.get("wikidata_id"),
    )


def detail_link_preference_rows(user):
    """Rows for the Preferences toggles: (key, label, enabled)."""
    rows = []
    for key, label in DETAIL_LINK_OPTIONS:
        rows.append(
            {
                "key": key,
                "label": label,
                "enabled": user_link_enabled(user, key),
            }
        )
    return rows
