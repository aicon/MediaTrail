"""Operations for live playback / Now Watching sessions."""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app.models import (
    DeviceDisplayName,
    Item,
    LEGACY_DEVICE_ID,
    LivePlayback,
    LivePlaybackStatus,
    MediaTypes,
)
from app.providers import services

logger = logging.getLogger(__name__)

LEGACY_DEVICE_LABEL = "Ismeretlen eszköz"

_YEAR_RE = re.compile(r"^(\d{4})")
# TMDB localized placeholders like "21. epizód" / "Episode 21" are not real titles.
_GENERIC_EPISODE_TITLE_RE = re.compile(
    r"^(?:"
    r"\d+\.?\s*epizód|"
    r"epizód\s*\d+|"
    r"\d+\.?\s*rész|"
    r"rész\s*\d+|"
    r"episode\s*\d+|"
    r"ep\.?\s*\d+|"
    r"capítulo\s*\d+|"
    r"folge\s*\d+"
    r")$",
    re.IGNORECASE,
)


class PlaybackItemNotFoundError(ValueError):
    """Raised when provider metadata does not contain the requested title."""


def dismiss_now_watching(user, device_id=None):
    """Clear live row(s) without writing history.

    When ``device_id`` is set, only that device strip is removed.
    """
    qs = LivePlayback.objects.filter(user=user)
    if device_id:
        qs = qs.filter(device_id=normalize_device_id(device_id))
    deleted, _ = qs.delete()
    return deleted


def normalize_device_id(device_id):
    """Return a safe device id, falling back to the legacy bucket."""
    cleaned = (device_id or "").strip()
    if not cleaned:
        return LEGACY_DEVICE_ID
    return cleaned[:128]


def normalize_device_label(device_label, device_id):
    """Return a display label for a device."""
    cleaned = (device_label or "").strip()
    if cleaned:
        return cleaned[:128]
    if normalize_device_id(device_id) == LEGACY_DEVICE_ID:
        return LEGACY_DEVICE_LABEL
    return ""


def set_device_display_name(user, device_id, custom_name):
    """Save or clear the user-chosen device label. Survives strip deletion."""
    resolved_id = normalize_device_id(device_id)
    cleaned = (custom_name or "").strip()[:128]
    if not cleaned:
        deleted, _ = DeviceDisplayName.objects.filter(
            user=user,
            device_id=resolved_id,
        ).delete()
        return deleted
    DeviceDisplayName.objects.update_or_create(
        user=user,
        device_id=resolved_id,
        defaults={"custom_name": cleaned},
    )
    return 1


def is_placeholder_episode_title(title, episode_number=None):
    """Return True when title is empty or a generated 'N. episode' label."""
    cleaned = (title or "").strip()
    if not cleaned:
        return True
    if _GENERIC_EPISODE_TITLE_RE.match(cleaned):
        return True
    if episode_number is not None:
        number = int(episode_number)
        if cleaned.lower() in {
            f"{number}. epizód",
            f"epizód {number}",
            f"episode {number}",
            f"ep {number}",
            f"ep. {number}",
        }:
            return True
    return False


def watching_stale_seconds():
    """Idle TTL for actively playing sessions (no progress ticks)."""
    return int(
        getattr(settings, "LIVE_PLAYBACK_WATCHING_STALE_SECONDS", 3 * 60),
    )


def paused_stale_seconds():
    """Idle TTL for paused sessions (progress ticks are not expected)."""
    return int(
        getattr(
            settings,
            "LIVE_PLAYBACK_PAUSED_STALE_SECONDS",
            getattr(settings, "LIVE_PLAYBACK_STALE_SECONDS", 10 * 60),
        ),
    )


def get_now_watching(user):
    """Return the newest non-stale live session for the user, or None.

    Stale rows are deleted with status-specific idle TTLs so a missed player
    `stop` cannot leave Now Watching stuck. Clearing live playback never
    touches history or tracked media status.
    """
    purge_stale_live_playbacks(user)
    return (
        LivePlayback.objects.filter(user=user)
        .select_related("item")
        .order_by("-updated_at")
        .first()
    )


