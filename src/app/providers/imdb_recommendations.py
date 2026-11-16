"""IMDb 'More like this' titles via the title page __NEXT_DATA__ blob."""

from __future__ import annotations

import json
import logging
import re

import requests

from app.providers import recommendation_cache
from app.recommendation_sources import SOURCE_IMDB

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_TT_RE = re.compile(r"^tt\d+$")
_IMDB_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 12


def more_like_this_ids(imdb_id: str, media_type: str) -> list[str]:
    """Return IMDb tt ids similar to ``imdb_id``, using durable SQLite cache."""
    if not imdb_id or not _TT_RE.match(imdb_id):
        return []

    cached = recommendation_cache.get_cached_payload(
        SOURCE_IMDB,
        media_type,
        imdb_id,
    )
    if cached is not None:
        return [tt for tt in cached if isinstance(tt, str) and _TT_RE.match(tt)]

    try:
        ids = _fetch_more_like_this(imdb_id)
    except Exception:
        logger.exception("IMDb more-like-this failed for %s", imdb_id)
        return []

    recommendation_cache.set_cached_payload(
        SOURCE_IMDB,
        media_type,
        imdb_id,
        ids,
    )
    return ids


def _fetch_more_like_this(imdb_id: str) -> list[str]:
    """HTTP fetch + parse IMDb title page for moreLikeThisTitles."""
    url = f"https://www.imdb.com/title/{imdb_id}/"
    response = requests.get(url, headers=_IMDB_UA, timeout=_TIMEOUT)
    response.raise_for_status()
    return parse_more_like_this_html(response.text)


def parse_more_like_this_html(html: str) -> list[str]:
    """Extract ordered unique tt ids from an IMDb title HTML page."""
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("IMDb __NEXT_DATA__ was not valid JSON")
        return []

    edges = (
        data.get("props", {})
        .get("pageProps", {})
        .get("mainColumnData", {})
        .get("moreLikeThisTitles", {})
        .get("edges", [])
    )
    if not isinstance(edges, list):
        return []

    seen = set()
    ids = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        tt = node.get("id") or ""
        if isinstance(tt, str) and _TT_RE.match(tt) and tt not in seen:
            seen.add(tt)
            ids.append(tt)
    return ids
