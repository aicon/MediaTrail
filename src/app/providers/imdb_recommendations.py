"""IMDb 'More like this' titles (HTML scrape, with Trakt related fallback)."""

from __future__ import annotations

import json
import logging
import re

import requests
from django.conf import settings

from app.providers import recommendation_cache
from app.recommendation_sources import SOURCE_IMDB

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_TT_RE = re.compile(r"^tt\d+$")
_IMDB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
_TIMEOUT = 15


def more_like_this_ids(imdb_id: str, media_type: str) -> list[str]:
    """Return IMDb tt ids similar to ``imdb_id``, using durable SQLite cache."""
    if not imdb_id or not _TT_RE.match(imdb_id):
        return []

    cached = recommendation_cache.get_cached_payload(
        SOURCE_IMDB,
        media_type,
        imdb_id,
    )
    # Never treat an empty cached list as authoritative (failed scrapes used to
    # stick for 30 days and hide IMDb forever after one WAF block).
    if cached:
        return [tt for tt in cached if isinstance(tt, str) and _TT_RE.match(tt)]

    ids = _fetch_more_like_this(imdb_id)
    if not ids:
        ids = _fetch_trakt_related_ids(imdb_id, media_type)
        if ids:
            logger.info(
                "IMDb page unavailable for %s; using Trakt related (%s titles)",
                imdb_id,
                len(ids),
            )

    if ids:
        recommendation_cache.set_cached_payload(
            SOURCE_IMDB,
            media_type,
            imdb_id,
            ids,
        )
        logger.info("IMDb-like recommendations for %s: %s titles", imdb_id, len(ids))
    else:
        logger.warning("No IMDb/Trakt related titles for %s", imdb_id)
    return ids


def _fetch_more_like_this(imdb_id: str) -> list[str]:
    """HTTP fetch + parse IMDb title page for moreLikeThisTitles."""
    url = f"https://www.imdb.com/title/{imdb_id}/"
    try:
        response = requests.get(url, headers=_IMDB_HEADERS, timeout=_TIMEOUT)
    except requests.RequestException:
        logger.exception("IMDb request failed for %s", imdb_id)
        return []

    if response.status_code != 200:
        logger.warning(
            "IMDb HTTP %s for %s (len=%s)",
            response.status_code,
            imdb_id,
            len(response.text or ""),
        )
        return []

    html = response.text or ""
    if _looks_like_waf(html):
        logger.warning("IMDb WAF/challenge page for %s", imdb_id)
        return []

    ids = parse_more_like_this_html(html)
    if not ids:
        logger.warning(
            "IMDb HTML for %s had no moreLikeThisTitles (html_len=%s)",
            imdb_id,
            len(html),
        )
    return ids


def _looks_like_waf(html: str) -> bool:
    lowered = (html or "").lower()
    return (
        "awswaf" in lowered
        or "captcha" in lowered
        or "challenge-platform" in lowered
        or "human verification" in lowered
    )


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

    edges = _find_more_like_edges(data)
    if not isinstance(edges, list):
        return []

    seen = set()
    ids = []
    for edge in edges:
        node = (edge or {}).get("node") or edge or {}
        tt = node.get("id") or ""
        if isinstance(tt, str) and _TT_RE.match(tt) and tt not in seen:
            seen.add(tt)
            ids.append(tt)
    return ids


def _find_more_like_edges(data):
    """Find moreLikeThisTitles.edges anywhere under pageProps."""
    page = (data or {}).get("props", {}).get("pageProps", {})
    main = page.get("mainColumnData") or {}
    direct = (main.get("moreLikeThisTitles") or {}).get("edges")
    if isinstance(direct, list):
        return direct

    # IMDb occasionally nests the block under a different column key.
    stack = [page]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "moreLikeThisTitles" in cur:
                edges = (cur.get("moreLikeThisTitles") or {}).get("edges")
                if isinstance(edges, list):
                    return edges
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur[:20])
    return []


def _fetch_trakt_related_ids(imdb_id: str, media_type: str) -> list[str]:
    """When IMDb HTML is blocked, use Trakt related titles for the same IMDb id."""
    client_id = (
        str(getattr(settings, "TRAKT_API_PKCE", "") or "").strip()
        or str(getattr(settings, "TRAKT_API", "") or "").strip()
    )
    if not client_id:
        return []

    kind = "shows" if media_type == "tv" else "movies"
    url = f"https://api.trakt.tv/{kind}/{imdb_id}/related"
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id,
        "User-Agent": "MediaTrail/1.0",
    }
    try:
        response = requests.get(url, headers=headers, timeout=_TIMEOUT)
    except requests.RequestException:
        logger.exception("Trakt related request failed for %s", imdb_id)
        return []

    if response.status_code != 200:
        logger.warning(
            "Trakt related HTTP %s for %s",
            response.status_code,
            imdb_id,
        )
        return []

    try:
        payload = response.json()
    except ValueError:
        return []

    seen = set()
    ids = []
    for entry in payload or []:
        ids_map = (entry or {}).get("ids") or {}
        tt = ids_map.get("imdb") or ""
        if isinstance(tt, str) and _TT_RE.match(tt) and tt not in seen:
            seen.add(tt)
            ids.append(tt)
    return ids