def list_live_playbacks(user, *, limit=20):
    """Return non-stale live sessions for the user in stable strip order.

    Order is first-seen (``created_at``), not last progress tick, so a phone
    and a TV keep their places when either device sends updates.
    """
    purge_stale_live_playbacks(user)
    return list(
        LivePlayback.objects.filter(user=user)
        .select_related("item")
        .order_by("created_at", "id")[:limit],
    )


def purge_stale_live_playbacks(user=None):
    """Delete idle live sessions using watching vs paused TTLs.

    Only removes ``LivePlayback`` rows. History and tracked media are untouched.
    """
    now = timezone.now()
    watching_cutoff = now - timedelta(seconds=watching_stale_seconds())
    paused_cutoff = now - timedelta(seconds=paused_stale_seconds())
    qs = LivePlayback.objects.filter(
        Q(
            status=LivePlaybackStatus.WATCHING,
            updated_at__lt=watching_cutoff,
        )
        | Q(
            status=LivePlaybackStatus.PAUSED,
            updated_at__lt=paused_cutoff,
        ),
    )
    if user is not None:
        qs = qs.filter(user=user)
    deleted, _ = qs.delete()
    if deleted:
        logger.info("Purged %s stale live playback row(s)", deleted)
    return deleted


@transaction.atomic
def upsert_live_playback(
    *,
    user,
    media_type,
    source,
    media_id,
    position_ms,
    duration_ms=None,
    status=LivePlaybackStatus.WATCHING,
    season_number=None,
    episode_number=None,
    device_id=None,
    device_label=None,
):
    """Create or update the live playback row for one device."""
    item = resolve_playback_item(
        media_type=media_type,
        source=source,
        media_id=media_id,
        season_number=season_number,
        episode_number=episode_number,
    )
    if item.media_type not in {MediaTypes.MOVIE.value, MediaTypes.EPISODE.value}:
        raise ValidationError("Live playback requires a movie or episode item.")

    status_value = _normalize_status(status)
    position_ms = max(0, int(position_ms))
    if duration_ms is not None:
        duration_ms = max(0, int(duration_ms)) or None
    resolved_device_id = normalize_device_id(device_id)
    resolved_label = normalize_device_label(device_label, resolved_device_id)

    playback, created = LivePlayback.objects.select_for_update().get_or_create(
        user=user,
        device_id=resolved_device_id,
        defaults={
            "item": item,
            "device_label": resolved_label,
            "position_ms": position_ms,
            "duration_ms": duration_ms,
            "status": status_value,
        },
    )

    if created:
        _apply_display_metadata(playback, item, force=True)
        playback.save()
        logger.info(
            "Created live playback device=%s item=%s (%s)",
            resolved_device_id,
            item,
            user,
        )
        return playback

    item_changed = playback.item_id != item.id
    if item_changed:
        playback.item = item
        playback.position_ms = position_ms
        _apply_display_metadata(playback, item, force=True)
    elif position_ms <= 0 and playback.position_ms > 0:
        # Zero-position guard: keep last known seek when client reports 0.
        logger.info(
            "Ignored zero position for device=%s; kept %sms",
            resolved_device_id,
            playback.position_ms,
        )
    else:
        playback.position_ms = position_ms

    if duration_ms is not None:
        playback.duration_ms = duration_ms
    playback.status = status_value
    if resolved_label:
        playback.device_label = resolved_label
    if not item_changed:
        _apply_display_metadata(playback, item, force=False)
    playback.save(
        update_fields=[
            "item",
            "device_label",
            "position_ms",
            "duration_ms",
            "status",
            "episode_title",
            "year",
            "poster_image",
            "updated_at",
        ],
    )
    logger.info(
        "Updated live playback device=%s item=%s to %sms (%s)",
        resolved_device_id,
        item,
        playback.position_ms,
        playback.status,
    )
    return playback


