from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from app.models import Episode, Item, LivePlayback, LivePlaybackStatus, MediaTypes, Sources
from app.playback_operations import upsert_live_playback

from .base import YamtrackApiTestCase

_LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "playback-api-tests",
    },
}


@override_settings(CACHES=_LOCMEM_CACHE)
class PlaybackApiTests(YamtrackApiTestCase):
    """API tests for live playback endpoints."""

    def setUp(self):
        """Create movie and episode fixtures."""
        super().setUp()
        self.movie = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="https://example.com/movie.jpg",
        )
        self.episode = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Breaking Bad",
            image="https://example.com/ep.jpg",
            season_number=2,
            episode_number=21,
        )
        self.meta_patcher = patch(
            "app.playback_operations.services.get_media_metadata",
            return_value={},
        )
        self.meta_patcher.start()
        self.addCleanup(self.meta_patcher.stop)

    def test_put_movie_playback(self):
        """PUT creates a movie live session."""
        response = self.client.put(
            reverse("api_playback"),
            {
                "media_type": "movie",
                "source": "tmdb",
                "media_id": "550",
                "position_ms": 1_200_000,
                "duration_ms": 7_200_000,
                "status": "watching",
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["percent_watched"], 16)
        self.assertEqual(response.data["media_type"], "movie")
        self.assertIsNone(response.data["season_episode"])

    def test_put_episode_playback(self):
        """PUT creates an episode live session with SxxExx."""
        response = self.client.put(
            reverse("api_playback"),
            {
                "media_type": "tv",
                "source": "tmdb",
                "media_id": "1396",
                "season_number": 2,
                "episode_number": 21,
                "position_ms": 600_000,
                "duration_ms": 2_400_000,
                "status": "paused",
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["season_episode"], "S02E21")
        self.assertEqual(response.data["media_type"], "tv")
        self.assertEqual(response.data["status"], "paused")
        self.assertEqual(response.data["percent_watched"], 25)

    def test_get_now_watching(self):
        """GET /playback/now returns the latest session."""
        upsert_live_playback(
            user=self.user1,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.WATCHING,
        )
        response = self.client.get(
            reverse("api_playback_now"),
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["media_id"], "550")

    def test_delete_playback(self):
        """DELETE clears a session without creating history."""
        episode_count_before = Episode.objects.count()
        upsert_live_playback(
            user=self.user1,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=10_000,
            duration_ms=100_000,
        )
        response = self.client.delete(
            reverse("api_playback"),
            {
                "media_type": "tv",
                "source": "tmdb",
                "media_id": "1396",
                "season_number": 2,
                "episode_number": 21,
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 204)
        now_response = self.client.get(
            reverse("api_playback_now"),
            **self.auth_headers,
        )
        self.assertEqual(now_response.status_code, 204)
        self.assertEqual(Episode.objects.count(), episode_count_before)
        self.assertFalse(LivePlayback.objects.filter(user=self.user1).exists())

    def test_delete_movie_playback(self):
        """DELETE clears a movie session without creating history."""
        upsert_live_playback(
            user=self.user1,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=11_000,
            duration_ms=100_000,
        )
        response = self.client.delete(
            reverse("api_playback"),
            {
                "media_type": "movie",
                "source": "tmdb",
                "media_id": "550",
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(LivePlayback.objects.filter(user=self.user1).exists())

    def test_delete_playback_now_clears_all(self):
        """DELETE /playback/now/ drops every live row for the user."""
        upsert_live_playback(
            user=self.user1,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=11_000,
            duration_ms=100_000,
        )
        response = self.client.delete(
            reverse("api_playback_now"),
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(LivePlayback.objects.filter(user=self.user1).exists())

    def test_put_progress_then_pause(self):
        """Progress raises percent; pause keeps the row with paused status."""
        progress = self.client.put(
            reverse("api_playback"),
            {
                "media_type": "movie",
                "source": "tmdb",
                "media_id": "550",
                "position_ms": 25_000,
                "duration_ms": 100_000,
                "status": "watching",
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.data["percent_watched"], 25)

        paused = self.client.put(
            reverse("api_playback"),
            {
                "media_type": "movie",
                "source": "tmdb",
                "media_id": "550",
                "position_ms": 25_000,
                "duration_ms": 100_000,
                "status": "paused",
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.data["status"], "paused")
        self.assertEqual(paused.data["percent_watched"], 25)
