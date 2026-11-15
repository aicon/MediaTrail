import json
import logging
from enum import StrEnum

from app.models import MediaTypes

from .base import BaseWebhookProcessor

logger = logging.getLogger(__name__)


class EmbyEvent(StrEnum):
    """Emby webhook event names."""

    PLAYBACK_START = "playback.start"
    PLAYBACK_PAUSE = "playback.pause"
    PLAYBACK_UNPAUSE = "playback.unpause"
    PLAYBACK_STOP = "playback.stop"


class EmbyWebhookProcessor(BaseWebhookProcessor):
    """Processor for Emby webhook events."""

    def process_payload(self, payload, user):
        """Process the incoming Emby webhook payload."""
        logger.debug(
            "Processing Emby webhook payload: %s",
            json.dumps(payload, indent=2),
        )

        event_type = payload.get("Event")
        if event_type in {EmbyEvent.PLAYBACK_PAUSE, EmbyEvent.PLAYBACK_UNPAUSE}:
            self._handle_live(payload, user)
            return

        if not self._is_supported_event(event_type):
            logger.debug("Ignoring Emby webhook event type: %s", event_type)
            return

        if not payload.get("Item"):
            logger.warning("Ignoring Emby webhook call because no item was found.")
            self._handle_live(payload, user)
            return

        ids = self._extract_external_ids(payload)
        logger.info("Extracted IDs from payload: %s", ids)

        if not any(ids.values()):
            logger.warning("Ignoring Emby webhook call because no ID was found.")
            self._handle_live(payload, user)
            return

        self._process_media(payload, user, ids)
        self._handle_live(payload, user)

    def _handle_live(self, payload, user):
        from integrations.emby_live import handle_live_event

        handle_live_event(user, payload)

    def _is_supported_event(self, event_type):
        return event_type in {EmbyEvent.PLAYBACK_START, EmbyEvent.PLAYBACK_STOP}

    def _is_played(self, payload):
        return payload.get("PlaybackInfo", {}).get("PlayedToCompletion", False) is True

    def _get_media_type(self, payload):
        return self.MEDIA_TYPE_MAPPING.get(payload["Item"].get("Type"))

    def _get_media_title(self, payload):
        """Get media title from payload."""
        title = None

        if self._get_media_type(payload) == MediaTypes.TV.value:
            series_name = payload["Item"].get("SeriesName")
            season_number = payload["Item"].get("ParentIndexNumber")
            episode_number = payload["Item"].get("IndexNumber")
            title = f"{series_name} S{season_number:02d}E{episode_number:02d}"

        elif self._get_media_type(payload) == MediaTypes.MOVIE.value:
            movie_name = payload["Item"].get("Name")
            year = payload["Item"].get("ProductionYear")

            title = f"{movie_name} ({year})" if movie_name and year else movie_name

        return title

    def _get_episode_number(self, payload):
        return payload["Item"].get("IndexNumber")

    def _extract_external_ids(self, payload):
        provider_ids = payload["Item"].get("ProviderIds") or {}
        folded = {str(key).casefold(): value for key, value in provider_ids.items()}
        return {
            "tmdb_id": folded.get("tmdb"),
            "imdb_id": folded.get("imdb"),
            "tvdb_id": folded.get("tvdb"),
        }