def clear_live_playback(
    *,
    user,
    media_type=None,
    source=None,
    media_id=None,
    season_number=None,
    episode_number=None,
    item=None,
    device_id=None,
):
    """Delete matching live playback row(s). Returns deleted count.

    Does not modify Episode/Movie history or tracked media status.
    When ``device_id`` is set, only that device is cleared.
    """
    qs = LivePlayback.objects.filter(user=user)
    if device_id:
        qs = qs.filter(device_id=normalize_device_id(device_id))

    if item is not None:
        deleted, _ = qs.filter(item=item).delete()
        return deleted

    if not all([media_type, source, media_id]):
        if device_id:
            deleted, _ = qs.delete()
            return deleted
        raise ValidationError(
            "media_type, source and media_id are required to clear playback.",
        )

    lookup = _item_lookup_kwargs(
        media_type=media_type,
        source=source,
        media_id=media_id,
        season_number=season_number,
        episode_number=episode_number,
    )
    items = Item.objects.filter(**lookup)
    deleted, _ = qs.filter(item__in=items).delete()
    return deleted


def clear_live_playback_for_item(*, user, item, device_id=None):
    """Delete live playback for a concrete Item (e.g. after completion)."""
    return clear_live_playback(user=user, item=item, device_id=device_id)


def refresh_playback_display(playback):
    """Re-fetch display metadata when a placeholder episode title is stored."""
    item = playback.item
    if item.media_type != MediaTypes.EPISODE.value:
        return playback
    if not is_placeholder_episode_title(playback.episode_title, item.episode_number):
        return playback
    _apply_display_metadata(playback, item, force=True)
    playback.save(
        update_fields=["episode_title", "year", "poster_image", "updated_at"],
    )
    return playback


def resolve_playback_item(
    *,
    media_type,
    source,
    media_id,
    season_number=None,
    episode_number=None,
):
    """Resolve or create the movie/episode Item for a playback payload."""
    normalized = _normalize_media_type(media_type)
    if normalized == MediaTypes.MOVIE.value:
        return _resolve_movie_item(source=source, media_id=str(media_id))
    return _resolve_episode_item(
        source=source,
        media_id=str(media_id),
        season_number=season_number,
        episode_number=episode_number,
    )


def _normalize_media_type(media_type):
    if media_type in {MediaTypes.TV.value, MediaTypes.EPISODE.value}:
        return MediaTypes.EPISODE.value
    if media_type == MediaTypes.MOVIE.value:
        return MediaTypes.MOVIE.value
    raise ValidationError(
        f"Unsupported media_type for live playback: {media_type}",
    )


def _normalize_status(status):
    if isinstance(status, LivePlaybackStatus):
        return status.value
    if status in LivePlaybackStatus.values:
        return status
    raise ValidationError(f"Unsupported playback status: {status}")


def _item_lookup_kwargs(
    *,
    media_type,
    source,
    media_id,
    season_number=None,
    episode_number=None,
):
    normalized = _normalize_media_type(media_type)
    if normalized == MediaTypes.MOVIE.value:
        return {
            "media_id": str(media_id),
            "source": source,
            "media_type": MediaTypes.MOVIE.value,
            "season_number__isnull": True,
            "episode_number__isnull": True,
        }
    if season_number is None or episode_number is None:
        raise ValidationError(
            "season_number and episode_number are required for TV playback.",
        )
    return {
        "media_id": str(media_id),
        "source": source,
        "media_type": MediaTypes.EPISODE.value,
        "season_number": int(season_number),
        "episode_number": int(episode_number),
    }


