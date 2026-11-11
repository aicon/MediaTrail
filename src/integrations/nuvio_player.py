"""Receive Nuvio player events and update Now Watching inside MediaTrail.

Matches the MediaTrail-Scrobbler addon contract: same path shape, unquoted
video ids, start at zero creates the strip, later zero ticks keep the last seek.
One live strip per device; stop/pause only touch that device.
"""

import logging
import re
from urllib.parse import parse_qs, unquote

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone

from app.episode_operations import EpisodeNotFoundError, watch_episode
from app.models import (
    LEGACY_DEVICE_ID,
    LivePlayback,
    LivePlaybackStatus,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from app.playback_operations import (
    clear_live_playback,
    normalize_device_id,
    normalize_device_label,
    resolve_playback_item,
    upsert_live_playback,
)
from app.providers import services, tmdb

logger = logging.getLogger(__name__)

IMDB_RE = re.compile(r"^tt\d+$", re.IGNORECASE)
WATCHED_THRESHOLD = 0.9
DEDUPE_SECONDS = 120


def manifest(logo=None):
    """Return the Stremio addon manifest Nuvio installs."""
    payload = {
        "id": "community.mediatrail.nuvio",
        "version": "1.0.2",
        "name": "MediaTrail",
        "description": "Sends Nuvio playback to this MediaTrail.",
        "resources": ["player"],
        "types": ["movie", "series"],
        "idPrefixes": ["tt"],
        "catalogs": [],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False,
        },
    }
    if logo:
        payload["logo"] = logo
    return payload


def handle_player(user, media_type, video_id, extra, query):
    """Apply one Nuvio player event for this user."""
    params = _player_params(extra, query)
    action = (params.get("action") or "").strip().lowercase()
    if action == "resume":
        action = "start"
    current_ms = _as_int(params.get("currentTime"))
    duration_ms = _as_int(params.get("duration"))
    device_id = normalize_device_id(params.get("deviceId") or params.get("device_id"))
    device_label = normalize_device_label(
        params.get("deviceName") or params.get("device_name"),
        device_id,
    )
    target = _parse_video_id(video_id)
    logger.info(
        "Nuvio player action=%s type=%s videoId=%s device=%s currentTime=%s duration=%s",
        action,
        media_type,
        video_id,
        device_id,
        current_ms,
        duration_ms,
    )
    if target is None:
        logger.warning("Nuvio player skipped bad videoId=%s", video_id)
        return
    if action not in {"start", "pause", "progress", "stop"}:
        return

    try:
        tmdb_id = _tmdb_id(target)
    except services.ProviderAPIError:
        logger.exception("TMDB lookup failed for %s", target["imdb_id"])
        return
    if not tmdb_id:
        logger.info("No TMDB id for %s", target["imdb_id"])
        return

    if action == "stop":
        _stop(
            user,
            target,
            tmdb_id,
            current_ms,
            duration_ms,
            device_id=device_id,
        )
        return
    _progress(
        user,
        target,
        tmdb_id,
        action,
        current_ms,
        duration_ms,
        device_id=device_id,
        device_label=device_label,
    )


def _progress(
    user,
    target,
    tmdb_id,
    action,
    current_ms,
    duration_ms,
    *,
    device_id,
    device_label,
):
    """Update the Now Watching row for one device."""
    # start@0 creates the strip immediately. Later zero/empty ticks keep the
    # last seek inside upsert_live_playback.
    if current_ms is None:
        if action != "start":
            return
        current_ms = 0
    if current_ms <= 0 and action != "start":
        current_ms = 0
    status = (
        LivePlaybackStatus.PAUSED
        if action == "pause"
        else LivePlaybackStatus.WATCHING
    )
    try:
        upsert_live_playback(
            user=user,
            media_type=_playback_type(target),
            source=Sources.TMDB.value,
            media_id=tmdb_id,
            position_ms=max(0, current_ms),
            duration_ms=duration_ms if duration_ms and duration_ms > 0 else None,
            status=status,
            season_number=target["season"],
            episode_number=target["episode"],
            device_id=device_id,
            device_label=device_label,
        )
    except (ValidationError, services.ProviderAPIError):
        logger.exception("Nuvio playback update failed for %s", target["key"])


