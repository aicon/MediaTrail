"""Emby Now Watching.

One locked /Sessions poll per MediaTrail user, started by playback webhooks
and rescheduled only while a device is still being followed. Idle servers
are not polled.
"""

import logging
from urllib.parse import urlparse

import requests
from django.core.cache import cache
from django.db import transaction

from app.models import LivePlaybackStatus, MediaTypes, Sources
from app.playback_operations import clear_live_playback, upsert_live_playback
from integrations.imports.helpers import decrypt, encrypt

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
LOCK_SECONDS = 90
STATE_SECONDS = 60 * 60
MISS_LIMIT = 2
DISCOVERY_POLLS = 4
DEVICE_PREFIX = "emby:"


class EmbyPollError(Exception):
    """The Sessions request did not return a usable list."""


def ticks_to_ms(ticks):
    """Convert Emby 100-nanosecond ticks to milliseconds."""
    if ticks is None:
        return None
    return max(0, int(ticks) // 10_000)


def provider_ids(item):
    """Read ProviderIds without caring about key case."""
    raw = (item or {}).get("ProviderIds") or {}
    folded = {str(key).casefold(): value for key, value in raw.items() if value}
    return {
        "tmdb_id": folded.get("tmdb"),
        "imdb_id": folded.get("imdb"),
        "tvdb_id": folded.get("tvdb"),
    }


def playing_sessions(rows, emby_user_id):
    """Return sessions that are actually playing for this Emby user."""
    playing = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = row.get("NowPlayingItem")
        if not isinstance(item, dict):
            continue
        if str(row.get("UserId") or "") != str(emby_user_id):
            continue
        device_id = str(row.get("DeviceId") or "").strip()
        if not device_id:
            continue
        playing.append(row)
    return playing


def strip_device_id(emby_device_id):
    """LivePlayback key for an Emby device. Session ids are not a key."""
    return f"{DEVICE_PREFIX}{emby_device_id}"[:128]


def configured(user):
    """Return True when this account can call the Emby Sessions API."""
    return bool(user.emby_server_url and user.emby_api_key and user.emby_user_id)


def save_connection(user, server_url, api_key, emby_user_id, emby_user_name):
    """Store the server origin, encrypted key, and stable Emby user id."""
    user.emby_server_url = server_url
    user.emby_api_key = encrypt(api_key)
    user.emby_user_id = emby_user_id
    user.emby_user_name = emby_user_name
    user.save(
        update_fields=[
            "emby_server_url",
            "emby_api_key",
            "emby_user_id",
            "emby_user_name",
        ],
    )


def clear_connection(user):
    """Remove saved Emby credentials and stop following its devices."""
    user.emby_server_url = ""
    user.emby_api_key = ""
    user.emby_user_id = ""
    user.emby_user_name = ""
    user.save(
        update_fields=[
            "emby_server_url",
            "emby_api_key",
            "emby_user_id",
            "emby_user_name",
        ],
    )
    _save_state(user.id, _empty_state())
    clear_live_playback_prefix(user)


def clear_live_playback_prefix(user):
    """Delete only this user's Emby strips."""
    from app.models import LivePlayback

    LivePlayback.objects.filter(
        user=user,
        device_id__startswith=DEVICE_PREFIX,
    ).delete()


def emby_identity_unchanged(user, server_url, username):
    """Return True when the saved server and user name still identify this account.

    Comparison ignores surrounding spaces, a trailing slash on the server,
    and letter case in the user name. A missing stored id is always a change.
    """
    if not (user.emby_user_id or "").strip():
        return False
    stored_url = validate_server_url(user.emby_server_url or "")
    submitted_url = validate_server_url(server_url or "")
    if not stored_url or not submitted_url or stored_url != submitted_url:
        return False
    stored_name = (user.emby_user_name or "").strip().casefold()
    submitted_name = (username or "").strip().casefold()
    if not stored_name or not submitted_name:
        return False
    return stored_name == submitted_name


def lookup_emby_user(server_url, api_key, username):
    """Resolve a display name to exactly one Emby user id."""
    url = f"{server_url.rstrip('/')}/emby/Users"
    try:
        response = requests.get(
            url,
            headers=_headers(api_key),
            timeout=10,
        )
        response.raise_for_status()
        users = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise EmbyPollError("Emby user lookup failed") from exc
    if not isinstance(users, list):
        raise EmbyPollError("Emby user lookup returned an unexpected payload")
    wanted = username.casefold()
    matches = [
        row
        for row in users
        if isinstance(row, dict) and str(row.get("Name") or "").casefold() == wanted
    ]
    if len(matches) != 1 or not matches[0].get("Id"):
        return None
    return str(matches[0]["Id"]), str(matches[0].get("Name") or username)


def validate_server_url(server_url):
    """Accept an http(s) origin without embedded credentials."""
    parsed = urlparse(server_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def handle_live_event(user, payload):
    """Apply one Emby playback webhook to the live-tracking state."""
    if not configured(user):
        return
    event_user = str((payload.get("User") or {}).get("Id") or "")
    if event_user and event_user != str(user.emby_user_id):
        return

    event = payload.get("Event")
    device_id = str((payload.get("Session") or {}).get("DeviceId") or "").strip()

    if event == "playback.start":
        if device_id:
            _track_device(user.id, device_id)
            _upsert_webhook(user, payload, LivePlaybackStatus.WATCHING)
        else:
            _set_discovery(user.id, DISCOVERY_POLLS)
            logger.info(
                "Emby start has no Session.DeviceId; discovering user=%s",
                user.id,
            )
        request_poll(user.id)
        return

    if event == "playback.stop":
        if not device_id:
            logger.warning("Emby stop has no Session.DeviceId user=%s", user.id)
            return
        _untrack_device(user.id, device_id)
        _clear_strip(user, device_id)
        if _tracking_active(user.id):
            request_poll(user.id)
        return

    if event == "playback.pause":
        if device_id and _is_tracked(user.id, device_id):
            _upsert_webhook(user, payload, LivePlaybackStatus.PAUSED)
        return

    if event == "playback.unpause":
        if device_id and _is_tracked(user.id, device_id):
            _upsert_webhook(user, payload, LivePlaybackStatus.WATCHING)
        request_poll(user.id)


def request_poll(user_id, *, delay=0):
    """Ask for a poll. The lock inside the task prevents overlapping calls."""
    cache.set(_want_key(user_id), "1", timeout=STATE_SECONDS)
    from integrations.tasks import poll_emby_sessions

    poll_emby_sessions.apply_async(args=[user_id], countdown=delay)


def run_poll(user_id):
    """Poll once, then reschedule only while tracking is still active."""
    if not cache.add(_lock_key(user_id), "1", timeout=LOCK_SECONDS):
        logger.info("Emby session poll skipped; already running user=%s", user_id)
        return
    try:
        cache.delete(_want_key(user_id))
        try:
            active = _poll_once(user_id)
        except Exception:
            logger.exception("Emby session poll failed user=%s", user_id)
            active = _tracking_active(user_id)
    finally:
        cache.delete(_lock_key(user_id))

    if cache.get(_want_key(user_id)):
        request_poll(user_id, delay=1)
        return
    if active:
        request_poll(user_id, delay=POLL_SECONDS)


def _poll_once(user_id):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.get(pk=user_id)
    if not configured(user):
        _save_state(user_id, _empty_state())
        return False

    before = _load_state(user_id)
    try:
        api_key = decrypt(user.emby_api_key)
        rows = fetch_sessions(user.emby_server_url, api_key)
    except (EmbyPollError, ValueError):
        logger.warning("Emby session poll kept existing strips user=%s", user_id)
        return _tracking_active(user_id)

    state = _load_state(user_id)
    removed_during = set(before["devices"]) - set(state["devices"])

    seen = {}
    for row in playing_sessions(rows, user.emby_user_id):
        device_id = str(row.get("DeviceId")).strip()
        if device_id in removed_during:
            continue
        seen[device_id] = row
        state["devices"][device_id] = {"misses": 0}
        _upsert_session(user, row)

    for device_id in list(state["devices"]):
        if device_id in seen:
            continue
        misses = int(state["devices"][device_id].get("misses", 0)) + 1
        if misses >= MISS_LIMIT:
            state["devices"].pop(device_id, None)
            _clear_strip(user, device_id)
            logger.info(
                "Emby device absent twice; removed strip user=%s device=%s",
                user_id,
                device_id,
            )
        else:
            state["devices"][device_id]["misses"] = misses

    if state["discovery"]:
        state["discovery"] = 0 if seen else state["discovery"] - 1

    _save_state(user_id, state)
    return bool(state["devices"]) or state["discovery"] > 0


def fetch_sessions(server_url, api_key):
    """GET /emby/Sessions. Errors are not an empty playing list."""
    url = f"{server_url.rstrip('/')}/emby/Sessions"
    try:
        response = requests.get(url, headers=_headers(api_key), timeout=10)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise EmbyPollError("Emby sessions request failed") from exc
    if not isinstance(payload, list):
        raise EmbyPollError("Emby sessions response was not a list")
    return payload


def resolve_now_playing(user, item):
    """Map an Emby item to a TMDB movie or episode, or return None."""
    from integrations.webhooks.emby import EmbyWebhookProcessor

    ids = provider_ids(item)
    media_type = (item or {}).get("Type")
    processor = EmbyWebhookProcessor()

    if media_type == "Episode":
        return _resolve_episode(processor, ids)
    if media_type == "Movie":
        return _resolve_movie(user, processor, ids)
    return None


def _resolve_episode(processor, ids):
    from app.providers import tvdb as tvdb_provider

    tvdb_id = ids.get("tvdb_id")
    if tvdb_id:
        media_id, season_number, episode_number = processor._find_tv_media_id(
            tvdb_id,
            "tvdb_id",
        )
        if not media_id:
            tvdb_episode = tvdb_provider.episode(int(tvdb_id))
            if tvdb_episode:
                media_id = tvdb_provider.series_tmdb_id(tvdb_episode["series_id"])
                season_number = tvdb_episode["season_number"]
                episode_number = tvdb_episode["episode_number"]
        if media_id:
            return (MediaTypes.TV.value, str(media_id), season_number, episode_number)

    imdb_id = ids.get("imdb_id")
    if imdb_id:
        media_id, season_number, episode_number = processor._find_tv_media_id(
            imdb_id,
            "imdb_id",
        )
        if media_id:
            return (MediaTypes.TV.value, str(media_id), season_number, episode_number)
    return None


def _resolve_movie(user, processor, ids):
    import app

    del user, processor
    tmdb_id = ids.get("tmdb_id")
    if tmdb_id:
        return (MediaTypes.MOVIE.value, str(tmdb_id), None, None)
    imdb_id = ids.get("imdb_id")
    if not imdb_id:
        return None
    response = app.providers.tmdb.find(imdb_id, "imdb_id")
    results = response.get("movie_results") or []
    if not results:
        return None
    return (MediaTypes.MOVIE.value, str(results[0]["id"]), None, None)


def _upsert_session(user, row):
    item = row.get("NowPlayingItem") or {}
    play_state = row.get("PlayState") or {}
    status = (
        LivePlaybackStatus.PAUSED
        if play_state.get("IsPaused")
        else LivePlaybackStatus.WATCHING
    )
    _upsert(
        user,
        item,
        position_ticks=play_state.get("PositionTicks"),
        status=status,
        device_id=str(row.get("DeviceId")).strip(),
        device_name=row.get("DeviceName") or "",
    )


def _upsert_webhook(user, payload, status):
    session = payload.get("Session") or {}
    device_id = str(session.get("DeviceId") or "").strip()
    if not device_id:
        return
    playback = payload.get("PlaybackInfo") or {}
    item = dict(payload.get("Item") or {})
    if item.get("RunTimeTicks") is None:
        source = playback.get("MediaSource") or {}
        if source.get("RunTimeTicks") is not None:
            item["RunTimeTicks"] = source["RunTimeTicks"]
    _upsert(
        user,
        item,
        position_ticks=playback.get("PositionTicks"),
        status=status,
        device_id=device_id,
        device_name=session.get("DeviceName") or "",
    )


def _upsert(user, item, *, position_ticks, status, device_id, device_name):
    target = resolve_now_playing(user, item)
    if not target:
        logger.info(
            "Emby item could not be matched user=%s device=%s",
            user.id,
            device_id,
        )
        return
    media_type, media_id, season_number, episode_number = target
    try:
        with transaction.atomic():
            upsert_live_playback(
                user=user,
                media_type=media_type,
                source=Sources.TMDB.value,
                media_id=media_id,
                position_ms=ticks_to_ms(position_ticks) or 0,
                duration_ms=ticks_to_ms(item.get("RunTimeTicks")),
                status=status,
                season_number=season_number,
                episode_number=episode_number,
                device_id=strip_device_id(device_id),
                device_label=device_name,
            )
    except Exception:
        logger.exception(
            "Emby strip update failed user=%s device=%s",
            user.id,
            device_id,
        )


def _clear_strip(user, emby_device_id):
    clear_live_playback(user=user, device_id=strip_device_id(emby_device_id))


def _headers(api_key):
    return {"X-Emby-Token": api_key, "Accept": "application/json"}


def _empty_state():
    return {"devices": {}, "discovery": 0}


def _state_key(user_id):
    return f"emby-live:{user_id}"


def _lock_key(user_id):
    return f"emby-live-lock:{user_id}"


def _want_key(user_id):
    return f"emby-live-want:{user_id}"


def _load_state(user_id):
    state = cache.get(_state_key(user_id))
    if not isinstance(state, dict):
        return _empty_state()
    devices = state.get("devices")
    if not isinstance(devices, dict):
        devices = {}
    return {"devices": devices, "discovery": int(state.get("discovery") or 0)}


def _save_state(user_id, state):
    cache.set(_state_key(user_id), state, timeout=STATE_SECONDS)


def _track_device(user_id, device_id):
    state = _load_state(user_id)
    state["devices"].setdefault(device_id, {"misses": 0})
    state["devices"][device_id]["misses"] = 0
    _save_state(user_id, state)


def _untrack_device(user_id, device_id):
    state = _load_state(user_id)
    state["devices"].pop(device_id, None)
    _save_state(user_id, state)


def _is_tracked(user_id, device_id):
    return device_id in _load_state(user_id)["devices"]


def _set_discovery(user_id, remaining):
    state = _load_state(user_id)
    state["discovery"] = remaining
    _save_state(user_id, state)


def _tracking_active(user_id):
    state = _load_state(user_id)
    return bool(state["devices"]) or state["discovery"] > 0