def _resolve_movie_item(*, source, media_id):
    existing = Item.objects.filter(
        media_id=media_id,
        source=source,
        media_type=MediaTypes.MOVIE.value,
        season_number__isnull=True,
        episode_number__isnull=True,
    ).first()
    if existing:
        return existing

    metadata = services.get_media_metadata(MediaTypes.MOVIE.value, media_id, source)
    if not metadata:
        raise PlaybackItemNotFoundError

    item, _ = Item.objects.get_or_create(
        media_id=media_id,
        source=source,
        media_type=MediaTypes.MOVIE.value,
        defaults={
            "title": metadata.get("title") or media_id,
            "image": metadata.get("image") or settings.IMG_NONE,
        },
    )
    return item


def _resolve_episode_item(*, source, media_id, season_number, episode_number):
    if season_number is None or episode_number is None:
        raise ValidationError(
            "season_number and episode_number are required for TV playback.",
        )
    season_number = int(season_number)
    episode_number = int(episode_number)

    existing = Item.objects.filter(
        media_id=media_id,
        source=source,
        media_type=MediaTypes.EPISODE.value,
        season_number=season_number,
        episode_number=episode_number,
    ).first()
    if existing:
        return existing

    tv_with_seasons = services.get_media_metadata(
        "tv_with_seasons",
        media_id,
        source,
        [season_number],
    )
    season_metadata = (tv_with_seasons or {}).get(f"season/{season_number}")
    if not season_metadata:
        raise PlaybackItemNotFoundError

    episode_meta = next(
        (
            episode
            for episode in season_metadata.get("episodes", [])
            if episode.get("episode_number") == episode_number
        ),
        None,
    )
    if episode_meta is None:
        raise PlaybackItemNotFoundError

    image = _episode_still(episode_meta, season_metadata)

    item, _ = Item.objects.get_or_create(
        media_id=media_id,
        source=source,
        media_type=MediaTypes.EPISODE.value,
        season_number=season_number,
        episode_number=episode_number,
        defaults={
            "title": tv_with_seasons.get("title") or media_id,
            "image": image,
        },
    )
    return item


def _apply_display_metadata(playback, item, *, force):
    """Fill year / episode title / poster when missing (or when force=True)."""
    placeholder_title = item.media_type == MediaTypes.EPISODE.value and (
        is_placeholder_episode_title(playback.episode_title, item.episode_number)
    )
    needs = force or not playback.year or not playback.poster_image or placeholder_title
    if item.media_type == MediaTypes.EPISODE.value:
        needs = needs or not playback.episode_title
    if not needs:
        return

    try:
        meta = _fetch_display_metadata(item)
    except Exception:  # noqa: BLE001
        logger.exception("Could not enrich live playback display for %s", item)
        return

    if meta.get("year") and (force or not playback.year):
        playback.year = meta["year"]
    if meta.get("poster_image") and (force or not playback.poster_image):
        playback.poster_image = meta["poster_image"]
    if item.media_type == MediaTypes.EPISODE.value:
        episode_title = (meta.get("episode_title") or "").strip()
        if episode_title and (
            force
            or not playback.episode_title
            or is_placeholder_episode_title(
                playback.episode_title,
                item.episode_number,
            )
        ):
            playback.episode_title = episode_title
        # Prefer episode still as backdrop when available.
        if meta.get("backdrop") and (
            force or not item.image or item.image == settings.IMG_NONE
        ):
            item.image = meta["backdrop"]
            item.save(update_fields=["image"])


