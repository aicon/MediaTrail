from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext as _

from app.models import BasicMedia, LivePlaybackStatus, MediaTypes, Status
from app.playback_operations import (
    get_now_watching,
    is_placeholder_episode_title,
    refresh_playback_display,
)
from app.templatetags.app_tags import slug


def get_now_watching_context(user):
    """Build template context for the Now Watching home strip."""
    playback = get_now_watching(user)
    if playback is None:
        return None

    item = playback.item
    is_episode = item.media_type == MediaTypes.EPISODE.value
    if is_episode and is_placeholder_episode_title(
        playback.episode_title,
        item.episode_number,
    ):
        refresh_playback_display(playback)
        playback.refresh_from_db()

    percent = playback.percent_watched
    episode_title = (playback.episode_title or "").strip()
    if is_placeholder_episode_title(episode_title, item.episode_number):
        # Never show "21. epizód" next to SxxExx; omit until a real title exists.
        episode_title = ""
    year = (playback.year or "").strip()
    poster = (playback.poster_image or "").strip() or item.image
    backdrop = item.image or poster

    title_slug = slug(item.title)
    if is_episode:
        detail_url = reverse(
            "season_details",
            kwargs={
                "source": item.source,
                "media_id": item.media_id,
                "title": title_slug,
                "season_number": item.season_number,
            },
        )
    else:
        detail_url = reverse(
            "media_details",
            kwargs={
                "source": item.source,
                "media_type": item.media_type,
                "media_id": item.media_id,
                "title": title_slug,
            },
        )

    return {
        "playback": playback,
        "item": item,
        "title": item.title,
        "year": year,
        "episode_title": episode_title,
        "image": backdrop,
        "poster_image": poster,
        "season_episode": playback.season_episode_label,
        "percent_watched": percent,
        "remaining_label": playback.remaining_label,
        "remaining_short": playback.remaining_short,
        "started_ago": playback.started_ago_label,
        "is_watching": playback.status == LivePlaybackStatus.WATCHING,
        "status_label": (
            _("Now Watching")
            if playback.status == LivePlaybackStatus.WATCHING
            else _("Paused")
        ),
        "is_episode": is_episode,
        "source": item.source,
        "media_id": item.media_id,
        "media_type": MediaTypes.TV.value if is_episode else item.media_type,
        "season_number": item.season_number,
        "detail_url": detail_url,
    }


def build_home_section(key, media_types):
    """Build home section payload."""
    return {
        "key": key,
        "id": slugify(key),
        "media_types": media_types,
        "count": sum(media_list["total"] for media_list in media_types.values()),
    }


def is_active_in_progress_media(media):
    """Return True when media still has released backlog."""
    if not _is_incoming_media(media):
        return True

    return media.max_progress is not None and media.progress < media.max_progress


def get_home_media_types(
    request,
    sort_by,
    section_key,
    items_limit,
    specific_media_type=None,
    *,
    hide_unreleased=False,
):
    """Return media types for a home section, or one type's load-more page."""
    media_types = BasicMedia.objects.get_home_status(
        user=request.user,
        status=section_key,
        sort_by=sort_by,
        items_limit=None if hide_unreleased else items_limit,
        specific_media_type=specific_media_type,
    )

    if not hide_unreleased:
        return media_types

    return _paginate_home_media_types(
        _filter_home_media_types(
            media_types,
            lambda media: _is_released_home_media(media, section_key),
        ),
        items_limit,
        page_start=items_limit if specific_media_type else 0,
    )


def _filter_home_media_types(media_types, predicate):
    """Filter home media entries by predicate."""
    filtered_media_types = {}
    for media_type, media_list in media_types.items():
        filtered_items = [media for media in media_list["items"] if predicate(media)]
        if filtered_items:
            filtered_media_types[media_type] = {
                "items": filtered_items,
                "total": len(filtered_items),
            }
    return filtered_media_types


def _paginate_home_media_types(media_types, items_limit, page_start=0):
    """Paginate already-grouped home media entries."""
    paginated_media_types = {}
    for media_type, media_list in media_types.items():
        page_end = None if items_limit is None else page_start + items_limit
        items = media_list["items"][page_start:page_end]

        if items or (page_start > 0 and media_list["total"]):
            paginated_media_types[media_type] = {
                "items": items,
                "total": media_list["total"],
            }
    return paginated_media_types


def _is_incoming_media(media):
    """Return True when media has a real upcoming release."""
    return bool(media.next_event and not media.next_event.is_max_datetime)


def _is_released_home_media(media, section_key):
    """Return True when media should remain after hiding unreleased entries."""
    if section_key == Status.IN_PROGRESS.value:
        return is_active_in_progress_media(media)

    return not _is_incoming_media(media)