def _stop(user, target, tmdb_id, current_ms, duration_ms, *, device_id):
    """Hide this device's Now Watching, then maybe save a finished watch."""
    progress = _progress_ratio(current_ms, duration_ms)
    if progress is None:
        progress = _stored_progress(user, target, tmdb_id, device_id=device_id)
    clear_live_playback(user=user, device_id=device_id)
    if progress is None or progress < WATCHED_THRESHOLD:
        return
    if cache.get(_dedupe_key(user, target)):
        return
    when = timezone.now().replace(second=0, microsecond=0)
    try:
        if target["kind"] == "movie":
            _complete_movie(user, tmdb_id, when, device_id=device_id)
        else:
            watch_episode(
                user=user,
                media_id=tmdb_id,
                source=Sources.TMDB.value,
                season_number=target["season"],
                episode_number=target["episode"],
                end_date=when,
            )
            clear_live_playback(
                user=user,
                media_type=MediaTypes.TV.value,
                source=Sources.TMDB.value,
                media_id=str(tmdb_id),
                season_number=target["season"],
                episode_number=target["episode"],
                device_id=device_id,
            )
    except (EpisodeNotFoundError, ValidationError, services.ProviderAPIError):
        logger.exception("Nuvio completion failed for %s", target["key"])
        return
    cache.set(_dedupe_key(user, target), 1, DEDUPE_SECONDS)


def _complete_movie(user, tmdb_id, when, *, device_id):
    """Mark the movie finished and drop this device's live row."""
    item = resolve_playback_item(
        media_type=MediaTypes.MOVIE.value,
        source=Sources.TMDB.value,
        media_id=str(tmdb_id),
    )
    movie = Movie.objects.filter(user=user, item=item).first()
    if movie is None:
        movie = Movie(user=user, item=item)
    movie.status = Status.COMPLETED.value
    movie.end_date = when
    movie.save()
    clear_live_playback(user=user, item=item, device_id=device_id)


def _stored_progress(user, target, tmdb_id, *, device_id):
    """Use the saved Now Watching position when the stop event has no time."""
    try:
        item = resolve_playback_item(
            media_type=_playback_type(target),
            source=Sources.TMDB.value,
            media_id=str(tmdb_id),
            season_number=target["season"],
            episode_number=target["episode"],
        )
    except (ValidationError, services.ProviderAPIError):
        return None
    row = LivePlayback.objects.filter(
        user=user,
        item=item,
        device_id=normalize_device_id(device_id),
    ).first()
    if row is None and normalize_device_id(device_id) != LEGACY_DEVICE_ID:
        row = LivePlayback.objects.filter(user=user, item=item).first()
    if row is None or not row.duration_ms:
        return None
    return max(0.0, min(1.0, row.position_ms / row.duration_ms))


def _tmdb_id(target):
    """Resolve an IMDb id to a TMDB movie or show id."""
    found = tmdb.find(target["imdb_id"], "imdb_id") or {}
    key = "movie_results" if target["kind"] == "movie" else "tv_results"
    rows = found.get(key) or []
    if not rows or rows[0].get("id") is None:
        return ""
    return str(rows[0]["id"])


def _parse_video_id(video_id):
    """Accept movie `tt…` and episode `tt…:season:episode` ids."""
    raw = unquote((video_id or "").strip())
    if raw.endswith(".json"):
        raw = raw[: -len(".json")]
    parts = raw.split(":")
    if len(parts) == 1 and IMDB_RE.match(parts[0]):
        imdb = parts[0].lower()
        return {
            "kind": "movie",
            "imdb_id": imdb,
            "season": None,
            "episode": None,
            "key": f"movie:{imdb}",
        }
    if len(parts) != 3 or not IMDB_RE.match(parts[0]):
        return None
    try:
        season = int(parts[1])
        episode = int(parts[2])
    except ValueError:
        return None
    if season < 0 or episode < 0:
        return None
    imdb = parts[0].lower()
    return {
        "kind": "episode",
        "imdb_id": imdb,
        "season": season,
        "episode": episode,
        "key": f"episode:{imdb}:{season}:{episode}",
    }


def _playback_type(target):
    """Map parsed video id to MediaTrail media_type."""
    if target["kind"] == "movie":
        return MediaTypes.MOVIE.value
    return MediaTypes.TV.value


def _player_params(extra, query):
    """Merge path extras and query string into one dict of first values."""
    params = {}
    if extra:
        raw = unquote(extra)
        if raw.endswith(".json"):
            raw = raw[: -len(".json")]
        params.update({k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()})
    if query:
        params.update({k: v[-1] for k, v in parse_qs(query, keep_blank_values=True).items()})
    return params


def _as_int(value):
    """Parse a non-negative int, or None."""
    if value is None or value == "":
        return None
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _progress_ratio(current_ms, duration_ms):
    """Return watched ratio 0–1, or None when unknown."""
    if current_ms is None or duration_ms is None or duration_ms <= 0:
        return None
    return max(0.0, min(1.0, current_ms / duration_ms))


def _dedupe_key(user, target):
    """Cache key so a double stop does not write history twice."""
    return f"nuvio-player-complete:{user.id}:{target['key']}"