def _fetch_display_metadata(item):
    """Load year, poster, and real episode title from provider metadata."""
    if item.media_type == MediaTypes.MOVIE.value:
        metadata = services.get_media_metadata(
            MediaTypes.MOVIE.value,
            item.media_id,
            item.source,
        )
        if not metadata:
            return {}
        release = (metadata.get("details") or {}).get("release_date") or ""
        return {
            "year": _year_from_date(release),
            "poster_image": metadata.get("image") or "",
            "episode_title": "",
            "backdrop": metadata.get("image") or "",
        }

    tv_with_seasons = services.get_media_metadata(
        "tv_with_seasons",
        item.media_id,
        item.source,
        [item.season_number],
    )
    if not tv_with_seasons:
        return {}
    season_metadata = tv_with_seasons.get(f"season/{item.season_number}") or {}
    episode_meta = next(
        (
            episode
            for episode in season_metadata.get("episodes", [])
            if episode.get("episode_number") == item.episode_number
        ),
        None,
    )
    details = tv_with_seasons.get("details") or {}
    first = details.get("first_air_date") or ""
    last = details.get("last_air_date") or ""
    year = _year_range(first, last)
    episode_title = _resolve_real_episode_title(
        item=item,
        episode_meta=episode_meta or {},
    )
    return {
        "year": year,
        "poster_image": tv_with_seasons.get("image") or season_metadata.get("image") or "",
        "episode_title": episode_title,
        "backdrop": _episode_still(episode_meta or {}, season_metadata),
    }


def _resolve_real_episode_title(*, item, episode_meta):
    """Prefer a real episode name; never keep localized 'N. epizód' placeholders."""
    candidates = [
        episode_meta.get("name"),
        episode_meta.get("title"),
        episode_meta.get("episode_title"),
        episode_meta.get("original_name"),
    ]
    for candidate in candidates:
        cleaned = (candidate or "").strip()
        if cleaned and not is_placeholder_episode_title(cleaned, item.episode_number):
            return cleaned

    # Dedicated episode endpoint: use episode_title only (title is the series name).
    try:
        episode_payload = services.get_media_metadata(
            MediaTypes.EPISODE.value,
            item.media_id,
            item.source,
            [item.season_number],
            item.episode_number,
        )
    except Exception:  # noqa: BLE001
        episode_payload = None
    if isinstance(episode_payload, dict):
        cleaned = (episode_payload.get("episode_title") or "").strip()
        if cleaned and not is_placeholder_episode_title(cleaned, item.episode_number):
            return cleaned
        # Some providers may still put the episode name in name/original_name.
        for key in ("name", "original_name"):
            cleaned = (episode_payload.get(key) or "").strip()
            if (
                cleaned
                and cleaned != item.title
                and not is_placeholder_episode_title(cleaned, item.episode_number)
            ):
                return cleaned

    english = _fetch_english_episode_title(
        media_id=item.media_id,
        season_number=item.season_number,
        episode_number=item.episode_number,
        source=item.source,
    )
    if english and not is_placeholder_episode_title(english, item.episode_number):
        return english
    return ""


def _fetch_english_episode_title(*, media_id, season_number, episode_number, source):
    """Fetch English episode name when the active TMDB language is a placeholder."""
    if source != "tmdb":
        return ""
    try:
        import requests

        from app.providers import tmdb
    except ImportError:
        return ""
    url = (
        f"{tmdb.base_url}/tv/{media_id}/season/{season_number}/episode/{episode_number}"
    )
    params = {**tmdb.base_params, "language": "en-US"}
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception:  # noqa: BLE001
        logger.exception(
            "English episode title fetch failed for %s S%sE%s",
            media_id,
            season_number,
            episode_number,
        )
        return ""
    return (payload.get("name") or payload.get("original_name") or "").strip()


def _episode_still(episode_meta, season_metadata):
    if episode_meta.get("still_path"):
        return f"https://image.tmdb.org/t/p/original{episode_meta['still_path']}"
    if episode_meta.get("image"):
        return episode_meta["image"]
    if season_metadata.get("image"):
        return season_metadata["image"]
    return settings.IMG_NONE


def _year_from_date(value):
    if not value:
        return ""
    match = _YEAR_RE.match(str(value).strip())
    return match.group(1) if match else ""


def _year_range(first, last):
    start = _year_from_date(first)
    end = _year_from_date(last)
    if start and end and end != start:
        return f"{start} - {end}"
    return start or end or ""
