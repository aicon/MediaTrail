from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext as _

from app.models import BasicMedia, LivePlaybackStatus, MediaTypes, Status
from app.playback_operations import (
    is_placeholder_episode_title,
    list_live_playbacks,
    refresh_playback_display,
)
from app.templatetags.app_tags import slug


def get_now_watching_contexts(user):
    """Build template contexts for every active Now Watching strip."""
    contexts = []
    for playback in list_live_playbacks(user):
        context = _playback_context(playback)
        if context is not None:
            contexts.append(context)
    return contexts


def get_now_watching_context(user):
    """Build template context for the newest Now Watching strip (compat)."""
    contexts = get_now_watching_contexts(user)
    return contexts[0] if contexts else None


def _playback_context(playback):
    """Build one strip context from a LivePlayback row."""
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
        "device_id": playback.device_id,
        "device_name": playback.display_device_name,
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
    if not _has_released_backlog(media):
        return False
    # A future premiere with no released episodes yet is not something to watch.
    if _is_incoming_media(media) and not getattr(media, "max_progress", None):
        return False
    return True


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
        items_limit=None,
        specific_media_type=specific_media_type,
    )
    if section_key == Status.IN_PROGRESS.value:
        media_types = _active_in_progress_media_types(media_types)
    if hide_unreleased:
        media_types = _filter_home_media_types(
            media_types,
            lambda media: _is_released_home_media(media, section_key),
        )
    # The first page is one row. "Load all" must append every remaining item,
    # otherwise the header count can never match the grid.
    page_start = items_limit if specific_media_type else 0
    page_size = None if specific_media_type else items_limit
    return _paginate_home_media_types(
        media_types,
        page_size,
        page_start=page_start,
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


def _active_in_progress_media_types(media_types):
    """Drop caught-up rows, and keep one in-progress season per show.

    Every season still flagged in progress was counted, so a show watched
    across several seasons inflated the header far past the cards on screen.
    """
    active = {}
    for media_type, media_list in media_types.items():
        items = [
            media for media in media_list["items"] if _has_released_backlog(media)
        ]
        if media_type == MediaTypes.SEASON.value:
            items = _one_season_per_show(items)
        if items:
            active[media_type] = {"items": items, "total": len(items)}
    return active


def _has_released_backlog(media):
    """True when released episodes/runtime remain, or the total is unknown."""
    max_progress = getattr(media, "max_progress", None)
    if not max_progress:
        return True
    return media.progress < max_progress


def _one_season_per_show(items):
    """Keep the first season of each show. The list is already home-sorted."""
    seen = set()
    chosen = []
    for media in items:
        key = (media.item.source, str(media.item.media_id))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(media)
    return chosen


def _paginate_home_media_types(media_types, page_size, page_start=0):
    """Paginate already-grouped home media entries."""
    paginated_media_types = {}
    for media_type, media_list in media_types.items():
        if page_size is None:
            items = media_list["items"][page_start:]
        else:
            items = media_list["items"][page_start : page_start + page_size]

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
