"""Queue MediaTrail watch-history changes toward the linked Nuvio account."""

from __future__ import annotations

import logging
from datetime import timezone as dt_timezone

from django.core.cache import cache

from app.models import MediaTypes, Sources, Status
from integrations.models import NuvioAccount

logger = logging.getLogger(__name__)

OUTBOUND_TTL_SECONDS = 15 * 60


def enqueue_watched_upsert(user, media):
    """Queue a watched upsert when the mark-watched sync toggle is on."""
    if not getattr(user, "nuvio_sync_mark_played_enabled", False):
        return
    if not _has_nuvio_account(user):
        return
    item = _watched_item_from_media(media)
    if item is None:
        return
    _mark_pending(user.id, item)
    from integrations.tasks import push_nuvio_watched_item

    push_nuvio_watched_item.delay(user.id, item)


def enqueue_watched_delete(user, media):
    """Queue a watched delete when the mark-unwatched sync toggle is on."""
    if not getattr(user, "nuvio_sync_mark_unplayed_enabled", False):
        return
    if not _has_nuvio_account(user):
        return
    key = _delete_key_from_media(media)
    if key is None:
        return
    _mark_pending(user.id, key)
    from integrations.tasks import delete_nuvio_watched_item

    delete_nuvio_watched_item.delay(user.id, key)


def is_pending_outbound(user_id, row):
    """True when this delta row matches a recent outbound push/delete."""
    key = _cache_key(user_id, _identity_from_row(row))
    return bool(key and cache.get(key))


def _has_nuvio_account(user):
    return NuvioAccount.objects.filter(user=user).exists()


def _watched_item_from_media(media):
    item = getattr(media, "item", None)
    if item is None or item.source != Sources.TMDB.value:
        return None
    media_type = item.media_type
    title = item.title or f"tmdb:{item.media_id}"
    watched_at = _watched_at_ms(getattr(media, "end_date", None))
    if media_type == MediaTypes.MOVIE.value:
        if getattr(media, "status", None) != Status.COMPLETED.value:
            return None
        return {
            "content_id": f"tmdb:{item.media_id}",
            "content_type": "movie",
            "title": title,
            "watched_at": watched_at,
        }
    if media_type == MediaTypes.EPISODE.value:
        season = item.season_number
        episode = item.episode_number
        if season is None or episode is None:
            return None
        return {
            "content_id": f"tmdb:{item.media_id}",
            "content_type": "series",
            "title": title,
            "season": int(season),
            "episode": int(episode),
            "watched_at": watched_at,
        }
    return None


def _delete_key_from_media(media):
    item = getattr(media, "item", None)
    if item is None or item.source != Sources.TMDB.value:
        return None
    if item.media_type == MediaTypes.MOVIE.value:
        return {"content_id": f"tmdb:{item.media_id}"}
    if item.media_type == MediaTypes.EPISODE.value:
        season = item.season_number
        episode = item.episode_number
        if season is None or episode is None:
            return None
        return {
            "content_id": f"tmdb:{item.media_id}",
            "season": int(season),
            "episode": int(episode),
        }
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
