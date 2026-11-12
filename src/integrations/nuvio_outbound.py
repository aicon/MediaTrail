"""Queue MediaTrail watch-history changes toward the linked Nuvio account."""

from __future__ import annotations

import logging
import re
from datetime import timezone as dt_timezone

from django.core.cache import cache

from app.models import MediaTypes, Sources, Status
from app.providers import services
from integrations.models import NuvioAccount

logger = logging.getLogger(__name__)

OUTBOUND_TTL_SECONDS = 15 * 60
_IMDB_ID = re.compile(r"(tt\d+)", re.IGNORECASE)


def enqueue_watched_upsert(user, media):
    """Queue watched upserts when the mark-watched sync toggle is on."""
    if not getattr(user, "nuvio_sync_mark_played_enabled", False):
        return
    if not _has_nuvio_account(user):
        return
    items = _watched_items_from_media(user, media)
    if not items:
        return
    for item in items:
        _mark_pending(user.id, item)
    logger.info(
        "Queue Nuvio watched push for %s (%s)",
        items[0].get("title"),
        ", ".join(item["content_id"] for item in items),
    )
    from integrations.tasks import push_nuvio_watched_item

    push_nuvio_watched_item.delay(user.id, items)


def enqueue_watched_delete(user, media):
    """Queue watched deletes when the mark-unwatched sync toggle is on."""
    if not getattr(user, "nuvio_sync_mark_unplayed_enabled", False):
        return
    if not _has_nuvio_account(user):
        return
    keys = _delete_keys_from_media(user, media)
    if not keys:
        return
    progress_keys = _progress_keys_from_delete_keys(keys)
    for key in keys:
        _mark_pending(user.id, key)
    logger.info(
        "Queue Nuvio watched delete keys %s progress %s",
        ", ".join(_identity_from_payload(key) or "?" for key in keys),
        ", ".join(progress_keys),
    )
    from integrations.tasks import delete_nuvio_watched_item

    delete_nuvio_watched_item.delay(user.id, keys, progress_keys)


def is_pending_outbound(user_id, row):
    """True when this delta row matches a recent outbound push/delete."""
    key = _cache_key(user_id, _identity_from_row(row))
    return bool(key and cache.get(key))


def _has_nuvio_account(user):
    return NuvioAccount.objects.filter(user=user).exists()


def _watched_items_from_media(user, media):
    item = getattr(media, "item", None)
    if item is None or item.source != Sources.TMDB.value:
        return []
    title = item.title or f"tmdb:{item.media_id}"
    watched_at = _watched_at_ms(getattr(media, "end_date", None))
    if item.media_type == MediaTypes.MOVIE.value:
        if getattr(media, "status", None) != Status.COMPLETED.value:
            return []
        return [
            {
                "content_id": content_id,
                "content_type": "movie",
                "title": title,
                "watched_at": watched_at,
            }
            for content_id in _content_id_variants(user, item.media_id, MediaTypes.MOVIE.value)
        ]
    if item.media_type == MediaTypes.EPISODE.value:
        season = item.season_number
        episode = item.episode_number
        if season is None or episode is None:
            return []
        return [
            {
                "content_id": content_id,
                "content_type": "series",
                "title": title,
                "season": int(season),
                "episode": int(episode),
                "watched_at": watched_at,
            }
            for content_id in _content_id_variants(user, item.media_id, MediaTypes.TV.value)
        ]
    return []


def _delete_keys_from_media(user, media):
    item = getattr(media, "item", None)
    if item is None or item.source != Sources.TMDB.value:
        return []
    if item.media_type == MediaTypes.MOVIE.value:
        return [
            {"content_id": content_id}
            for content_id in _content_id_variants(
                user,
                item.media_id,
                MediaTypes.MOVIE.value,
            )
        ]
    if item.media_type == MediaTypes.EPISODE.value:
        season = item.season_number
        episode = item.episode_number
        if season is None or episode is None:
            return []
        return [
            {
                "content_id": content_id,
                "season": int(season),
                "episode": int(episode),
            }
            for content_id in _content_id_variants(
                user,
                item.media_id,
                MediaTypes.TV.value,
            )
        ]
    return []


def _progress_keys_from_delete_keys(keys):
    """Build Nuvio progress_key values (contentId or contentId_sXeY)."""
    progress_keys = []
    for key in keys:
        content_id = str(key.get("content_id") or "").strip()
        if not content_id:
            continue
        season = key.get("season")
        episode = key.get("episode")
        if season is None or episode is None:
            progress_keys.append(content_id)
        else:
            progress_keys.append(f"{content_id}_s{int(season)}e{int(episode)}")
    return progress_keys


def _content_id_variants(user, tmdb_id, media_type):
    """IDs Nuvio may store for the same title (Stremio often uses bare tt…)."""
    tmdb_id = str(tmdb_id).strip()
    variants = [f"tmdb:{tmdb_id}"]
    imdb_id = _resolve_imdb_id(user, tmdb_id, media_type)
    if imdb_id:
        variants.append(imdb_id)
        variants.append(f"imdb:{imdb_id}")
    # Preserve order, drop duplicates.
    seen = set()
    ordered = []
    for value in variants:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _resolve_imdb_id(user, tmdb_id, media_type):
    tmdb_id = str(tmdb_id)
    try:
        account = user.nuvio_account
        for imdb_id, mapped in (account.imdb_map or {}).items():
            if str(mapped) == tmdb_id and _IMDB_ID.fullmatch(str(imdb_id)):
                return str(imdb_id).lower()
    except NuvioAccount.DoesNotExist:
        pass

    try:
        metadata = services.get_media_metadata(media_type, tmdb_id, Sources.TMDB.value)
    except Exception:
        logger.exception("Could not resolve IMDb id for TMDB %s", tmdb_id)
        return None
    links = (metadata or {}).get("external_links") or {}
    match = _IMDB_ID.search(str(links.get("IMDb") or ""))
    if match:
        return match.group(1).lower()
    return None


def _watched_at_ms(end_date):
    if end_date is None:
        from django.utils import timezone

        end_date = timezone.now()
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=dt_timezone.utc)
    return int(end_date.timestamp() * 1000)


def _mark_pending(user_id, payload):
    identity = _identity_from_payload(payload)
    key = _cache_key(user_id, identity)
    if key:
        cache.set(key, True, OUTBOUND_TTL_SECONDS)


def _identity_from_payload(payload):
    content_id = str(payload.get("content_id") or "").strip()
    if not content_id:
        return None
    season = payload.get("season")
    episode = payload.get("episode")
    if season is None or episode is None:
        return content_id
    return f"{content_id}:{int(season)}:{int(episode)}"


def _identity_from_row(row):
    if not isinstance(row, dict):
        return None
    content_id = str(row.get("content_id") or "").strip()
    if not content_id:
        return None
    season = row.get("season")
    episode = row.get("episode")
    if season is None or episode is None:
        return content_id
    try:
        return f"{content_id}:{int(season)}:{int(episode)}"
    except (TypeError, ValueError):
        return content_id


def _cache_key(user_id, identity):
    if not identity:
        return None
    return f"nuvio_outbound:{user_id}:{identity}"
