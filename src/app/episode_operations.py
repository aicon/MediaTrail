import logging

from django.conf import settings
from django.db import transaction

from app.models import Item, MediaTypes, Season, Status
from app.playback_operations import clear_live_playback_for_item
from app.providers import services

logger = logging.getLogger(__name__)


class EpisodeNotFoundError(ValueError):
    """Raised when provider metadata does not contain the requested episode."""


def get_or_create_season(
    *,
    user,
    media_id,
    source,
    season_number,
    tv_with_seasons_metadata=None,
):
    """Return the user's Season row, creating TV/Season parents when missing.

    Does not create Episode rows. Used by watch_episode and mid-watch resume.
    """
    season_number = int(season_number)
    related_season = Season.objects.filter(
        item__media_id=str(media_id),
        item__source=source,
        item__season_number=season_number,
        item__episode_number=None,
        user=user,
    ).first()
    if related_season is not None:
        return related_season

    if tv_with_seasons_metadata is None:
        tv_with_seasons_metadata = services.get_media_metadata(
            "tv_with_seasons",
            media_id,
            source,
            [season_number],
        )
    season_metadata = tv_with_seasons_metadata.get(f"season/{season_number}")
    if not season_metadata:
        raise EpisodeNotFoundError

    item, _ = Item.objects.get_or_create(
        media_id=str(media_id),
        source=source,
        media_type=MediaTypes.SEASON.value,
        season_number=season_number,
        defaults={
            "title": tv_with_seasons_metadata["title"],
            "image": season_metadata.get("image") or settings.IMG_NONE,
        },
    )
    related_season = Season.objects.create(
        item=item,
        user=user,
        score=None,
        status=Status.IN_PROGRESS.value,
        notes="",
    )
    logger.info("%s did not exist, it was created successfully.", related_season)
    return related_season


@transaction.atomic
def watch_episode(
    *,
    user,
    media_id,
    source,
    season_number,
    episode_number,
    end_date,
):
    """Create a watched episode and any missing user-owned parent records."""
    season_number = int(season_number)
    episode_number = int(episode_number)

    tv_with_seasons_metadata = services.get_media_metadata(
        "tv_with_seasons",
        media_id,
        source,
        [season_number],
    )
    season_metadata = tv_with_seasons_metadata.get(f"season/{season_number}")
    if not season_metadata:
        raise EpisodeNotFoundError

    episode_exists = any(
        episode.get("episode_number") == episode_number
        for episode in season_metadata.get("episodes", [])
    )
    if not episode_exists:
        raise EpisodeNotFoundError

    related_season = get_or_create_season(
        user=user,
        media_id=media_id,
        source=source,
        season_number=season_number,
        tv_with_seasons_metadata=tv_with_seasons_metadata,
    )

    episode = related_season.watch(
        episode_number,
        end_date,
        season_metadata=season_metadata,
    )
    related_season.clear_resume(persist=True)
    clear_live_playback_for_item(user=user, item=episode.item)
    from integrations.nuvio_outbound import enqueue_watched_upsert

    enqueue_watched_upsert(user, episode)
    return episode
